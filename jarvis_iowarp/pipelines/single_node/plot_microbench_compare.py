"""
Plot Redis vs IOWarp CTE Micro-benchmark Comparison
====================================================
Reads results CSVs from:
  - microbench_redis.yaml  → Redis (DRAM-backed in-memory store)
  - microbench_cte.yaml    → IOWarp CTE (ram::cache, DRAM-only)

and generates side-by-side comparison plots of throughput.

For the IOWarp side the "best" config per (io_size, nprocs) is selected:
  best = highest throughput across (ipc_mode × runtime.num_threads).

Throughput formulas:
  Redis  MB/s = (count * req_size_bytes) / (runtime_s * 1024^2)
  IOWarp MB/s = (nprocs * io_count * io_size_bytes) / (runtime_s * 1024^2)

Usage:
  conda activate iowarp311
  python3 plot_microbench_compare.py \\
      --redis ~/redis_microbench_results/results.csv \\
      --cte   ~/cte_microbench_results/results.csv \\
      --out   ~/microbench_compare_plots/
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
    s = str(s).strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmg]?)$", s)
    if not m:
        return int(s)
    val, suffix = float(m.group(1)), m.group(2)
    return int(val * {"k": 1024, "m": 1024**2, "g": 1024**3}.get(suffix, 1))


def fmt_size(b):
    if b >= 1024 ** 2:
        return f"{int(b // 1024**2)}MB"
    if b >= 1024:
        return f"{int(b // 1024)}KB"
    return f"{int(b)}B"


def redis_thr(count, req_size_bytes, runtime_s):
    if runtime_s <= 0:
        return 0.0
    return (count * req_size_bytes) / (runtime_s * 1024 ** 2)


def cte_thr(nprocs, io_count, io_size_bytes, runtime_s):
    if runtime_s <= 0:
        return 0.0
    return (nprocs * io_count * io_size_bytes) / (runtime_s * 1024 ** 2)


# ── build best-config lookup for IOWarp ───────────────────────────────────────

def best_cte(rows, io_count):
    """
    Returns dict[(io_size_bytes, nprocs)] → best_throughput_mbs.
    'Best' = max throughput across all (ipc_mode, runtime.num_threads) combinations.
    """
    best = {}
    for r in rows:
        ios  = parse_io_size(r.get("cte_bench.io_size", "4k"))
        np_  = int(fval(r, "cte_bench.nprocs"))
        thr  = cte_thr(np_, io_count, ios, fval(r, "runtime"))
        key  = (ios, np_)
        if thr > best.get(key, 0.0):
            best[key] = thr
    return best


# ── plot 1: throughput vs I/O size — Redis vs IOWarp (several client counts) ──

def plot_vs_iosize(redis_rows, cte_rows, count, io_count, out_dir):
    # Common I/O sizes (bytes) present in both datasets
    redis_sizes = sorted(set(int(fval(r, "redis_bench.req_size")) for r in redis_rows))
    cte_sizes   = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in cte_rows))
    common_sizes = sorted(set(redis_sizes) & set(cte_sizes))

    redis_clients = sorted(set(int(fval(r, "redis_bench.nthreads")) for r in redis_rows))
    cte_clients   = sorted(set(int(fval(r, "cte_bench.nprocs"))     for r in cte_rows))
    common_clients = sorted(set(redis_clients) & set(cte_clients))

    if not common_sizes or not common_clients:
        print("Warning: no matching I/O sizes or client counts between Redis and CTE — skipping comparison plot.")
        return

    cte_best = best_cte(cte_rows, io_count)

    # One subplot per client count
    ncols = min(len(common_clients), 3)
    nrows = (len(common_clients) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(6 * ncols, 4.5 * nrows),
                             squeeze=False)
    fig.suptitle("Redis vs IOWarp CTE Throughput vs I/O Size\n"
                 "(IOWarp = best config across ipc_mode × num_threads)", fontsize=11)

    for idx, nc in enumerate(common_clients):
        ax = axes[idx // ncols][idx % ncols]

        # Redis line
        rs_sub = [r for r in redis_rows if int(fval(r, "redis_bench.nthreads")) == nc]
        rs_sub = sorted(rs_sub, key=lambda r: fval(r, "redis_bench.req_size"))
        rs_xs  = [int(fval(r, "redis_bench.req_size")) for r in rs_sub]
        rs_ys  = [redis_thr(count, x, fval(r, "runtime")) for r, x in zip(rs_sub, rs_xs)]

        # IOWarp line (best config)
        iow_xs = common_sizes
        iow_ys = [cte_best.get((ios, nc), 0.0) for ios in iow_xs]

        if rs_xs:
            ax.plot(rs_xs, rs_ys, "o-", color="steelblue", label=f"Redis")
        if iow_xs:
            ax.plot(iow_xs, iow_ys, "s--", color="tomato",    label=f"IOWarp (best)")

        ax.set_xscale("log", base=2)
        ax.set_xticks(common_sizes)
        ax.set_xticklabels([fmt_size(s) for s in common_sizes], rotation=30, ha="right")
        ax.set_xlabel("I/O size")
        ax.set_ylabel("Throughput (MB/s)")
        ax.set_title(f"{nc} client(s)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    # Hide unused subplots
    for idx in range(len(common_clients), nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.tight_layout()
    p = out_dir / "compare_throughput_vs_iosize.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── plot 2: throughput vs clients — Redis vs IOWarp (several I/O sizes) ───────

def plot_vs_clients(redis_rows, cte_rows, count, io_count, out_dir):
    redis_sizes = sorted(set(int(fval(r, "redis_bench.req_size")) for r in redis_rows))
    cte_sizes   = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in cte_rows))
    common_sizes = sorted(set(redis_sizes) & set(cte_sizes))

    redis_clients = sorted(set(int(fval(r, "redis_bench.nthreads")) for r in redis_rows))
    cte_clients   = sorted(set(int(fval(r, "cte_bench.nprocs"))     for r in cte_rows))
    common_clients = sorted(set(redis_clients) & set(cte_clients))

    if not common_sizes or not common_clients:
        return

    cte_best = best_cte(cte_rows, io_count)

    ncols = min(len(common_sizes), 4)
    nrows = (len(common_sizes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(6 * ncols, 4.5 * nrows),
                             squeeze=False)
    fig.suptitle("Redis vs IOWarp CTE Throughput vs Client Count\n"
                 "(IOWarp = best config across ipc_mode × num_threads)", fontsize=11)

    for idx, ios in enumerate(common_sizes):
        ax = axes[idx // ncols][idx % ncols]

        # Redis line
        rs_sub = [r for r in redis_rows if int(fval(r, "redis_bench.req_size")) == ios]
        rs_sub = sorted(rs_sub, key=lambda r: fval(r, "redis_bench.nthreads"))
        rs_xs  = [int(fval(r, "redis_bench.nthreads")) for r in rs_sub]
        rs_ys  = [redis_thr(count, ios, fval(r, "runtime")) for r in rs_sub]

        # IOWarp line (best config)
        iow_xs = common_clients
        iow_ys = [cte_best.get((ios, nc), 0.0) for nc in iow_xs]

        if rs_xs:
            ax.plot(rs_xs, rs_ys, "o-", color="steelblue", label="Redis")
        if iow_xs:
            ax.plot(iow_xs, iow_ys, "s--", color="tomato",    label="IOWarp (best)")

        ax.set_xticks(common_clients)
        ax.set_xlabel("Clients")
        ax.set_ylabel("Throughput (MB/s)")
        ax.set_title(fmt_size(ios))
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    for idx in range(len(common_sizes), nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.tight_layout()
    p = out_dir / "compare_throughput_vs_clients.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── plot 3: summary bar — Redis vs IOWarp peak throughput per I/O size ─────────

def plot_peak_bar(redis_rows, cte_rows, count, io_count, out_dir):
    redis_sizes = sorted(set(int(fval(r, "redis_bench.req_size")) for r in redis_rows))
    cte_sizes   = sorted(set(parse_io_size(r.get("cte_bench.io_size", "4k")) for r in cte_rows))
    common_sizes = sorted(set(redis_sizes) & set(cte_sizes))

    if not common_sizes:
        return

    cte_best = best_cte(cte_rows, io_count)

    redis_peak, iow_peak = [], []
    for ios in common_sizes:
        rs_rows = [r for r in redis_rows if int(fval(r, "redis_bench.req_size")) == ios]
        rpeak = max((redis_thr(count, ios, fval(r, "runtime")) for r in rs_rows), default=0.0)
        ipeak = max((cte_best.get((ios, nc), 0.0)
                     for nc in set(int(fval(r, "cte_bench.nprocs")) for r in cte_rows)), default=0.0)
        redis_peak.append(rpeak)
        iow_peak.append(ipeak)

    x = np.arange(len(common_sizes))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w/2, redis_peak, w, label="Redis (peak over all clients)",   color="steelblue")
    ax.bar(x + w/2, iow_peak,   w, label="IOWarp (peak over all configs)",  color="tomato")
    ax.set_xticks(x)
    ax.set_xticklabels([fmt_size(s) for s in common_sizes], rotation=30, ha="right")
    ax.set_xlabel("I/O size")
    ax.set_ylabel("Peak Throughput (MB/s)")
    ax.set_title("Redis vs IOWarp CTE — Peak Throughput by I/O Size")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    p = out_dir / "compare_peak_bar.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"Saved: {p}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--redis",    required=True,
                        help="results.csv from microbench_redis.yaml")
    parser.add_argument("--cte",      required=True,
                        help="results.csv from microbench_cte.yaml")
    parser.add_argument("--count",    type=int, default=100000,
                        help="Redis request count (default: 100000)")
    parser.add_argument("--io-count", type=int, default=1000,
                        help="CTE io_count per process (default: 1000)")
    parser.add_argument("--out", default=None,
                        help="Output directory for plots (default: ~/microbench_compare_plots/)")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else Path.home() / "microbench_compare_plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    redis_rows = [r for r in load_csv(args.redis) if r.get("status") == "success"]
    cte_rows   = [r for r in load_csv(args.cte)   if r.get("status") == "success"]
    print(f"Redis CSV: {len(redis_rows)} successful rows")
    print(f"CTE CSV:   {len(cte_rows)} successful rows")

    plot_vs_iosize(redis_rows, cte_rows, args.count, args.io_count, out_dir)
    plot_vs_clients(redis_rows, cte_rows, args.count, args.io_count, out_dir)
    plot_peak_bar(redis_rows, cte_rows, args.count, args.io_count, out_dir)


if __name__ == "__main__":
    main()
