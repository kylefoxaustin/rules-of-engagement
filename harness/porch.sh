#!/bin/sh
# PORCH PROTOCOL — M41. Front porch / house / back porch.
#
# Kyle's architecture, 2026-08-20:
#   1. front porch  peek at the board, confirm idle. Carry the COMPLETE payload and the
#                   instructions: how to set up, what to measure, how to record it, the
#                   output format -- and most importantly how to remove it and all traces.
#   2. the house    the actual run, watched so it cannot just sit there.
#   3. back porch   follow the teardown the front porch declared, then run the SAME idle
#                   test the front porch ran.
#
# The symmetry is the point. One predicate, run twice. If every run starts clean and ends
# clean, a dirty board has exactly one owner and the log says who. Without the exit check,
# residue is discovered by the NEXT run -- late, and attributed to the wrong person.
#
# Two incidents paid for this file:
#   * two orphaned llama-cli survived a killed parent for 43 and 59 min, pinned two cores
#     of a Thor, and blocked every later measurement.
#   * two orphaned qnn-net-run in uninterruptible sleep wedged an IQ-9075 into needing a
#     physical power cycle.
# Both were caught by a later run's ENTRY check. An exit check catches them immediately.
#
# THE WATCHDOG IS EXTERNAL, and that is not a preference. When the IQ-9075's DSP wedged,
# every on-board observer wedged with it. A watchdog that shares fate with the thing it
# watches is decoration.

# ---- the ONE idle predicate. Used by both porches. --------------------------
# Takes an optional accelerator-process name; always checks load and residue.
porch_idle_check() {
  _accel_proc=${1:-}
  _fail=""
  if [ -n "$_accel_proc" ]; then
    _n=$(pgrep -x "$_accel_proc" 2>/dev/null | wc -l | tr -d ' ')
    [ "$_n" -gt 0 ] && _fail="$_fail ${_n}x${_accel_proc}"
    _orph=$(ps -eo ppid,comm 2>/dev/null | awk -v c="$_accel_proc" '$1==1 && $2==c' | wc -l | tr -d ' ')
    [ "$_orph" -gt 0 ] && _fail="$_fail ${_orph}x${_accel_proc}-orphaned-to-init"
  fi
  _la=$(awk '{print $1}' /proc/loadavg)
  _nc=$(nproc 2>/dev/null || echo 1)
  _pct=$(awk -v l="$_la" -v n="$_nc" 'BEGIN{printf "%d",100*l/n}')
  # Linux loadavg COUNTS UNINTERRUPTIBLE (D-state) TASKS, so it conflates two states a
  # benchmark must tell apart: CPUs actually contended, versus a kernel quietly finishing
  # writeback with every core free. Thor sat at load 2.9 on 14 cores with procs_running=1
  # -- the whole figure was kworker/u28 ext4-rsv-conversion plus three blocked
  # kworker/*+events. Killing the browser moved it by 0.3, because the browser was never
  # the cause. Report both, and judge contention on the RUNNABLE count.
  _run=$(awk '/^procs_running/{print $2}' /proc/stat 2>/dev/null)
  _dstate=$(ps -eo stat= 2>/dev/null | grep -c '^D' || true)
  _dstate=$(printf '%s' "${_dstate:-0}" | head -1)
  _runpct=$(awk -v r="${_run:-0}" -v n="$_nc" 'BEGIN{printf "%d",100*r/n}')
  # runnable contention is the blocking condition; a high loadavg that is purely D-state
  # is reported but does NOT refuse, because refusing on it would block every board that
  # happens to be flushing a file.
  [ "${_runpct:-0}" -ge 50 ] && _fail="$_fail runnable=${_runpct}%"
  [ "$_pct" -ge 50 ] && [ "${_runpct:-0}" -lt 50 ] && \
    echo "note: loadavg ${_pct}% but only ${_runpct}% runnable (${_dstate} in D state) — background I/O, not CPU contention" >&2
  # RESIDUE. The first version grepped /dev/shm for a hardcoded prefix list
  # (R_|EV_|LA_|LAT|SMOKE|AB_|X_). It found NOTHING while 158 MB of this harness's own
  # residue sat there in 33 files across FIVE naming conventions -- LA12_, la_, lat_,
  # lat1_, ev_, ab_in -- none of which the list matched. The porch reported an IQ-9075
  # clean while it was dirty, which is worse than not checking: it launders the board.
  #
  # The fix is NOT to add LA12_ to the list. That is whack-a-mole with the same defect,
  # and it violates the standing rule about not formalising a name string that the
  # producers never formalised. A residue check must not depend on the name of the
  # residue. So: SIZE, not names. An idle board's /dev/shm is near-empty; anything
  # occupying real space there is somebody's leftover regardless of what it is called.
  # (The exit side is stronger still -- see the byte delta in porch_back.)
  _shm_mb=$(du -sm /dev/shm 2>/dev/null | awk '{print $1}')
  _shm_n=$(ls -A /dev/shm 2>/dev/null | wc -l | tr -d ' ')
  [ "${_shm_mb:-0}" -gt "${PORCH_SHM_MB_MAX:-8}" ] && _fail="$_fail shm=${_shm_mb}MB_in_${_shm_n}_entries"
  # DISK RESIDUE. Benchmarks have left GIGABYTES of /tmp behind. Rather than whitelist
  # paths (which only finds what you thought of), record free space and compare entry to
  # exit -- that catches a leftover file ANYWHERE, including ones we did not anticipate.
  # An IQ-9075 in this fleet is currently at 90% full, so this is not hypothetical.
  _free_kb=$(df -Pk / 2>/dev/null | awk 'NR==2{print $4}')
  _use_pct=$(df -Pk / 2>/dev/null | awk 'NR==2{gsub(/%/,"",$5); print $5}')
  [ "${_use_pct:-0}" -ge 90 ] && _fail="$_fail disk_${_use_pct}%_full"
  _tmp_mb=$(du -sm /tmp 2>/dev/null | awk '{print $1}')
  [ "${_tmp_mb:-0}" -gt "${PORCH_TMP_MB_MAX:-256}" ] && _fail="$_fail tmp=${_tmp_mb}MB"
  if [ -n "$_fail" ]; then
    printf '{"idle":false,"reasons":"%s","loadavg_pct":%s,"disk_free_kb":%s,"disk_used_pct":%s,"tmp_mb":%s,"shm_mb":%s,"utc":"%s"}' \
      "$(echo $_fail)" "$_pct" "${_free_kb:-0}" "${_use_pct:-0}" "${_tmp_mb:-0}" "${_shm_mb:-0}" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    return 1
  fi
  printf '{"idle":true,"loadavg_pct":%s,"runnable_pct":%s,"d_state":%s,"disk_free_kb":%s,"disk_used_pct":%s,"tmp_mb":%s,"shm_mb":%s,"utc":"%s"}' \
    "$_pct" "${_runpct:-0}" "${_dstate:-0}" "${_free_kb:-0}" "${_use_pct:-0}" "${_tmp_mb:-0}" "${_shm_mb:-0}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  return 0
}

# ---- front porch ------------------------------------------------------------
# Declares the teardown plan BEFORE the run. A teardown written afterwards removes only
# what its author remembers creating.
porch_front() {
  _accel_proc=${1:-}
  PORCH_ENTRY=$(porch_idle_check "$_accel_proc")
  PORCH_ENTRY_OK=$?
  PORCH_TEARDOWN_PLAN="${PORCH_TEARDOWN_PLAN:-}"
  [ $PORCH_ENTRY_OK -ne 0 ] && {
    echo "FRONT PORCH REFUSES: board not idle -> $PORCH_ENTRY" >&2
    return 1
  }
  echo "front porch: board idle; teardown plan declared" >&2
  return 0
}

# Register a thing to remove. Call as you create things, not at the end.
porch_will_remove() { PORCH_TEARDOWN_PLAN="$PORCH_TEARDOWN_PLAN $1"; }

# ---- back porch -------------------------------------------------------------
porch_back() {
  _accel_proc=${1:-}
  _removed=""
  for _t in $PORCH_TEARDOWN_PLAN; do
    if [ -e "$_t" ]; then rm -rf "$_t" 2>/dev/null && _removed="$_removed $_t"; fi
  done
  # never SIGKILL blind: SIGTERM, then check for D state before escalating (M29)
  if [ -n "$_accel_proc" ]; then
    for _p in $(pgrep -x "$_accel_proc" 2>/dev/null); do kill -TERM "$_p" 2>/dev/null; done
    sleep 2
    for _p in $(pgrep -x "$_accel_proc" 2>/dev/null); do
      _st=$(ps -o stat= -p "$_p" 2>/dev/null | tr -d ' ')
      case "$_st" in
        D*) echo "back porch: $_accel_proc $_p in D state -- device reset needed, NOT another signal (M29)" >&2 ;;
        *)  kill -KILL "$_p" 2>/dev/null ;;
      esac
    done
  fi
  PORCH_EXIT=$(porch_idle_check "$_accel_proc")
  PORCH_EXIT_OK=$?
  # DISK DELTA: free space at entry vs exit. A benchmark that consumed disk and did not
  # give it back left files somewhere, and the whole point of measuring the delta rather
  # than scanning known paths is that it finds the ones nobody predicted.
  _f0=$(echo "$PORCH_ENTRY" | sed -n 's/.*"disk_free_kb":\([0-9]*\).*/\1/p')
  _f1=$(echo "$PORCH_EXIT"  | sed -n 's/.*"disk_free_kb":\([0-9]*\).*/\1/p')
  DISK_DELTA_MB=0
  if [ -n "$_f0" ] && [ -n "$_f1" ]; then
    DISK_DELTA_MB=$(awk -v a="$_f0" -v b="$_f1" 'BEGIN{printf "%d",(a-b)/1024}')
  fi
  # SHM DELTA. /dev/shm is tmpfs -- it does NOT consume "/" free space, so the disk
  # delta above is blind to it. That is precisely how 158 MB of harness residue survived
  # both the pattern check and the byte check simultaneously. Measure it separately.
  _s0=$(echo "$PORCH_ENTRY" | sed -n 's/.*"shm_mb":\([0-9]*\).*/\1/p')
  _s1=$(echo "$PORCH_EXIT"  | sed -n 's/.*"shm_mb":\([0-9]*\).*/\1/p')
  SHM_DELTA_MB=0
  if [ -n "$_s0" ] && [ -n "$_s1" ]; then
    SHM_DELTA_MB=$(awk -v a="$_s0" -v b="$_s1" 'BEGIN{printf "%d",b-a}')
  fi
  if [ "${SHM_DELTA_MB:-0}" -gt 8 ]; then
    echo "BACK PORCH: /dev/shm grew ${SHM_DELTA_MB} MB -- this run left shared memory behind" >&2
    PORCH_EXIT_OK=1
  fi
  if [ "${DISK_DELTA_MB:-0}" -gt 100 ]; then
    echo "BACK PORCH: ${DISK_DELTA_MB} MB of disk NOT returned -- this run left files behind" >&2
    PORCH_EXIT_OK=1
  fi
  if [ $PORCH_EXIT_OK -ne 0 ]; then
    echo "BACK PORCH: DIRTY EXIT -> $PORCH_EXIT" >&2
    echo "  This run left the board dirty. Its numbers may still be valid, but the residue" >&2
    echo "  is a confound for everything that follows, and it is attributable to THIS run." >&2
  fi
  printf '{"entry":%s,"teardown":{"planned":"%s","removed":"%s"},"exit":%s,"disk_delta_mb":%s,"shm_delta_mb":%s,"clean_exit":%s}' \
    "$PORCH_ENTRY" "$(echo $PORCH_TEARDOWN_PLAN)" "$(echo $_removed)" "$PORCH_EXIT" \
    "${DISK_DELTA_MB:-0}" "${SHM_DELTA_MB:-0}" "$([ $PORCH_EXIT_OK -eq 0 ] && echo true || echo false)"
}

# ---- self-test ---------------------------------------------------------------
# Every case is a way this file has ALREADY been wrong on a real board.
porch_self_test() {
  _d=$(mktemp -d); _bad=0
  _chk() {  # name, expect_caught(0|1), actual_caught(0|1)
    if [ "$2" = "$3" ]; then echo "  [ok ] $1"; else echo "  [BUG] $1"; _bad=$((_bad+1)); fi
  }
  # THE REAL MISS: 33 files, 158 MB, named LA12_/la_/lat_/lat1_/ev_/ab_in -- the old
  # prefix list matched NONE of them and the porch called the board clean.
  _before=$(du -sm /dev/shm 2>/dev/null | awk '{print $1}')
  dd if=/dev/zero of=/dev/shm/LA12_v8l_b16_o12_sp bs=1M count=32 2>/dev/null
  _out=$(porch_idle_check ""); _caught=$(echo "$_out" | grep -c '"idle":false')
  _chk "residue whose name matches NO known prefix is still caught (size, not names)" 1 "$_caught"
  rm -f /dev/shm/LA12_v8l_b16_o12_sp
  # Assert on the shm REASON, not on overall idle: an unrelated dirty surface on the
  # test host (skippy had 32 GB in /tmp) must not mask or fake this case.
  _out=$(porch_idle_check ""); _noshm=$(echo "$_out" | grep -c 'shm=')
  _chk "no shm complaint once the residue is removed" 0 "$_noshm"
  # shm is tmpfs: prove the "/" disk delta alone would NOT have seen it
  _f=$(df -Pk / | awk 'NR==2{print $4}')
  dd if=/dev/zero of=/dev/shm/anything_at_all bs=1M count=32 2>/dev/null
  _f2=$(df -Pk / | awk 'NR==2{print $4}')
  _dd=$(awk -v a="$_f" -v b="$_f2" 'BEGIN{printf "%d",(a-b)/1024}')
  _chk "tmpfs residue is invisible to the / disk delta (why shm_delta exists)" 1 \
       "$([ "${_dd:-0}" -lt 8 ] && echo 1 || echo 0)"
  rm -f /dev/shm/anything_at_all
  rmdir "$_d" 2>/dev/null
  echo; echo "$((3-_bad))/3 self-test cases pass"
  return $_bad
}

# Guard matches porch*.sh, not the exact string "porch.sh". Copying this file to a board
# as porch_check.sh made it exit 0 having done NOTHING -- a check that silently no-ops
# when renamed is worse than one that errors, because rc=0 reads as "board is clean".
case "${0##*/}" in porch*.sh|porch*)
  case "${1:-}" in
    --self-test) porch_self_test; exit $? ;;
    *) porch_idle_check "${1:-}"; echo ;;
  esac
  ;;
esac
