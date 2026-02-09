from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import matplotlib.pyplot as plt

def plot_hbar_top(rows_with_scores: List[Tuple[Dict, float]], topk: int=20,
                  title: str="Top by Bayesian Score", xlabel: str="Bayesian Score (0–10)",
                  show_values: bool=True, style: str="default",
                  output_path: Optional[str]=None) -> None:
    rows_sorted = sorted(rows_with_scores, key=lambda x: x[1], reverse=True)[:topk]
    if not rows_sorted: print("Nothing to plot."); return
    names = [f"{i+1:>2}. {r['title']} ({r.get('year') or '—'})" for i, (r, _) in enumerate(rows_sorted)]
    scores = [round(s, 3) for _, s in rows_sorted]
    plt.style.use(style)
    fig, ax = plt.subplots(figsize=(12, max(6, 0.45*len(names))))
    cmap = plt.cm.Blues
    if len(scores) > 1:
        colors = [cmap(0.35 + 0.6 * i / (len(scores) - 1)) for i in range(len(scores))]
    else:
        colors = [cmap(0.6)]
    bars = ax.barh(names, scores, color=colors)
    ax.invert_yaxis()
    ax.set_title(title, pad=12)
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    if show_values:
        for bar, score in zip(bars, scores):
            ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
                    f"{score:.3f}", va="center", ha="left", fontsize=9)
    fig.tight_layout()
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=200, bbox_inches="tight")
        print(f"Saved plot → {out}")
    plt.show()
