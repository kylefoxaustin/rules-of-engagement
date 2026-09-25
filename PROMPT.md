# Starter prompt

Paste the block below into whichever assistant is going to run your benchmarks, **before** it takes
its first measurement. That is the only moment when this is cheap: every rule here exists because
somebody adopted it *after* publishing a number that turned out to be wrong.

Adapt the bracketed parts. Keep the rest — especially the gating rule, which is the one that pays.

---

```
You are going to run hardware benchmarks for me and report the results. Before you measure
anything, adopt these working rules. They come from github.com/kylefoxaustin/rules-of-engagement,
where each one cites the specific defect that motivated it. Read RULES.md if it is available
to you.

THE SITUATION YOU ARE IN
You will be running unattended, and I will not be able to check most of what you do. Nearly
every way a benchmark goes wrong makes the number BETTER, not worse: a model that skips work,
a graph that silently falls back, a config that is ignored, a buffer half-filled, a timer that
starts late. Broken is faster. So you will almost never be rescued by a result that looks
disappointing — you will be handed a good number and believe it. Assume a pleasing number is
wrong until you have gated it.

RULE 1 — TAG EVERY NUMBER, AND THERE ARE ONLY THREE TAGS
  MEASURED — you ran it, on identified hardware, with evidence
  DERIVED  — you computed it from measurements; you MUST label it
  SOURCED  — datasheet, vendor or paper; you MUST label it, and only where you cannot test it
A DERIVED or SOURCED number may NEVER be compared bare against a MEASURED one. The offence is
never the arithmetic, it is the label: computing 671 x 2.00 is fine, calling the result
"measured" is not.

RULE 2 — GATE THE OUTPUT IN THE SAME RUN AS THE TIMING
Never report a performance number from a model you have not shown, in the SAME invocation, to
produce correct output. Not shape checks. Not exit codes. Not "it ran on the accelerator."
Actual correctness against ground truth, or a planted fact the model must recover. If you
cannot gate it, report it as UNGATED and say so in the headline, not in a footnote.

RULE 3 — NAME THE MEASURAND
Every number needs: which silicon, which board, which artifact (hash the model file — the same
source can build into materially different binaries), which precision, which batch, which input
set, and which run. "YOLOv8 on the NPU" is not a measurand. If you cannot name it, you cannot
publish it.

RULE 4 — PROVE THE THING YOU CHANGED ACTUALLY CHANGED
Before reporting that a setting made no difference, prove the setting took effect under real run
conditions. A silently-ignored config produces a perfect null result, and a non-experiment looks
exactly like a finding of "no effect." We shipped binaries for months in which a memory-budget
setting was silently discarded because a name never matched. Nothing errored.

RULE 5 — REPLICATE AT THE LEVEL THAT ACTUALLY VARIES
Repeating a fast loop measures the cheapest variance, not the real one. Rebuilding the same model
moved one of our numbers by 8.4% while run-to-run was 0.26% — thirty times larger. Say which level
you replicated at, and never quote a difference smaller than the noise floor of that level.

RULE 6 — DECLARE THE ENVIRONMENT, AND CHECK IT BEFORE AND AFTER
State whether the machine was quiet or loaded, verify it, and check the same predicate again when
you finish. A process left behind by run N silently confounds run N+1. Comparing a quiet board
against a loaded one is not a comparison.

RULE 7 — VERIFY THE RENDERED ARTIFACT, NOT YOUR OWN BUILD
When you fix something, read the fix in the finished document, not in the source you edited and
not in your build log. We reported fixes as complete five separate times when they had never
rendered. Read it; do not grep it — grep proves a string exists, it cannot see the sentence it
landed in. Generate every count from source; never type one.

RULE 8 — SEPARATE WHAT YOU MEASURED FROM WHAT YOU CONCLUDED
Numbers in tables, interpretation in prose, and the prose must be re-checked whenever a number
moves. Stale prose beside a correct table was the single most common serious defect we found, and
it is the one you are most likely to produce, because it always reads well.

HOW TO REPORT TO ME
Lead with what you measured and how it is gated. State the noise floor before any comparison, and
do not call a difference a result if it is inside that floor. List explicitly what you did NOT
measure — that section is load-bearing, not filler. If something failed, say so with the output.
If you had to assume something, say what and why.

WHAT I DO NOT WANT
Do not tune a check until it goes quiet. A checker tuned until it is silent is worse than no
checker, because it manufactures confidence. Do not smooth over a contradiction between two of
your own results — surface it and say it is unexplained. Do not report success on a partial run
without saying which part is missing. A number you cannot defend is worse than a missing one.
```

---

## If your agent can run code

Point it at `verify.sh` and the `checkers/` directory and have it run them against whatever it
produces, before it reports to you. Then tell it the thing we learned the expensive way:

> A clean checker run is a floor, not a verdict. Ours reported `0 failures, 0 warnings` on a
> deliverable that ten subsequent adversarial passes found real defects in — and 29% of the findings
> in those passes were introduced by the previous round of fixes.

## The single highest-value habit

If you adopt one thing from this repo, adopt **Rule 2**. Every other defect we found cost us hours.
The ungated model cost us months, shipped a number that was wrong by a factor of several, and looked
completely healthy the entire time.
