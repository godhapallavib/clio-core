"""
Plot Gray Scott: IOWarp vs Filesystem Comparison
=================================================
Reads results CSVs from:
  - gray_scott_test.yaml  (BP5 / filesystem baseline, varying nprocs)
  - gray_scott_iowarp.yaml (IOWarp engine, varying nprocs × worker threads)

and generates side-by-side comparison plots of runtime and throughput.

Usage:
  conda activate iowarp311

  # Generate comparison plot (IOWarp vs BP5):
  python3 plot_gray_scott_compare.py \\
      --fs   ~/gray_scott_explore_nprocs/results.csv \\
      --iow  ~/gray_scott_iowarp_results/results.csv \\
      --out  ~/gray_scott_compare_plots/

  # If you only have the IOWarp results (shows scaling by nprocs and workers):
  python3 plot_gray_scott_compare.py \\
      --iow  ~/gray_scott_iowarp_results/results.csv \\
      --out  ~/gray_scott_compare_plots/
"""

import argparse, csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# ── helpers ───────────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def fval(row, key, default=None):
    v = row.get(key, default)
    if v in (None, "", "None"):
        return default
    return float(v)


def theory_bytes(L, steps, plotgap):
    return int(L)**3 * 2 * 8 * (int(steps) // int(plotgap))


def throughput_gbs(row, fallback_bytes=None):
    """Compute I/O throughput in GB/s from runtime and output bytes.

    For IOWarp (DRAM engine), gs_out_bytes is 0 because data never hits disk.
    Pass fallback_bytes=theory_bytes(...) to compute theoretical throughput.
    """
    rt  = fval(row, "runtime", 0)
    obs = fval(row, "gs_out_bytes", 0)
    if rt <= 0:
        return 0.0
    if obs <= 0:
        obs = fallback_bytes or 0
    if obs <= 0:
        return 0.0
    return obs / 1024**3 / rt


# ── IOWarp-only plots ─────────────────────────────────────────────────────────

def plot_iowarp_scaling(rows, out_dir, fallback_bytes=None):
    """
    Heatmap and line plot of runtime/throughput as a function of
    (nprocs, runtime.num_threads) for gray_scott_iowarp.yaml results.

    fallback_bytes: theoretical I/O bytes per run (used when gs_out_bytes==0,
                    i.e. IOWarp DRAM engine).  Pass theory_bytes(L,steps,plotgap).
    """
    # Extract unique parameter values
    nprocs_col   = "gsbench.nprocs"
    workers_col  = "runtime.num_threads"

    if nprocs_col not in rows[0]:
        print(f"Warning: '{nprocs_col}' not in CSV columns: {list(rows[0].keys())}")
        # Fall back to whatever nprocs column is present
        nprocs_col = next((k for k in rows[0] if "nprocs" in k.lower()), None)
    if workers_col not in rows[0]:
        workers_col = next((k for k in rows[0] if "thread" in k.lower() or "worker" in k.lower()), None)

    nprocs_vals  = sorted(set(int(fval(r, nprocs_col, 1)) for r in rows))
    workers_vals = sorted(set(int(fval(r, workers_col, 4)) for r in rows)) if workers_col else [None]

    # ── Line plot: runtime vs nprocs, one line per worker count ──────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle("Gray Scott over IOWarp — Scaling Study\n"
                 "(L=128, steps=200, plotgap=10, engine=iowarp)", fontsize=11)

    colors = plt.cm.viridis(np.linspace(0.1, 0.9, max(len(workers_vals), 1)))

    for i, wt in enumerate(workers_vals):
        if wt is None:
            subset = rows
            label = "IOWarp"
        else:
            subset = [r for r in rows if int(fval(r, workers_col, 0)) == wt]
        subset = sorted(subset, key=lambda r: fval(r, nprocs_col, 1))

        xv  = [fval(r, nprocs_col, 1) for r in subset]
        rts = [fval(r, "runtime", 0) for r in subset]
        thr = [throughput_gbs(r, fallback_bytes) for r in subset]

        label = f"{wt} IOWarp workers" if wt else "IOWarp"
        axes[0].plot(xv, rts, "o-", color=colors[i], label=label)
        axes[1].plot(xv, thr, "o-", color=colors[i], label=label)

    axes[0].set_xlabel("Gray Scott nprocs"); axes[0].set_ylabel("Runtime (s)")
    axes[0].set_title("Runtime vs nprocs"); axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].set_xlabel("Gray Scott nprocs"); axes[1].set_ylabel("Throughput (GB/s)")
    axes[1].set_title("I/O Throughput vs nprocs"); axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    p = out_dir / "iowarp_scaling.png"
    fig.savefig(p, dpi=150); plt.close(fig)
    print(f"Saved: {p}")

    # ── Heatmap: runtime as function of (nprocs, workers) ────────────────────
    if workers_col and len(workers_vals) > 1:
        rt_matrix = np.zeros((len(workers_vals), len(nprocs_vals)))
        for r in rows:
            ni = nprocs_vals.index(int(fval(r, nprocs_col, 1)))
            wi = workers_vals.index(int(fval(r, workers_col, 1)))
            rt_matrix[wi, ni] = fval(r, "runtime", 0)

        fig, ax = plt.subplots(figsize=(7, 5))
        im = ax.imshow(rt_matrix, aspect="auto", cmap="RdYlGn_r",
                       origin="lower")
        ax.set_xticks(range(len(nprocs_vals)));  ax.set_xticklabels(nprocs_vals)
        ax.set_yticks(range(len(workers_vals))); ax.set_yticklabels(workers_vals)
        ax.set_xlabel("Gray Scott nprocs (simulation parallelism)")
        ax.set_ylabel("IOWarp worker threads")
        ax.set_title("Runtime (s) heatmap\n(green = faster)")
        plt.colorbar(im, ax=ax, label="Runtime (s)")
        for wi in range(len(workers_vals)):
            for ni in range(len(nprocs_vals)):
                v = rt_matrix[wi, ni]
                ax.text(ni, wi, f"{v:.1f}", ha="center", va="center",
                        fontsize=8, color="black")
        fig.tight_layout()
        p = out_dir / "iowarp_heatmap.png"
        fig.savefig(p, dpi=150); plt.close(fig)
        print(f"Saved: {p}")


# ── IOWarp vs filesystem comparison ───────────────────────────────────────────

def plot_comparison(fs_rows, iow_rows, out_dir, fallback_bytes=None):
    """
    Compare runtime and throughput between BP5 (filesystem) and IOWarp.
    Both datasets should have a 'gsbench.nprocs' dimension.

    fallback_bytes: theoretical I/O bytes for IOWarp throughput calculation
                    (needed when gs_out_bytes==0, i.e. DRAM engine).
    """
    nprocs_col = "gsbench.nprocs"

    # For IOWarp, use the best (fastest) worker-thread config per nprocs
    workers_col = "runtime.num_threads"
    iow_by_nprocs = {}
    for r in iow_rows:
        np_ = int(fval(r, nprocs_col, 1))
        if np_ not in iow_by_nprocs or fval(r, "runtime", 0) < fval(iow_by_nprocs[np_], "runtime", 0):
            iow_by_nprocs[np_] = r

    # Common nprocs values
    fs_nprocs  = sorted(set(int(fval(r, nprocs_col, 1)) for r in fs_rows))
    iow_nprocs = sorted(iow_by_nprocs.keys())

    fs_rt_map  = {int(fval(r, nprocs_col,1)): fval(r, "runtime", 0) for r in fs_rows}
    iow_rt_map = {n: fval(r, "runtime", 0) for n,r in iow_by_nprocs.items()}
    fs_thr = {int(fval(r, nprocs_col,1)): throughput_gbs(r) for r in fs_rows}
    iow_thr= {n: throughput_gbs(r, fallback_bytes) for n,r in iow_by_nprocs.items()}

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle("Gray Scott: IOWarp vs Filesystem (BP5)\n"
                 "(L=128, steps=200, plotgap=10)", fontsize=11)

    # Runtime comparison
    ax = axes[0]
    ax.plot(fs_nprocs,  [fs_rt_map.get(n,0)  for n in fs_nprocs],
            "o-", color="steelblue", label="BP5 (filesystem)")
    ax.plot(iow_nprocs, [iow_rt_map.get(n,0) for n in iow_nprocs],
            "s--", color="tomato",    label="IOWarp (best config)")
    ax.set_xlabel("nprocs"); ax.set_ylabel("Runtime (s)")
    ax.set_title("Runtime vs nprocs"); ax.legend(); ax.grid(True, alpha=0.3)

    # Throughput comparison
    ax = axes[1]
    ax.plot(fs_nprocs,  [fs_thr.get(n,0)  for n in fs_nprocs],
            "o-", color="steelblue", label="BP5 (filesystem)")
    ax.plot(iow_nprocs, [iow_thr.get(n,0) for n in iow_nprocs],
            "s--", color="tomato",    label="IOWarp (best config)")
    ax.set_xlabel("nprocs"); ax.set_ylabel("I/O Throughput (GB/s)")
    ax.set_title("Throughput vs nprocs"); ax.legend(); ax.grid(True, alpha=0.3)

    fig.tight_layout()
    p = out_dir / "iowarp_vs_fs_comparison.png"
    fig.savefig(p, dpi=150); plt.close(fig)
    print(f"Saved: {p}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fs",  default=None,
                        help="results.csv from gray_scott_test.yaml (nprocs sweep, BP5)")
    parser.add_argument("--iow", required=True,
                        help="results.csv from gray_scott_iowarp.yaml")
    parser.add_argument("--out", default=str(Path.home() / "gray_scott_compare_plots"),
                        help="Output directory for plots")
    parser.add_argument("--L",       type=int, default=128,
                        help="Grid dimension used in IOWarp runs (default: 128)")
    parser.add_argument("--steps",   type=int, default=200,
                        help="Simulation steps used in IOWarp runs (default: 200)")
    parser.add_argument("--plotgap", type=int, default=10,
                        help="Plot gap used in IOWarp runs (default: 10)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Theoretical bytes per IOWarp run (data goes to DRAM, not disk)
    fb = theory_bytes(args.L, args.steps, args.plotgap)
    print(f"IOWarp theoretical I/O per run: {fb/1024**2:.1f} MB  "
          f"(L={args.L}, steps={args.steps}, plotgap={args.plotgap})")

    iow_rows = load_csv(args.iow)
    print(f"IOWarp CSV: {len(iow_rows)} rows from {args.iow}")

    # Always produce IOWarp-only scaling plots
    plot_iowarp_scaling(iow_rows, out_dir, fallback_bytes=fb)

    # Produce comparison only if filesystem CSV is provided
    if args.fs:
        fs_rows = load_csv(args.fs)
        print(f"Filesystem CSV: {len(fs_rows)} rows from {args.fs}")
        plot_comparison(fs_rows, iow_rows, out_dir, fallback_bytes=fb)
    else:
        print("No --fs CSV provided; skipping IOWarp vs filesystem comparison plot.")
        print("To generate it, run gray_scott_test.yaml with a nprocs sweep first:")
        print("  (uncomment the nprocs sweep block in gray_scott_test.yaml)")
        print("  jarvis ppl run yaml gray_scott_test.yaml")
        print("  python3 plot_gray_scott_compare.py --fs ~/gray_scott_explore_nprocs/results.csv --iow <this_file>")


if __name__ == "__main__":
    main()
