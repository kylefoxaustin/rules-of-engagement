# Broken Is Faster

**A measurement harness for benchmarking hardware with an AI agent — built out of the specific ways
one got it wrong.**

Every rule here exists because a real benchmark produced a real wrong number, on real silicon, and
something later disagreed with it. Nothing in this repo is a best practice someone thought sounded
sensible. It is a failure register with enforcement attached.

---

## The finding that names the repo

An INT8 object detector was re-timed after a rebuild. The new engine was **8.3% faster**. It was
briefly recorded as an improvement.

The engine was uncalibrated. It scored **mAP 0.0021** — it detected essentially nothing. It was faster
*because* it was broken.

That is not an anecdote, it is a direction, and it is the single most useful thing in this repo:

> ### ⭐ Broken is faster. So measurement error is not symmetric — it flatters the accelerator.
> A model that skips work, a graph that falls back to a stub, a buffer half-filled, a config silently
> ignored, a timer that starts late: nearly every one of these makes the number *better*. You will
> almost never be saved by a result that looks disappointing. **You will be handed a good number and
> believe it.**

The same detector, on another board, ran at full speed and returned **zero detections** on every
anchor — for months — passing exit-code checks, tensor-shape checks, and "did it execute on the
accelerator" checks. None of those look at whether anything was *detected*.

**Therefore the founding rule: gate the OUTPUT in the SAME run as the timing.** A performance number
from a model producing garbage is worth nothing, and it is worth *less* than nothing when it is faster.

---

## What this is

A harness plus 45 rules of engagement, 11 checker programs, and 19 harness
programs, for the situation where **an AI agent is running your benchmarks unattended** and you have
to decide whether to believe the report it hands you.

It targets the failure modes that are specific to that situation:

- the agent measures something subtly different from what you asked, and says it succeeded
- the numbers are fine but the *prose written about them* has drifted out of agreement with the tables
- a fix is reported as applied, and was applied to a source file that never rendered
- the agent writes its own verification, and its verification has the same blind spots it does

## What this is NOT

- **Not a benchmark suite.** No models, no datasets, no scores. It is the scaffolding around whatever
  you already measure.
- **Not our measurements.** Deliberately. The method transfers; our numbers are about our boards.
- **Not general.** These rules encode *a specific past*. We measured that directly: 37 crafted defects
  were run against our own checkers and **35 passed** — every checker caught faithful replicas of the
  defect it was built from and missed nearly every variation. **Assume the same is true for you.**
  Expect to add rules; the amendment procedure at the bottom of `RULES.md` tells you how.
- **Not finished.** See the caveats before you trust any of it.

---

## Quick start

```bash
git clone https://github.com/kylefoxaustin/broken-is-faster
cd broken-is-faster
./build_readme.sh          # regenerates this file's counts from source — see M44
cat PROMPT.md              # paste this into your agent to start it benchmarking
```

Then hand `PROMPT.md` to whichever assistant is going to run your benchmarks. It sets the agent's
working rules before it takes a single measurement, which is the only moment when doing so is cheap.

Run the checkers against a deliverable you already have. **Expect it to hurt** — ours reported
`0 failures, 0 warnings` on a document that ten subsequent adversarial passes found defects in.

---

## What is in here

| path | what it is |
|---|---|
| `PROMPT.md` | the starter prompt — paste into your agent |
| `RULES.md` | 45 rules, each citing the defect that motivated it |
| `FAILURES.md` | 26 failures, in detail, with how each was caught |
| `checkers/` | 11 programs that read finished artifacts and refuse to pass them |
| `harness/` | 19 programs that run at measurement time — gates, porch protocol, samplers |
| `schema/` | the record format a measurement must satisfy to be quotable |
| `adversarial/` | how to run the audit, and the passes that beat us |
| `verify.sh` | the single entry point; runs everything and returns a verdict |

### The three ideas doing most of the work

**1. Every number carries a provenance tag, and there are only three.**
`MEASURED` (you ran it, with proof) · `DERIVED` (computed — must be labelled) · `SOURCED`
(datasheet/vendor — must be labelled, and only where you genuinely cannot test it).

> **A DERIVED or SOURCED number may never be compared bare against a MEASURED one.**

Nearly every real defect we found was a mixed-tier comparison — beating a real measurement with a
multiplication, or ranking latency-reciprocals in a column of saturated throughputs. Note that the sin
is never the arithmetic; it is the label. `671 × 2.00` is legal. Calling the product *measured* is not.

**2. Gate the output in the same run as the timing.** Not afterwards, not in a separate script that
can drift, not "we checked that model last week." Same invocation, or the number is not quotable.

**3. Verify the rendered artifact, never the build that produced it.** A green build proves the code
ran. It says nothing about whether the document is right. Read it — do not grep it; grep proves a
string exists and cannot see the sentence it landed in.

---

## Four classes of trust, because reproduction only covers one

The thing that surprised us most: *running it again* verifies far less than it feels like it does.

| | what is at risk | verified by | how it fails |
|---|---|---|---|
| **1. Measurement** | world → number | **reproduction** | silently, and **fast** |
| **2. Relation** | number → number | **condition matching** | silently, and **arithmetically correct** |
| **3. Narrative** | number → sentence | **tracing + consistency** | silently, and **fluently** |
| **4. Record** | claimed fix → actual fix | **diffing the change** | silently, and **confidently** |

Reproduction only verifies class 1. Re-running a benchmark tells you nothing about whether a ratio is
legitimate, whether a sentence still matches the table above it, or whether the fix you reported
actually landed. Most of our cost was in classes 3 and 4, which have no equivalent of "run it again."

**Class 3 is the one that arrived with AI.** An agent writes fluent, confident prose about its own
results, and the prose goes stale the moment a number moves. It still reads perfectly. As the person
who ran this put it: *you can hash a file; you cannot hash a sentence — its meaning lives outside its
bytes.* That is why class 3 needs a different verifier, and why `checkers/prose_integrity.py` exists.

---

---

## Does any of this actually work? We ran the experiment. The answer is "we could not tell."

In August 2026 we ran a pre-registered, blinded A/B test of this harness: 12 matched benchmarking tasks
across four boards, each done twice — once by an operator given these rules and checkers, once by an
operator given only the task. A third, blinded reviewer scored the write-ups for defects.

| | without the harness | with it |
|---|---:|---:|
| defects found | 4 | 2 |
| defects per report | 0.36 | 0.18 |
| **cost** | **1×** | **2.4× the tokens** |

**Paired sign test: p = 1.000.** Three pairs favoured the harness, two favoured the control, six tied.

**And the experiment could not have detected an effect if one existed.** At a base rate of 0.36
defects per report most pairs tie; only five carried any signal, and a sign test on five discordant
pairs cannot reach p < 0.05 however they split. We fixed the sample size before knowing the base rate.
That is a design error, and it is ours.

So: **we cannot claim this harness reduces defects.** We also cannot claim it does not — a null from an
underpowered test is not evidence of absence. What we can say is that on small, well-specified tasks,
competent operators produced few defects either way, and this harness cost 2.4× the effort with no
demonstrated benefit *at that scale of task*.

**Read `adversarial/AB_EXPERIMENT.md` for the full result, including the three protocol failures we
committed while running it** — an invented identifier, a mid-experiment protocol deviation that biased
toward our own hypothesis, and an entire arm we lost for four hours. All three were caught by
mechanisms, none by attention. That is the most honest argument for mechanising this that we have.

**What the experiment did produce** is `FAILURES.md` class 7 — four separate cases of a compiler
deleting a benchmark and returning a fast, plausible number. **Two were found by operators who did not
have these rules.** That is why M45 exists, and it is a fair warning about what else these rules do not
yet cover.

## Caveats — read these before trusting anything here

- **These rules will rot.** They encode toolchain behaviours from a specific window in 2026. Some will
  be fixed upstream and become noise; some will be silently wrong for your stack. Read the failure each
  rule cites and decide whether it still applies to you.
- **We measured our own checkers and they are weak.** 35 of 37 crafted defects passed. One checker
  passed the exact trap case quoted in its own docstring. **Do not let a green run end your review.**
- **A checker teaches its blind spot to every reviewer who trusts it.** Our parity gate compares
  *numbers*, so a block of pure guidance prose lived in one artifact and was missing from the other —
  and **all ten** adversarial passes inherited that blindness and walked past it. It was found by a
  human asking a naive question. Budget for a reviewer who is told to ignore the tooling entirely.
- **Fixing is a leading source of defects.** Across our first seven audit passes, **29% of findings
  were introduced by the previous fix**. Late in a review, a cosmetic fix is a bad bet. We shipped with
  two known-MINOR wording issues on exactly those odds.
- **Paths are not portable.** Several harness programs carry absolute paths and SDK locations from the
  machine they were written on. They are here as method, not as a turnkey install.
- **The counts in this README are generated** by `build_readme.sh`. If you edit them by hand you have
  reintroduced the bug the file warns you about — ours rotted within an hour of being quoted.

---

## Contributing

The valuable contribution is **a failure**, not a feature. If a rule here missed something on your
hardware, open an issue with the artifact and how it was eventually caught. `RULES.md` is amended by
finding a new way to be wrong — adding a rule requires citing the defect that motivated it, with
evidence. Rules are removed only when the failure mode has become structurally impossible.

## Licence

MIT. See `LICENSE`.
