from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
import requests

JIKAN_BASE = "https://api.jikan.moe/v4/anime"

def _fetch_page(params: Dict[str, Any], session: Optional[requests.Session] = None) -> Dict[str, Any]:
    sess = session or requests.Session()
    while True:
        resp = sess.get(JIKAN_BASE, params=params, timeout=20)
        if resp.status_code == 429:
            retry = int(resp.headers.get("Retry-After", "2"))
            time.sleep(max(1, retry)); continue
        resp.raise_for_status()
        return resp.json()

def iterate(q: str = "", type_: str = "", status: str = "", start_year: Optional[int] = None,
            end_year: Optional[int] = None, min_score: Optional[float] = None,
            limit_per_page: int = 25, max_pages: Optional[int] = None, sfw: bool = True
            ) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    page, sess = 1, requests.Session()
    while True:
        params: Dict[str, Any] = {
            "page": page, "limit": limit_per_page, "order_by": "score", "sort": "desc",
            "sfw": str(sfw).lower()
        }
        if q: params["q"] = q
        if type_: params["type"] = type_.lower()
        if status: params["status"] = status.lower()
        if start_year: params["start_date"] = f"{start_year}-01-01"
        if end_year: params["end_date"] = f"{end_year}-12-31"
        if min_score is not None: params["min_score"] = min_score

        data = _fetch_page(params, session=sess)
        results.extend(data.get("data", []) or [])
        pg = data.get("pagination", {}) or {}
        if (max_pages is not None and page >= max_pages) or not pg.get("has_next_page", False):
            break
        page = pg.get("current_page", page) + 1
        time.sleep(0.4)
    return results

def flatten(a: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # ... construct dict ...
        return row
    except Exception:
        return {}  # return empty dict
