"""
Plot IOWarp CTE Micro-benchmark Results (from microbench_cte.yaml)
==================================================================
Reads the results.csv produced by:
  jarvis ppl run microbench_cte.yaml

and generates throughput plots across I/O sizes, client counts,
transport modes (ipc_mode), and runtime thread counts.

Throughput formula:
  MB/s = (nprocs * io_count * io_size_bytes) / (runtime_s * 1024^2)

Usage:
  conda activate iowarp311
  python3 plot_microbench_cte.py ~/cte_microbench_results/results.csv
  python3 plot_microbench_cte.py ~/cte_microbench_results/results.csv \\
      --io-count 1000 --out ~/cte_plots/
"""

import argparse, csv, re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# ── helpers ───────────────────────────────────────────────────────────────────

def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def fval(row, key, default=0.0):
    v = row.get(key, default)
    if v in (None, "", "None"):
        return default
    return float(v)


def parse_io_size(s):
    """Convert size string like '4k', '1m', '16m' to bytes."""
    s = str(s).strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmg]?)$", s)
    if not m:
        return int(s)
    val, suffix = float(m.group(1)), m.group(2)
    return int(val * {"k": 1024, "m": 1024**2, "g": 1024**3}.get(suffix, 1))


def throughput_mbs(nprocs, io_count, io_size_bytes, runtime_s):
    if runtime_s <= 0:
        return 0.0
    return (nprocs * io_count * io_size_bytes) / (runtime_s * 1024 ** 2)


def fmt_size(b):
    if b >= 1024 ** 2:
        return f"{int(b // 1024**2)}MB"
    if b >= 1024:
        return f"{int(b // 1024)}KB"
    return f"{int(b)}B"


# ── plot 1: throughput vs I/O size per ipc_mode (subplots per num_threads) ───

def plot_vs_iosize(rows, io_count, out_dir):
    ipc_modes   = sorted(set(r.get("runtime.ipc_mode", "shm") for r in rows))
    num_threads = sorted(set(int(fval(r, "runtime.num_threads")) for r in rows))
    nprocs_vals = sorted(set(int(fval(r, "cte_bench.nprocs")) for r in rows))
    io_sizes    = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in rows))

    for nt in num_threads:
        fig, axes = plt.subplots(1, len(ipc_modes), figsize=(6 * len(ipc_modes), 5),
                                 sharey=True)
        if len(ipc_modes) == 1:
            axes = [axes]
        fig.suptitle(f"IOWarp CTE Throughput vs I/O Size  (runtime.num_threads={nt})",
                     fontsize=11)
        colors = plt.cm.viridis(np.linspace(0.1, 0.9, len(nprocs_vals)))

        for ax, mode in zip(axes, ipc_modes):
            for i, np_ in enumerate(nprocs_vals):
                subset = [r for r in rows
                          if r.get("runtime.ipc_mode") == mode
                          and int(fval(r, "runtime.num_threads")) == nt
                          and int(fval(r, "cte_bench.nprocs")) == np_]
                subset = sorted(subset, key=lambda r: parse_io_size(r.get("cte_bench.io_size", "4k")))
                xs  = [parse_io_size(r.get("cte_bench.io_size", "4k")) for r in subset]
                yth = [throughput_mbs(np_, io_count, x, fval(r, "runtime"))
                       for r, x in zip(subset, xs)]
                if xs:
                    ax.plot(xs, yth, "o-", color=colors[i], label=f"{np_} clients")

            ax.set_xscale("log", base=2)
            ax.set_xticks(io_sizes)
            ax.set_xticklabels([fmt_size(s) for s in io_sizes], rotation=30, ha="right")
            ax.set_xlabel("I/O size")
            ax.set_title(f"ipc_mode={mode}")
            ax.grid(True, alpha=0.3)
            ax.legend(title="Clients (nprocs)", fontsize=7)

        axes[0].set_ylabel("Throughput (MB/s)")
        fig.tight_layout()
        p = out_dir / f"cte_throughput_vs_iosize_nt{nt}.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        print(f"Saved: {p}")


# ── plot 2: throughput vs clients per ipc_mode (subplots per num_threads) ─────

def plot_vs_clients(rows, io_count, out_dir):
    ipc_modes   = sorted(set(r.get("runtime.ipc_mode", "shm") for r in rows))
    num_threads = sorted(set(int(fval(r, "runtime.num_threads")) for r in rows))
    nprocs_vals = sorted(set(int(fval(r, "cte_bench.nprocs")) for r in rows))
    io_sizes    = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in rows))

    for nt in num_threads:
        fig, axes = plt.subplots(1, len(ipc_modes), figsize=(6 * len(ipc_modes), 5),
                                 sharey=True)
        if len(ipc_modes) == 1:
            axes = [axes]
        fig.suptitle(f"IOWarp CTE Throughput vs Client Count  (runtime.num_threads={nt})",
                     fontsize=11)
        colors = plt.cm.plasma(np.linspace(0.1, 0.9, len(io_sizes)))

        for ax, mode in zip(axes, ipc_modes):
            for i, ios in enumerate(io_sizes):
                subset = [r for r in rows
                          if r.get("runtime.ipc_mode") == mode
                          and int(fval(r, "runtime.num_threads")) == nt
                          and parse_io_size(r.get("cte_bench.io_size", "4k")) == ios]
                subset = sorted(subset, key=lambda r: fval(r, "cte_bench.nprocs"))
                xs  = [int(fval(r, "cte_bench.nprocs")) for r in subset]
                yth = [throughput_mbs(x, io_count, ios, fval(r, "runtime"))
                       for r, x in zip(subset, xs)]
                if xs:
                    ax.plot(xs, yth, "o-", color=colors[i], label=fmt_size(ios))

            ax.set_xticks(nprocs_vals)
            ax.set_xlabel("Clients (nprocs)")
            ax.set_title(f"ipc_mode={mode}")
            ax.grid(True, alpha=0.3)
            ax.legend(title="I/O size", fontsize=7)

        axes[0].set_ylabel("Throughput (MB/s)")
        fig.tight_layout()
        p = out_dir / f"cte_throughput_vs_clients_nt{nt}.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
        print(f"Saved: {p}")


# ── plot 3: effect of runtime.num_threads per ipc_mode ────────────────────────

def plot_vs_num_threads(rows, io_count, out_dir):
    ipc_modes   = sorted(set(r.get("runtime.ipc_mode", "shm") for r in rows))
    num_threads = sorted(set(int(fval(r, "runtime.num_threads")) for r in rows))
    io_sizes    = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in rows))
    nprocs_vals = sorted(set(int(fval(r, "cte_bench.nprocs")) for r in rows))

    # Pick the median nprocs value for this plot
    mid_nprocs = nprocs_vals[len(nprocs_vals) // 2]

    fig, axes = plt.subplots(1, len(ipc_modes), figsize=(6 * len(ipc_modes), 5),
                             sharey=True)
    if len(ipc_modes) == 1:
        axes = [axes]
    fig.suptitle(f"IOWarp CTE Throughput vs Runtime Threads  (nprocs={mid_nprocs})",
                 fontsize=11)
    colors = plt.cm.plasma(np.linspace(0.1, 0.9, len(io_sizes)))

    for ax, mode in zip(axes, ipc_modes):
        for i, ios in enumerate(io_sizes):
            subset = [r for r in rows
                      if r.get("runtime.ipc_mode") == mode
                      and parse_io_size(r.get("cte_bench.io_size", "4k")) == ios
                      and int(fval(r, "cte_bench.nprocs")) == mid_nprocs]
            subset = sorted(subset, key=lambda r: fval(r, "runtime.num_threads"))
            xs  = [int(fval(r, "runtime.num_threads")) for r in subset]
            yth = [throughput_mbs(mid_nprocs, io_count, ios, fval(r, "runtime"))
                   for r in subset]
            if xs:
                ax.plot(xs, yth, "o-", color=colors[i], label=fmt_size(ios))

        ax.set_xticks(num_threads)
        ax.set_xlabel("IOWarp runtime threads (num_threads)")
        ax.set_title(f"ipc_mode={mode}")
        ax.grid(True, alpha=0.3)
        ax.legend(title="I/O size", fontsize=7)

    axes[0].set_ylabel("Throughput (MB/s)")
    fig.tight_layout()
    p = out_dir / "cte_throughput_vs_num_threads.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── plot 4: heatmap — throughput(io_size × nprocs) for each ipc_mode × num_threads

def plot_heatmap(rows, io_count, out_dir):
    ipc_modes   = sorted(set(r.get("runtime.ipc_mode", "shm") for r in rows))
    num_threads = sorted(set(int(fval(r, "runtime.num_threads")) for r in rows))
    io_sizes    = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in rows))
    nprocs_vals = sorted(set(int(fval(r, "cte_bench.nprocs")) for r in rows))

    for nt in num_threads:
        for mode in ipc_modes:
            matrix = np.zeros((len(nprocs_vals), len(io_sizes)))
            for r in rows:
                if r.get("runtime.ipc_mode") != mode:
                    continue
                if int(fval(r, "runtime.num_threads")) != nt:
                    continue
                ios = parse_io_size(r.get("cte_bench.io_size", "4k"))
                np_ = int(fval(r, "cte_bench.nprocs"))
                if ios not in io_sizes or np_ not in nprocs_vals:
                    continue
                ri = io_sizes.index(ios)
                ni = nprocs_vals.index(np_)
                matrix[ni, ri] = throughput_mbs(np_, io_count, ios, fval(r, "runtime"))

            fig, ax = plt.subplots(figsize=(10, 5))
            im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", origin="lower")
            ax.set_xticks(range(len(io_sizes)))
            ax.set_xticklabels([fmt_size(s) for s in io_sizes], rotation=30, ha="right")
            ax.set_yticks(range(len(nprocs_vals)))
            ax.set_yticklabels(nprocs_vals)
            ax.set_xlabel("I/O size")
            ax.set_ylabel("Clients (nprocs)")
            ax.set_title(f"IOWarp CTE Throughput Heatmap (MB/s)\n"
                         f"ipc_mode={mode}, runtime.num_threads={nt}")
            plt.colorbar(im, ax=ax, label="Throughput (MB/s)")
            for ni in range(len(nprocs_vals)):
                for ri in range(len(io_sizes)):
                    v = matrix[ni, ri]
                    ax.text(ri, ni, f"{v:.0f}", ha="center", va="center",
                            fontsize=7, color="black")
            fig.tight_layout()
            p = out_dir / f"cte_heatmap_{mode}_nt{nt}.png"
            fig.savefig(p, dpi=150)
            plt.close(fig)
            print(f"Saved: {p}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="Path to results.csv from jarvis ppl run microbench_cte.yaml")
    parser.add_argument("--io-count", type=int, default=1000,
                        help="io_count used in the benchmark (default: 1000)")
    parser.add_argument("--out", default=None,
                        help="Output directory for plots (default: <csv_dir>/plots/)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.out) if args.out else csv_path.parent / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_csv(csv_path)
    rows = [r for r in rows if r.get("status") == "success"]
    print(f"Loaded {len(rows)} successful rows from {csv_path}")

    plot_vs_iosize(rows, args.io_count, out_dir)
    plot_vs_clients(rows, args.io_count, out_dir)
    plot_vs_num_threads(rows, args.io_count, out_dir)
    plot_heatmap(rows, args.io_count, out_dir)


if __name__ == "__main__":
    main()
