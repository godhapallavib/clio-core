"""
Plot Redis Micro-benchmark Results (from microbench_redis.yaml)
===============================================================
Reads the results.csv produced by:
  jarvis ppl run microbench_redis.yaml

and generates throughput plots across I/O sizes and client counts.

Throughput formula:
  MB/s = (count * req_size_bytes) / (runtime_s * 1024^2)

Usage:
  conda activate iowarp311
  python3 plot_microbench_redis.py ~/redis_microbench_results/results.csv
  python3 plot_microbench_redis.py ~/redis_microbench_results/results.csv \\
      --count 100000 --out ~/redis_plots/
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


def fval(row, key, default=0.0):
    v = row.get(key, default)
    if v in (None, "", "None"):
        return default
    return float(v)


def throughput_mbs(count, req_size_bytes, runtime_s):
    if runtime_s <= 0:
        return 0.0
    return (count * req_size_bytes) / (runtime_s * 1024 ** 2)


def fmt_size(b):
    """Format bytes as human-readable string for axis labels."""
    if b >= 1024 ** 2:
        return f"{int(b // 1024**2)}MB"
    if b >= 1024:
        return f"{int(b // 1024)}KB"
    return f"{int(b)}B"


# ── plot 1: throughput vs I/O size, one line per nthreads ─────────────────────

def plot_vs_iosize(rows, count, out_dir):
    req_sizes  = sorted(set(int(fval(r, "redis_bench.req_size")) for r in rows))
    nthreads_v = sorted(set(int(fval(r, "redis_bench.nthreads")) for r in rows))

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = plt.cm.viridis(np.linspace(0.1, 0.9, len(nthreads_v)))

    for i, nt in enumerate(nthreads_v):
        subset = [r for r in rows if int(fval(r, "redis_bench.nthreads")) == nt]
        subset = sorted(subset, key=lambda r: fval(r, "redis_bench.req_size"))
        xs  = [int(fval(r, "redis_bench.req_size")) for r in subset]
        yth = [throughput_mbs(count, x, fval(r, "runtime")) for r, x in zip(subset, xs)]
        ax.plot(xs, yth, "o-", color=colors[i], label=f"{nt} clients")

    ax.set_xscale("log", base=2)
    ax.set_xticks(req_sizes)
    ax.set_xticklabels([fmt_size(s) for s in req_sizes], rotation=30, ha="right")
    ax.set_xlabel("I/O size (req_size)")
    ax.set_ylabel("Throughput (MB/s)")
    ax.set_title(f"Redis Throughput vs I/O Size\n(count={count:,} requests per case)")
    ax.legend(title="Clients (nthreads)", fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    p = out_dir / "redis_throughput_vs_iosize.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── plot 2: throughput vs clients, one line per I/O size ──────────────────────

def plot_vs_clients(rows, count, out_dir):
    req_sizes  = sorted(set(int(fval(r, "redis_bench.req_size")) for r in rows))
    nthreads_v = sorted(set(int(fval(r, "redis_bench.nthreads")) for r in rows))

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = plt.cm.plasma(np.linspace(0.1, 0.9, len(req_sizes)))

    for i, rs in enumerate(req_sizes):
        subset = [r for r in rows if int(fval(r, "redis_bench.req_size")) == rs]
        subset = sorted(subset, key=lambda r: fval(r, "redis_bench.nthreads"))
        xs  = [int(fval(r, "redis_bench.nthreads")) for r in subset]
        yth = [throughput_mbs(count, rs, fval(r, "runtime")) for r in subset]
        ax.plot(xs, yth, "o-", color=colors[i], label=fmt_size(rs))

    ax.set_xticks(nthreads_v)
    ax.set_xlabel("Number of clients (nthreads)")
    ax.set_ylabel("Throughput (MB/s)")
    ax.set_title(f"Redis Throughput vs Client Count\n(count={count:,} requests per case)")
    ax.legend(title="I/O size", fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    p = out_dir / "redis_throughput_vs_clients.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── plot 3: heatmap — throughput(req_size × nthreads) ─────────────────────────

def plot_heatmap(rows, count, out_dir):
    req_sizes  = sorted(set(int(fval(r, "redis_bench.req_size")) for r in rows))
    nthreads_v = sorted(set(int(fval(r, "redis_bench.nthreads")) for r in rows))

    matrix = np.zeros((len(nthreads_v), len(req_sizes)))
    for r in rows:
        ri = req_sizes.index(int(fval(r, "redis_bench.req_size")))
        ni = nthreads_v.index(int(fval(r, "redis_bench.nthreads")))
        matrix[ni, ri] = throughput_mbs(count, req_sizes[ri], fval(r, "runtime"))

    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", origin="lower")
    ax.set_xticks(range(len(req_sizes)))
    ax.set_xticklabels([fmt_size(s) for s in req_sizes], rotation=30, ha="right")
    ax.set_yticks(range(len(nthreads_v)))
    ax.set_yticklabels(nthreads_v)
    ax.set_xlabel("I/O size (req_size)")
    ax.set_ylabel("Clients (nthreads)")
    ax.set_title(f"Redis Throughput Heatmap (MB/s)\n(count={count:,})")
    plt.colorbar(im, ax=ax, label="Throughput (MB/s)")
    for ni in range(len(nthreads_v)):
        for ri in range(len(req_sizes)):
            v = matrix[ni, ri]
            ax.text(ri, ni, f"{v:.0f}", ha="center", va="center",
                    fontsize=7, color="black")
    fig.tight_layout()
    p = out_dir / "redis_heatmap.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="Path to results.csv from jarvis ppl run microbench_redis.yaml")
    parser.add_argument("--count", type=int, default=100000,
                        help="Request count used in the benchmark (default: 100000)")
    parser.add_argument("--out", default=None,
                        help="Output directory for plots (default: <csv_dir>/plots/)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    out_dir  = Path(args.out) if args.out else csv_path.parent / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_csv(csv_path)
    rows = [r for r in rows if r.get("status") == "success"]
    print(f"Loaded {len(rows)} successful rows from {csv_path}")

    plot_vs_iosize(rows, args.count, out_dir)
    plot_vs_clients(rows, args.count, out_dir)
    plot_heatmap(rows, args.count, out_dir)


if __name__ == "__main__":
    main()
