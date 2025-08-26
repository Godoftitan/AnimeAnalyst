from __future__ import annotations
from typing import Dict, List, Optional

def filter_rows(rows: List[Dict],
                type_: Optional[str]=None, status: Optional[str]=None,
                year_from: Optional[int]=None, year_to: Optional[int]=None,
                min_score: Optional[float]=None, min_scored_by: Optional[int]=None,
                include_any_genres: Optional[List[str]]=None, include_all_genres: Optional[List[str]]=None
                ) -> List[Dict]:
    def toks(s: str) -> List[str]: return [t.strip().lower() for t in s.split(",")] if s else []
    out: List[Dict] = []
    for r in rows:
        if type_ and (r.get("type") or "").lower() != type_.lower(): continue
        if status and (r.get("status") or "").lower() != status.lower(): continue
        y = None
        if r.get("year") not in (None, ""):
            try: y = int(r["year"])
            except Exception: y = None
        if year_from and (y is None or y < year_from): continue
        if year_to and (y is None or y > year_to): continue
        if min_score is not None:
            try: sc = float(r["score"]) if r["score"] not in (None, "") else None
            except Exception: sc = None
            if sc is None or sc < min_score: continue
        if min_scored_by is not None:
            try: sb = int(r.get("scored_by") or 0)
            except Exception: sb = 0
            if sb < min_scored_by: continue
        gs = toks(r.get("genres",""))
        if include_any_genres and not any(g.lower() in gs for g in include_any_genres): continue
        if include_all_genres and not all(g.lower() in gs for g in include_all_genres): continue
        out.append(r)
    return out
