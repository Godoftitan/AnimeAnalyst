from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import requests

ANILIST_GQL = "https://graphql.anilist.co"
FORMAT = {"tv":"TV","movie":"MOVIE","ova":"OVA","ona":"ONA","special":"SPECIAL","music":"MUSIC"}
STATUS = {"airing":"RELEASING","complete":"FINISHED","upcoming":"NOT_YET_RELEASED"}
STATUS_BACK = {"RELEASING":"airing","FINISHED":"complete","NOT_YET_RELEASED":"upcoming"}

def _to_yyyymmdd(y: int, end: bool = False) -> int: return int(f"{y}{'1231' if end else '0101'}")

_QUERY = """
query ($page:Int,$perPage:Int,$search:String,$format:MediaFormat,$status:MediaStatus,$start:Int,$end:Int){
  Page(page:$page, perPage:$perPage){
    pageInfo{currentPage hasNextPage}
    media(type:ANIME, search:$search, format:$format, status:$status, startDate_greater:$start, startDate_lesser:$end){
      id idMal title{romaji english native} format status episodes duration
      averageScore popularity favourites seasonYear startDate{year} siteUrl
    }
  }
}
"""

def iterate(q: str="", type_: str="", status: str="", start_year: Optional[int]=None,
            end_year: Optional[int]=None, per_page: int=50, max_pages: Optional[int]=None
            ) -> List[Dict[str, Any]]:
    page, out, sess = 1, [], requests.Session()
    vars: Dict[str, Any] = {
        "page": page, "perPage": per_page,
        "search": q or None,
        "format": FORMAT.get(type_.lower()) if type_ else None,
        "status": STATUS.get(status.lower()) if status else None,
        "start": _to_yyyymmdd(start_year, False) if start_year else None,
        "end": _to_yyyymmdd(end_year, True) if end_year else None,
    }
    while True:
        vars["page"] = page
        resp = sess.post(ANILIST_GQL, json={"query": _QUERY, "variables": vars}, timeout=20)
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "2")); time.sleep(max(1, retry)); continue
        resp.raise_for_status()
        data = resp.json()["data"]["Page"]
        out.extend(data.get("media") or [])
        info = data["pageInfo"]
        if (max_pages is not None and page >= max_pages) or not info.get("hasNextPage"):
            break
        page = info.get("currentPage", page) + 1
        time.sleep(0.25)
    return out

def flatten(a: Dict[str, Any]) -> Dict[str, Any]:
    t = a.get("title") or {}
    title = t.get("english") or t.get("romaji") or t.get("native") or ""
    y = a.get("seasonYear") or (a.get("startDate", {}) or {}).get("year")
    return {
        "anilist_id": a.get("id"),
        "mal_id": a.get("idMal"),
        "title": title,
        "title_romaji": t.get("romaji") or "",
        "type": a.get("format") or "",
        "status": (STATUS_BACK.get(a.get("status") or "", "")).lower(),
        "year": y,
        "episodes": a.get("episodes"),
        "duration": a.get("duration"),
        "score_anilist": (a.get("averageScore") / 10.0) if a.get("averageScore") not in (None, "") else None,
        "popularity_anilist": a.get("popularity"),
        "favourites_anilist": a.get("favourites"),
        "url_anilist": a.get("siteUrl") or "",
    }
