#!/bin/sh
# BOARD-SIDE EVIDENCE COLLECTOR — everything the record schema requires, from ONE run.
#
# The record schema has existed since 2026-08-17 and has validated exactly zero real
# measurements, because nothing ever emitted a record. Ten rules (M4 M6 M9 M10 M11 M12
# M14 M16 M23 M28) are enforced on paper and enforce nothing: the validator runs, finds
# an empty directory, and reports success. That is worse than an unbuilt check.
#
# This closes it. For each model it captures, IN THE SAME RUN as the timing:
#   M9   the log path on this box (not stdout)
#   M10  tenancy BEFORE and AFTER, from the same session
#   M4   the config requested (what we asked for) -- readback happens host-side
#   M6   n replicates, so a noise floor can be computed rather than assumed
#   M12  the runtime status, kept distinct from the gate outcome
#   M28  wall clock per rep, so an implausibly FAST run is detectable
#   M14  which terms are included: accelerator execute time, host excluded
#
# Usage: collect_evidence.sh <model> [reps] [num_inferences]
set -u
export LD_LIBRARY_PATH=/root/qnn/lib
export ADSP_LIBRARY_PATH=/root/qnn/skel
. /root/qnn/require_quiet.sh

M=${1:?model}; REPS=${2:-5}; K=${3:-200}
BIN=/root/qnn/batch
B=/root/qnn/bin
# BATCH must not be inferred from a filename (M34). This was:
#     N=$(echo "$M" | sed 's/.*_b\([0-9]*\)_.*/\1/')
# a plain s/// which ECHOES THE WHOLE INPUT UNCHANGED when the pattern does not match.
# The batch-curve binaries are named v8n_b1_o12_sp (trailing underscore, matches); the
# fp16 binaries are named v8n_f16_b1 (no trailing underscore, does NOT match). N therefore
# became the literal string "v8n_f16_b1", which selected the nonexistent input directory
# gate_u8_bv8n_f16_b1 AND emitted  "batch":v8n_f16_b1  -- unquoted, INVALID JSON, silently.
# Kyle's rule: do not be cute formalising a name string that the producers never
# formalised. Accept an explicit BATCH, infer only as a fallback, and REFUSE rather than
# guess.
N=${BATCH:-}
if [ -z "$N" ]; then
  N=$(printf '%s' "$M" | sed -n 's/.*_b\([0-9][0-9]*\)\(_.*\)\?$/\1/p')
fi
case "$N" in
  ''|*[!0-9]*)
    printf '{"status":"CANNOT_RUN","why":"batch not determinable from model name %s and BATCH not set (M34: never derive a machine value from a human-editable string)","model":"%s"}\n' "$M" "$M"
    exit 8 ;;
esac
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
# ---- RUN PROVENANCE TOKEN ---------------------------------------------------
# Kyle's question, 2026-08-19: "should we sign a result file so we know it wasn't
# copied from somewhere else?" Yes -- but what matters is not the signature, it is
# what the signature is taken OVER. A signature proves integrity; it cannot make a
# fabricated number true. What DOES defeat copying is binding each run to something
# it alone can produce:
#   boot_id      changes every boot        -> a file from a previous boot is visible
#   monotonic ns cannot repeat on a board  -> two runs can never share it
#   urandom      unpredictable             -> cannot be guessed or pre-computed
# Concatenated and hashed, that is a RUN ID. Reusing evidence means reusing a run id,
# and duplicate run ids are trivially detectable. This is chain of custody, not
# cryptography, and it is the right tool for the actual threat: not a malicious
# attacker, but a tired engineer at 2am copying a file to make a red check go green.
# per-UNIT board identity: hostname and model are shared across units (M30)
. "$(dirname "$0")/board_identity.sh" 2>/dev/null || . /root/qnn/board_identity.sh 2>/dev/null || true
BOARD_ID_JSON=$(board_identity 2>/dev/null || echo '{}')
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown)
RUN_ID=$(printf '%s|%s|%s' "$BOOT_ID" "$(date +%s%N)" "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" | sha256sum | cut -c1-32)

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

LOG=/root/qnn/evidence/${M}_${STAMP}.log
OUT=/root/qnn/evidence/${M}_${STAMP}.json
mkdir -p /root/qnn/evidence

envelope() {   # M13: a number without its power/clock/thermal state is not comparable
  printf '{"power_mode":"%s","cpu_governor":"%s","cpu_max_khz":"%s","soc_temp_mC":"%s","accel_perf_mode":"burst"}' \
    "burst(HTP)" \
    "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)" \
    "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null || echo unknown)" \
    "$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo unknown)"
}

tenancy() {   # accel procs, loadavg, free MB -- the environment AT the measurement
  printf '{"accel_procs":%s,"loadavg":"%s","mem_free_mb":%s,"utc":"%s"}' \
    "$(pgrep -x qnn-net-run | wc -l)" \
    "$(cut -d' ' -f1-3 /proc/loadavg)" \
    "$(awk '/MemAvailable/{printf "%d",$2/1024}' /proc/meminfo)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

{
  echo "=== collect_evidence $M reps=$REPS K=$K $STAMP"
  require_quiet_board || { echo "REFUSED: board not quiet"; exit 9; }
} >"$LOG" 2>&1
[ $? -eq 9 ] && { echo '{"status":"CANNOT_RUN","why":"board not quiet (M10)"}' >"$OUT"; cat "$OUT"; exit 9; }

start_stimulus

# ---- M41 PORCH ---------------------------------------------------------------
# The porch protocol existed as a standalone script that NOTHING CALLED. `require_quiet`
# is only half the contract: entry-only, and blind to disk, /tmp and /dev/shm -- the
# surfaces that have actually cost this fleet gigabytes. One predicate, run twice.
. "$(dirname "$0")/porch.sh" 2>/dev/null || . "/root/qnn/porch.sh" 2>/dev/null || true
PORCH=1; command -v porch_front >/dev/null 2>&1 || PORCH=0
ACCEL_PROC=qnn-net-run
if [ "$PORCH" = 1 ]; then
  if ! porch_front "$ACCEL_PROC"; then
    printf '{"status":"CANNOT_RUN","why":"front porch refused: board not idle (M41)","porch_entry":%s,"label":"%s"}\n' \
      "${PORCH_ENTRY:-null}" "$M" > "$OUT"
    cat "$OUT"; exit 9
  fi
  # back porch must run even if the benchmark dies, or a crash leaves the board dirty
  # AND unattributed -- the exact pair the protocol exists to prevent.
  trap 'porch_back "$ACCEL_PROC" >/dev/null 2>&1 || true' EXIT INT TERM
fi

TEN_BEFORE=$(tenancy)
# The input directory encodes a DTYPE (gate_u8_*). An fp16 graph needs fp16 input; feeding
# it the u8 set produced a run with no profiling output and status RUNTIME_ERROR -- which is
# at least loud. Allow an explicit override and check the file exists BEFORE running.
INDIR=${INPUT_DIR:-$BIN/gate_u8_b${N}}
if [ ! -r "$INDIR/0000.raw" ]; then
  printf '{"status":"CANNOT_RUN","why":"input tensor %s/0000.raw not readable; set INPUT_DIR for non-u8 graphs","model":"%s"}\n' "$INDIR" "$M"
  exit 8
fi
ls $INDIR/0000.raw > /dev/shm/ev_$M.txt 2>>"$LOG"

ACC=""; WALL=""; RC_ALL=0
i=1
while [ $i -le "$REPS" ]; do
  rm -rf /dev/shm/EV_$M
  T0=$(date +%s%3N)
  $B/qnn-net-run --backend /root/qnn/lib/libQnnHtp.so --retrieve_context $BIN/$M.bin \
    --input_list /dev/shm/ev_$M.txt --output_dir /dev/shm/EV_$M --keep_num_outputs 1 \
    --num_inferences $K --use_native_input_files \
    --device_options "device_id:0;core_id:0" \
    --config_file /root/qnn/rm_ext_burst_d0.json \
    --profiling_level basic --log_level error >>"$LOG" 2>&1
  RC=$?; T1=$(date +%s%3N)
  [ $RC -ne 0 ] && RC_ALL=$RC
  A=$($B/qnn-profile-viewer --input_log /dev/shm/EV_$M/qnn-profiling-data_0.log 2>>"$LOG" \
      | awk '/Backend \(Accelerator \(execute\) time\)/{print $(NF-1); exit}')
  [ -n "$A" ] && ACC="$ACC${ACC:+,}$(awk -v a=$A -v n=$N 'BEGIN{printf "%.2f",a/n}')"
  WALL="$WALL${WALL:+,}$((T1-T0))"
  i=$((i+1))
done
TEN_AFTER=$(tenancy)
stop_stimulus
trap - EXIT INT TERM
PORCH_JSON=null
[ "$PORCH" = 1 ] && PORCH_JSON=$(porch_back "$ACCEL_PROC")

# M12: a runtime failure is NOT a measurement. Say so, and carry no value.
STATUS=OK; [ $RC_ALL -ne 0 ] && STATUS=RUNTIME_ERROR
[ -z "$ACC" ] && STATUS=RUNTIME_ERROR

cat > "$OUT" <<EOF
{"model":"$M","batch":$N,"host":"iq9",
 "board_identity":$BOARD_ID_JSON,"status":"$STATUS",
 "run_provenance":{"run_id":"$RUN_ID","boot_id":"$BOOT_ID",
   "_what_this_proves":"this evidence was produced by ONE execution on this boot; a duplicate run_id across evidence files means a file was copied, and a content_sha256 mismatch means it was edited after the fact",
   "_what_this_does_NOT_prove":"that the numbers are true. A signature over a fabricated measurement is a valid signature over a fabricated measurement. This moves the trust boundary to the person running the harness and makes violations attributable; it does not remove the boundary."},
 "log":"$LOG","utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "artifact":{"path":"$BIN/$M.bin","md5":"$(md5sum $BIN/$M.bin | cut -d' ' -f1)"},
 "config_requested":{"vtcm_mb":8,"O":3,"dsp_arch":"v73","core_id":0,"burst":true,"batch":$N,
   "num_inferences":$K},
 "measurement":{"metric":"accelerator_execute_time_per_image_us",
   "includes":"device compute only; host pre/post and dvapi round-trip EXCLUDED (M14)",
   "accel_us_per_image":[$ACC],"wall_ms_per_rep":[$WALL],"reps":$REPS,"K":$K},
 "envelope":$(envelope),
 "environment":$(env_declared_json),
 "tenancy":{"before":$TEN_BEFORE,"after":$TEN_AFTER},
 "porch":${PORCH_JSON:-null},
 "rc":$RC_ALL}
EOF
# content hash over the evidence body -- detects post-hoc editing
CH=$(sha256sum "$OUT" | cut -c1-64)
python3 - "$OUT" "$CH" <<'PY' 2>/dev/null || true
import json,sys
p,ch=sys.argv[1],sys.argv[2]
d=json.load(open(p)); d["run_provenance"]["content_sha256_of_body"]=ch
json.dump(d,open(p,"w"),indent=1)
PY
cat "$OUT"
