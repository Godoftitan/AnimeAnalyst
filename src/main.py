# main.py
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any, Dict, List
import requests  # fetch genres from Jikan

from jikan_analyze import (
    jikan_iterate, flatten_anime, save_csv, load_csv,
    filter_rows, compute_bayesian_scores, plot_hbar_top
)

# ---- Param spec (choices & help) ----
PARAM_SPEC: Dict[str, Dict[str, Any]] = {
    "q":               {"type": str,   "default": "",   "help": "keyword (title search)"},
    "type":            {"type": str,   "default": "",   "choices": ["tv","movie","ova","special","ona","music",""], "help": "type: tv, movie, ova, special, ona, music"},
    "status":          {"type": str,   "default": "",   "choices": ["airing","complete","upcoming",""], "help": "status: airing, complete, upcoming"},
    "year_from":       {"type": int,   "default": None, "help": "start year (inclusive)"},
    "year_to":         {"type": int,   "default": None, "help": "end year (inclusive)"},
    "min_score":       {"type": float, "default": None, "help": "minimum score (0–10)"},
    "min_scored_by":   {"type": int,   "default": None, "help": "minimum number of voters"},
    "any_genres":      {"type": "list","default": None, "help": "match any of these genres (names). IDs are mapped to names"},
    "all_genres":      {"type": "list","default": None, "help": "must include all of these genres (names)"},
    "limit_per_page":  {"type": int,   "default": 25,   "help": "items per page (1–25)"},
    "max_pages":       {"type": int,   "default": 5,    "help": "max pages to fetch"},
    "sfw":             {"type": bool,  "default": False,"help": "safe-for-work only (filters R+/Rx)"},
    "no_fetch":        {"type": bool,  "default": False,"help": "skip fetching; load local CSV"},
    "csv":             {"type": str,   "default": "data/anime_cache.csv", "help": "CSV path"},
    "prior_m":         {"type": float, "default": None, "help": "Bayesian prior weight m"},
    "topk":            {"type": int,   "default": 20,   "help": "plot top K"},
}

# ---- Genre resolver (cache anime genres) ----
class GenreResolver:
    API_URL = "https://api.jikan.moe/v4/genres/anime"

    def __init__(self) -> None:
        self._id_to_name: Dict[int, str] = {}
        self._name_to_id: Dict[str, int] = {}
        self._loaded = False

    def ensure_loaded(self) -> None:
        """Load once and cache."""
        if self._loaded:
            return
        r = requests.get(self.API_URL, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
        self._id_to_name = {int(g["mal_id"]): g["name"] for g in data}
        self._name_to_id = {g["name"].strip().lower(): int(g["mal_id"]) for g in data}
        self._loaded = True

    def list_all(self) -> List[tuple[int, str]]:
        """Return (id, name) sorted by id."""
        self.ensure_loaded()
        return sorted(self._id_to_name.items(), key=lambda x: x[0])

    def ids_from_tokens(self, tokens: List[str]) -> List[int]:
        """Accept tokens ('10' or 'Action'); return valid MAL IDs."""
        self.ensure_loaded()
        ids: List[int] = []
        for t in tokens:
            s = t.strip()
            if not s:
                continue
            if s.isdigit():
                i = int(s)
                if i in self._id_to_name:
                    ids.append(i)
            else:
                i = self._name_to_id.get(s.lower())
                if i is not None:
                    ids.append(i)
        return ids

    def names_from_tokens(self, tokens: List[str]) -> List[str]:
        """Convert tokens to genre names (for local filtering)."""
        ids = self.ids_from_tokens(tokens)
        return [self._id_to_name[i] for i in ids]

GENRES = GenreResolver()

# ---- Print interactive help ----
def _print_param_help() -> None:
    print("\nHow to use: type `key value` or `key=value` to set; repeat to overwrite; type `start` to run.")
    for k, spec in PARAM_SPEC.items():
        line = f"  {k}"
        if "choices" in spec and spec["choices"]:
            line += f" ∈ {spec['choices']}"
        if "help" in spec and spec["help"]:
            line += f" — {spec['help']}"
        line += f"  [default: {spec['default']}]"
        print(line)
    print(
        "\nCommands:\n"
        "  show               print current params\n"
        "  reset              reset to defaults\n"
        "  help               show this help\n"
        "  quit               exit\n"
        "  genre_all          list all anime genres (id : name)\n"
        "  genre_any <tokens> set ANY-match genres; tokens can be names or IDs, separated by commas/spaces\n"
        "                     e.g., `genre_any Action,Fantasy` or `genre_any 1 10`\n"
    )

# ---- Type coercion for interactive inputs ----
def _coerce_bool(val: str | None, cur: bool) -> bool:
    """Toggle if empty; parse common boolean literals."""
    if val is None or val == "":
        return not cur
    v = val.strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off"):
        return False
    raise ValueError("use: true/false/1/0/yes/no/on/off or empty to toggle")

def _coerce_value(key: str, val: str | None, state: Dict[str, Any]) -> Any:
    """Coerce a string to the declared type in PARAM_SPEC."""
    spec = PARAM_SPEC[key]
    typ = spec["type"]
    if "choices" in spec and spec["choices"] and val is not None:
        if val not in spec["choices"]:
            raise ValueError(f"{key} choices: {spec['choices']}")
    if typ is bool:
        return _coerce_bool(val, bool(state.get(key, spec["default"])))
    if typ is int:
        if val is None:
            raise ValueError("integer required")
        return int(val)
    if typ is float:
        if val is None:
            raise ValueError("float required")
        return float(val)
    if typ == "list":
        if not val:
            return None
        return [x.strip() for x in val.replace(",", " ").split() if x.strip()]
    if typ is str:
        return "" if val is None else val
    raise ValueError(f"unknown type: {typ}")

# ---- Interactive CLI ----
def interactive_collect() -> argparse.Namespace:
    """Collect params interactively; type `start` to run."""
    state: Dict[str, Any] = {k: spec["default"] for k, spec in PARAM_SPEC.items()}
    _print_param_help()
    while True:
        line = input(">>> ").strip()
        if not line:
            continue
        cmd = line.lower()

        # control commands
        if cmd == "start":
            break
        if cmd in ("quit", "exit"):
            raise SystemExit(0)
        if cmd == "help":
            _print_param_help()
            continue
        if cmd == "show":
            print("Current params:")
            for k in PARAM_SPEC.keys():
                print(f"  {k}: {state.get(k)}")
            continue
        if cmd == "reset":
            state = {k: spec["default"] for k, spec in PARAM_SPEC.items()}
            print("Reset to defaults.")
            continue

        # list all genres
        if cmd == "genre_all":
            try:
                pairs = GENRES.list_all()
                print("\nGenres (id : name):")
                for i, name in pairs:
                    print(f"  {i:>3} : {name}")
                print()
            except Exception as e:
                print(f"[!] Failed to fetch genres: {e}")
            continue

        # set any_genres from names/ids
        if cmd.startswith("genre_any"):
            tokens_str = line[len("genre_any"):].strip()
            if not tokens_str:
                print("[!] Usage: genre_any <name or ID, comma/space separated>")
                continue
            tokens = [t.strip() for t in tokens_str.replace(",", " ").split() if t.strip()]
            try:
                names = GENRES.names_from_tokens(tokens)
                if not names:
                    print("[!] No valid genres found. Try `genre_all` first.")
                    continue
                state["any_genres"] = names
                print(f"ok: any_genres = {names}")
            except Exception as e:
                print(f"[!] Parse failed: {e}")
            continue

        # regular key=value or key value
        if "=" in line:
            key, val = line.split("=", 1)
        else:
            parts = line.split(None, 1)
            key, val = parts[0], (parts[1] if len(parts) > 1 else None)

        key = key.strip()
        if key not in PARAM_SPEC:
            print(f"[!] Unknown param: {key}. Type `help` to list all params.")
            continue

        try:
            new_val = _coerce_value(key, val, state)
            state[key] = new_val
            print(f"ok: {key} = {new_val}")
        except Exception as e:
            print(f"[!] Set failed: {e}")

    return argparse.Namespace(**state)

# ---- Run pipeline ----
def run_pipeline(args: argparse.Namespace) -> None:
    """Fetch (optional), load, filter, score, and plot."""
    csv_path = Path(args.csv)

    if not args.no_fetch:
        print("Fetching from Jikan ...")
        raw = jikan_iterate(
            q=args.q,
            type_=args.type,
            status=args.status,
            start_year=args.year_from,
            end_year=args.year_to,
            min_score=args.min_score,
            limit_per_page=args.limit_per_page,
            max_pages=args.max_pages,
            sfw=args.sfw,
        )
        rows = [flatten_anime(a) for a in raw]
        save_csv(rows, csv_path)
    else:
        print("Skip fetching. Load CSV only.")

    rows = load_csv(csv_path)
    if not rows:
        print("No rows. Exit.")
        return

    rows_f = filter_rows(
        rows,
        type_=args.type or None,
        status=args.status or None,
        year_from=args.year_from,
        year_to=args.year_to,
        min_score=args.min_score,
        min_scored_by=args.min_scored_by,
        include_any_genres=args.any_genres,   # local name-based genre filter
        include_all_genres=args.all_genres,
    )
    print(f"Filtered: {len(rows_f)} rows")

    scored = compute_bayesian_scores(rows_f, prior_weight=args.prior_m)
    if not scored:
        print("No scored rows to plot.")
        return

    bits: List[str] = []
    if args.q: bits.append(f'q="{args.q}"')
    if args.type: bits.append(args.type.upper())
    if args.status: bits.append(args.status)
    if args.year_from or args.year_to: bits.append(f'{args.year_from or ""}-{args.year_to or ""}')
    if args.min_score is not None: bits.append(f"min_score>={args.min_score}")
    if args.min_scored_by is not None: bits.append(f"min_votes>={args.min_scored_by}")
    if args.any_genres: bits.append("genres_any=" + "|".join(args.any_genres))
    title = "Anime Bayesian Ranking" + (" - " + ", ".join(bits) if bits else "")

    plot_hbar_top(scored, topk=args.topk, title=title)

if __name__ == "__main__":
    args = interactive_collect()
    run_pipeline(args)
