from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, List

def save_csv(rows: List[Dict], path: Path) -> None:
    if not rows: print("No rows to save."); return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"Saved {len(rows)} rows → {path}")

def load_csv(path: Path) -> List[Dict]:
    if not path.exists(): return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
