"""
Run Redis microbenchmark and produce results.csv using redis-benchmark's
own "X requests per second" line — not wall-clock time.

Usage:  python3 run_redis_bench.py
Output: ~/redis_microbench_results/results.csv
        ~/redis_microbench_results/plots/
"""
import subprocess, csv, re, time, sys
from pathlib import Path

COUNT     = 100_000
REQ_SIZES = [4096, 16384, 65536, 131072, 262144, 1048576, 16777216]
NTHREADS  = [1, 2, 4, 8, 16, 32]
PORT      = 6399
OUT_DIR   = Path.home() / "redis_microbench_results"
PLOT_DIR  = OUT_DIR / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PLOT_DIR.mkdir(parents=True, exist_ok=True)

def start_redis():
    subprocess.run(["redis-server", "--daemonize", "yes",
                    f"--port", str(PORT),
                    "--save", "", "--appendonly", "no",
                    "--logfile", str(OUT_DIR / "redis.log")],
                   check=True)
    time.sleep(0.8)

def stop_redis():
    subprocess.run(["redis-cli", "-p", str(PORT), "shutdown", "nosave"],
                   capture_output=True)

def run_one(req_size, nthreads):
    """Returns ops_per_sec (float) or 0 on failure."""
    # Use a smaller count for very large payloads to keep runtime reasonable
    count = COUNT if req_size <= 1048576 else 10000
    cmd = [
        "redis-benchmark",
        "-p", str(PORT),
        "-n", str(count),
        "-t", "get",
        "--threads", str(nthreads),
        "-d", str(req_size),
        "-P", "1",
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                      timeout=120).decode()
    except subprocess.CalledProcessError as e:
        out = e.output.decode()
    except subprocess.TimeoutExpired:
        return 0.0, count

    # Parse "X requests per second" (last occurrence wins)
    matches = re.findall(r"([\d.]+)\s+requests per second", out)
    if not matches:
        # Try completed-in line: "N requests completed in T seconds"
        m = re.search(r"(\d+) requests completed in ([\d.]+) seconds", out)
        if m:
            ops = float(m.group(1)) / float(m.group(2))
            return ops, count
        return 0.0, count
    return float(matches[-1]), count

def fmt_size(b):
    if b >= 1 << 20: return f"{b >> 20}MB"
    if b >= 1 << 10: return f"{b >> 10}KB"
    return f"{b}B"

# ── run ───────────────────────────────────────────────────────────────────────
print("Starting Redis server on port", PORT)
start_redis()

rows = []
for req_size in REQ_SIZES:
    for nt in NTHREADS:
        print(f"  req_size={fmt_size(req_size):6s}  nthreads={nt:2d} ...", end=" ", flush=True)
        ops_per_sec, count = run_one(req_size, nt)
        # runtime = count / ops_per_sec (actual benchmark time, not wall-clock)
        runtime = count / ops_per_sec if ops_per_sec > 0 else 0
        mbs = (ops_per_sec * req_size) / (1024 ** 2) if ops_per_sec > 0 else 0
        rows.append({
            "redis_bench.req_size": req_size,
            "redis_bench.nthreads": nt,
            "redis_bench.count":    count,
            "ops_per_sec":          round(ops_per_sec, 2),
            "throughput_mbs":       round(mbs, 2),
            "runtime":              round(runtime, 6),
            "status":               "success" if ops_per_sec > 0 else "failure",
        })
        print(f"ops/s={ops_per_sec:>10.1f}  MB/s={mbs:>8.1f}")

stop_redis()

# ── write CSV ─────────────────────────────────────────────────────────────────
csv_path = OUT_DIR / "results.csv"
with open(csv_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
print(f"\nCSV written to {csv_path}")

# ── plot ──────────────────────────────────────────────────────────────────────
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def make_plots(rows):
    req_sizes  = sorted(set(r["redis_bench.req_size"] for r in rows))
    nthreads_v = sorted(set(r["redis_bench.nthreads"] for r in rows))

    # Plot 1: Throughput (MB/s) vs I/O size, one line per nthreads
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(nthreads_v)))
    for i, nt in enumerate(nthreads_v):
        sub = sorted([r for r in rows if r["redis_bench.nthreads"] == nt],
                     key=lambda r: r["redis_bench.req_size"])
        xs = [r["redis_bench.req_size"] for r in sub]
        ys = [r["throughput_mbs"] for r in sub]
        ax.plot(xs, ys, "o-", color=colors[i], label=f"{nt} clients")
    ax.set_xscale("log", base=2)
    ax.set_xticks(req_sizes)
    ax.set_xticklabels([fmt_size(s) for s in req_sizes], rotation=30, ha="right")
    ax.set_xlabel("I/O size (req_size)")
    ax.set_ylabel("Throughput (MB/s)")
    ax.set_title(f"Redis Throughput vs I/O Size\n(count={COUNT:,} requests per case)")
    ax.legend(title="Clients (nthreads)", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p = PLOT_DIR / "redis_throughput_vs_iosize.png"
    fig.savefig(p, dpi=150); plt.close(fig)
    print(f"Saved: {p}")

    # Plot 2: Throughput vs clients, one line per size
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors2 = plt.cm.plasma(np.linspace(0.05, 0.95, len(req_sizes)))
    for i, rs in enumerate(req_sizes):
        sub = sorted([r for r in rows if r["redis_bench.req_size"] == rs],
                     key=lambda r: r["redis_bench.nthreads"])
        xs = [r["redis_bench.nthreads"] for r in sub]
        ys = [r["throughput_mbs"] for r in sub]
        ax.plot(xs, ys, "o-", color=colors2[i], label=fmt_size(rs))
    ax.set_xticks(nthreads_v)
    ax.set_xlabel("Number of clients (nthreads)")
    ax.set_ylabel("Throughput (MB/s)")
    ax.set_title(f"Redis Throughput vs Client Count\n(count={COUNT:,} requests per case)")
    ax.legend(title="I/O size", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p = PLOT_DIR / "redis_throughput_vs_clients.png"
    fig.savefig(p, dpi=150); plt.close(fig)
    print(f"Saved: {p}")

    # Plot 3: Heatmap
    matrix = np.zeros((len(nthreads_v), len(req_sizes)))
    for r in rows:
        ri = req_sizes.index(r["redis_bench.req_size"])
        ni = nthreads_v.index(r["redis_bench.nthreads"])
        matrix[ni, ri] = r["throughput_mbs"]
    fig, ax = plt.subplots(figsize=(11, 5))
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", origin="lower")
    ax.set_xticks(range(len(req_sizes)))
    ax.set_xticklabels([fmt_size(s) for s in req_sizes], rotation=30, ha="right")
    ax.set_yticks(range(len(nthreads_v)))
    ax.set_yticklabels(nthreads_v)
    ax.set_xlabel("I/O size"); ax.set_ylabel("Clients (nthreads)")
    ax.set_title(f"Redis Throughput Heatmap (MB/s)  (count={COUNT:,})")
    plt.colorbar(im, ax=ax, label="Throughput (MB/s)")
    for ni in range(len(nthreads_v)):
        for ri in range(len(req_sizes)):
            v = matrix[ni, ri]
            ax.text(ri, ni, f"{v:.0f}", ha="center", va="center",
                    fontsize=7, color="black")
    fig.tight_layout()
    p = PLOT_DIR / "redis_heatmap.png"
    fig.savefig(p, dpi=150); plt.close(fig)
    print(f"Saved: {p}")

make_plots(rows)
print("\nDone.")
