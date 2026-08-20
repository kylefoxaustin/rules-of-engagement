#!/bin/bash
# Perf-per-watt for Jetson boards, measured from the on-board INA3221 rails.
#
# WHAT EACH BOARD CAN ACTUALLY ISOLATE -- this is not symmetric and must travel with
# the numbers:
#   Thor : VDD_GPU          = GPU only, a dedicated rail.  VIN = total board input.
#   Orin : VDD_GPU_SOC      = GPU **and SoC on one rail**; they cannot be separated
#                             in hardware. VIN_SYS_5V0 = 5V system rail.
# So a Thor-GPU-watt and an Orin-GPU-watt are NOT the same quantity. The comparable
# figure across boards is DELTA OVER IDLE, which cancels whatever else shares the
# rail, and total board power.
#
# Method: sample tegrastats continuously; take an idle baseline immediately before
# the timed run and the mean during it. Report absolute, delta, and both perf/W forms
# (inferences per joule, and millijoules per inference).
set -u
cd /home/kyle/acc
T=/usr/src/tensorrt/bin/trtexec
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG=/home/kyle/acc/power_${STAMP}.log
TG=/tmp/tegra_${STAMP}.log

rails() {   # mean mW per rail over the sample window
  python3 - "$1" <<'PY'
import re, sys, collections
acc = collections.defaultdict(list)
for line in open(sys.argv[1], errors="ignore"):
    for name, mw in re.findall(r"(VDD_[A-Z0-9_]+|VIN[A-Z0-9_]*)\s+(\d+)mW", line):
        acc[name].append(int(mw))
for k in sorted(acc):
    if acc[k]:
        print(f"{k}={sum(acc[k])/len(acc[k]):.0f}")
PY
}

{
echo "== POWER BENCH $STAMP =="
date -u; nvpmodel -q 2>/dev/null | tr '\n' ' '; echo
echo "cores=$(nproc)"
echo "== rails this board exposes =="
timeout 3 tegrastats --interval 500 2>/dev/null | head -1 | grep -oE "(VDD|VIN)[A-Za-z0-9_]* [0-9]+mW" || true

for m in yolov8n yolov8l; do
  for b in 1 4; do
    E=${m}_b${b}.fp16.engine
    [ -s "$E" ] || { echo "  $m b$b: no engine"; continue; }

    # idle baseline, immediately before the run so thermal state matches
    ( timeout 12 tegrastats --interval 200 > $TG.idle 2>/dev/null ) || true
    IDLE=$(rails $TG.idle)

    # timed run with power sampled across it
    ( timeout 60 tegrastats --interval 200 > $TG.load 2>/dev/null ) &
    TGPID=$!
    OUT=$($T --loadEngine=$E --iterations=400 --warmUp=2000 --avgRuns=100 \
             --noDataTransfers --useSpinWait 2>&1)
    kill $TGPID 2>/dev/null; wait $TGPID 2>/dev/null
    LOAD=$(rails $TG.load)

    MS=$(echo "$OUT" | grep 'GPU Compute Time' | head -1 | sed 's/.*median = //; s/ ms.*//')
    IPS=$(awk -v x="$MS" -v n="$b" 'BEGIN{printf "%.1f", n*1000/x}')

    echo "  --- $m batch-$b : ${MS} ms/batch, ${IPS} img/s ---"
    for r in $(echo "$LOAD" | cut -d= -f1); do
      LW=$(echo "$LOAD" | grep "^$r=" | cut -d= -f2)
      IW=$(echo "$IDLE" | grep "^$r=" | cut -d= -f2)
      [ -z "$LW" ] && continue
      [ -z "$IW" ] && IW=0
      awk -v r="$r" -v lw="$LW" -v iw="$IW" -v ips="$IPS" 'BEGIN{
        d = lw - iw
        printf "      %-18s idle %6.2f W  load %6.2f W  delta %6.2f W", r, iw/1000, lw/1000, d/1000
        if (d > 50) printf "   %7.2f img/J(delta)  %8.2f mJ/img(delta)", ips/(d/1000), (d)/ips
        if (lw > 0) printf "   [%6.2f img/J abs]", ips/(lw/1000)
        printf "\n"
      }'
    done
  done
done
rm -f $TG.idle $TG.load
echo POWER_BENCH_DONE
} 2>&1 | tee -a $LOG
