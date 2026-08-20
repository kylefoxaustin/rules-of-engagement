#!/usr/bin/env bash
# Renders README.md from README.md.in, substituting counts GENERATED from this repo.
# This exists because of M44: "generate counts, never type them." A README about
# count rot that carries a typed count is the bug it warns you about. Run it after
# adding a rule, a checker or a harness program; CI should fail if the diff is dirty.
set -euo pipefail
cd "$(dirname "$0")"
RULES=$(grep -c '^\*\*M[0-9]' RULES.md)
CHECKERS=$(ls checkers/*.py | wc -l | tr -d ' ')
HARNESS=$(ls harness/ | wc -l | tr -d ' ')
FAILURES=$(grep -c '^### ' FAILURES.md)
sed -e "s/{{RULES}}/$RULES/g" -e "s/{{CHECKERS}}/$CHECKERS/g" \
    -e "s/{{HARNESS}}/$HARNESS/g" -e "s/{{FAILURES}}/$FAILURES/g" README.md.in > README.md
echo "README.md rendered: $RULES rules, $CHECKERS checkers, $HARNESS harness programs, $FAILURES failures"
