#!/bin/bash
# The one way to verify. Runs every checker, logs every trip to the campaign log.
#
# Built because an audit found builder_guard and supersession_linter existed, were
# reporting real defects, and were wired into NOTHING -- no build, no CI, no hook.
# A checker nobody runs is a checker that does not exist.
cd "$(dirname "$0")"
FAIL=0
echo "═══ VERIFY ═══"
for t in "deliverable_check:the sent artifacts" \
         "builder_guard:builders read their declared source" \
         "supersession_linter:no retracted value reaches a reader" \
         "void_check:no DEAD value is asserted as data" \
         "discrepancy_check:one live value per measurand (M36/M37)" \
         "context_and_caveat_check:shared context + caveat debt (M35/M19)"; do
  name="${t%%:*}"; desc="${t#*:}"
  printf "\n── %s — %s\n" "$name" "$desc"
  python3 "tools/$name.py" 2>&1 | tail -3
  [ "${PIPESTATUS[0]}" != "0" ] && FAIL=1
done
# An adversarial review on 2026-08-18 put a fabricated 160,000-IPS record with no
# gate, log or artifact through this block and verify.sh printed ALL CLEAR: the
# original loop piped to `tail` and never consulted PIPESTATUS. It also ran zero
# times, because campaign/records/ does not exist -- a silently-skipped check that
# reports success is worse than no check.
echo ""
echo "── frozen_guard — shipped artifacts have not silently diverged"
python3 tools/frozen_guard.py || true
printf "\n── record_schema — measurement records defend themselves\n"
if ls campaign/records/*.json >/dev/null 2>&1; then
  for f in campaign/records/*.json; do
    python3 tools/record_schema.py "$f" 2>&1 | tail -2
    [ "${PIPESTATUS[0]}" != "0" ] && FAIL=1
  done
else
  echo "  NO RECORDS FOUND in campaign/records/ — every MEASURED claim is supposed to"
  echo "  emit one. An empty record store means this check is inert, not that it passed."
  echo "  (not failing the build yet: Phase 0 has not backfilled records)"
fi

printf "\n── self-tests — the checkers' own negative controls\n"
for st in tools/void_check tools/discrepancy_check tools/artifact_fingerprint \
          tools/run_gate tools/emit_records tools/context_and_caveat_check \
          harness/gate_map harness/gate_llm; do
  python3 "$st.py" --self-test >/dev/null 2>&1 \
    && echo "  $(basename $st): self-test PASSES" \
    || { echo "  $(basename $st): SELF-TEST FAILING — the checker itself is broken"; FAIL=1; }
done
printf "\n═══ %s ═══\n" "$([ $FAIL = 0 ] && echo 'ALL CLEAR' || echo 'BLOCKED — do not send')"
exit $FAIL
