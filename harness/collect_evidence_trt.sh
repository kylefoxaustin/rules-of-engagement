#!/bin/bash
# TENSORRT EVIDENCE COLLECTOR — the second board family, proving the adapter contract.
#
# The evidence JSON contract is BOARD-AGNOSTIC. Only four things are board-specific,
# and this file exists to demonstrate that they are the only four:
#
#   1. the runner            qnn-net-run          ->  trtexec --loadEngine
#   2. the timing source     profile-viewer       ->  "GPU Compute Time ... median"
#   3. the quiet-board probe pgrep qnn-net-run    ->  nvidia-smi compute processes
#   4. the config readback   vtcm/O from binary   ->  precision+shape from the engine
#
# Everything else — run provenance token, tenancy before/after, artifact md5, replicate
# capture, status distinct from gate (M12) — is copied verbatim from the Hexagon
# collector because it is not Hexagon-specific.
#
# One genuine difference worth stating: TensorRT engine builds are NOT deterministic.
# The same ONNX built twice yields different md5s and can differ several percent in
# latency (M24). So artifact identity is per-BUILD here, not per-model, and a build
# family needs its own replicate treatment.
#
# Usage: collect_evidence_trt.sh <engine> <label> [reps] [iterations]
set -u
ENGINE=${1:?engine path}
LABEL=${2:?label e.g. v8n_b1_fp16}
REPS=${3:-5}
ITERS=${4:-200}
TRTEXEC=${TRTEXEC:-/usr/src/tensorrt/bin/trtexec}
# hostname -s on this Jetson is "ubuntu" -- useless as a board identity, and it would
# have labelled every Orin record with a name shared by half the fleet. Explicit.
BOARD=${BOARD:-}
if [ -z "$BOARD" ]; then
  if [ -r /proc/device-tree/model ]; then
    BOARD=$(tr -d "\0" < /proc/device-tree/model | tr " " "-")
  else BOARD=$(hostname -s); fi
fi
HOST=$BOARD
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTDIR=$HOME/evidence
mkdir -p "$OUTDIR"
LOG=$OUTDIR/${LABEL}_${STAMP}.log
OUT=$OUTDIR/${LABEL}_${STAMP}.json

# per-UNIT board identity: hostname and model are shared across units (M30)
. "$(dirname "$0")/board_identity.sh" 2>/dev/null || . /root/qnn/board_identity.sh 2>/dev/null || true
BOARD_ID_JSON=$(board_identity 2>/dev/null || echo '{}')
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)
RUN_ID=$(printf '%s|%s|%s' "$BOOT_ID" "$(date +%s%N)" "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" | sha256sum | cut -c1-32)
# NOTE: this MUST stay on one line. It was previously written with a trailing "\" and
# the continuation line was lost, leaving an unterminated $( that swallowed everything
# up to the next unbalanced ")" -- which ate start_stimulus, stop_stimulus and
# env_declared_json. Result: no run provenance, no stimulus control, M40 environment
# declaration silently disabled, and "environment":, emitted as INVALID JSON. It
# survived because `bash -n` PARSES it: the stray $( is closed by a later ")".
# A syntax check is not a behaviour check.

# ---- M40: DECLARE the environment, do not inherit it -------------------------
# ENV_INTENT=QUIET             nothing else runs; verified, and refused if not
# ENV_INTENT=LOADED:<stimulus> the benchmark GENERATES the load itself, because the
#                              load is an independent variable of the experiment
# There is no third option. A board that merely happens to be busy is an unknown, not
# a loaded board -- and the difference is the whole of experimental control.
ENV_INTENT=${ENV_INTENT:-QUIET}
STIMULUS_PID=""
# NOTE: $(( )) is deliberately NOT used inside the case branch -- bash mis-parses the
# closing )) as the case terminator. Computed before the case instead.
_stim_kind=""; _stim_n=0
case "$ENV_INTENT" in
  LOADED:*)
    _spec=${ENV_INTENT#LOADED:}
    _stim_kind=${_spec%%/*}
    _stim_n=${_spec##*/}
    ;;
esac
if [ "$_stim_n" = "$_stim_kind" ]; then _stim_n=$(expr $(nproc) / 2); fi

start_stimulus() {
  [ -z "$_stim_kind" ] && return 0
  echo "generating declared stimulus: $_stim_kind on $_stim_n workers" >&2
  _i=0
  while [ "$_i" -lt "$_stim_n" ]; do
    setsid sh -c 'while true; do :; done' >/dev/null 2>&1 &
    STIMULUS_PID="$STIMULUS_PID $!"
    _i=$(expr $_i + 1)
  done
  sleep 2   # let the load register before the measurement window opens
}
stop_stimulus() {
  # A load generator that outlives its benchmark IS the defect M40 exists to prevent.
  # SIGTERM, verify, and escalate only if the process is not in uninterruptible sleep (M29).
  [ -z "$STIMULUS_PID" ] && return 0
  kill -TERM $STIMULUS_PID 2>/dev/null
  sleep 1
  for _p in $STIMULUS_PID; do
    if kill -0 "$_p" 2>/dev/null; then
      _st=$(ps -o stat= -p "$_p" 2>/dev/null | tr -d ' ')
      case "$_st" in
        D*) echo "stimulus $_p in D state -- leaving it, device reset needed (M29)" >&2 ;;
        *)  kill -KILL "$_p" 2>/dev/null ;;
      esac
    fi
  done
  sleep 1
  _left=0
  for _p in $STIMULUS_PID; do kill -0 "$_p" 2>/dev/null && _left=$(expr $_left + 1); done
  [ "$_left" -gt 0 ] && echo "WARNING: $_left stimulus worker(s) survived teardown" >&2
  return 0
}
env_declared_json() {
  printf '{"intent":"%s","stimulus_workers":%s,"_rule":"M40 — declared, not inherited: QUIET is verified and refused on failure; LOADED is GENERATED by this benchmark so the stimulus travels with it and is identical across boards by construction"}' \
    "$ENV_INTENT" "$(echo $STIMULUS_PID | wc -w)"
}


# --- 3. quiet-board probe -----------------------------------------------------
# Two portability lessons paid for here, both of which failed LOUDLY (good):
#   * `nvidia-smi --query-compute-apps` is UNSUPPORTED on Jetson -- it prints "[N/A]",
#     which a naive `grep -c .` counts as one running process, so the collector
#     refused to run on a completely idle board.
#   * `pgrep -f trtexec` SELF-MATCHES the ssh command that invokes it (the same trap
#     that wedged the IQ-9075 with a kill -9). Match on the process NAME, not the
#     command line.
# The probe that actually works on Jetson is real GPU utilisation from tegrastats.
gpu_busy_pct() {
  local v
  v=$(timeout 4 tegrastats --interval 500 2>/dev/null | head -2 | tail -1 \
      | grep -oE "GR3D_FREQ [0-9]+%" | grep -oE "[0-9]+" | head -1)
  echo "${v:-0}"
}
# `pgrep | grep -c` already prints 0 when empty; the `|| echo 0` appended a SECOND
# zero and produced invalid JSON ("trtexec_procs":0\n0). wc -l always prints exactly one.
gpu_procs() { pgrep -x trtexec 2>/dev/null | wc -l | tr -d " "; }
require_quiet() {
  local n; n=$(gpu_procs)
  if [ "$n" -gt 0 ]; then
    echo "REFUSING TO MEASURE: $n trtexec process(es) already running" >&2
    return 1
  fi
  local g; g=$(gpu_busy_pct)
  if [ "$g" -gt 15 ]; then
    echo "REFUSING TO MEASURE: GPU is $g% busy (GR3D_FREQ) -- something else is resident" >&2
    return 1
  fi
  # loadavg must be PER CORE. A flat ">= 3" refused to measure on a 14-core Thor whose
  # load was entirely background kworkers (devfreq, ext4) -- 3.19/14 = 23%, i.e. idle.
  # An absolute threshold silently encodes an assumption about core count.
  local la ncpu pct
  la=$(awk '{print $1}' /proc/loadavg)
  ncpu=$(nproc 2>/dev/null || echo 1)
  pct=$(awk -v l="$la" -v n="$ncpu" 'BEGIN{printf "%d", 100*l/n}')
  if [ "$pct" -ge 50 ]; then
    echo "REFUSING TO MEASURE: loadavg $la on $ncpu cores = ${pct}% >= 50%" >&2; return 1
  fi
  echo "board quiet: 0 GPU procs, loadavg $la on $ncpu cores (${pct}%)"
}

envelope() {   # M13
  printf '{"power_mode":"%s","cpu_governor":"%s","gpu_clock_mhz":"%s","soc_temp_mC":"%s"}' \
    "$(nvpmodel -q 2>/dev/null | grep -A1 'Power Mode' | tail -1 | tr -d '\n' || echo unknown)" \
    "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)" \
    "$(nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ' || echo unknown)" \
    "$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo unknown)"
}

tenancy() {
  printf '{"trtexec_procs":%s,"gpu_busy_pct":%s,"loadavg":"%s","mem_free_mb":%s,"power_mode":"%s","utc":"%s"}' \
    "$(gpu_procs)" "$(gpu_busy_pct)" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    "$(awk '/MemAvailable/{printf "%d",$2/1024}' /proc/meminfo)" \
    "$(nvpmodel -q 2>/dev/null | grep -A1 'Power Mode' | tail -1 | tr -d '\n' || echo unknown)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

{ echo "=== collect_evidence_trt $LABEL reps=$REPS iters=$ITERS $STAMP"; require_quiet; } >"$LOG" 2>&1
if ! require_quiet >/dev/null 2>&1; then
  printf '{"status":"CANNOT_RUN","why":"board not quiet (M10)","label":"%s"}\n' "$LABEL" > "$OUT"
  cat "$OUT"; exit 9
fi


# ---- M41 PORCH ---------------------------------------------------------------
# The porch protocol existed as a standalone script that NOTHING CALLED. A run path that
# does not invoke its own entry/exit check is not protected by it, and `require_quiet`
# alone is only half the contract: it checks GPU procs and loadavg at entry, never at
# exit, and never looks at disk, /tmp or /dev/shm -- the surfaces that have actually
# cost this fleet gigabytes.
. "$(dirname "$0")/porch.sh" 2>/dev/null || . "$HOME/porch.sh" 2>/dev/null || true
PORCH=1; command -v porch_front >/dev/null 2>&1 || PORCH=0
ACCEL_PROC=trtexec
if [ "$PORCH" = 1 ]; then
  if ! porch_front "$ACCEL_PROC"; then
    printf '{"status":"CANNOT_RUN","why":"front porch refused: board not idle (M41)","porch_entry":%s,"label":"%s"}\n' \
      "${PORCH_ENTRY:-null}" "$LABEL" > "$OUT"
    cat "$OUT"; exit 9
  fi
  porch_will_remove "$OUTDIR/.stimulus_$$"
  # back porch must run even if the benchmark dies, or a crash leaves the board dirty
  # AND unattributed -- the exact pair the protocol exists to prevent.
  trap 'porch_back "$ACCEL_PROC" >/dev/null 2>&1 || true' EXIT INT TERM
fi

# ---- POWER SAMPLED IN THE SAME RUN (Kyle, 2026-08-20) -----------------------
# perf/W was a SEPARATE measurement group, which means the power figure and the timing
# figure came from different runs -- different thermal state, different clocks, possibly a
# different engine. That is an M35 shared-context violation by construction, and it is the
# reason a perf/W ratio could never be better than "about right". Sampling the rails inside
# the SAME run makes the ratio exact, costs one background process, and doubles as a
# limiter diagnostic: on Thor, yolov8n plateaus at ~61 W while yolov8l on the same board
# draws 96 W, which is how we identified the small model as dispatch-limited rather than
# device-bound -- a question the previous sweep left open as "limiter not identified".
POWER_LOG=""
RAILS_LOG=""
if [ -r "$HOME/read_rails.sh" ]; then
  RAILS_LOG=/tmp/rails_$$.txt
  nohup sh "$HOME/sample_rails.sh" "$RAILS_LOG" 0.2 >/dev/null 2>&1 &
  POWER_PID=$!
  porch_will_remove "$RAILS_LOG"
  sleep 1
elif command -v tegrastats >/dev/null 2>&1; then
  POWER_LOG=/tmp/pw_$$.txt
  nohup timeout 600 tegrastats --interval 500 > "$POWER_LOG" 2>&1 &
  POWER_PID=$!
  porch_will_remove "$POWER_LOG"
  sleep 1
fi
power_json() {
  # PREFER INA3221 sysfs over tegrastats. The published perf/W used sysfs rails explicitly
  # because tegrastats on Orin reports only 3 of 4 rails and OMITS DRAM (VDDQ_VDD2_1V8AO).
  # Sampling the weaker source would have made this rerun's perf/W quietly incomparable
  # with the figures it exists to reproduce -- an M35 break introduced by "improving" the
  # instrument mid-campaign. tegrastats stays as a fallback where sysfs is absent.
  if [ -n "$RAILS_LOG" ] && [ -s "$RAILS_LOG" ]; then
    python3 - "$RAILS_LOG" <<'PYEOF'
import json,sys
rows=[json.loads(l) for l in open(sys.argv[1]) if l.strip().startswith("{")]
if not rows: print("null"); raise SystemExit
keys=sorted({k for r in rows for k in r["rails_mW"]})
peak={k:max(r["rails_mW"].get(k,0) for r in rows) for k in keys}
mean={k:round(sum(r["rails_mW"].get(k,0) for r in rows)/len(rows),1) for k in keys}
print(json.dumps({"rails_peak_mW":peak,"rails_mean_mW":mean,
 "sum_peak_mW":sum(peak.values()),"sum_mean_mW":round(sum(mean.values()),1),
 "samples":len(rows),
 "source":"INA3221 sysfs, ALL rails incl DRAM, sampled DURING the run at 200ms",
 "_use":"sum_mean_mW is the basis for energy-per-inference; sum_peak_mW is comparable to a tegrastats peak"}))
PYEOF
    return
  fi
  [ -z "$POWER_LOG" ] && { printf 'null'; return; }
  [ -r "$POWER_LOG" ] || { printf 'null'; return; }
  _gpu=$(grep -oE 'VDD_GPU [0-9]+mW' "$POWER_LOG" | awk '{print $2}' | tr -dc '0-9\n' | sort -n | tail -1)
  _vin=$(grep -oE 'VIN [0-9]+mW' "$POWER_LOG" | awk '{print $2}' | tr -dc '0-9\n' | sort -n | tail -1)
  _n=$(grep -c 'VDD_GPU' "$POWER_LOG")
  _n=$(printf '%s' "${_n:-0}" | head -1)
  printf '{"gpu_rail_peak_mW":%s,"board_vin_peak_mW":%s,"samples":%s,"source":"tegrastats @500ms, sampled DURING this run","_caveat":"PEAK of an instantaneous rail, not an integrated energy measurement. A perf/W built from this is an upper bound on power and therefore a LOWER bound on efficiency."}' \
    "${_gpu:-0}" "${_vin:-0}" "${_n:-0}"
}

start_stimulus
TEN_BEFORE=$(tenancy)
GPU_MS=""; WALL=""; RC_ALL=0
for _ in $(seq 1 "$REPS"); do
  T0=$(date +%s%3N)
  OUTPUT=$("$TRTEXEC" --loadEngine="$ENGINE" --iterations="$ITERS" --warmUp=500 \
           --noDataTransfers --useSpinWait 2>&1)
  RC=$?; T1=$(date +%s%3N)
  echo "$OUTPUT" >>"$LOG"
  [ $RC -ne 0 ] && RC_ALL=$RC
  # --- 2. timing source: GPU Compute Time, median. Device compute only; the
  #        enqueue/H2D/D2H terms are reported separately and EXCLUDED (M14).
  M=$(echo "$OUTPUT" | awk -F'median = ' '/GPU Compute Time/{split($2,a," "); print a[1]; exit}')
  [ -n "$M" ] && GPU_MS="$GPU_MS${GPU_MS:+,}$M"
  WALL="$WALL${WALL:+,}$((T1-T0))"
done
TEN_AFTER=$(tenancy)
stop_stimulus
# ---- IN-RUN OUTPUT GATE (M1/M2) ---------------------------------------------
# Added after a timing run of an engine that DETECTS NOTHING was recorded as a result.
# It passed every check the harness had -- porch clean, 3 replicates, 0.5% spread, status
# OK, artifact md5 -- because all of those describe the RUN. The output was never looked
# at, and the broken engine was 8.3% FASTER than the working one. M12 still holds: status
# (did it execute) stays SEPARATE from gate (is the output valid); a gate failure does not
# rewrite status, it makes the number unpublishable.
GATE_JSON=null; GATE_STATUS=NOT_RUN
if [ -x "$HOME/gate_inline_trt.py" ] || [ -r "$HOME/gate_inline_trt.py" ]; then
  GATE_JSON=$(python3 "$HOME/gate_inline_trt.py" "$ENGINE" "${GATE_N:-64}" 2>/dev/null)
  GATE_RC=$?
  [ -z "$GATE_JSON" ] && GATE_JSON=null
  GATE_STATUS=$([ "$GATE_RC" = 0 ] && echo PASS || echo FAIL)
  if [ "$GATE_STATUS" = "FAIL" ]; then
    echo "GATE FAIL: this engine is not detecting. The timing is real and must NOT be published." >&2
  fi
fi

[ -n "${POWER_PID:-}" ] && kill "$POWER_PID" 2>/dev/null
POWER_JSON=$(power_json)
PUBLISHABLE=true
[ "$GATE_STATUS" = "FAIL" ] && PUBLISHABLE=false
[ "$GATE_STATUS" = "NOT_RUN" ] && PUBLISHABLE=false
trap - EXIT INT TERM
PORCH_JSON=null
[ "$PORCH" = 1 ] && PORCH_JSON=$(porch_back "$ACCEL_PROC")

STATUS=OK
[ $RC_ALL -ne 0 ] && STATUS=RUNTIME_ERROR
[ -z "$GPU_MS" ] && STATUS=RUNTIME_ERROR

# --- 4. config readback from the ENGINE itself (M4 + M38) ---------------------
# `grep -c` PRINTS 0 and EXITS 1 when it matches nothing, so `|| echo 0` appended a
# SECOND zero -> "0\n0" -> "[: integer expression expected", and PREC silently fell to
# unknown. FOURTH occurrence of this exact idiom in this codebase.
INSPECT=$("$TRTEXEC" --loadEngine="$ENGINE" --dumpLayerInfo --profilingVerbosity=detailed \
          --iterations=1 2>/dev/null | grep -ciE 'fp16|half')
INSPECT=$(printf '%s' "${INSPECT:-0}" | head -1)
PREC=fp16; [ "$INSPECT" -eq 0 ] && PREC=unknown
case "$LABEL" in *int8*) PREC=int8;; esac
BATCH=$(echo "$LABEL" | sed -n 's/.*_b\([0-9]*\)_.*/\1/p'); BATCH=${BATCH:-1}

cat > "$OUT" <<EOF
{"model":"$LABEL","batch":$BATCH,"host":"$HOST",
 "board_identity":$BOARD_ID_JSON,"precision":"$PREC","status":"$STATUS",
 "run_provenance":{"run_id":"$RUN_ID","boot_id":"$BOOT_ID",
   "_what_this_proves":"one execution on this boot; a duplicate run_id means a copied file",
   "_what_this_does_NOT_prove":"that the numbers are true"},
 "log":"$LOG","utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "artifact":{"path":"$ENGINE","md5":"$(md5sum "$ENGINE" | cut -d' ' -f1)",
   "_note":"TensorRT engine builds are NOT deterministic; identity is per-BUILD, not per-model (M24)"},
 "config_requested":{"precision":"$PREC","batch":$BATCH,"iterations":$ITERS,
   "power_mode":"MAXN","no_data_transfers":true,"spin_wait":true},
 "measurement":{"metric":"gpu_compute_time_per_inference_ms",
   "includes":"device compute only; enqueue, H2D and D2H EXCLUDED (M14)",
   "gpu_ms_per_inference":[$GPU_MS],"wall_ms_per_rep":[$WALL],"reps":$REPS,"K":$ITERS},
 "envelope":$(envelope),
 "environment":$(env_declared_json),
 "tenancy":{"before":$TEN_BEFORE,"after":$TEN_AFTER},
 "porch":${PORCH_JSON:-null},
 "power":${POWER_JSON:-null},
 "gate":${GATE_JSON:-null},
 "gate_status":"${GATE_STATUS}",
 "publishable":$PUBLISHABLE,
 "rc":$RC_ALL}
EOF
CH=$(sha256sum "$OUT" | cut -c1-64)
python3 - "$OUT" "$CH" <<'PY' 2>/dev/null || true
import json,sys
p,ch=sys.argv[1],sys.argv[2]
d=json.load(open(p)); d["run_provenance"]["content_sha256_of_body"]=ch
json.dump(d,open(p,"w"),indent=1)
PY
cat "$OUT"
