#!/bin/bash
# LLM EVIDENCE COLLECTOR — the third adapter, and the first NON-CNN workload.
#
# The two prior adapters (Hexagon qnn-net-run, TensorRT trtexec) both measured
# images/second on a vision model. This one measures tokens/second on a language
# model, which is the real test of whether the evidence contract is workload-agnostic
# or merely board-agnostic.
#
# What stays identical (and therefore was never CNN-specific):
#   run provenance token, board + accelerator identity, tenancy before/after, power
#   envelope, artifact md5, replicate capture, status distinct from gate (M12),
#   explicit statement of what the timing includes (M14).
#
# What changes:
#   1. runner        qnn-net-run / trtexec   ->  llama-bench (throughput) + llama-cli (gate)
#   2. metric        us/image                ->  tok/s, separately for PREFILL and DECODE
#   3. gate          COCO mAP                ->  needle recovery, graded from a run in the
#                                                same session (gate_llm.py tier 1)
#   4. plausibility  min time per inference  ->  MAX tok/s from the memory-bandwidth roofline
#
# (4) is a genuine addition. For a CNN the impossible direction is "too fast per image".
# For decode the bound is physics: tokens/s cannot exceed DDR_BW / bytes_per_token, because
# every token streams the weights. A decode figure above its roofline did not happen --
# and per the directional-bias law, that is exactly the error nobody questions.
#
# Usage: collect_evidence_llm.sh <gguf> <label> [reps] [ddr_bw_GBs]
set -u
GGUF=${1:?gguf path}
LABEL=${2:?label e.g. qwen3-8b-q4km}
REPS=${3:-3}
DDR_BW_GBS=${4:-0}          # measured DDR bandwidth; 0 = roofline check skipped, loudly
LLAMA_BENCH=${LLAMA_BENCH:-$(command -v llama-bench || echo /root/llama/llama-bench)}
LLAMA_CLI=${LLAMA_CLI:-$(command -v llama-cli || echo /root/llama/llama-cli)}
THREADS=${THREADS:-6}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTDIR=${OUTDIR:-$HOME/evidence}; mkdir -p "$OUTDIR"
LOG=$OUTDIR/${LABEL}_${STAMP}.log
OUT=$OUTDIR/${LABEL}_${STAMP}.json

. "$(dirname "$0")/board_identity.sh" 2>/dev/null || . "$HOME/board_identity.sh" 2>/dev/null || true
BOARD_ID_JSON=$(board_identity 2>/dev/null || echo '{}')
ACCEL_ID_JSON=$(accelerator_identity 2>/dev/null || echo '{}')
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


busy_procs() { pgrep -x llama-bench 2>/dev/null | wc -l | tr -d ' '; }
require_quiet() {
  local n; n=$(busy_procs)
  [ "$n" -gt 0 ] && { echo "REFUSING: $n llama-bench already running" >&2; return 1; }
  local la ncpu pct; la=$(awk '{print $1}' /proc/loadavg); ncpu=$(nproc 2>/dev/null || echo 1)
  pct=$(awk -v l="$la" -v n="$ncpu" 'BEGIN{printf "%d",100*l/n}')
  [ "$pct" -ge 50 ] && { echo "REFUSING: load $la on $ncpu cores = ${pct}%" >&2; return 1; }
  echo "board quiet: loadavg $la on $ncpu cores (${pct}%)"
}
envelope() {
  printf '{"power_mode":"%s","cpu_governor":"%s","threads":%s,"soc_temp_mC":"%s"}' \
    "$(nvpmodel -q 2>/dev/null | grep -A1 'Power Mode' | tail -1 | tr -d '\n' || echo default)" \
    "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)" \
    "$THREADS" \
    "$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo unknown)"
}
tenancy() {
  printf '{"llama_procs":%s,"loadavg":"%s","mem_free_mb":%s,"utc":"%s"}' \
    "$(busy_procs)" "$(cut -d' ' -f1-3 /proc/loadavg)" \
    "$(awk '/MemAvailable/{printf "%d",$2/1024}' /proc/meminfo)" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

{ echo "=== collect_evidence_llm $LABEL reps=$REPS $STAMP"; require_quiet; } >"$LOG" 2>&1
if ! require_quiet >/dev/null 2>&1; then
  printf '{"status":"CANNOT_RUN","why":"board not quiet (M10)","label":"%s"}\n' "$LABEL" >"$OUT"
  cat "$OUT"; exit 9
fi

start_stimulus

# ---- M41 PORCH ---------------------------------------------------------------
# The porch protocol existed as a standalone script that NOTHING CALLED. `require_quiet`
# is only half the contract: entry-only, and blind to disk, /tmp and /dev/shm -- the
# surfaces that have actually cost this fleet gigabytes. One predicate, run twice.
. "$(dirname "$0")/porch.sh" 2>/dev/null || . "$HOME/porch.sh" 2>/dev/null || true
PORCH=1; command -v porch_front >/dev/null 2>&1 || PORCH=0
ACCEL_PROC=llama-cli
if [ "$PORCH" = 1 ]; then
  if ! porch_front "$ACCEL_PROC"; then
    printf '{"status":"CANNOT_RUN","why":"front porch refused: board not idle (M41)","porch_entry":%s,"label":"%s"}\n' \
      "${PORCH_ENTRY:-null}" "$LABEL" > "$OUT"
    cat "$OUT"; exit 9
  fi
  # back porch must run even if the benchmark dies, or a crash leaves the board dirty
  # AND unattributed -- the exact pair the protocol exists to prevent.
  trap 'porch_back "$ACCEL_PROC" >/dev/null 2>&1 || true' EXIT INT TERM
fi

TEN_BEFORE=$(tenancy)
PP=""; TG=""; RC_ALL=0
for _ in $(seq 1 "$REPS"); do
  O=$(timeout 600 "$LLAMA_BENCH" -m "$GGUF" -p 512 -n 128 -t "$THREADS" -r 1 2>&1)
  RC=$?; [ $RC -ne 0 ] && RC_ALL=$RC
  echo "$O" >>"$LOG"
  # llama-bench table: "pp512" and "tg128" rows carry tok/s in the last numeric column
  # The llama-bench cell is "1350.39 ± 0.00". Stripping all non-numerics glued the value
  # to its stddev and produced "1350.390.00" -- a malformed number that json.load accepts
  # as a string and every downstream consumer would have silently mishandled. Take the
  # FIRST numeric token only.
  P=$(echo "$O" | awk -F'|' '/pp512/{n=split($(NF-1),a,"[^0-9.]"); for(i=1;i<=n;i++) if(a[i]!=""){print a[i]; exit}}')
  T=$(echo "$O" | awk -F'|' '/tg128/{n=split($(NF-1),a,"[^0-9.]"); for(i=1;i<=n;i++) if(a[i]!=""){print a[i]; exit}}')
  [ -n "$P" ] && PP="$PP${PP:+,}$P"
  [ -n "$T" ] && TG="$TG${TG:+,}$T"
done

# ---- GATE (M1): correctness from a run in the SAME session as the timing ------
NEEDLE=$((RANDOM % 90000 + 10000))
# A raw -p prompt on an INSTRUCT model produced a degenerate "> > > >" loop at full
# speed -- the exact broken-is-faster case. Instruct models need their chat template.
GATE_PROMPT="<|im_start|>user
The access code is ${NEEDLE}. What is the access code? Answer with the number only.<|im_end|>
<|im_start|>assistant
"
# BOUNDED. An unbounded gate run orphaned TWO llama-cli processes on Thor for 43 and 59
# minutes after an ssh timeout killed the parent -- they pinned two cores each, pushed
# loadavg to 7.10/14 = exactly the 50% refusal threshold, and blocked every subsequent
# measurement. The quiet guard caught it, which is the system working; but a step that
# can run forever will eventually run forever. Same orphan class as the IQ-9075 kill -9.
GATE_OUT=$(timeout 180 "$LLAMA_CLI" -m "$GGUF" -p "$GATE_PROMPT" -n 24 -t "$THREADS" \
           --temp 0 2>/dev/null | tr -d '\n' | tail -c 400)
GATE_RC=$?
[ $GATE_RC -eq 124 ] && GATE_OUT="TIMEOUT after 180s — gate could not complete"
echo "GATE needle=$NEEDLE out=$GATE_OUT" >>"$LOG"
case "$GATE_OUT" in *"$NEEDLE"*) GATE_PASS=true;; *) GATE_PASS=false;; esac

TEN_AFTER=$(tenancy)
stop_stimulus
trap - EXIT INT TERM
PORCH_JSON=null
[ "$PORCH" = 1 ] && PORCH_JSON=$(porch_back "$ACCEL_PROC")
STATUS=OK
[ $RC_ALL -ne 0 ] && STATUS=RUNTIME_ERROR
[ -z "$TG" ] && STATUS=RUNTIME_ERROR

MODEL_BYTES=$(stat -c%s "$GGUF")
# roofline: decode streams the weights once per token, so tok/s <= DDR_BW / model_bytes
ROOFLINE=$(awk -v b="$DDR_BW_GBS" -v m="$MODEL_BYTES" 'BEGIN{ if(b>0 && m>0) printf "%.2f", b*1e9/m; else print "null" }')

cat > "$OUT" <<EOF
{"model":"$LABEL","workload":"llm","batch":1,"host":"$(hostname -s)","status":"$STATUS",
 "board_identity":$BOARD_ID_JSON,
 "accelerator_identity":$ACCEL_ID_JSON,
 "run_provenance":{"run_id":"$RUN_ID","boot_id":"$BOOT_ID",
   "_what_this_proves":"one execution on this boot; a duplicate run_id means a copied file",
   "_what_this_does_NOT_prove":"that the numbers are true"},
 "log":"$LOG","utc":"$(date -u +%Y-%m-%dT%H:%M:%SZ)",
 "artifact":{"path":"$GGUF","md5":"$(md5sum "$GGUF" | cut -d' ' -f1)","bytes":$MODEL_BYTES},
 "config_requested":{"quant":"from-filename","threads":$THREADS,"prefill_tokens":512,
   "decode_tokens":128,"batch":1},
 "measurement":{"metric":"tokens_per_second",
   "includes":"llama-bench steady-state; model load EXCLUDED (M14)",
   "prefill_tps":[$PP],"decode_tps":[$TG],"reps":$REPS},
 "roofline":{"ddr_bw_GBs":$DDR_BW_GBS,"max_decode_tps":$ROOFLINE,
   "_meaning":"decode streams the weights once per token; a decode rate above this did not happen (M28, upper bound)"},
 "gate":{"kind":"needle","status":"$([ "$GATE_PASS" = true ] && echo PASS || echo FAIL)",
   "needle":"$NEEDLE","answer":"$(echo "$GATE_OUT" | sed 's/"/\\"/g' | cut -c1-160)",
   "tier":1,
   "_limit":"tier 1 supports 'this configuration ran'. It does NOT support a cross-precision speed claim -- that needs a task-accuracy score against a reference artifact (M31)"},
 "envelope":$(envelope),
 "environment":$(env_declared_json),
 "tenancy":{"before":$TEN_BEFORE,"after":$TEN_AFTER},
 "porch":${PORCH_JSON:-null},
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
