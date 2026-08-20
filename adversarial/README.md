# Adversarial review — how to run it, and what it costs

The checkers are necessary and they are not sufficient. This directory is the part of the method that
found what they could not.

## The headline result

One benchmark deliverable — three boards, four questions, twelve tabs — was taken through **ten**
adversarial passes. Findings per pass:

```
pass    1   2   3   4   5   6   7   8   9  10
found  14  17  19  10   7   8   1   3   3   0  → SEND
```

Two things in that curve matter more than its shape:

| | |
|---|---|
| **Pre-existing defects per pass** | 14, 6, 16, 9, 4, 5, 0, 0, 0 |
| **Findings injected by the previous fix** | **22 of 76 (29%)** across passes 1–7 |

**Seven of nine passes contained at least one defect created by the previous round of fixes.** That is
the number that should change how you run a review. Fixing is not free, and late in a review it is the
single largest source of new defects.

## Procedure

1. **Freeze the artifacts by hash first.** Record the md5 of every file under review. One of our passes
   was invalidated because the files were rebuilt mid-audit and the findings no longer referred to
   anything that existed.
2. **Use a reviewer that did not write the code.** A separate agent, a separate model if you can. The
   author's blind spots are in the artifact *and* in the checkers they wrote.
3. **Tell it to find nothing if there is nothing.** Explicitly authorise the verdict SEND. A reviewer
   that believes it must produce findings will produce findings, and you will then spend a fix round —
   and a fix round injects defects at roughly one in three.
4. **Require a failure scenario per finding**, not a style objection: concrete inputs or state, and the
   wrong output or wrong claim that results.
5. **Re-audit after every fix round.** Non-negotiable, given the injection rate.
6. **Stop** when a pass finds no pre-existing defect **above MINOR** *and* the changelog matches the
   diff. (The unqualified "no pre-existing defects" version of this criterion is one we published and
   had to retract — our last three passes each did find MINOR pre-existing items.)

## What to point the reviewer at

Ranked by what actually yielded, on our corpus:

1. **Prose adjacent to a table.** Highest yield by a wide margin. Numbers get corrected; the sentence
   describing them does not, and it still reads perfectly.
2. **Assertions the document makes about itself** — "every cell names its build", "all figures are
   gated". Check them against the document rather than believing them.
3. **Anything the tooling cannot see.** Ask the reviewer directly: *what in here contains no number?*
   Our worst late finding was two rows of pure guidance prose missing from one of two artifacts, and it
   survived ten passes because the parity gate compares numbers.
4. **The changelog against the diff.** Class 4 defects — a fix reported and not applied — are invisible
   to every content check, because the content check inspects the artifact and the lie is in the record.
5. **Superseded values still alive somewhere.** After any correction, grep every artifact for the old
   value. Two live values for one measurand is a defect even when the new one is quoted correctly.

## Attacking your own checkers

Do this separately, and do it before you trust a green run. We wrote 37 defects designed to look like
the ones our checkers were built for, and ran them through:

```
checker A   13/13 passed        checker D   6/7 passed
checker B    5/5  passed        checker E   5/6 passed
checker C    5/5  passed        checker F   1/1 passed
                              → 35 of 37 defects passed
```

Every checker caught faithful **replicas** of the defect it was written from, and missed nearly every
**variation**. One passed the exact trap case quoted in its own docstring. The single entry point
reported ALL CLEAR over a fabricated 160,000 IPS record.

**The lesson is not "our checkers were bad."** It is that a checker encodes *a specific past*, not a
class of error, and the only way to find out where its edges are is to attack it deliberately. Every
gate in this repo therefore ships with a negative control. When you change a gate, re-run its control —
a gate that has never fired is not evidence that anything is clean.

## The honest accounting

Ten passes on one deliverable is expensive, and most of that cost was not the reviewing. It was the
**fixing, and the re-reviewing made necessary by the fixing**. If you take one operational decision
from this: batch your fixes, apply only what is above MINOR, and re-audit — rather than polishing.

What it bought, measured: on re-measurement **19 of 20 published figures reproduced within 1%**, and
the accuracy figures reproduced **exactly to four decimals**. The numbers had been good. What was
missing was the *evidence* that they were good — and, in one case, the answer to the question that was
actually asked.
