#!/usr/bin/env bash
# Renders README.md from README.md.in, substituting counts GENERATED from this repo.
# This exists because of M44: "generate counts, never type them." A README about
# count rot that carries a typed count is the bug it warns you about. Run it after
# adding a rule, a checker or a harness program; CI should fail if the diff is dirty.
set -euo pipefail
cd "$(dirname "$0")"
RULES=$(grep -cE '^(\*\*|#{1,6}[[:space:]]+)M[0-9]' RULES.md)
CHECKERS=$(ls checkers/*.py | wc -l | tr -d ' ')
HARNESS=$(ls harness/ | wc -l | tr -d ' ')
FAILURES=$(grep -c '^### ' FAILURES.md)

# M76 corpus-parity: a generated count certifies the FILE, not that the file IS the corpus.
# Second, independent enumeration — the rule-ID SET must be contiguous 1..N and unique.
IDS=$(grep -oE '^(\*\*|#{1,6}[[:space:]]+)M[0-9]+' RULES.md | grep -oE '[0-9]+' | sort -n)
NIDS=$(printf '%s\n' "$IDS" | grep -c .)
UNIQ=$(printf '%s\n' "$IDS" | sort -nu | grep -c .)
MAXID=$(printf '%s\n' "$IDS" | tail -1)
if [ "$NIDS" != "$RULES" ] || [ "$NIDS" != "$UNIQ" ] || [ "$IDS" != "$(seq 1 "$MAXID")" ]; then
  echo "CORPUS PARITY FAIL: count=$RULES ids=$NIDS uniq=$UNIQ max=$MAXID (rule-ID set is not a contiguous unique 1..$RULES)" >&2
  exit 1
fi
echo "corpus parity OK: M1..M$MAXID, $NIDS rules, contiguous + unique"

sed -e "s/{{RULES}}/$RULES/g" -e "s/{{CHECKERS}}/$CHECKERS/g" \
    -e "s/{{HARNESS}}/$HARNESS/g" -e "s/{{FAILURES}}/$FAILURES/g" README.md.in > README.md
echo "README.md rendered: $RULES rules, $CHECKERS checkers, $HARNESS harness programs, $FAILURES failures"
