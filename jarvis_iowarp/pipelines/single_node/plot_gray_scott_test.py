"""
Plot Gray Scott Exploration Results (from gray_scott_test.yaml)
================================================================
Reads the results.csv produced by:
  jarvis ppl run yaml gray_scott_test.yaml

and generates plots showing how L, steps, and plotgap affect
output size and runtime.

Usage:
  conda activate iowarp311
  # L sweep:
  python3 plot_gray_scott_test.py ~/gray_scott_explore_L/results.csv --dim L
  # steps sweep:
  python3 plot_gray_scott_test.py ~/gray_scott_explore_steps/results.csv --dim steps
  # plotgap sweep:
  python3 plot_gray_scott_test.py ~/gray_scott_explore_plotgap/results.csv --dim plotgap
"""

import argparse, csv, os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── theory ───────────────────────────────────────────────────────────────────
def theory_bytes(L, steps, plotgap):
    """L³ × 2 vars × 8 bytes (float64) × snapshots"""
    return int(L)**3 * 2 * 8 * (int(steps) // int(plotgap))


# ── load csv ──────────────────────────────────────────────────────────────────
def load_csv(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


# ── plot ──────────────────────────────────────────────────────────────────────
def plot(rows, dim, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Map dim → column name in CSV
    col = f"gsbench.{dim}"
    if col not in rows[0]:
        raise KeyError(f"Column '{col}' not in CSV. Available: {list(rows[0].keys())}")

    rows = sorted(rows, key=lambda r: float(r[col]))

    x       = [float(r[col])              for r in rows]
    obs_mb  = [float(r["gs_out_bytes"]) / 1024**2 for r in rows]
    rts     = [float(r["runtime"]) for r in rows]
    L_vals  = [float(r["gsbench.L"])     for r in rows]
    st_vals = [float(r.get("gsbench.steps", 100)) for r in rows]
    pg_vals = [float(r.get("gsbench.plotgap", 10)) for r in rows]
    th_mb   = [theory_bytes(L, s, pg) / 1024**2
               for L, s, pg in zip(L_vals, st_vals, pg_vals)]

    fixed_L     = rows[0]["gsbench.L"]
    fixed_steps = rows[0].get("gsbench.steps", "100")
    fixed_pg    = rows[0].get("gsbench.plotgap", "10")
    nprocs      = rows[0].get("gsbench.nprocs", "4")

    if dim == "L":
        title_fixed = f"steps={fixed_steps}, plotgap={fixed_pg}, nprocs={nprocs}"
        xlabel = "L  (grid dimension)"
        size_title  = "Output size  ∝  L³"
        rt_title    = "Runtime  ∝  L³"
    elif dim == "steps":
        title_fixed = f"L={fixed_L}, plotgap={fixed_pg}, nprocs={nprocs}"
        xlabel = "steps"
        size_title  = "Output size  ∝  steps  (linear)"
        rt_title    = "Runtime  ∝  steps"
    else:  # plotgap
        title_fixed = f"L={fixed_L}, steps={fixed_steps}, nprocs={nprocs}"
        xlabel = "plotgap  (steps between I/O)"
        size_title  = "Output size  ∝  1/plotgap"
        rt_title    = "Runtime (I/O overhead visible)"

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle(f"Gray Scott — vary {dim}  ({title_fixed})", fontsize=12)

    # ── left: output size ────────────────────────────────────────────────────
    ax = axes[0]
    ax.plot(x, obs_mb, "o-", color="steelblue", label="Measured (BP5)")
    ax.plot(x, th_mb,  "s--", color="orange",    label="Theory  L³×2×8B×snaps")
    if dim == "plotgap":
        # annotate snapshot count
        snaps = [int(s)//int(pg) for s,pg in zip(st_vals, pg_vals)]
        for xi, yi, s in zip(x, obs_mb, snaps):
            ax.annotate(f"{s}snaps", (xi, yi), textcoords="offset points",
                        xytext=(3, 4), fontsize=8, color="steelblue")
        ax.invert_xaxis()
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Output size (MB)")
    ax.set_title(size_title)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # ── right: runtime ────────────────────────────────────────────────────────
    ax = axes[1]
    ax.plot(x, rts, "o-", color="tomato")
    if dim == "plotgap":
        ax.invert_xaxis()
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Wall-clock time (s)")
    ax.set_title(rt_title)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path = out_dir / f"{dim}_sweep.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="Path to results.csv from jarvis ppl run")
    parser.add_argument("--dim", default="L", choices=["L", "steps", "plotgap"],
                        help="Which dimension was swept (default: L)")
    parser.add_argument("--out", default=None,
                        help="Output directory for plots (default: same dir as CSV)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.out) if args.out else csv_path.parent / "plots"

    rows = load_csv(csv_path)
    print(f"Loaded {len(rows)} rows from {csv_path}")
    plot(rows, args.dim, out_dir)


if __name__ == "__main__":
    main()
