# A/B experiment — PRE-REGISTRATION
**Written and committed BEFORE any arm was run.** Commit this file first; if it is amended after data
exists, the amendment must be dated and the original left visible in git history.

## The claim under test
> A self-written verification harness reduces the rate at which defects reach a published artifact.

We already have the *gate-blindness* half measured retrospectively: 37 crafted defects run against our
own checkers, **35 passed**. That measures blindness on crafted input. It does **not** measure escape
rate on real work, which is the number a reviewer will ask for, and which can only be collected
prospectively.

## Design
**Unit of randomisation:** one measurement task = `(board, quantity)`. Not a board (too few units),
not a claim (claims inside one run are not independent).

**Arms** — both are FRESH subagents with no inherited context, launched in the same message so neither
sees the other's output.

| | **A — CONTROL** | **B — TREATMENT** |
|---|---|---|
| instructions | task text only | identical task text + the harness |
| rules doc | withheld | provided |
| checkers | withheld | provided |
| porch / gates | withheld | provided |

**⚠ Contamination hazard.** I know the rules and would apply them unconsciously, so I cannot be the
control. The control's prompt must not mention gates, provenance, tagging, or this campaign.

**Manipulation check (this is a CHECK, not a hope).** For every control run, assert the transcript
contains zero reads of `MEASUREMENT_RULES_OF_ENGAGEMENT.md` and zero invocations of anything under
`tools/`. A control arm that silently self-gated is a **non-experiment** and looks identical to "the
harness does nothing" — so a failed check **invalidates that pair**, it does not contribute a null.

**Scoring.** A third, blinded auditor receives both write-ups with all arm markers stripped, in
randomised order, and does not know which harness produced which. It classifies each finding and
records whether a gate could have caught it.

## Pre-registered outcomes
- **PRIMARY:** defects per published claim. Directional prediction: **arm B < arm A**.
- **SECONDARY:** fraction of defects that are one-signed. Prediction: arm A's defects flatter the
  accelerator more often than chance, per the campaign's directional-bias law.
- **SECONDARY:** fraction of arm-A defects that a gate *would* have caught, had one been present.

## Stopping rule
Fixed N, decided now: **12 pairs** for this pilot. No peeking-and-extending. If the result is
ambiguous at 12, that is reported as ambiguous and a second pre-registered block is written.

## What would falsify the claim
Arm B showing equal or more defects per claim than arm A, with manipulation checks passing in both.
That result gets published exactly as loudly as the favourable one.

## Held-out slice
Tasks are quantities that are **not** in any shipped deliverable and will not be published as fleet
results. They exist to be measured badly or well, not to be quoted.

## Known limits of this pilot
- N=12 pairs is small. It can detect a large effect, not a subtle one.
- One agent model on both arms; this is not a model comparison.
- The auditor is blinded to arm but is the same model family as the arms.
- Defect counts are auditor judgements, not ground truth.
