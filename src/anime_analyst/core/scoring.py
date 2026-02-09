from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple

def bayesian_score(avg: float, n: float, C: float, m: float) -> float:
    return (n / (n + m)) * avg + (m / (n + m)) * C

def compute_bayesian_scores(rows: List[Dict], prior_weight: Optional[float]=None) -> List[Tuple[Dict, float]]:
    vals: List[Tuple[Dict, float, int]] = []; votes: List[int] = []
    for r in rows:
        try:
            s = float(r["score"]) if r["score"] not in (None, "") else None
            nb = int(r.get("scored_by") or 0)
        except Exception:
            s, nb = None, 0
        if s is not None and nb > 0:
            vals.append((r, s, nb)); votes.append(nb)
    if not vals: return []
    tot = sum(nb for *_, nb in vals)
    C = sum(s*nb for _, s, nb in vals)/tot
    m = float(prior_weight) if prior_weight is not None else max(1000, sorted(votes)[len(votes)//2])
    return [(r, bayesian_score(s, nb, C, m)) for r, s, nb in vals]

def _norm_range(vals: List[float]) -> List[float]:
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if math.isclose(lo, hi):
        return [0.0 for _ in vals]
    span = hi - lo
    return [(v - lo) / span for v in vals]

def _extract_year(row: Dict) -> Optional[int]:
    raw = row.get("year")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except Exception:
        return None

def _extract_popularity(row: Dict) -> float:
    for key in ("members", "popularity", "scored_by"):
        val = row.get(key)
        if val in (None, ""):
            continue
        try:
            return float(val)
        except Exception:
            continue
    return 0.0

def compute_recommendation_scores(
    rows: List[Dict],
    prior_weight: Optional[float]=None,
    pop_weight: float=0.20,
    recency_weight: float=0.10,
) -> List[Tuple[Dict, float]]:
    vals: List[Tuple[Dict, float, int]] = []
    votes: List[int] = []
    for r in rows:
        try:
            s = float(r["score"]) if r["score"] not in (None, "") else None
            nb = int(r.get("scored_by") or 0)
        except Exception:
            s, nb = None, 0
        if s is not None and nb > 0:
            vals.append((r, s, nb))
            votes.append(nb)
    if not vals:
        return []
    tot = sum(nb for *_, nb in vals)
    C = sum(s * nb for _, s, nb in vals) / tot
    m = float(prior_weight) if prior_weight is not None else max(1000, sorted(votes)[len(votes) // 2])
    base_scores = [bayesian_score(s, nb, C, m) for _, s, nb in vals]
    pop_values = [math.log10(1.0 + _extract_popularity(r)) for r, _, _ in vals]
    pop_norm = _norm_range(pop_values)

    years = [_extract_year(r) for r, _, _ in vals]
    year_vals = [float(y) for y in years if y is not None]
    year_min = min(year_vals) if year_vals else None
    year_max = max(year_vals) if year_vals else None
    recency_norm: List[float] = []
    for y in years:
        if y is None or year_min is None or year_max is None or math.isclose(year_min, year_max):
            recency_norm.append(0.0)
        else:
            recency_norm.append((y - year_min) / (year_max - year_min))

    scored: List[Tuple[Dict, float]] = []
    for (r, _, _), base, pop_boost, rec_boost in zip(vals, base_scores, pop_norm, recency_norm):
        boost = (pop_weight * pop_boost) + (recency_weight * rec_boost)
        scored.append((r, base + boost))
    return scored

def compute_consensus_bayesian(merged_rows: List[Dict], prior_weight: Optional[float]=None,
                               alpha_pop_to_votes: float=0.30) -> List[Tuple[Dict, float]]:
    recs: List[Tuple[Dict, float, float]] = []
    w = lambda n: math.log10(1.0 + max(0.0, n))
    for r in merged_rows:
        s_mal = float(r["score"]) if r.get("score") not in (None, "") else None
        try: n_mal = int(r.get("scored_by") or 0)
        except Exception: n_mal = 0
        s_ani = r.get("score_anilist")
        n_ani = alpha_pop_to_votes * float(r.get("popularity_anilist") or 0)
        parts, weights = [], []
        if s_mal is not None and n_mal > 0: parts.append(s_mal); weights.append(w(n_mal))
        if s_ani is not None and n_ani > 0: parts.append(float(s_ani)); weights.append(w(n_ani))
        if parts and sum(weights) > 0:
            s = sum(p*wt for p, wt in zip(parts, weights))/sum(weights); n = n_mal + n_ani
            r["consensus_score"] = s; r["consensus_votes"] = int(round(n))
            recs.append((r, s, n))
        else:
            if s_mal is not None: recs.append((r, s_mal, max(1.0, n_mal)))
            elif s_ani is not None: recs.append((r, float(s_ani), max(1.0, n_ani)))
    if not recs: return []
    tot = sum(n for *_, n in recs)
    C = sum(s*n for _, s, n in recs)/tot
    ns = sorted(int(n) for *_, n in recs)
    m = float(prior_weight) if prior_weight is not None else max(1000.0, float(ns[len(ns)//2]))
    return [(r, bayesian_score(s, n, C, m)) for r, s, n in recs]
