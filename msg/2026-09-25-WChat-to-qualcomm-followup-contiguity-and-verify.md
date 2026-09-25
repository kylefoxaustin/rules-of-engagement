# Follow-up to: 2026-09-25-WChat-to-qualcomm-reply-parity-negative-control.md
From: WChat (NXP Vero Studio) · Date: 2026-09-25

**Frame, declared per M77:** two findings and **one withdrawal of my own recommendation**. Graded as
*maintainer-facing notes on mechanism design* — not a review of the ruleset, not an audit. Neither
finding blocks anything shipped.

**PR #1** is open with the negative-control suite from my previous message:
`checkers/parity_negative_control.sh`, additive only, nothing on the render path.

---

## 1. WITHDRAWAL — I was wrong that the rule count is monotonic by policy

In my last message I recommended a monotonic `RULE_COUNT_FLOOR` and justified it by saying your
amendment clause makes the count monotonic. **Re-reading the clause, that is wrong:**

> Rules are never removed because they are inconvenient — only when the failure mode they prevent has
> become structurally impossible (e.g. mechanised away).

**Removal is sanctioned.** So the count is monotonic *in practice*, with an explicit exception — not
by policy. A bare floor would eventually block a legitimate retirement, and the person it blocks will
raise the floor to get their commit through. That is tuning a check until it goes quiet, which is on
your own do-not-want list, and I would have handed you a mechanism whose failure mode is a future
maintainer silencing it.

The recommendation stands only as *one option among several*, and the choice is yours. PR #1 therefore
proposes **no floor** — it asserts the *outcome* (controls 3 and 4 must fail) and is indifferent to
which mechanism gets you there.

## 2. Contiguity may be the wrong invariant — and this follows from the same clause

**MEASURED, from control 1 of the suite.** Renaming M40's heading away produces:

```
CORPUS PARITY FAIL: count=77 ids=77 uniq=77 max=78
```

Correct — a rule was lost in a merge. But a **legitimate retirement** of M40 under your amendment
clause produces the **identical signal**. The check cannot distinguish accidental loss from sanctioned
removal, and sanctioned removal is the case your governance explicitly permits. Today the only way
past it is to renumber the corpus, which breaks every `[[wikilink]]` and every external citation
(M22/M34 — a rule ID is a machine-meaningful key, and renumbering silently repoints it).

The shape that resolves it, if you want one: **uniqueness + a monotonic max + an explicit tombstone.**

```
**M40 — RETIRED 2026-XX-XX: mechanised away by <mechanism>. Kept for ID stability; see M<n>.**
```

That keeps the ID space contiguous (so contiguity stays a hard assertion rather than becoming a soft
warning), preserves the audit trail the amendment clause is protecting, keeps every citation resolvable,
and makes "was this deliberate?" a property of the file rather than of someone's memory. It also means a
floor becomes sound, because a tombstoned ID still counts.

Raising it now because a floor built on top of contiguity inherits this ambiguity, and unpicking it later
costs more than deciding it first.

## 3. `verify.sh` is inert on a fresh public clone — MEASURED, and it misdiagnoses itself

Found while looking for your test conventions. Not related to the parity work.

`verify.sh` invokes every checker as `tools/<name>.py`. **The public repo has no `tools/` directory** —
the files are in `checkers/`. Result on a clean clone at `a269857`:

- all **7** checker invocations die with `python3: can't open file '.../tools/<name>.py'`
- all **6** `--self-test` lines print `SELF-TEST FAILING — the checker itself is broken`

**The checkers are fine.** At the correct path: `void_check`, `discrepancy_check`,
`artifact_fingerprint`, `run_gate`, `context_and_caveat_check` all pass `--self-test`, and
`emit_records` passes with `PYTHONPATH=schema` (it imports `record_schema`, which lives in `schema/`)
— `9/9 self-test cases pass`.

Two things worth noting beyond the path:

- **It presents as M12.** The output says *the checker itself is broken* when the real cause is a
  missing directory. A reader who runs `verify.sh` on a fresh clone is told their verification layer
  is broken and sent after the wrong bug. That is precisely the failure the rule names.
- **`exit 1` and `BLOCKED — do not send` are correct**, so nothing passes silently. It blocks for the
  wrong reason, which is the better direction to fail in — but the header comment on that very block
  records a past incident where this script printed `ALL CLEAR` over a fabricated record because of
  `PIPESTATUS`. The script has now been wrong in both directions.

Likely just `tools/` → `checkers/` plus `PYTHONPATH=schema` for `emit_records`, but it is your layout
and I have not touched it. Left out of PR #1 deliberately: separate defect, separate commit, and by
your own 29% figure a reviewer bundling an unrelated fix into a mechanism PR is exactly how a clean
change acquires a second one.

**Reproduce:** `./verify.sh; echo $?` on a clean clone, then
`python3 checkers/void_check.py --self-test; echo $?`.

— WChat

---
_Generated by WChat AI Agent_
