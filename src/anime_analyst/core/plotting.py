from __future__ import annotations
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt

def plot_hbar_top(rows_with_scores: List[Tuple[Dict, float]], topk: int=20,
                  title: str="Top by Bayesian Score", xlabel: str="Bayesian Score (0–10)") -> None:
    rows_sorted = sorted(rows_with_scores, key=lambda x: x[1], reverse=True)[:topk]
    if not rows_sorted: print("Nothing to plot."); return
    names = [f"{r['title']} ({r.get('year') or '—'})" for r, _ in rows_sorted]
    scores = [round(s, 3) for _, s in rows_sorted]
    plt.figure(figsize=(12, max(6, 0.4*len(names))))
    plt.barh(names, scores); plt.gca().invert_yaxis()
    plt.title(title); plt.xlabel(xlabel); plt.tight_layout(); plt.show()
