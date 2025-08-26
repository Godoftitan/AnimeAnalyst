from __future__ import annotations
from typing import Dict, List, Tuple
import requests

class GenreResolver:
    API_URL = "https://api.jikan.moe/v4/genres/anime"
    def __init__(self) -> None:
        self._id_to_name: Dict[int, str] = {}
        self._name_to_id: Dict[str, int] = {}
        self._loaded = False

    def ensure_loaded(self) -> None:
        if self._loaded: return
        r = requests.get(self.API_URL, timeout=15); r.raise_for_status()
        data = r.json().get("data", []) or []
        self._id_to_name = {int(g["mal_id"]): g["name"] for g in data}
        self._name_to_id = {g["name"].strip().lower(): int(g["mal_id"]) for g in data}
        self._loaded = True

    def list_all(self) -> List[Tuple[int, str]]:
        self.ensure_loaded()
        return sorted(self._id_to_name.items())

    def ids_from_tokens(self, tokens: List[str]) -> List[int]:
        self.ensure_loaded()
        out: List[int] = []
        for t in tokens:
            s = t.strip()
            if not s: continue
            if s.isdigit():
                i = int(s)
                if i in self._id_to_name: out.append(i)
            else:
                i = self._name_to_id.get(s.lower())
                if i is not None: out.append(i)
        return out

    def names_from_tokens(self, tokens: List[str]) -> List[str]:
        return [self._id_to_name[i] for i in self.ids_from_tokens(tokens)]
