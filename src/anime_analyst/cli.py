from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any, Dict, List
import requests

from anime_analyst.clients import jikan as jikan
from anime_analyst.clients import anilist as anilist
from anime_analyst.data.io import save_csv, load_csv
from anime_analyst.data.genres import GenreResolver
from anime_analyst.core.filter import filter_rows
from anime_analyst.core.merge import merge_mal_anilist
from anime_analyst.core.scoring import (
    compute_bayesian_scores,
    compute_consensus_bayesian,
    compute_recommendation_scores,
)
from anime_analyst.core.plotting import plot_hbar_top

PARAM_SPEC: Dict[str, Dict[str, Any]] = {
    "q": {"type": str, "default": "", "help": "title keyword"},
    "type": {"type": str, "default": "", "choices": ["tv","movie","ova","special","ona","music",""], "help": "tv/movie/ova/special/ona/music"},
    "status": {"type": str, "default": "", "choices": ["airing","complete","upcoming",""], "help": "airing/complete/upcoming"},
    "year_from": {"type": int, "default": None},
    "year_to": {"type": int, "default": None},
    "min_score": {"type": float, "default": None},
    "min_scored_by": {"type": int, "default": None},
    "any_genres": {"type": "list", "default": None},
    "all_genres": {"type": "list", "default": None},
    "limit_per_page": {"type": int, "default": 25},
    "max_pages": {"type": int, "default": 5},
    "sfw": {"type": bool, "default": False},
    "no_fetch": {"type": bool, "default": False},
    "csv": {"type": str, "default": "data/anime_cache.csv"},
    "prior_m": {"type": float, "default": None},
    "topk": {"type": int, "default": 20},
    "use_anilist": {"type": bool, "default": False},
    "al_pop_alpha": {"type": float, "default": 0.30},
    "recommend": {"type": bool, "default": True},
    "pop_weight": {"type": float, "default": 0.20},
    "recency_weight": {"type": float, "default": 0.10},
}

GENRES = GenreResolver()

def _print_param_help() -> None:
    print("\nType `key value` or `key=value`. Repeat to overwrite. Type `start` to run.")
    for k, spec in PARAM_SPEC.items():
        line = f"  {k}"
        if "choices" in spec and spec["choices"]: line += f" ∈ {spec['choices']}"
        if "help" in spec and spec["help"]: line += f" — {spec['help']}"
        line += f"  [default: {spec['default']}]"; print(line)
    print("\nCommands: show / reset / help / quit / genre_all / genre_any <names|IDs>\n")

def _coerce_bool(val: str | None, cur: bool) -> bool:
    if not val: return not cur
    v = val.strip().lower()
    if v in ("1","true","t","yes","y","on"): return True
    if v in ("0","false","f","no","n","off"): return False
    raise ValueError("true/false/1/0/yes/no/on/off or empty to toggle")

def _coerce_value(key: str, val: str | None, state: Dict[str, Any]) -> Any:
    spec = PARAM_SPEC[key]; typ = spec["type"]
    if "choices" in spec and spec["choices"] and val is not None and val not in spec["choices"]:
        raise ValueError(f"{key} choices: {spec['choices']}")
    if typ is bool: return _coerce_bool(val, bool(state.get(key, spec["default"])))
    if typ is int:
        if val is None: raise ValueError("integer required"); return int(val)
        return int(val)
    if typ is float:
        if val is None: raise ValueError("float required"); return float(val)
        return float(val)
    if typ == "list":
        if not val: return None
        return [x.strip() for x in val.replace(",", " ").split() if x.strip()]
    if typ is str:
        return "" if val is None else val
    raise ValueError(f"unknown type: {typ}")

def interactive_collect() -> argparse.Namespace:
    state: Dict[str, Any] = {k: spec["default"] for k, spec in PARAM_SPEC.items()}
    _print_param_help()
    while True:
        line = input(">>> ").strip()
        if not line: continue
        cmd = line.lower()
        if cmd == "start": break
        if cmd in ("quit","exit"): raise SystemExit(0)
        if cmd == "help": _print_param_help(); continue
        if cmd == "show":
            print("Current params:"); [print(f"  {k}: {state.get(k)}") for k in PARAM_SPEC.keys()]; continue
        if cmd == "reset": state = {k: spec["default"] for k, spec in PARAM_SPEC.items()}; print("Reset."); continue

        if cmd == "genre_all":
            try:
                for i, name in GENRES.list_all(): print(f"  {i:>3} : {name}")
            except Exception as e: print(f"[!] Failed: {e}")
            continue
        if cmd.startswith("genre_any"):
            tokens_str = line[len("genre_any"):].strip()
            if not tokens_str: print("[!] Usage: genre_any <name or ID>"); continue
            tokens = [t.strip() for t in tokens_str.replace(",", " ").split() if t.strip()]
            try:
                names = GENRES.names_from_tokens(tokens)
                if not names: print("[!] No valid genres. Use genre_all."); continue
                state["any_genres"] = names; print(f"ok: any_genres = {names}")
            except Exception as e: print(f"[!] Parse failed: {e}")
            continue

        if "=" in line: key, val = line.split("=", 1)
        else:
            parts = line.split(None, 1); key, val = parts[0], (parts[1] if len(parts) > 1 else None)
        if key not in PARAM_SPEC: print(f"[!] Unknown param: {key}"); continue
        try:
            state[key] = _coerce_value(key, val, state); print(f"ok: {key} = {state[key]}")
        except Exception as e:
            print(f"[!] Set failed: {e}")
    return argparse.Namespace(**state)

def run_pipeline(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv)
    rows_ani: List[Dict[str, Any]] = []
    rows_mal: List[Dict[str, Any]] = []

    if not args.no_fetch:
        print("Fetching from Jikan ...")
        mal_raw = jikan.iterate(q=args.q, type_=args.type, status=args.status,
                                start_year=args.year_from, end_year=args.year_to,
                                min_score=args.min_score, limit_per_page=args.limit_per_page,
                                max_pages=args.max_pages, sfw=args.sfw)
        rows_mal = [jikan.flatten(a) for a in mal_raw]
        save_csv(rows_mal, csv_path)

        if args.use_anilist:
            print("Fetching from AniList ...")
            ani_raw = anilist.iterate(q=args.q, type_=args.type, status=args.status,
                                      start_year=args.year_from, end_year=args.year_to,
                                      per_page=50, max_pages=args.max_pages)
            rows_ani = [anilist.flatten(a) for a in ani_raw]
    else:
        print("Skip fetching. Load CSV only.")
        rows_mal = load_csv(csv_path)
    if not rows_mal:
        print("No rows. Exit."); return

    rows_f = filter_rows(rows_mal, type_=args.type or None, status=args.status or None,
                         year_from=args.year_from, year_to=args.year_to,
                         min_score=args.min_score, min_scored_by=args.min_scored_by,
                         include_any_genres=args.any_genres, include_all_genres=args.all_genres)
    print(f"Filtered: {len(rows_f)} rows")

    if args.use_anilist:
        merged = merge_mal_anilist(rows_f, rows_ani if not args.no_fetch else [])
        scored = compute_consensus_bayesian(merged, prior_weight=args.prior_m, alpha_pop_to_votes=args.al_pop_alpha)
        title_prefix = "Anime Consensus Ranking (MAL+AniList)"
    else:
        if args.recommend:
            scored = compute_recommendation_scores(
                rows_f,
                prior_weight=args.prior_m,
                pop_weight=args.pop_weight,
                recency_weight=args.recency_weight,
            )
            title_prefix = "Anime Recommendation Ranking"
        else:
            scored = compute_bayesian_scores(rows_f, prior_weight=args.prior_m)
            title_prefix = "Anime Bayesian Ranking"

    if not scored:
        print("No scored rows to plot."); return

    bits: List[str] = []
    if args.q: bits.append(f'q="{args.q}"')
    if args.type: bits.append(args.type.upper())
    if args.status: bits.append(args.status)
    if args.year_from or args.year_to: bits.append(f'{args.year_from or ""}-{args.year_to or ""}')
    if args.min_score is not None: bits.append(f"min_score>={args.min_score}")
    if args.min_scored_by is not None: bits.append(f"min_votes>={args.min_scored_by}")
    if args.any_genres: bits.append("genres_any=" + "|".join(args.any_genres))
    title = title_prefix + (" - " + ", ".join(bits) if bits else "")

    plot_hbar_top(scored, topk=args.topk, title=title)

def main():
    args = interactive_collect()
    run_pipeline(args)

if __name__ == "__main__":
    main()
