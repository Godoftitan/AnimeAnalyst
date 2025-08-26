from __future__ import annotations
import re
from typing import Dict, List, Tuple

def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

def merge_mal_anilist(mal_rows: List[Dict], ani_rows: List[Dict]) -> List[Dict]:
    ani_by_mal: Dict[int, Dict] = {}
    for a in ani_rows:
        if a.get("mal_id"): ani_by_mal[int(a["mal_id"])] = a
    merged: List[Dict] = []
    used_ani = set()
    for m in mal_rows:
        mid = m.get("mal_id")
        row = dict(m)
        if mid and int(mid) in ani_by_mal:
            a = ani_by_mal[int(mid)]
            used_ani.add(a.get("anilist_id"))
            for k in ("anilist_id","title_romaji","score_anilist","popularity_anilist","favourites_anilist","url_anilist"):
                row[k] = a.get(k)
        merged.append(row)
    seen = {(_norm_title(r.get("title","")), r.get("year")) for r in merged}
    for a in ani_rows:
        if a.get("anilist_id") in used_ani: continue
        key = (_norm_title(a.get("title","")), a.get("year"))
        if key in seen: continue
        merged.append({
            "mal_id": a.get("mal_id"),
            "title": a.get("title"),
            "title_english": "",
            "type": a.get("type"),
            "status": a.get("status"),
            "year": a.get("year"),
            "episodes": a.get("episodes"),
            "duration": a.get("duration"),
            "score": None, "scored_by": 0, "rank": None, "popularity": None,
            "members": None, "favorites": None, "studios": "", "genres": "", "url": "",
            "anilist_id": a.get("anilist_id"),
            "title_romaji": a.get("title_romaji"),
            "score_anilist": a.get("score_anilist"),
            "popularity_anilist": a.get("popularity_anilist"),
            "favourites_anilist": a.get("favourites_anilist"),
            "url_anilist": a.get("url_anilist"),
        })
    return merged
