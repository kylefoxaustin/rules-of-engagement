# A/B experiment — RESULT
**Pre-registered 2026-08-20 (commit `dcb5d4a`) before any data existed. This reports what was
pre-registered, in the direction it came out.**

## Headline: NULL. And the pilot could not have found an effect if one existed.

| | control | treatment |
|---|---:|---:|
| reports | 11 | 11 |
| defects (blinded auditor) | **4** | **2** |
| defects per report | 0.36 | 0.18 |
| clean reports | 8/11 | 9/11 |
| one-signed defects | 1 | 0 |
| **token cost (mean)** | **63,269** | **~142,000 (2.4×)** |

**Paired sign test** — the right test for a matched design: 3 pairs favoured treatment, 2 favoured
control, **6 were ties**. Exact two-sided binomial on the 5 discordant pairs: **p = 1.000**.

### ⭐ The finding that matters more than the result
**The experiment was underpowered by construction.** With a base rate of 0.36 defects per report, most
pairs are ties — 6 of 11 here. Only 5 pairs carried any signal. A sign test on 5 discordant pairs
**cannot reach p < 0.05 no matter how they split**: a perfect 5–0 sweep would give p = 0.062.

So this pilot could not have produced a significant result even if the harness were spectacularly
effective. **I fixed N = 12 before knowing the base rate.** That is a design error, and it is mine. The
correct sequence is to estimate the defect base rate first, then power the experiment against it. At
0.36 defects/report, detecting a halving at 80% power needs on the order of 100+ pairs, not 12.

## What can and cannot be claimed
**CANNOT:** that the harness reduces defects. The data do not support it (p = 1.000) and could not have.
**CANNOT:** that the harness does *not* reduce defects. A null from an underpowered test is not evidence
of absence.
**CAN:** that on small, well-specified microbenchmark tasks, **competent agents produce few defects
either way** — 8 defects across 24 reports, 17 of 24 reports clean.
**CAN:** that the harness costs **2.4× the tokens** on these tasks, and that no defect reduction has
been demonstrated to justify it *at this scale of task*.

## The pre-registered secondary outcomes
- **One-signed fraction:** control 1 of 4, treatment 0 of 2. n far too small to test. Not evidence.
- **Gate-catchable fraction:** not separately scored; a gap in my brief.

## ⚠ Threats to validity, all recorded before unblinding
1. **Blinding was PARTIAL.** Textual tells were redacted and verified gone, but methodology description
   is a behavioural fingerprint: 8/9 treatment vs 1/10 control describe an entry/exit discipline. An
   auditor could plausibly infer arm.
2. **Effort confound, unregistered.** Treatment spent 2.4× the tokens. Any defect difference could be
   effort, not rule content. Separating them needs an effort-matched control arm.
3. **Protocol deviation (mine).** The iq9 Q3 re-run control got a time bound and a hint no other arm
   received; it used 0.61× the effort of a normal control. That pair is excluded from the primary.
4. **A lost arm.** Task 0's treatment was never launched for four hours; found by an inventory script,
   then run. No result affected.
5. **An invented run id.** I launched one task against an id absent from the map; caught and redirected
   before the report was written.
6. **Measurand drift I designed in.** "L2 latency" named a 1 MiB cache on thor, 256 KB on orin, 512 KB
   on iq9 and 64 KB on imx95. Within-pair comparisons hold; cross-board Q2 numbers do not.
7. One model family across both arms and the auditor. Not a model comparison.
8. Defect counts are auditor judgement, not ground truth.

## What the experiment actually produced
The pre-registered outcome is null. The **qualitative** yield is not, and it came from **both arms**:

- **The compiler deletes benchmarks and returns a fast, plausible number.** Four independent incidents.
  `-O2` removed an entire pointer-chase loop (would have published a quotable L2 latency); `memchr` was
  constant-folded to 14,000,000,000 MB/s; warm-up chases were dead-code-eliminated; an elided-loop
  negative control ran at 3.5e10 MB/s. **Two of these were found by CONTROL arms**, by disassembling
  and by noticing impossible magnitudes — neither of which our rules mandate. → **rule candidate M45**.
- **Hardware prefetchers both hide defects and manufacture plausible wrong numbers.** A broken loop cost
  no time because the prefetcher streamed the skipped lines; a naive pointer-chase read 2.02 ns instead
  of 4.0 because the predictor learned the cycle. Only a counter inside the timed region separates these.
- **Thor's single-core bandwidth is bimodal, 2.5×.** EMC rests at 665.6 MHz and steps to 2750 MHz after
  ~7.3 s of sustained load. **Any Thor bandwidth measurement shorter than ~8 s measures the floor.**
- **A counter-example to our own directional law.** Thor's cores idle at 972 MHz; an unverified clock
  would have *understated* throughput. Validity-of-computation defects are one-signed; environment and
  config defects are two-signed. Our summaries had been overstating this.

**These are worth more than the primary outcome.** They were found by running the measurements, not by
comparing arms — which is itself a result about how to spend effort in this domain.

## What to do next
1. **Do not run block 2 as a bigger version of block 1.** Estimate the base rate, then power against it.
2. **Add an effort-matched control** (same token/tool budget, no rules) to separate content from effort.
3. **Choose harder tasks.** A 0.36 defect base rate leaves no room to detect improvement. The defects
   this campaign actually suffered came from multi-day, many-number deliverables — not 400-word reports
   on one quantity. **The experiment should be run on the kind of work where the defects live.**
4. Score gate-catchability explicitly; the brief omitted it.
