#!/usr/bin/env bash
# run_experiments.sh
# Runs gray-scott (L, steps, nprocs sweeps) and redis benchmark,
# writes results.csv for each, then plots everything.
#
# Usage:  bash run_experiments.sh
# Outputs:
#   ~/gray_scott_explore_L/results.csv      + plots/
#   ~/gray_scott_explore_steps/results.csv  + plots/
#   ~/gray_scott_explore_nprocs/results.csv + plots/
#   ~/redis_microbench_results/results.csv  + plots/

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GS_BIN="/home/gbhogadi/miniconda3/envs/iowarp/bin/gray-scott"
MPI="/home/gbhogadi/miniconda3/envs/iowarp/bin/mpirun"
ADIOS_XML="/home/gbhogadi/clio-core/jarvis_iowarp/jarvis_iowarp/adios2_gray_scott/config/adios2.xml"
PYTHON="/home/gbhogadi/miniconda3/bin/python"

# ── helper: run one gray-scott case and return "runtime_s,out_bytes" ─────────
run_gs() {
    local L=$1 steps=$2 plotgap=$3 nprocs=$4
    local RUNDIR
    RUNDIR=$(mktemp -d /tmp/gs_XXXXXX)
    local OUT_BP="$RUNDIR/out.bp"
    local SETTINGS="$RUNDIR/settings.json"
    local ADIOS_COPY="$RUNDIR/adios2.xml"

    cp "$ADIOS_XML" "$ADIOS_COPY"

    cat > "$SETTINGS" <<EOF
{
  "L": $L,
  "Du": 0.2,
  "Dv": 0.1,
  "F": 0.01,
  "k": 0.05,
  "dt": 2.0,
  "plotgap": $plotgap,
  "steps": $steps,
  "noise": 0.01,
  "output": "$OUT_BP",
  "checkpoint": false,
  "checkpoint_freq": 70,
  "checkpoint_output": "$RUNDIR/ckpt.bp",
  "restart": false,
  "restart_input": "$RUNDIR/ckpt.bp",
  "adios_span": false,
  "adios_memory_selection": false,
  "mesh_type": "image",
  "adios_config": "$ADIOS_COPY"
}
EOF

    local T_START T_END
    T_START=$(date +%s%3N)
    $MPI -np "$nprocs" --map-by core --bind-to core \
         "$GS_BIN" "$SETTINGS" 0 \
         > "$RUNDIR/stdout.txt" 2>&1
    T_END=$(date +%s%3N)

    local RT_MS=$(( T_END - T_START ))
    local RT_S
    RT_S=$(awk "BEGIN{printf \"%.3f\", $RT_MS/1000}")

    local OUT_BYTES=0
    if [ -e "$OUT_BP" ]; then
        OUT_BYTES=$(du -sb "$OUT_BP" | awk '{print $1}')
    fi

    rm -rf "$RUNDIR"
    echo "$RT_S,$OUT_BYTES"
}

# ── write CSV header ──────────────────────────────────────────────────────────
write_header() {
    echo "gsbench.L,gsbench.steps,gsbench.plotgap,gsbench.nprocs,gsbench.ppn,engine,runtime,gs_out_bytes,gs_out_gib,status"
}

write_row() {
    local L=$1 steps=$2 plotgap=$3 nprocs=$4 rt=$5 bytes=$6
    local gib
    gib=$(awk "BEGIN{printf \"%.6f\", $bytes/1073741824}")
    echo "$L,$steps,$plotgap,$nprocs,$nprocs,bp5,$rt,$bytes,$gib,success"
}

# ════════════════════════════════════════════════════════════════════════════
# SWEEP 1: vary L  (steps=100, plotgap=10, nprocs=4)
# ════════════════════════════════════════════════════════════════════════════
L_OUTDIR="$HOME/gray_scott_explore_L"
mkdir -p "$L_OUTDIR"
CSV="$L_OUTDIR/results.csv"
write_header > "$CSV"

for L in 64 96 128 192 256; do
    echo "  [L-sweep] L=$L ..."
    RESULT=$(run_gs $L 100 10 4)
    RT=$(echo "$RESULT" | cut -d, -f1)
    BYTES=$(echo "$RESULT" | cut -d, -f2)
    write_row $L 100 10 4 "$RT" "$BYTES" >> "$CSV"
    echo "    → runtime=${RT}s  bytes=${BYTES}"
done
echo "L sweep done → $CSV"

# ════════════════════════════════════════════════════════════════════════════
# SWEEP 2: vary steps  (L=128, plotgap=10, nprocs=4)
# ════════════════════════════════════════════════════════════════════════════
STEPS_OUTDIR="$HOME/gray_scott_explore_steps"
mkdir -p "$STEPS_OUTDIR"
CSV="$STEPS_OUTDIR/results.csv"
write_header > "$CSV"

for STEPS in 50 100 200 400; do
    echo "  [steps-sweep] steps=$STEPS ..."
    RESULT=$(run_gs 128 $STEPS 10 4)
    RT=$(echo "$RESULT" | cut -d, -f1)
    BYTES=$(echo "$RESULT" | cut -d, -f2)
    write_row 128 $STEPS 10 4 "$RT" "$BYTES" >> "$CSV"
    echo "    → runtime=${RT}s  bytes=${BYTES}"
done
echo "Steps sweep done → $CSV"

# ════════════════════════════════════════════════════════════════════════════
# SWEEP 3: vary nprocs  (L=128, steps=200, plotgap=10)
# ════════════════════════════════════════════════════════════════════════════
NPROCS_OUTDIR="$HOME/gray_scott_explore_nprocs"
mkdir -p "$NPROCS_OUTDIR"
CSV="$NPROCS_OUTDIR/results.csv"
write_header > "$CSV"

for NP in 1 2 4 8; do
    echo "  [nprocs-sweep] nprocs=$NP ..."
    RESULT=$(run_gs 128 200 10 $NP)
    RT=$(echo "$RESULT" | cut -d, -f1)
    BYTES=$(echo "$RESULT" | cut -d, -f2)
    write_row 128 200 10 $NP "$RT" "$BYTES" >> "$CSV"
    echo "    → runtime=${RT}s  bytes=${BYTES}"
done
echo "nprocs sweep done → $CSV"

# ════════════════════════════════════════════════════════════════════════════
# REDIS BENCHMARK
# ════════════════════════════════════════════════════════════════════════════
REDIS_OUTDIR="$HOME/redis_microbench_results"
mkdir -p "$REDIS_OUTDIR"
REDIS_CSV="$REDIS_OUTDIR/results.csv"

echo "redis_bench.req_size,redis_bench.nthreads,runtime,status" > "$REDIS_CSV"

# Start redis-server in background
redis-server --daemonize yes --port 6399 --logfile /tmp/redis_bench.log \
             --save "" --appendonly no
sleep 1

for REQ_SIZE in 4096 16384 65536 131072 262144 1048576 16777216; do
    for NTHREADS in 1 2 4 8 16 32; do
        echo "  [redis] req_size=${REQ_SIZE}B nthreads=${NTHREADS} ..."
        T_START=$(date +%s%3N)
        redis-benchmark -p 6399 -n 100000 -t get \
            --threads "$NTHREADS" -d "$REQ_SIZE" -P 1 \
            -q > /tmp/redis_out.txt 2>&1
        T_END=$(date +%s%3N)
        RT_MS=$(( T_END - T_START ))
        RT_S=$(awk "BEGIN{printf \"%.3f\", $RT_MS/1000}")
        echo "$REQ_SIZE,$NTHREADS,$RT_S,success" >> "$REDIS_CSV"
        echo "    → runtime=${RT_S}s"
    done
done

redis-cli -p 6399 shutdown nosave 2>/dev/null || true
echo "Redis benchmark done → $REDIS_CSV"

# ════════════════════════════════════════════════════════════════════════════
# GENERATE PLOTS
# ════════════════════════════════════════════════════════════════════════════
echo ""
echo "=== Generating plots ==="

$PYTHON "$SCRIPT_DIR/plot_gray_scott_test.py" \
    "$HOME/gray_scott_explore_L/results.csv" --dim L \
    --out "$HOME/gray_scott_explore_L/plots"

$PYTHON "$SCRIPT_DIR/plot_gray_scott_test.py" \
    "$HOME/gray_scott_explore_steps/results.csv" --dim steps \
    --out "$HOME/gray_scott_explore_steps/plots"

$PYTHON "$SCRIPT_DIR/plot_gray_scott_test.py" \
    "$HOME/gray_scott_explore_nprocs/results.csv" --dim nprocs 2>/dev/null || \
$PYTHON - <<'PYEOF'
# nprocs uses a custom plot since plot_gray_scott_test.py doesn't support nprocs dim
import csv, os
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv_path = Path.home() / "gray_scott_explore_nprocs/results.csv"
out_dir  = Path.home() / "gray_scott_explore_nprocs/plots"
out_dir.mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader(open(csv_path)))
rows = sorted(rows, key=lambda r: int(r["gsbench.nprocs"]))
x   = [int(r["gsbench.nprocs"]) for r in rows]
rts = [float(r["runtime"]) for r in rows]
t1  = rts[0]
speedup = [t1 / rt for rt in rts]
ideal   = [float(n) / x[0] for n in x]

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
fig.suptitle("Gray Scott — vary nprocs  (L=128, steps=200, plotgap=10)", fontsize=12)

axes[0].plot(x, rts, "o-", color="steelblue")
axes[0].set_xlabel("nprocs"); axes[0].set_ylabel("Wall-clock time (s)")
axes[0].set_xticks(x); axes[0].set_title("Runtime vs nprocs"); axes[0].grid(True, alpha=0.3)

axes[1].plot(x, speedup, "o-", color="tomato",    label="Measured speedup")
axes[1].plot(x, ideal,   "s--", color="gray",      label="Ideal (linear)")
axes[1].set_xlabel("nprocs"); axes[1].set_ylabel("Speedup")
axes[1].set_xticks(x); axes[1].set_title("Speedup vs nprocs")
axes[1].legend(); axes[1].grid(True, alpha=0.3)

fig.tight_layout()
p = out_dir / "nprocs_sweep.png"
fig.savefig(p, dpi=150); plt.close(fig)
print(f"Saved: {p}")
PYEOF

$PYTHON "$SCRIPT_DIR/plot_microbench_redis.py" \
    "$HOME/redis_microbench_results/results.csv" \
    --count 100000 \
    --out "$HOME/redis_microbench_results/plots"

echo ""
echo "=== All done ==="
echo "Plots written to:"
echo "  ~/gray_scott_explore_L/plots/"
echo "  ~/gray_scott_explore_steps/plots/"
echo "  ~/gray_scott_explore_nprocs/plots/"
echo "  ~/redis_microbench_results/plots/"
