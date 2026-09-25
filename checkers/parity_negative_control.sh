#!/usr/bin/env bash
# parity_negative_control.sh — negative controls for the M76 corpus-parity check in build_readme.sh.
#
# WHY THIS EXISTS (M2: prove the gate can fail).
# The corpus-parity assertion added in a269857 closed the 45->61 / 61->75 drift by asserting the
# rule-ID set is contiguous 1..MAXID and unique. Two of its three failure modes are genuinely
# caught. The third -- truncation at the END of the corpus, which is the shape of BOTH historical
# drifts -- is not, because MAXID is derived from the same file under test: "IDS == seq 1 MAXID"
# is a tautology when the tail is missing. A corpus cut short is still contiguous and still
# unique; it is simply a shorter N.
#
# This script is a NEGATIVE CONTROL SUITE, not a checker. It asserts only that build_readme.sh
# FAILS on known-bad corpora. It makes no claim that any corpus is correct, so it cannot
# manufacture confidence -- it can only ever report that a control did or did not trip.
#
# Controls 1 and 2 are expected to PASS today (the check catches them).
# Controls 3 and 4 are expected to FAIL today: they are the OPEN finding, and they are written as
# xfail so this suite is green on an unfixed tree while still naming the gap. When the boundary
# gap is closed, flip EXPECT_BOUNDARY_FIXED=1 (or export it in CI) and they become hard
# assertions -- control 4 is the regression test this incident earns.
#
# Usage:  ./checkers/parity_negative_control.sh
#         EXPECT_BOUNDARY_FIXED=1 ./checkers/parity_negative_control.sh
# Exit:   0 = every control behaved as expected. 1 = a control regressed.
#
# Provenance: MEASURED on a269857 by WChat (NXP Vero Studio), 2026-09-25. Every control below was
# run and its exact output recorded in msg/2026-09-25-WChat-to-qualcomm-reply-parity-negative-control.md

set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
EXPECT_BOUNDARY_FIXED="${EXPECT_BOUNDARY_FIXED:-0}"
PREMERGE_REF="${PREMERGE_REF:-4e4479f}"   # the real 61-rule corpus, before the 61->76 merge
FAIL=0

# Run build_readme.sh against a throwaway copy of the repo that a mutator has broken.
# Never mutates the real tree: the working copy is a fresh `git worktree`-free cp in /tmp.
run_control () {
  local name="$1" expect="$2" mutate="$3" note="$4"
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  cp -r "$REPO"/. "$tmp"/ 2>/dev/null
  ( cd "$tmp" && eval "$mutate" ) >/dev/null 2>&1 || {
    printf "  %-34s SETUP FAILED (mutator errored) -- control did not run\n" "$name"
    FAIL=1; return
  }

  local out rc
  out="$( cd "$tmp" && ./build_readme.sh 2>&1 )"; rc=$?

  # M12: a harness error is not a result. A mutator that produced no change, or a script that
  # died for an unrelated reason, must not be scored as "the check caught it".
  if [ "$rc" != 0 ] && ! printf '%s' "$out" | grep -q 'CORPUS PARITY FAIL'; then
    printf "  %-34s RUNTIME_ERROR -- nonzero exit with no parity verdict\n" "$name"
    printf "      %s\n" "$(printf '%s' "$out" | tail -2)"
    FAIL=1; return
  fi

  local got; [ "$rc" = 0 ] && got=pass || got=fail

  if [ "$got" = "$expect" ]; then
    printf "  %-34s %s as expected\n" "$name" "$(printf '%s' "$got" | tr a-z A-Z)"
    [ -n "$note" ] && printf "      %s\n" "$note"
  else
    printf "  %-34s REGRESSED: expected %s, got %s\n" "$name" "$expect" "$got"
    printf "      %s\n" "$(printf '%s' "$out" | grep -E 'PARITY|parity' | head -1)"
    FAIL=1
  fi
}

echo "═══ CORPUS-PARITY NEGATIVE CONTROLS ═══"
echo "repo: $REPO"
echo "boundary-gap expected fixed: $EXPECT_BOUNDARY_FIXED"
echo

echo "── interior defects (the check handles these)"

# 1. A rule vanishes from the MIDDLE of the range -> leaves a hole -> must fail.
run_control "1 interior gap (M40 removed)" fail \
  "python3 -c \"
import re,io
s=open('RULES.md').read()
s=re.sub(r'^\\*\\*M40 ', '**MGAP40 ', s, count=1, flags=re.M)
open('RULES.md','w').write(s)\"" \
  ""

# 2. An ID is used twice -> uniqueness violation -> must fail.
run_control "2 duplicate id (M56 -> M55)" fail \
  "python3 -c \"
import re
s=open('RULES.md').read()
s=re.sub(r'^\\*\\*M56 ', '**M55 ', s, count=1, flags=re.M)
open('RULES.md','w').write(s)\"" \
  ""

echo
echo "── boundary defects (the OPEN finding: truncation at the tail)"

BOUNDARY_EXPECT=fail
BOUNDARY_NOTE=""
if [ "$EXPECT_BOUNDARY_FIXED" != 1 ]; then
  BOUNDARY_EXPECT=pass
  BOUNDARY_NOTE="XFAIL -- known gap: MAXID comes from the file under test, so a missing tail is invisible."
fi

# 3. The tail of the corpus is cut off. Still contiguous, still unique, just shorter.
run_control "3 tail truncated (M77,M78 cut)" "$BOUNDARY_EXPECT" \
  "python3 -c \"
s=open('RULES.md').read()
i=s.index('**M77 ')
open('RULES.md','w').write(s[:i])\"" \
  "$BOUNDARY_NOTE"

# 4. THE REGRESSION TEST. Restore the actual pre-merge RULES.md -- the real 61-rule corpus whose
#    silent acceptance motivated the parity check in the first place. If the mechanism cannot fail
#    on the artifact that caused the incident, it is not the mechanism for that incident.
run_control "4 real pre-merge corpus ($PREMERGE_REF)" "$BOUNDARY_EXPECT" \
  "git checkout $PREMERGE_REF -- RULES.md" \
  "$BOUNDARY_NOTE"

echo
if [ "$FAIL" = 0 ]; then
  echo "═══ CONTROLS OK — every control behaved as expected ═══"
  if [ "$EXPECT_BOUNDARY_FIXED" != 1 ]; then
    echo "    NOTE: controls 3 and 4 are XFAIL. The parity check still certifies a truncated"
    echo "    corpus as whole. This suite is green because it faithfully records that gap --"
    echo "    NOT because the gap is closed. Re-run with EXPECT_BOUNDARY_FIXED=1 after fixing."
  fi
else
  echo "═══ CONTROLS REGRESSED — a negative control did not behave as recorded ═══"
fi
exit $FAIL
