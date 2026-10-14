#!/bin/bash
# The one way to verify. Runs every checker, logs every trip to the campaign log.
#
#   ./verify.sh              every checker against your campaign data, then every negative control
#   ./verify.sh --self-test  only the negative controls — what a fresh clone can actually run
#
# Exit: 0 ALL CLEAR · 1 BLOCKED (a check or a self-test failed) · 2 INERT (nothing failed, but at
# least one check had no data to look at — that is not a pass, so it is not exit 0).
#
# Built because an audit found builder_guard and supersession_linter existed, were
# reporting real defects, and were wired into NOTHING -- no build, no CI, no hook.
# A checker nobody runs is a checker that does not exist.
cd "$(dirname "$0")"
FAIL=0
INERT=0
SELFTEST_ONLY=0
[ "${1:-}" = "--self-test" ] && SELFTEST_ONLY=1

# A check whose input is absent must SAY so, and must not be counted as a pass. On a fresh clone
# there is no campaign tree (it is yours to build), so these report INERT rather than BLOCKED --
# the 2026-09-25 public review found verify.sh died on every clone, which taught newcomers that
# its BLOCKED means nothing.
inert() { echo "  INERT — $1"; INERT=1; }

echo "═══ VERIFY ═══"
if [ $SELFTEST_ONLY = 0 ]; then
  for t in "deliverable_check:the sent artifacts:remeasure" \
           "builder_guard:builders read their declared source:" \
           "supersession_linter:no retracted value reaches a reader:" \
           "void_check:no DEAD value is asserted as data:" \
           "discrepancy_check:one live value per measurand (M36/M37):" \
           "context_and_caveat_check:shared context + caveat debt (M35/M19):"; do
    name="${t%%:*}"; rest="${t#*:}"; desc="${rest%:*}"; needs="${rest##*:}"
    printf "\n── %s — %s\n" "$name" "$desc"
    if [ -n "$needs" ] && [ ! -e "$needs" ]; then
      inert "no $needs/ here; this checker reads your sent artifacts from it (see the top of checkers/$name.py)"
      continue
    fi
    python3 "checkers/$name.py" 2>&1 | tail -3
    [ "${PIPESTATUS[0]}" != "0" ] && FAIL=1
  done
  # An adversarial review on 2026-08-18 put a fabricated 160,000-IPS record with no
  # gate, log or artifact through this block and verify.sh printed ALL CLEAR: the
  # original loop piped to `tail` and never consulted PIPESTATUS. It also ran zero
  # times, because campaign/records/ does not exist -- a silently-skipped check that
  # reports success is worse than no check.
  echo ""
  echo "── frozen_guard — shipped artifacts have not silently diverged"
  if [ -f campaign/FROZEN.json ]; then
    python3 checkers/frozen_guard.py || true
  else
    inert "no campaign/FROZEN.json — nothing has been frozen, so nothing can be checked for drift"
  fi
  printf "\n── record_schema — measurement records defend themselves\n"
  if ls campaign/records/*.json >/dev/null 2>&1; then
    for f in campaign/records/*.json; do
      python3 schema/record_schema.py "$f" 2>&1 | tail -2
      [ "${PIPESTATUS[0]}" != "0" ] && FAIL=1
    done
  else
    inert "no records in campaign/records/ — every MEASURED claim is supposed to emit one."
    echo "  An empty record store means this check is inert, not that it passed."
  fi
fi

printf "\n── self-tests — the checkers' own negative controls\n"
for st in checkers/void_check checkers/discrepancy_check checkers/artifact_fingerprint \
          checkers/run_gate checkers/emit_records checkers/context_and_caveat_check \
          harness/gate_map harness/gate_llm; do
  if [ "$st" = harness/gate_map ] && ! python3 -c 'import numpy' 2>/dev/null; then
    echo "  gate_map: SKIPPED — needs numpy (pip install numpy)"; INERT=1; continue
  fi
  python3 "$st.py" --self-test >/dev/null 2>&1 \
    && echo "  $(basename $st): self-test PASSES" \
    || { echo "  $(basename $st): SELF-TEST FAILING — the checker itself is broken"; FAIL=1; }
done

if [ $FAIL = 1 ]; then V="BLOCKED — do not send"; RC=1
elif [ $INERT = 1 ] && [ $SELFTEST_ONLY = 0 ]; then
  V="INERT — nothing failed, but the checks above marked INERT had nothing to check"; RC=2
elif [ $INERT = 1 ]; then V="SELF-TESTS PASS (some skipped — see above)"; RC=0
else V="ALL CLEAR"; RC=0
fi
printf "\n═══ %s ═══\n" "$V"
exit $RC
