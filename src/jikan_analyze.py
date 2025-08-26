from __future__ import annotations
import time
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests
import matplotlib.pyplot as plt

JIKAN_BASE = "https://api.jikan.moe/v4/anime"

# ---------- Fetch ----------
def jikan_fetch_page(params: Dict[str, Any], session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Fetch a single page (retry on HTTP 429)."""
    sess = session or requests.Session()
    while True:
        resp = sess.get(JIKAN_BASE, params=params, timeout=20)
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "2"))
            time.sleep(max(1, retry))
            continue
        resp.raise_for_status()
        return resp.json()

def jikan_iterate(
    q: str = "",
    type_: str = "",
    status: str = "",                 # airing | complete | upcoming
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    min_score: Optional[float] = None,
    limit_per_page: int = 25,
    max_pages: Optional[int] = None,
    sfw: bool = True,
) -> List[Dict[str, Any]]:
    """Paginate until no next page or max_pages reached."""
    results: List[Dict[str, Any]] = []
    page = 1
    sess = requests.Session()
    while True:
        params: Dict[str, Any] = {
            "page": page,
            "limit": limit_per_page,
            "order_by": "score",
            "sort": "desc",
            "sfw": str(sfw).lower()
        }
        if q:
            params["q"] = q
        if type_:
            params["type"] = type_.lower()  # tv/movie/ova/ona/special/music
        if status:
            params["status"] = status.lower()  # airing/complete/upcoming
        if start_year:
            params["start_date"] = f"{start_year}-01-01"
        if end_year:
            params["end_date"] = f"{end_year}-12-31"
        if min_score is not None:
            params["min_score"] = min_score

        data = jikan_fetch_page(params, session=sess)
        items = data.get("data", []) or []
        results.extend(items)

        pagination = data.get("pagination", {}) or {}
        has_next = pagination.get("has_next_page", False)
        current = pagination.get("current_page", page)

        if max_pages is not None and page >= max_pages:
            break
        if not has_next:
            break
        page = current + 1
        time.sleep(0.4)  # basic rate limiting to avoid 429
    return results

# ---------- Flattening & cache ----------
def flatten_anime(a: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one anime item into CSV-friendly fields."""
    def year_from_aired(anime: Dict[str, Any]) -> Optional[int]:
        if anime.get("year"):
            return anime["year"]
        frm = anime.get("aired", {}).get("from")
        if frm:
            try:
                return int(frm[:4])
            except Exception:
                return None
        return None

    studios = ", ".join([s["name"] for s in (a.get("studios") or [])])
    genres  = ", ".join([g["name"] for g in (a.get("genres")  or [])])
    titles  = {t["type"]: t["title"] for t in (a.get("titles") or [])}

    return {
        "mal_id": a.get("mal_id"),
        "title": a.get("title") or titles.get("Default") or "",
        "title_english": a.get("title_english") or titles.get("English") or "",
        "type": a.get("type") or "",
        "status": (a.get("status") or "").lower(),   # store status for local filtering
        "year": year_from_aired(a),
        "episodes": a.get("episodes"),
        "duration": a.get("duration") or "",
        "score": a.get("score"),
        "scored_by": a.get("scored_by"),
        "rank": a.get("rank"),
        "popularity": a.get("popularity"),
        "members": a.get("members"),
        "favorites": a.get("favorites"),
        "studios": studios,
        "genres": genres,
        "url": a.get("url") or "",
    }

def save_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    """Save rows to CSV."""
    if not rows:
        print("No rows to save.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows → {path}")

def load_csv(path: Path) -> List[Dict[str, Any]]:
    """Load rows from CSV if exists."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ---------- Filtering & Bayesian ----------
def filter_rows(
    rows: List[Dict[str, Any]],
    type_: Optional[str] = None,
    status: Optional[str] = None,            # filter by airing/complete/upcoming
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    min_score: Optional[float] = None,
    min_scored_by: Optional[int] = None,
    include_any_genres: Optional[List[str]] = None,
    include_all_genres: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter by type, status, year, score, voters, and genres (name-based)."""
    def genre_tokens(s: str) -> List[str]:
        return [t.strip().lower() for t in s.split(",")] if s else []

    out: List[Dict[str, Any]] = []
    for r in rows:
        # type filter
        if type_ and (r.get("type") or "").lower() != type_.lower():
            continue
        # status filter
        if status and (r.get("status") or "").lower() != status.lower():
            continue

        # year filter
        y = None
        if r.get("year") not in (None, ""):
            try:
                y = int(r["year"])  # type: ignore[arg-type]
            except Exception:
                y = None
        if year_from and (y is None or y < year_from):
            continue
        if year_to and (y is None or y > year_to):
            continue

        # score filter
        if min_score is not None:
            try:
                sc = float(r["score"]) if r["score"] not in (None, "") else None
            except Exception:
                sc = None
            if sc is None or sc < min_score:
                continue

        # min voters filter
        if min_scored_by is not None:
            try:
                sb = int(r["scored_by"]) if r["scored_by"] not in (None, "") else 0
            except Exception:
                sb = 0
            if sb < min_scored_by:
                continue

        # genre filters (name-based, from flattened CSV)
        gs = genre_tokens(r.get("genres", ""))
        if include_any_genres and not any(g.lower() in gs for g in include_any_genres):
            continue
        if include_all_genres and not all(g.lower() in gs for g in include_all_genres):
            continue

        out.append(r)
    return out

def bayesian_score(avg: float, n: int, C: float, m: float) -> float:
    """Compute (n/(n+m))*avg + (m/(n+m))*C."""
    return (n / (n + m)) * avg + (m / (n + m)) * C

def compute_bayesian_scores(
    rows: List[Dict[str, Any]],
    prior_weight: Optional[float] = None
) -> List[Tuple[Dict[str, Any], float]]:
    """Compute Bayesian-weighted score using score and scored_by."""
    vals: List[Tuple[Dict[str, Any], float, int]] = []
    votes: List[int] = []
    for r in rows:
        try:
            s = float(r["score"]) if r["score"] not in (None, "") else None
            nb = int(r["scored_by"]) if r["scored_by"] not in (None, "") else 0
        except Exception:
            s, nb = None, 0
        if s is not None and nb > 0:
            vals.append((r, s, nb))
            votes.append(nb)
    if not vals:
        return []

    total_votes = sum(nb for _, _, nb in vals)
    C = sum(s * nb for _, s, nb in vals) / total_votes
    if prior_weight is None:
        votes_sorted = sorted(votes)
        mid = votes_sorted[len(votes_sorted)//2]
        m = max(1000, mid)
    else:
        m = float(prior_weight)

    out: List[Tuple[Dict[str, Any], float]] = []
    for r, s, nb in vals:
        out.append((r, bayesian_score(s, nb, C, m)))
    return out

# ---------- Plotting ----------
def plot_hbar_top(
    rows_with_scores: List[Tuple[Dict[str, Any], float]],
    topk: int = 20,
    title: str = "Top by Bayesian Score",
    xlabel: str = "Bayesian Score (0–10)"
) -> None:
    """Plot top-K items by Bayesian score."""
    rows_sorted = sorted(rows_with_scores, key=lambda x: x[1], reverse=True)[:topk]
    if not rows_sorted:
        print("Nothing to plot.")
        return

    names = [f"{r['title']} ({r.get('year') or '—'})" for r, _ in rows_sorted]
    scores = [round(s, 3) for _, s in rows_sorted]

    bar_height = 0.4
    height = max(6, bar_height * len(names))
    plt.figure(figsize=(12, height))
    plt.barh(names, scores)   # do not set explicit colors
    plt.gca().invert_yaxis()
    plt.title(title)
    plt.xlabel(xlabel)
    plt.tight_layout()
    plt.show()
