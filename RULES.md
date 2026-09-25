# Rules of Engagement — Measurement

**Status:** binding on every benchmark in this repo, from the moment Kyle says *"let's measure something."*
**Version:** 1.0 — 2026-08-16
**Evidence base:** 22 confirmed defects found in this corpus between 2026-08-14 and 2026-08-16 (six by
direct discovery, sixteen by two independent adversarial audits). Every rule below exists because
something in that list got past us. Nothing here is hypothetical.

This document exists because we are about to run *thousands* of benchmarks. At that volume, "we'll
catch it in review" is not a control. Each rule therefore has a **CHECK** — the specific, mechanical
thing that proves compliance — because a rule you cannot check is a preference.

---

## PART I — THE TWO LAWS

Everything else is a corollary of these.

### LAW 1 — A benchmark measures what the harness ACTUALLY DID, not what you believed it would do.
The gap between those two is where every defect lives. Speed is the one output a benchmark always
produces, whether or not the thing under test is configured, loaded, correct, or even present.

### LAW 2 — Both numbers being real does not make their difference real.
Two honestly measured quantities can be non-comparable (different overheads, different operating
points, different search effort) or indistinguishable (inside the noise floor). A comparison is a
third claim requiring its own evidence.

### THE COROLLARY — **Broken is faster.**
A model that detects nothing, a graph that fell back to a stub, an engine that skipped quantisation, a
prompt that was truncated — all run *faster* than the correct thing. Therefore **every measurement
error is biased in the direction that flatters the accelerator.** Any result that beats expectation is
a suspected defect until proven otherwise. This asymmetry is why "it looked plausible" is not evidence.

---

## PART II — THE FAILURE REGISTER

The taxonomy earned the hard way. When designing a new measurement, read this list and ask which one
you are about to repeat.

### Class A — A proxy was checked instead of the thing
| # | Checked | Assumed | Reality |
|---|---|---|---|
| A1 | exit code, tensor shape, DSP execute proof | the model detected something | IQ9 int8 YOLO: all 8400×80 class scores exactly 0.0, for months |
| A2 | `trtexec --int8` built and ran | the engine was usable | no calibration cache; max score 0.1575, zero detections |
| A3 | a `--profile` flag was passed | a profile was produced | genie refuses to overwrite an existing file; silent no-output run |
| A4 | the process ran | the accelerator was configured | missing `ADSP_LIBRARY_PATH` → "device 1008" |
| A5 | grep found 0 fallback warnings | there was no fallback | the grep pattern could not match the real warning string |
| A6 | `runtime_prompt_n` was right | the whole prefill was correct | a needle proves ~10 tokens survived, not 4106 |

### Class B — The independent variable never moved
| # | Believed varied | Actually |
|---|---|---|
| B1 | context length (`llama-bench -p 128`) | no context flag exists; n_ctx derived from p+n |
| B2 | context length (`llama-server -c`) | **pinned at 8192 for every point**; only prompt length moved |
| B3 | needle depth 10/50/90% | placed by *paragraph* index; at 1024 tok the body is 5 paragraphs, so "90%" was 60% |
| B4 | batch correctness across 4 slots | the same image fed 4× — cannot detect a broken batch stride |

### Class C — The comparison was invalid though both numbers were real
| # | Defect |
|---|---|
| C1 | IQ9 throughput includes per-inference host I/O; Thor/Orin used `--noDataTransfers`. Thor's "saturated" number equals 1/latency exactly — zero overhead by construction, up to 1.3 ms/inference on the other side |
| C2 | Thor fp16 ranked against IQ9 int8 and Orin int8 — the exact error the accuracy section forbids, sign reversed |
| C3 | search-space asymmetry: Thor swept 3 configs, Orin ~8, IQ9 12 per model — "each at its own best" is not symmetric when effort differs |
| C4 | precision chosen per board rather than swept as an axis; IQ9 has hardware fp16 and was never measured in it |
| C5 | quoting a customer-specified operating point (128 tokens) that sits exactly on a 128-token chunk boundary — the single most favourable length in [1,256]; 129 tokens costs 2× |

### Class D — Statistics
| # | Defect |
|---|---|
| D1 | a 17–25% run-to-run noise floor sat unnoticed in the data as an accidental replicate, while 9% effects were reported as findings |
| D2 | a "linear model" fitted to two points that both fell inside one quantum → 6.6× extrapolation error |
| D3 | a "flat 1.45× across four context lengths" that is one measurement restated four times (both boards' prefill is flat, so the ratio is necessarily flat) |
| D4 | max-of-N over noisy configs quoted as a ceiling, upward-biased by ~1σ, with N differing per board |
| D5 | mixed estimators — headline computed by mean for two boards and median for the third |

### Class F — The tool reported something other than what you asked for
| # | Tool | Assumed | Reality |
|---|---|---|---|
| F1 | `tegrastats` on Orin | reports the board's power rails | reports **3 of 4**; silently omits `VDDQ_VDD2_1V8AO`, so DRAM power was never counted |
| F2 | `tegrastats` across boards | the same rails, comparably | different names, different groupings, and measured at **different voltages** (Thor 19.7 V at the barrel, Orin 12.1 V downstream of a conversion stage) |
| F3 | a power sample taken over 14 s | the mean power of the run | the run finished in **0.4 s**; the mean was mostly idle, reading 3.7× low and entirely plausible |

### Class E — Custody
| # | Defect |
|---|---|
| E1 | the shipped .xlsx/.md were never rebuilt after the source data was corrected — the colleague's copy still held six struck numbers |
| E2 | the builder declares "Source of every number: <file>" and **hardcodes every value, never opening that file** |
| E3 | a config string ("batch 4, streams=2") attached to a number whose real config was never recorded — belonging in fact to a different, uncalibrated sweep |
| E4 | an entire board's numbers (gate, 4 latencies, 12 throughputs) existed only in terminal scrollback — no artifact on the box |
| E5 | superseded blocks with no local supersession marker, including one named `THE_HEADLINE` |
| E6 | a measurement taken while an 8.2 GB model server was resident on the same GPU, under a census claiming "GPU idle" |

---

## PART III — THE RULES

### A. DESIGN — before anything is run

**M1 — The output gate ships with the number, or neither ships.**
Any timing of a model must be accompanied by evidence, produced by *the same artifact in the same
**invocation***, that the model computed something *correct*. Never a proxy from Class A.

> **TIGHTENED 2026-08-25: "same session" → "same invocation."** The original wording was *same
> session*, and it is too loose to do the job. The Orin int8 incident had a detection gate in the
> toolchain and a timing path that never called it — a gate run anywhere in the same *session*
> against a different artifact would have satisfied the old wording while proving nothing about the
> engine that produced the number. Two artifacts one token apart in filename
> (`yolov8n.int8.engine` / `yolov8n_cal.int8.engine`), both genuinely INT8, one detecting nothing:
> only a gate bound to the *same invocation* distinguishes them. Note what this does NOT change: the
> Orin number violated the old wording too, because no gate ran at all.
- Detector → detection count, max score, and class plausibility for a known image.
- LLM/VLM → a gradeable answer obtainable **only** from the supplied input.
- VLA → trajectory sanity against a reference.
> **CHECK:** the result record contains a `gate` object with a pass/fail and the observed values, and
> that gate ran in the SAME invocation against the SAME artifact. No gate object → the number does not
> exist. **Mechanised by `bench_data/tools/run_gate.py`**, which scores predictions against ground
> truth and stamps the verdict with the `artifact_md5` it judged; `emit_records.py` refuses a gate
> whose `artifact_md5` does not match the artifact being timed. That binding exists because a
> reviewer once dropped a resnet50 evidence file into the pipeline and it inherited yolov8l's COCO
> PASS verbatim — a fully "defensible" record for a model that had never been gated.
>
> *On documents written before the tightening:* several say a gate ran "in the same **session**, on
> the same artifact". That wording no longer demonstrates compliance on its face. It is not
> automatically a violation — the frozen colleague deliverable, for instance, carries that sentence
> and then states two lines later that all 16/16 engines were re-scored *in the same invocation as
> their timing* (2026-08-20), which satisfies the tightened rule in substance. Check the substance
> before rewriting the sentence, and **do not edit a frozen artifact to fix wording** — a shipped
> document is a snapshot in someone else's hands (see `campaign/FROZEN.json`).

> **AMENDED 2026-08-25 — the ungated-legacy clause, because the tightening created a debt and
> pretending otherwise would be the worse defect.** Tightening M1 to *same invocation* instantly put
> a set of already-published numbers on the wrong side of it: the GenAI decode rates (Orin eager /
> Orin compiled / iq9 QNN w4a16, re-measured 2026-07-16) are timings of models with **no
> output-correctness gate at all** — the harness reports tok/s and never looks at the generated text.
> Read strictly, M1 says those numbers do not exist. They do exist, they are in a shipped deck, and
> deleting them silently would be a worse outcome than saying so.
>
> So: **a timing with no output gate is not MEASURED for comparison purposes. It is
> `[MEASURED, UNGATED]`, and it carries the same restriction as DERIVED — it may be reported,
> labelled, never placed bare beside a gated MEASURED number, and never in a headline.** Every such
> figure is listed in `bench_data/campaign/ungated_timings.json` with the gate it owes. The register
> is the point: an exemption that is not enumerated is not an exemption, it is an erosion.
>
> ⚠️ **And it must be GENERATED, not hand-listed.** The first version of that register was written
> by hand, listed **11** figures, and asserted "Every such figure is listed". A generated sweep
> (`bench_data/tools/ungated_check.py`, in the pre-send gate) finds **84** — every llama.cpp decode
> figure, the whole iq9 qwen ladder, the ARA240 7B number taken with the random-input trick, the
> prefill and e2e families — and **zero** gated among them. A hand-listed exemption enumerates
> whatever its author remembered; this one enumerated a fifth of its own debt while claiming
> completeness, which is *worse than no register*, because it reads as a bound. M44 says generate
> counts rather than typing them; a register is a count of a set.
>
> *Limit of the check, stated:* it is a SOURCE-side test — it asks whether the cited raw record
> contains a gate object at all, not whether that gate was bound to the same invocation, which is
> what M1 actually requires. It therefore **under-reports the debt and never over-reports it**.
>
> This is not a loophole for new work. A NEW timing ships with its gate or it does not ship. The
> clause exists to make an existing debt visible and finite, and the register is how you can tell
> whether it is shrinking.

**M2 — Prove the gate can fail.**
Once per harness per session, run it against a deliberately broken artifact (needle removed, weights
zeroed, wrong expected value) and show it FAILS. An always-passing gate is indistinguishable from no gate.
- Motivated by A5 (a grep that could never match) and by 24/24 identical PASSes with no negative control.
> **CHECK:** the session log contains one recorded intentional FAIL.

**M3 — The gate must cover every output the number depends on.**
Not just the convenient one. If the model emits boxes *and* scores, check both — a collapsed box scale
is the mirror image of the bug we fixed and passes a scores-only gate. If the number is a batch number,
feed **different** inputs per slot with different expected results.
> **CHECK:** enumerate the model's outputs; each appears in the gate assertion. Batch gates use N distinct inputs.

**M4 — Query the independent variable back from the runtime.**
The thing you believe you varied must be read back *from the system under test, in the same run*, and
recorded. Not inferred from the flag you passed, the filename, or the input.
- context length → the runtime's own `n_ctx` (e.g. `llama-server /props`), **which is a different variable from prompt length — do not substitute one for the other**
- precision → the engine's actual per-layer precisions, not the build flag
- power mode → query it back
- batch → the binding shape reported by the engine
> **CHECK:** every swept axis has a `measured_value` field alongside its `requested_value`, and they agree.

**M5 — Sweep both sides, with comparable effort, and quote each at its own best.**
An asymmetric sweep is an invalid comparison even when every individual number is honest. Precision and
operating point are **axes of the sweep, not per-board defaults**: if board A is quoted at fp16 and
board B at int8, that is asymmetry regardless of local justification.
> **CHECK:** record the config count per board. If they differ, either close the gap or state the missing cells explicitly.

**M6 — Every sweep contains a deliberate replicate; the noise floor is published; no effect smaller than it is a finding.**
Run at least one configuration twice, non-adjacently. Report the observed disagreement as the harness
noise floor next to the results. Any claimed difference below that floor is reported as "indistinguishable".
- This alone would have caught D1 automatically — the replicate was already in the data, unrecognised.
> **CHECK:** `noise_floor_pct` present in every sweep record, derived from an actual repeated config.

**M7 — Probe either side of a quantum.**
If the runtime processes work in fixed blocks (chunked prefill, fixed batch, tiles, wavefronts), measure
at `k·q`, `k·q+1` and `(k+1)·q`, and publish the step. Never quote an operating point that sits on a
boundary without saying so.
> **CHECK:** for any blocked runtime, the record contains the block size and at least one measurement immediately past a boundary.

**M8 — Accuracy is measured at the configuration quoted for speed.**
Same batch, precision, streams, placement. Otherwise the speed row carries an explicit annotation that
accuracy was measured elsewhere.
> **CHECK:** the accuracy record's config equals the speed record's config, field by field, or a divergence note exists.

### B. EXECUTION — while it runs

**M9 — stdout is not an artifact.**
Every timing and gate run tees to a file **on the machine under test**, named
`<artifact>_<UTC timestamp>.log`. A number whose only home is terminal scrollback ceases to exist when
the session closes — and it will be the newest, most flattering board that has none (E4).
> **CHECK:** every quoted number resolves to a log file path on a named host.

**M10 — Tenancy is captured in the same log as the number, at the moment of measurement.**
Not once per session. A resident server or leftover process invalidates a census taken hours earlier (E6).
Record: accelerator utilisation, top processes by memory, power mode, clocks, temperature.
> **CHECK:** the log's tenancy block timestamp is within the run window.

**M11 — Chain of custody.**
A number resolves to: artifact **hash**, host, the config *actually used*, and the gate result *for that
artifact*. If the artifact is gone, the number is unverifiable — re-measure or strike it.
> **CHECK:** `md5`/`sha` recorded at measurement time, not reconstructed later.

**M12 — A runtime error is never a model result.**
Harness failures report in a distinct channel from wrong answers. A crashed, misconfigured or
never-started run must never be recorded as a failed gate — that reads as "the model got it wrong" and
sends you hunting the wrong bug (A3, A4 both presented this way).
> **CHECK:** the result schema has a `RUNTIME_ERROR` status distinct from `gate: FAIL`.

**M13 — State the envelope.**
Power class, power mode, thermal state, tenancy and clock mode travel with every cross-platform number.
Boards in different power classes may not be ranked on raw throughput without the envelope stated in
the same table.

### C. INFERENCE — what you may conclude

**M14 — Both sides must include or exclude the same overheads, shown numerically.**
Publish, per board, `quoted_metric / device_compute_only_metric`. If those ratios differ across boards,
the comparison is not like-for-like (C1: one side 0.57–0.96, the other 1.00).
> **CHECK:** the ratio is in the record for every board in a comparison.

**M15 — No model from two points; no extrapolation beyond the measured span.**
A fit needs ≥3 points spanning the range of interest, and the residual must be published. If the system
is quantised (M7), the model must be expressed in quanta, not per-unit.
> **CHECK:** `n_points`, `span`, `residual` recorded with any fitted relationship.

**M16 — A "ceiling" must show it is bounded by the device.**
Quote delivered throughput as a fraction of the part's peak alongside every saturated number. Below
~30% it is a floor, not a ceiling, and the limiter must be named. A "saturated throughput" that equals
1/latency contains no concurrency and is not a ceiling at all.
> **CHECK:** `pct_of_peak` and `limiter` present on any number called a ceiling.

**M17 — A cross-check must differ in the thing that could be wrong.**
Record build hash and model hash for both routes. Same codebase + same weights + same device = a
repetition, and must be reported as run-to-run spread, not corroboration. Never validate a number
against a row of the dataset it is meant to validate.

**M18 — Broken is faster.**
Any result that flatters the accelerator or beats expectation is triaged as suspected breakage before it
is celebrated. Write down what you checked to rule that out.

**M19 — If a caveat names a measurement that would change the ranking, make that measurement.**
"A perf/W comparison would rank them very differently" is a finding announced and withheld. Either
measure it or record explicitly why it cannot be measured.

### D. PUBLISHING

**M20 — The deliverable is an artifact under custody.**
A correction is not applied until the *sent file* is rebuilt and re-verified in the same commit as the
source-of-record change. **No builder may hardcode a value while naming a source it does not read; the
build must fail if the cited source is not opened** (E1, E2 — the reason correcting the data did not
correct the deliverable).
> **CHECK:** builder reads the JSON; CI fails on a hardcoded numeric literal in a data cell.

**M21 — A config label is a measurement, not a caption.**
Never attach a configuration string to a number unless that exact string came out of the same run
record. An unlabelled number is honest; a mislabelled one is a fabrication (E3).

**M22 — Supersession is local and machine-checkable.**
Every superseded block carries its own `_SUPERSEDED` key naming its replacement. A retraction written in
a neighbouring block does not travel with the number — and top-level blocks named `THE_HEADLINE` are the
ones most likely to be read without it (E5).
> **CHECK:** a linter walks the source of record and fails if any value appears in a deliverable while its block carries `_SUPERSEDED`.

**M24 — Build-to-build variance is a separate, larger noise source than run-to-run. Measure it once per model per toolchain.**
Rebuilding the *same* ONNX with the *same* flags does not produce the same engine — TensorRT re-selects
tactics, and every build has a different hash. MEASURED on Orin, 2026-08-17:

| | run-to-run (same engine) | build-to-build (same ONNX+flags, 3 builds) |
|---|---|---|
| yolov8n b1 fp16 | **0.26%** (2.15161 / 2.14600) | 0.8% (2.157 / 2.147 / 2.140) |
| yolov8l b1 fp16 | **0.18%** (10.0463 / 10.0281) | **8.4%** (9.611 / 9.581 / 10.381) |

So the floor that matters for *"engine A vs engine B"* is up to **32× wider** than the one you get from
repeating a run. Any comparison across separately-built engines — a rebuild, a different precision, a
different board's export — must be judged against the BUILD floor, not the run floor. A single build is
a sample of one from a distribution with an 8% tail.
> **CHECK:** any claim comparing separately-built artifacts cites a build-variance figure for that model/toolchain, or builds ≥3 times and quotes the median.

**M25 — MEASURE TWICE, CUT ONCE. The verification runs before the artifact ships, not after — and it is code, not a reviewer.**

This rule was bought expensively. One deliverable went through *three* build-review-fix
cycles. Each review found real defects; each fix pass introduced new ones — the third pass
closed 15 and created 8. That is not a review process, it is **cut, measure, cut again**.

Every one of the new defects had a single cause: **two artifacts, two mechanisms, patched
independently.** A workbook that read its numbers from the source and a markdown that
hardcoded them cannot be fixed together, so a correction landed in one and not the other.
Five disclosures ended up existing only in the workbook — and the markdown is the file that
gets forwarded.

Three corollaries, in order of force:

1. **One source, one mechanism, one cut.** If two artifacts can disagree about a number,
   eventually they will. Generate every artifact from the same data by the same code path.
   Two files that must agree are one file that must be generated twice.
2. **The check is part of the build.** A rule enforced by a reviewer is a rule enforced
   sometimes. Wire the verification into the builder so a failing artifact cannot be
   produced without an explicit override — `build → check → block`, not `build → ship →
   review → patch`.
3. **Every defect that ships once becomes a permanent test.** Not a note, not a habit — an
   assertion that fails the build. A defect that recurs was never actually fixed; it was
   only edited.

> **CHECK:** `results/bench_data/tools/deliverable_check.py`, invoked by the builder, exits
> non-zero on: cross-artifact disagreement, values from `_SUPERSEDED` blocks, "not measured"
> claims contradicted by the source, a blacklist of phrases that have already shipped wrong,
> numbers traceable to no source value, and claimed replicate counts exceeding the source.
> Each check exists because that exact defect reached a file that was about to be sent.

**M26 — THE TOOL DID NOT REPORT WHAT YOU ASSUMED. Enumerate the source, don't trust the summary view.**

Convenience tools silently omit channels, and the omission looks exactly like a zero.
Measured cases from this fleet:

| tool | what you assume | what it actually does |
|---|---|---|
| `tegrastats` on Orin | reports the board's power rails | reports **3 of 4** — silently omits `VDDQ_VDD2_1V8AO`, so **DRAM power is never counted** |
| `tegrastats` on Thor | same rails as Orin, comparably | different set, different names, measured at a **different voltage** (19.7 V vs 12.1 V) |
| `qnn-context-binary-generator` | applied your `vtcm_mb` | discards the whole config on a graph-name mismatch, **no error** |
| `trtexec --int8` | built an int8 engine | builds one with no calibration that detects nothing |
| `llama-bench -p 128` | ran at your context length | has **no context flag at all** |

The pattern: a summarising tool answers a *different question* than the one you asked, and
answers it confidently.

**Do this instead:**
1. **Enumerate the underlying source, not the friendly view.** Read `/sys/class/hwmon/*/in*_label`
   rather than parsing `tegrastats`; read the compiled artifact rather than trusting the build flag.
2. **Count the channels and assert the count.** If a board exposes 4 rails and your parser found 3,
   fail — do not silently sum 3.
3. **Check the units and the measurement point.** Two rails with similar names on two boards may be
   measured at different voltages, on different sides of a regulator, covering different blocks.
   Record volts and amps, not just watts.
4. **Name what is NOT covered.** "Sum of instrumented rails" is not "board power". Publish the
   coverage fraction where it can be computed (Thor: rails sum to 86% of `VIN`) and say **unknown**
   where it cannot (Orin has no board-input rail).

> **CHECK:** any power/telemetry record carries `channels_found`, `channels_expected`, the volts and
> amps per channel, and an explicit `coverage_vs_total` or `coverage: unknown`. A record whose channel
> count is below expected fails.

**M27 — The workload must outlast the sampling window.**
A corollary bought immediately after M26. Sampling power for 14 s across a run that finishes in 0.4 s
gives you a mean that is mostly idle — and it looks like a plausible number, 3.7× low. Drive the device
for a fixed **duration**, sample strictly inside it, and record both the run length and the sample
window so the ratio is visible.

> **CHECK:** every power record carries `run_duration_s` and `sample_window_s`, and fails if the
> sample window is not fully contained within the load period.

**M28 — A run that is implausibly FAST did not happen.**
Bought at 06:20 on 2026-08-18. After a wedged DSP, `qnn-net-run` returned for **1600 inferences in
10 ms** — arithmetically 160,000 IPS on a part whose real ceiling is ~1,200. Every instinct is tuned
to distrust a *slow* result; nothing distrusts a fast one, and the fast one is the direction that
flatters the accelerator. The floor is knowable: you cannot execute K inferences in less than
K × (fastest single inference ever observed on this part).

> **CHECK:** every timed run declares a `min_plausible_ms = K * per_inference_floor_ms`. A wall-clock
> below it is a **hard error**, not a record. The same check catches an exit that never ran the graph.

**M29 — Never SIGKILL an accelerator process.**
Same morning, same root cause. `kill -9` on `qnn-net-run` processes holding fastrpc mappings put them
in uninterruptible sleep (`D` state, where SIGKILL is inert) and left the Hexagon glink channel wedged:
`glink-edge: intent request timed out` every 10 s, `fastrpc:compute-cb@2: unmmap pt fd = 24 error`.
The board then ran **24× slow** while still returning plausible-looking numbers, and recovery required
a `remoteproc` stop/start. Two of my three measurement disasters this week began with a `kill -9`.

> **CHECK:** teardown sends SIGTERM and waits. Escalation to SIGKILL requires first confirming the
> process is not in `D` state; if it is, the device — not the process — is what needs resetting.
> Before any measurement, `require_quiet_board` must pass: zero accelerator processes, no orphans
> reparented to init, loadavg below threshold.

**M30 — MEASURED says a number came off a box. It does not say WHICH MODEL produced it.**
The whole of M1–M29 certifies pedigree and consistency; none of it certifies *identity*. An md5 is
recorded but bound to nothing. Swap yolov8n's engine for yolov8s, or an ONNX exported at 416²
instead of 640², and every check passes — faster, and in the direction that flatters the part. Every
headline in this corpus is a cross-board ratio, and nothing anywhere checks that the two sides are
the same computation.

**Amended 2026-08-19.** As first written this rule covered only the MODEL. Two further identity
gaps were then found the same way — by being bitten:

| what must be identified | the gap when it is missing | what it cost |
|---|---|---|
| **the measurand** — which model, at which opset | two binaries identical on every recorded attribute, 21% apart | a correct published figure was nearly retracted |
| **the instrument** — which piece of silicon | `hostname` returns `ubuntu` on both Jetsons; the device-tree *model* is identical across every unit of a type | two identical Thors would be indistinguishable in the record |
| **the execution** — which single run | nothing distinguished a record from a copy of another run's evidence | a copied evidence file validated clean |

The instrument is the accelerator, **not its carrier**. A discrete GPU moved to another host is
the same instrument; identifying it by motherboard would count one instrument as two, and two
cards in one chassis as one. Identity strength must be graded and recorded, because the available
sources differ per board and are not equally trustworthy:

- **STRONG** — a serial burned into silicon: GPU UUID (`nvidia-smi --query-gpu=uuid`), device-tree
  `serial-number` (Jetson), `soc0/serial_number` (Qualcomm), DMI product serial.
- **MEDIUM** — a NIC MAC. Hardware, but administratively reassignable.
- **WEAK** — `/etc/machine-id` alone. It looks unique and is stable across boots, but it is
  **cloned when two boards are flashed from the same image** — precisely the identical-units case —
  and it changes on OS reinstall. Simultaneously not-unique-enough and not-stable-enough.

> **CHECK:** every measurement record carries three separate identities, each captured in the same
> run: **`accel_id`** (the silicon that computed it, with its `identity_strength`), **`board_id`**
> (the carrier), and **`run_id`** (the single execution, unique per run so a copied evidence file is
> detectable). Plus the artifact fingerprint — input/output shape, op count, **opset**, and whether
> NMS is inside the graph. A cross-board comparison fails unless the artifact fingerprints match on
> everything but the backend; a cross-run comparison fails if two records share a `run_id`.

*Mechanised in:* `harness/board_identity.sh` (accel + board identity with strength grading),
`harness/collect_evidence*.sh` (run token), `tools/artifact_fingerprint.py` (measurand).

**M31 — Correctness is not binary, and the failure mode is DEGRADATION.**
The gates ask "did it detect *something*". A quantisation that halves mAP while raising throughput
passes M1, M2 and M3 — and the corollary says that error will flatter the accelerator. An adversarial
probe put five broken output tensors through the detection gate (every anchor saturated at 0.9; the
box branch replaced by pure noise; every detection the wrong class; 98% recall collapse; 9% degenerate
boxes) and **all five passed**. The gate images have ground truth. It never consults it.

> **CHECK:** a gate on a model with published accuracy asserts a *quantitative* floor against ground
> truth (mAP / top-1 within a stated tolerance of the fp32 reference), not merely "n_det > 0".

**M32 — A checker is code, and untested code is not a control.**
Thirty-seven crafted defects were run against this project's own verification tools; **thirty-five
passed.** Each tool caught faithful replicas of the defect it was built from and missed every
variation — they encode a specific past, not a class. One tool passed the exact trap cell quoted in
its own docstring. The single entry point reported ALL CLEAR over a fabricated 160,000-IPS record.

> **CHECK:** every checker ships a `--self-test` whose cases are *previously successful bypasses*, and
> the entry point fails if any self-test fails. A checker with no negative control is an assertion.

**M33 — Beware the rules that generate the bias they are meant to prevent.**
M5 says quote each platform at its own best configuration; that is max-of-N selection, which is
upward-biased, and D4 already documents it. Re-measuring only the *suspicious* claims biases the
surviving corpus toward whatever the first measurement flattered. And across ~746 claims with noise
floors near 17%, some "findings" are guaranteed false positives — M6 governs one comparison at a
time and nothing governs the family.

> **CHECK:** where a config is chosen as "best of N", record N and the spread, and report the median
> alongside. Any claim of a difference smaller than the family-wise noise floor is not a finding.

**M40 — A benchmark declares and ESTABLISHES its own environment. Ambient state is never an input.**
M10 says capture the tenancy. That is observation, and it is not enough: it records what the board
happened to be doing, which means the experiment inherits whatever was left running. A benchmark must
instead *specify* the environment it requires and then make it so — or refuse.

There are exactly two legitimate environments, and both are declared:

1. **QUIET** — nothing else runs. The benchmark verifies this before measuring and refuses otherwise.
2. **LOADED(stimulus)** — the benchmark **creates the load itself**, from a declared, reproducible
   stimulus that is *part of the experiment*. "Run Dhrystone on half the A-cores, then run the NPU
   benchmark, to determine whether core burden affects NPU control" is a complete experiment. The
   load is an independent variable, not weather.

Ambient load is neither, and must never be accepted. A measurement taken on a board that happened to
be busy is not a measurement of a loaded board — it is a measurement of an unknown.

*Cost of learning this:* two orphaned `llama-cli` processes from a killed parent pinned two cores of a
Thor for 43 and 59 minutes and pushed loadavg to exactly the refusal threshold. The quiet guard caught
it. But had the load been slightly lower, the run would have proceeded and produced depressed
tokens/second that looked entirely plausible.

*And it explains an earlier withdrawal:* this corpus withdrew a CPU-interference comparison because
"the memory stimulus applied to each board differed by up to 8×". Under M40 that cannot happen — the
stimulus travels with the benchmark, so it is identical by construction rather than by luck (M5, M35).

> **CHECK:** every evidence record declares `environment.intent` = `QUIET` or `LOADED(<stimulus id>)`.
> For QUIET the run verifies and refuses on failure. For LOADED the benchmark *generates* the stimulus,
> records its identity and parameters, and confirms it was actually running during the measurement
> window. A record whose declared environment does not match its observed tenancy is a defect, not a
> footnote — and an undeclared environment fails outright.

*Corollary:* the benchmark is the whole experiment, not the timed part of it. If a result depends on
CPU load, thermal state, a co-resident model, or a specific clock, generating that condition is
**inside** the benchmark's responsibility. Anything the experiment needs and does not create, it has
merely assumed.

**M41 — FRONT PORCH / HOUSE / BACK PORCH. A run leaves the board as it found it, and proves it.**
M40 says the benchmark establishes its environment. M41 says it must also *dismantle* it, and that the
proof of a clean exit is a mandatory part of the result.

**Front porch — before anything runs.**
Verify the board is idle (M40). Then stage the *complete* payload: the artifacts, the stimulus, the
run instructions, the output format, **and the teardown plan** — written down BEFORE the run, not
improvised after it. A teardown invented at the end only removes what its author remembers creating.

**The house — the run itself.**
Timed work, gated output, evidence captured. Watched by a watchdog that is **EXTERNAL to the board**.
This is not a preference; it is the lesson of a wedged IQ-9075: the DSP hung, and every on-board
observer hung with it. A watchdog sharing fate with the thing it watches is decoration. The external
watchdog must be able to answer "is it still making progress?" and to declare a run dead without the
board's cooperation.

**Back porch — after the run.**
Execute the teardown the front porch declared. Then run *the same idle check the front porch ran*.
That symmetry is the whole point: **a board that is not idle at the end was left dirty by this run.**
Residue is not limited to processes — check temp files, `/dev/shm`, loaded models, mounted images,
held device handles, and freed memory.

*Cost of learning this:* two orphaned `llama-cli` processes survived a killed parent for 43 and 59
minutes and blocked every later measurement on that board. Two orphaned `qnn-net-run` processes in
uninterruptible sleep wedged an IQ-9075 so thoroughly it needed a physical power cycle. Both were
detected by the NEXT run's entry check — which is to say, late, by luck, and only because an entry
check existed at all. An exit check catches the same thing immediately and attributes it correctly.

> **CHECK:** every evidence record carries `porch.entry` (idle verified, timestamp), `porch.teardown`
> (the plan declared up front, and what it actually removed), and `porch.exit` (the same idle check,
> re-run). A run whose exit check fails is marked `DIRTY_EXIT`: its numbers may still be valid, but the
> NEXT run on that board is refused until a human clears it — because the residue is now a confound for
> everything that follows. The watchdog's host and heartbeat interval are recorded, and an on-board-only
> watchdog fails the check.

*Corollary — the exit check is the entry check.* Do not write two. One predicate, run twice, is what
makes the property transitive across a campaign: if every run starts clean and ends clean, then a dirty
board has exactly one owner, and the log says who.

**M43 — A replicate must vary the thing that actually varies. Replicating at the cheapest level measures the wrong variance and manufactures false confidence.**
Three independent instances in this campaign, each one caught only because something later
disagreed with a number everybody trusted:

1. **Build level.** Three TensorRT rebuilds of one ONNX, made in one session on one
   toolchain state, agreed to **0.8%** — and were used to declare a historical figure "NOT
   reproducible." Running the historical artifact and a rebuild back-to-back on one board
   showed **+10.0%** between build *families*. The three rebuilds were not independent
   samples; they selected the same tactics. The cheap replicate understated the real
   spread **twelve-fold**.
2. **Invocation level.** Thor's documented run-to-run floor is **0.41%**, derived from
   `trtexec`'s own median across iterations *inside one invocation*. Four separate
   invocations of the identical command on an idle board spread **1.76%** — **4.3×** the
   documented floor. Every Thor comparison thinner than ~1.8% was therefore being read as
   a finding when it is noise.
3. **Aggregation level.** An IQ-9075 "replicate" that recomputed a derived aggregate
   rather than re-running the measurement reported a 25.5% floor that described the
   arithmetic, not the device.

The common shape: replication was performed at whichever level was *cheapest to repeat*,
and the variance that dominates lives at a level that is expensive to repeat. The result is
always the same direction — **tight agreement, high confidence, wrong number** — because
agreement among correlated samples looks exactly like precision.

> **CHECK:** every noise floor names the LEVEL it was measured at — within-invocation,
> across-invocation, across-build, across-boot, across-board — and a comparison must be
> judged against the floor for the level at which its two sides differ. Two numbers from
> different BUILDS may not be compared against a within-invocation floor. A record states
> `replicate_level` explicitly; "n=3" without a level is not a replicate count, it is a
> decoration.

*Corollary — agreement is not evidence of correctness when the samples share a cause.* The
question is never "did my repeats agree" but "what did my repeats allow to change".

**M42 — An input set is a measurand. It gets an identity, a home, and a hash — or it is not a condition, it is a rumour.**
M35 says everything except the variable under study must actually be the same. That rule is
*unenforceable* when the thing being compared has no name. On 2026-08-20, cleaning a scratch directory,
this was the actual state of the campaign:

- The 500-image COCO calibration set behind every published opset-12 batch-curve number existed **only**
  as preprocessed `.raw` tensors inside a `/tmp` session scratchpad. The source JPEGs were already gone.
  No hash of it existed anywhere in the repo. Deleting that directory — the explicitly authorised task —
  would have made every one of those numbers permanently unreproducible, and **no checker would have
  reported anything**.
- Worse: a **second**, near-disjoint 500-image COCO set was also on disk (503 tensors, only **3** in
  common by content hash — 0.6% overlap), identical in shape, dtype and file size. Nothing distinguished
  them but their parent directory name.
- The M35 checker reported **clean** throughout, because it compared `None` against `None`. Its own
  docstring promised that "not recorded fails the same as different"; the code implemented `va != vb`,
  and `None != None` is false. **The check was most silent exactly where the context was least known.**

The conditions were not wrong. They were *prose* — `int8` in a free-text field, "64 val2017 images"
inside a gate's human-readable observation. A checker cannot read prose, so a structured checker
inspecting a prose-only record finds nothing and says so confidently.

> **CHECK:** every input set that can vary between runs — calibration data, evaluation images, prompt
> sets, stimulus corpora — has (a) a **name**, (b) a **durable location outside any scratch or temp
> directory**, and (c) a **manifest with per-file and aggregate SHA-256** committed to the repo. Records
> name the set as a *structured field*, never only in prose, and the hash appears in `measured` as a
> genuine recomputation — not copied from `requested`, which M4/M21 already reject as a caption.
> A context field absent on **both** sides of a comparison is a **finding**, not a pass.

*Corollary — an artifact whose only copy is in `/tmp` is already lost; it just has not been collected
yet.* The cleanup that finds this is the one authorised to delete it, which is the worst possible moment
to discover the gap. Fingerprint on creation, not on eviction.

**M34 — Never derive a machine-meaningful key from a human-editable string.**
The `vtcm_mb` disaster was not really a config bug. It was an *identity* bug: the builder computed the
HTP graph name from the ONNX **filename stem**, and the runtime matched that key against the graph
name actually inside the binary. When they disagreed, the config was silently discarded — no error,
no warning, every binary we ever built running at half its memory budget.

The tempting fix is a cleverer name-deriver: strip suffixes, normalise case, try variants. That fix
is wrong, because **the filename is not a formal identifier.** It is under human whim. Someone renames
it for clarity, typos it, appends `_v2`, or decides "good enough, they'll figure it out." A string
nobody has agreed to keep stable cannot be load-bearing, and building an inference engine on top of
one just moves the failure somewhere harder to see.

Ask the authoritative source instead. The DLC knows its own graph name. The binary knows its own graph
name. Query it; do not deduce it. And where a name genuinely must be typed by hand, **type it and
verify it** — a human hardcoding the right string after reading it out of the artifact is more robust
than any parser, because the verification step is what carries the safety, not the derivation.

> **CHECK:** no identifier used to *match* anything (graph names, tensor names, layer names, node keys)
> may be computed from a path, filename, or label. It is read back from the artifact, and the run
> asserts that the key it sent was the key that was honoured (M4). If the authoritative name cannot be
> read, the build **fails loudly** rather than guessing.

*Corollary, generalised:* a name is a convenience for humans. The moment a name becomes a key, either
it is enforced by a schema or it is a latent silent-failure. There is no third option, and "we all
know the convention" is not a schema.

**M35 — Everything except the variable under study must actually be the same, and you must go looking.**
Every comparison carries a **shared context** that is not in any config file: the calibration set, the
dataset, the driver and firmware, the harness version, the ambient temperature, the input images. These
ride along invisibly. Nothing errors when they diverge, and the divergence is usually introduced by a
past decision that was reasonable at the time.

Instance: the IQ-9075 batch-knee table compares batch-1 at 1699 us against batch-4 at 1982.8 us. The
batch-1 models were quantised with **500 COCO train2017 images**; the batch-4 models with **8 crops of
a single JPEG**. The table's whole purpose is to isolate batch size, and batch size was not the only
thing that changed. Both facts were sitting in the source of record, one block apart.

**The trap is "similar but not the same."** Calibration is calibration; both sets are photographs; the
latency probably does not care. Every one of those is plausible, and each is a reason to not redo the
run. The engineer's correct reaction — *"crap, that step used the wrong set, this is going to take all
night"* — is not pedantry. It is the recognition that the cost of the redo is simply the price of
being allowed to make the comparison. **If you are not willing to pay it, you are not entitled to the
comparison; state the confound instead.**

> **CHECK:** a comparison record declares a `shared_context` manifest — dataset, calibration set +
> size + hash, driver/firmware version, harness version, precision, input set — for **every** side.
> The checker fails when any field differs between sides unless that field IS the variable under
> study. "Not recorded" fails the same as "different", because an unrecorded condition is one nobody
> verified.

*Why it needs to be mechanical:* this class is invisible to output gating. Both sides run, both sides
detect, both numbers are real. The defect is in the **join**, not in either measurement — so no amount
of checking a single run will ever surface it.

**M36 — An unexplained discrepancy BLOCKS. A caveat is not an explanation.**
On 2026-08-18 a rebuild disagreed with the published figure by 20% on one model. Every gate passed on
both builds. The document was written, verified, and about to be sent — carrying an honest caveat that
said *the reason is not established*. Chasing it instead found an ONNX opset that changed the on-chip
working set 9.5x, and proved the **published number was right and the rebuild was wrong**. Had it
shipped, the caveat would have been true, well-written, and would have retracted a correct result.

Writing down that you do not understand something is not a substitute for understanding it. The caveat
is what makes shipping feel responsible, which is precisely what makes it dangerous.

> **CHECK:** any disagreement between two measurements of the same quantity that exceeds the stated
> noise floor is a **blocking defect** until its cause is identified — not a footnote, not an
> UNVERIFIED tag. If it cannot be resolved, the affected claim is withdrawn, not published with a
> caveat. "We don't know why" is a reason to hold, never a reason to send.

**M37 — Corrections are PROPAGATED, not APPENDED.**
Two independent adversarial reviews of the same corrected deliverable reached the same verdict: the edit
was half-applied. The corrected value appeared in the section describing the correction while the
original value stayed live in the headline table, the caveats list and the summary — the ceiling
(928.1 vs 968.4), the noise floor (17.5% vs 0.73%), the spill (7.6 vs 28.4 MB) and the Orin vintage
(6.023 vs 6.038) each existed in **two live versions inside one document**. A reader quoting the table
quotes the dead number.

This is the same failure the whole standard exists to prevent, committed while fixing it. Appending
feels like diligence — the correction is *right there*, prominently, with a date on it.

> **CHECK:** a correction is complete when **no instance of the old value remains** except inside a
> retraction that names its replacement. Grep for the old value across every artifact before declaring
> the fix done; two live values for one measurand is a blocking defect (M36).

*Corollary — withdrawal cascades.* When a claim is withdrawn, every claim derived from it is withdrawn
in the same pass. A withdrawn premise left in place turns its dependents into nonsense: this corpus
briefly contained "YOLOv8L degrades **only** +26.0%" and "spills 5.5 MiB, so it is over the cliff"
where 5.5 MiB is comfortably *inside* the budget.

**M38 — The shipped artifact is the authority, not the log that describes it.**
The build log reported `spill_bytes=37,486,592`; the context binary that actually deploys reported
`31,850,496` for the same graph. Both were produced by the vendor toolchain, minutes apart. The log
figure was quoted in a deliverable without ever being checked against the artifact.

> **CHECK:** where a property can be read from the deployed artifact, that reading is authoritative and
> the log is corroboration. Any disagreement between them is itself a finding (M26), and the artifact
> value is the one that ships.

**M39 — A better method can produce a worse answer.**
The rebuild that got yolov8L wrong was better in every respect this standard asks for: gated on ground
truth, one calibration regime, a superior instrument, a 20x lower noise floor, full provenance. It was
also **wrong**, and its rigour made the wrong answer more persuasive than the right one it replaced.
The improvement had silently changed a variable nobody was recording.

> **CHECK:** when a re-measurement disagrees with a prior result, the burden of proof is on the NEW
> measurement, however much better its methodology. Reproduce the OLD result with the NEW instrument
> first — same board, same session — and only then trust the new number. Methodological superiority is
> not evidence.

**M23 — Provenance tags (existing fleet law, restated).**
MEASURED / DERIVED / SOURCED. Only MEASURED may appear bare or in a headline. **A DERIVED or SOURCED
number may never be compared against a MEASURED one.** An interpretation (e.g. "this is thermal
throttling") is DERIVED until a counter is read, and must be labelled as such.

---

## PART IV — THE RECORD SCHEMA

Every measurement emits this. If a field cannot be filled, the number is not publishable.

```json
{
  "value": 0.657227, "unit": "ms", "provenance": "MEASURED",
  "what": "yolov8n batch-1 fp16 GPU compute median",
  "host": "thor", "utc": "2026-08-16T08:49:35Z",
  "artifact": {"path": "/home/researcher/acc/yolov8n_b1.fp16.engine", "md5": "..."},
  "log": "/home/researcher/acc/thor_perf_20260816T084935Z.log",
  "config": {"requested": {...}, "measured": {...}},
  "gate": {"status": "PASS", "observed": "59 det >0.25, max 0.9272", "negative_control": "verified failing 2026-08-16"},
  "tenancy": {"accel_util_pct": 0, "top_rss": "...", "power_mode": "MAXN", "tj_c": 41.5},
  "stats": {"n": 3, "estimator": "median", "spread_pct": 0.15, "noise_floor_pct": 1.2},
  "overhead_ratio": 1.00,
  "status": "OK"
}
```

`status` ∈ `OK` | `RUNTIME_ERROR` | `CANNOT_RUN` (with reason) — never conflated with `gate.status`.

---

## PART V — PRE-FLIGHT CHECKLIST

Before the first real run of any campaign:

1. [ ] What exactly am I claiming, and what would make it false?
2. [ ] What is the gate, and **have I watched it fail?** (M2)
3. [ ] Does the gate cover every output the number depends on? (M3)
4. [ ] Can I read the independent variable back from the runtime? (M4)
5. [ ] Is the sweep symmetric in axes *and effort* across boards? (M5)
6. [ ] Which config is my replicate? (M6)
7. [ ] Is the runtime quantised — do I know the block size? (M7)
8. [ ] Do both sides include the same overheads? (M14)
9. [ ] Where on the box does the log land? (M9)
10. [ ] Is the box single-tenant *right now*, recorded in that log? (M10)
11. [ ] If the result flatters, what is my breakage hypothesis? (M18)

**The one-line test before publishing any comparison:**
> *Could this difference be produced by anything other than the thing I am claiming?*
> Enumerate the alternatives and say how each was excluded.

---

## PART VI — MECHANISATION

Rules that survive at scale are the ones a machine enforces. Priority order:

1. **Schema validator** — reject any record missing `gate`, `log`, `tenancy`, `artifact.md5`. Kills Class A and E at the source.
2. **Builder guard** — the deliverable build fails if it does not open its cited source, or if a data cell is a hardcoded literal. Kills E1/E2.
3. **Supersession linter** — fails if a value from a `_SUPERSEDED` block reaches a deliverable. Kills E5.
4. **Replicate enforcer** — a sweep runner that automatically re-runs one config and computes the noise floor. Kills D1.
5. **Negative-control harness** — a `--self-test` flag on every gate that runs the deliberately-broken case. Kills M2 drift.
6. **Tenancy hook** — pre/post capture wrapped around every timed run, written into the same log.
7. **Plausibility floor** — reject any run faster than `K x per_inference_floor`. Kills M28, and it is
   two lines of arithmetic.
8. **Quiet-board precondition** — refuse to start when the accelerator is already busy. Kills the
   contention class outright (`require_quiet.sh` on iq9). Kills M29 and M10 together.
9. **Void register** — an explicit list of dead values, enforced by exact match on every deliverable
   including .xlsx cells. Replaces the keyword-based supersession heuristic, which passed a cell that
   asserted a fabricated value using the word "corrected".
10. **Checker self-tests** — each tool's `--self-test` is a regression suite of bypasses that once
    worked. This is the only defence against tools that encode one specific past.
11. **Artifact identity fingerprint** — shapes, opset, op count, NMS-in-graph, captured in the same
    run. Without it a cross-board ratio is not known to compare the same computation (M30).
12. **Ground-truth accuracy floor in the gate** — the gate images have annotations; use them (M31).
13. **Identifier readback** — every match-key read from the artifact, never derived from a filename,
    with an assert that the key sent was the key honoured (M34). This is the cheapest of all of them
    and it would have prevented the single most widespread defect in the corpus.
14. **Shared-context manifest** — emitted per side of every comparison, diffed automatically (M35).
    Catches the one defect class that output gating structurally cannot see.
15. **Discrepancy blocker** — any two measurements of one quantity differing by more than the noise
    floor block the build until explained (M36). This is the check that would have saved the 2026-08-18
    deliverable, and the only thing that did save it was a human declining to ship.
16. **Correction completeness** — after any fix, grep every artifact for the old value; the build fails
    while two live values exist for one measurand (M37).
17. **Three-layer identity** — `accel_id` (which silicon), `board_id` (which carrier), `run_id`
    (which execution), each captured in the run and graded for strength (M30). Every one of the
    three was found missing by being bitten, not by inspection.
18. **Declared environment** — `environment.intent` = QUIET or LOADED(stimulus), verified for the
    first and *generated* for the second (M40). Turns the quiet guard from an observation into an
    experimental control, and makes cross-board stimulus asymmetry impossible by construction.
19. **Porch protocol** — entry check, declared teardown, exit check using the SAME predicate, plus an
    EXTERNAL watchdog (M41). Makes "who left this board dirty" answerable, and stops residue from one
    run silently confounding the next.

**M44 — Verify the RENDERED artifact, never the build that produced it. A build that reports success has proved that the code ran, not that the document says the right thing.**
This is the rendering-layer twin of the law that a passing run proves nothing about the output
(M31). It has now bitten this campaign five separate times, and every instance shared one shape: a
fix was applied to a *source* and its success was inferred from the *builder*, never read in the file
a human would open.

1. **Three fixes reported complete had never rendered.** They were applied to the source JSON, the
   build succeeded, and the changelog said "done." Neither artifact contained them. Caught by pass 5,
   by grepping the rendered files rather than the source.
2. **A commit message asserted a reconciliation that was not applied.** The script printed "1 optional
   items applied"; the message described three. The build was green throughout.
3. **"VERIFIED IN THE RENDERED ARTIFACTS" was itself unverified.** The verification consisted of
   grepping for the *presence* of a string, never reading the sentence around it — so a spliced
   sentence (`it.15.5%`) shipped inside the passage that claimed to have been verified. Presence is
   not correctness.
4. **A standing-claims gate enforced presence, not consistency.** The source held both a claim and its
   retraction; the gate confirmed both were present in both files and stamped the contradiction into
   both artifacts.
5. **Guidance prose lived in one artifact only.** A Method row of pure prose sat in the workbook and
   was absent from the markdown. The parity gate compares *numbers*, so it was structurally blind, and
   ten adversarial passes walked past it. Found by a human asking "did you update the README tab?"

**The rule.** A change is not complete when the builder exits zero. It is complete when the changed
text has been read *in every rendered artifact that carries it*. Concretely:

- **Read it, do not grep it.** Grep proves a string exists; it cannot see the sentence it landed in.
  Any automated presence check must be paired with reading the surrounding passage.
- **Render to every artifact, then check every artifact.** A single source is necessary and not
  sufficient — a source can render to one target and silently skip another.
- **Prose-only content needs its own parity gate.** Number-parity checks cannot see it. Every prose
  block must be either verbatim in all artifacts or explicitly declared as covered elsewhere, and the
  build must refuse when a block is neither.
- **A gate that has never fired is not evidence.** Every gate ships with a negative control that
  deliberately breaks it, and the control is re-run whenever the gate changes.
- **Generate counts, never type them.** Any count in a document (rules, checkers, sheets, sections) is
  computed at build time from the thing it counts. A typed count is stale the moment the thing grows;
  this document's own rule count is generated for exactly this reason.

The failure direction is consistent and worth naming: an unrendered fix always makes the document look
*more* correct than it is, because the changelog records the intent and the artifact keeps the defect.

**M45 — Verify that the work is present in the EMITTED CODE. A benchmark the compiler deleted is infinitely fast, and the number it returns is not absurd unless you look.**
Found by the A/B experiment of 2026-08-20, in which four independent arms on four boards hit this in
one afternoon. It is the founding law (M31) one layer below where we had been looking: M31 says a model
must be shown to produce correct output, but says nothing about whether the *measurement harness* still
contains the work it claims to time.

1. **The whole loop deleted.** A plain-C pointer chase compiled at `-O2` left **zero instructions**
   between the two `clock_gettime` calls. It would have returned a fast, perfectly quotable L2 latency.
   Caught by disassembling and requiring `16x ldr x0,[x0]` to be present.
2. **Constant-folded.** A `memchr` bandwidth loop was folded away because the compiler could prove the
   buffer was all 1s. It reported **14,000,000,000 MB/s** — caught only because that is absurd.
3. **Warm-up eliminated.** Warm-up and pilot chases removed because their results were unused, silently
   changing the cache state the timed region ran in.
4. **An elided-loop negative control** clocked **3.5e10 MB/s** — the signature of a loop that no longer
   exists.

**The rule.** For any hand-written microbenchmark, prove the work survived compilation:
- **disassemble** and assert the expected instructions are present, or
- use an **optimisation barrier** on the accumulated value, or
- **gate on a value the compiler cannot constant-fold** — a closed-form checksum of data it cannot
  predict, verified in the same run as the timing.

*"The source contains a loop"* is not evidence the loop ran. Neither is "it compiled", "it linked", or
"it produced a number".

**Direction:** one-signed, and severely. A compiler removing work always makes the machine look faster;
there is no optimisation that invents work. Case 1 above is the worst kind — the result was **not**
absurd, so nothing would have flagged it.

**Two of the four incidents were found by arms with no rules document and no checkers**, by disassembling
and by noticing impossible magnitudes. Neither behaviour was mandated by this document at the time. That
is why this rule exists: the harness was blind to its own instrument.

**M46 — Predict what CORRECT looks like before you measure. A gate with a threshold you guessed can only catch the failures you imagined.**
Found 2026-08-20 on the IQ-9075, and it nearly cost a published claim.

A generic MatMul with signed int8 Q/DQ was compiled by QNN into an **UNSIGNED**
`QNN_DATATYPE_UFIXED_POINT_8` with zero-point 0 — clipping **every negative activation to zero** and
destroying half the input distribution. The converter succeeded. The context binary built. The graph
ran. The output had the right shape, a plausible magnitude, and no all-zero tensor.

**And the timing was identical.** The run with catastrophically wrong quantisation and the run with
correct scales differ by **0.4%** (758 vs 755 µs). This is not "broken is faster" — it is *broken is
exactly the same speed*, which is worse, because there is no anomaly to notice. Timing cannot see this
defect in either direction.

**What caught it was arithmetic done in advance.** Before running, simulate the operation at the
intended precision and compute the accuracy a CORRECT implementation should achieve. Here that
prediction was cosine **0.999877**. The measurement returned **0.710964**.

**A generic threshold would have passed it.** "cosine > 0.7" — a number that sounds strict — accepts
this result. The gate worked only because the expected value was computed first, from the same inputs,
rather than chosen because it felt demanding.

**And the prediction identifies the MECHANISM, not just the failure.** Simulating the suspected fault —
activations clipped to unsigned — reproduced the measured output at cosine **1.000000**. That is the
difference between "something is wrong" and "the converter dropped the sign bit": the first is a
caveat, the second is a bug report.

**The rule.** For any quantised or reduced-precision run:
- compute the expected accuracy by simulating that precision on the host, from the same inputs;
- gate against THAT number, not a round one;
- when it fails, simulate the suspected mechanism and require the simulation to match the measurement
  before naming a cause.

**Corollary — a silent precision downgrade is invisible to every check except output.** Not to the
build, not to the logs, not to the tensor shapes, not to the clock. See M31 and M45; this is the same
family, and it is the member with no timing signature at all.

---

## AMENDMENT

This document is amended by *finding a new way to be wrong*, not by opinion. Adding a rule requires
citing the defect that motivated it, in the Failure Register, with evidence. Rules are never removed
because they are inconvenient — only when the failure mode they prevent has become structurally
impossible (e.g. mechanised away).

---

**M47 — When you compare a fresh measurement against a published one, name the CELL you compared against. A sound measurement can still produce a false verdict.**
Found 2026-08-21, in my own re-measure record, hours after writing it.

`fleet_triad_2026-08-21.json` recorded two defects that did not exist:

    "o6_aggregate":   {"published": 27.6, "measured": 40.749, "verdict": "UNRECONCILED (48%)"}
    "orin_aggregate": {"published": 43.0, "measured": 61.309, "verdict": "UNRECONCILED (43%)"}

The O6 dossier's table header reads `| Benchmark | 1-thread | multi-thread | fleet context |`.
So **27.6 is the SINGLE-thread cell** — I compared it against my *aggregate*. And **43.0 is O6's
multi-thread cell** — not an Orin figure at all. Paired correctly, three of four agree within 5.2%:
O6 1t −3.5%, O6 agg −5.2%, imx95 agg +0.4%. The corpus was right; my verdict manufactured two
phantom defects and put "UNRECONCILED" into two builders before I caught it.

**Every measurement-class control passed.** The binary was fingerprinted (md5
`cf3426083a4ae1b51fb8ae3f78d07573`), the checksum was exact (M46 — 74666662.0 on all 8 runs), the
emitted code was disassembled (M45). Nothing about the *measurement* was wrong. This is the
**RELATION** class — number against number — and reproduction cannot detect it, because repeating a
correct measurement reproduces the same correct number and the same wrong comparison.

It is also the *inverse* of the usual failure. The rest of these rules exist because a number was
too good; this one exists because a verdict was too harsh. **A checker that manufactures false
defects is not "safely conservative" — it spends the same credibility as a missed one, and it
pushes real deliverables toward wrong values.** I had already edited two builders.

*The rule:* any record citing a published value must carry a sibling field naming its origin — a
cell, a column, a table, or `file#key`. Naming it is what makes a mispairing visible, to the next
reader and to the author. Enforced by `tools/comparison_pairing.py`; it found **24** unpaired claims
on first run, including every record I had written that day.

*Corollary:* read the table HEADER, not the value ordering you assumed. Both errors here were
column-position guesses that a two-second look at the header would have refuted.

---

**M48 — A ZERO IS A CLAIM ABOUT THE HARNESS UNTIL A POSITIVE CONTROL SAYS OTHERWISE. Never record a
null, zero, or degenerate result without a same-harness control that produced a non-null one.**

Earned across 2026-08-23 and 2026-08-24, four times in three different tools. (An earlier draft of
this rule said "three times in one day"; instances 1 and 2 are dated 2026-08-23 in
`xboard_quant/XBOARD_QUANTIZER_RESULT.json` and instance 3 on 08-24. The compressed arc was
narrative, and a rules document that demands cited evidence may not itself round its own chronology.)

**Instance 1 — the harness was wrong.** Driving the iq9's int8 YOLOv8 for the cross-board quantiser
audit returned **zero class scores on every image**, with boxes that did not change when the input
changed. Read at face value: *every int8 model on the fleet's reference part is broken* — a BLOCKER
against a vendor. It was mine. The board's validated path reaches the accelerator through a TFLite
delegate with NHWC/uint8 inputs; I was feeding NCHW tensors to context binaries from a different
artifact family. The board's own known-good path returns 5 detections at 156 FPS.

**Instance 2 — the ENGINE was wrong, and it was OURS.** Later the Orin produced the **identical symptom**, zero detections, and there the artifact
really was broken: an int8 engine built with no calibrator. Two corrections to how this was first
written. First, that engine was **built by our own benchmarking pipeline**, not shipped by NVIDIA —
`orin_full.json` already described it as *"TensorRT INT8 (perf-only … NO calibration cache)"* with
*"DETECTION ACCURACY IS INVALID — do not quote mAP"*. Second, and worse for us: **the caveat already
existed and the zero still reached a cross-board comparison table.** A warning written in one record
does not travel with the number into the next one. The *only* thing that
separated instance 1 from instance 2 was running a **control on the same runner** — an fp16 engine
that detected fine, proving the runner sound and the engine broken. Without it I would have shipped a
false accusation against one vendor and a misdiagnosis of **our own build** as the other's silicon —
with equal confidence in both.

**Instance 3 — and this is the one that would have entered the corpus.** An NVMe-vs-UFS fio comparison
returned **0.0 MB/s on all eight tests** and wrote a well-formed record, `"tag": "MEASURED"`, correct
units, reproducible, with an immaculate provenance chain. `fio` could not load `libaio` (the `.so.1`
exists; the loader symlink does not), every job died, and the parser turned "no output" into `0.0`.
Nothing in the record said so. **A zero is the most publishable wrong answer there is: it needs no
excuse, it survives every provenance check, and no reader questions it.**

*The rule:*
1. **A null/zero/degenerate result is a finding about the measurement path, not the device, until a
   POSITIVE CONTROL on the SAME harness returns a non-null result.** fp16 where int8 read zero; a
   known-good model where the model under test read zero; any run that proves the pipe carries data.
2. **Harnesses must fail loudly, never default.** A parser that cannot find a value must say so in the
   record and in the log. `${x:-0}` is how a broken run becomes a measured zero. Emit
   `RETURNED NOTHING — do not trust this row`, and never a bare number.
3. **This is not covered by reproduction.** A broken harness reproduces its zero perfectly, on every
   run, on every board.

   *What this adds over M31 and M46, stated plainly, because the overlap is real and a reader is
   entitled to know which rule to reach for:*
   - **M31** (*correctness is not binary; the failure mode is DEGRADATION*) demands a quantitative
     floor against a reference rather than a did-it-detect-anything gate. Where a model produces
     gradeable output, M31 **does** catch a zero, and catches it instantly — a non-detecting detector
     scores mAP 0 and fails any floor. That covers instance 1 and instance 2. What it does not reach
     is a zero from a measurement with **no model output to grade at all**: the fio storage record
     had no mAP, no reference and no prediction — just a bandwidth field reading `0.0`, which is a
     perfectly well-formed value. M31 assumes there is something to score.
   - **M46** (predict what CORRECT looks like before you measure) would catch instance 3 — a predicted
     NVMe sequential read of ~3 GB/s makes `0.0 MB/s` fail on sight. It would NOT catch instance 1 or
     the amendment: at the time, "the iq9's int8 models detect nothing" and "UFS sustained writes are
     bad" were both *plausible predictions*, and the amendment's zeros arrived beside correct reads
     that made the run look predicted-shaped. (This gloss was corrected on 2026-08-25: an earlier
     draft claimed M31 "gives the right instruction and no traction" against any zero, which
     overstated the gap by ignoring M31's mAP floor.)
   - **M48 adds the control.** Neither M31 nor M46 tells you to run a *second* thing. The specific act
     that separated instance 1 (my harness) from instance 2 (the artifact) was an fp16 engine on the
     same runner — not inspecting harder and not predicting better, but producing a non-null result
     through the same pipe. That is the new obligation, and it is why this is its own rule rather
     than a clause appended to either of the other two.

*Corollary, with its limit stated:* the direction of the error is not always flattering. A zero
throughput or a zero detection count makes the part look WORSE — which is why it can survive a reviewer
who is only watching for numbers that are too good. **But this does not hold for every instance here.**
Instance 2's *published* measurand was 82.9 FPS on an engine doing no work — squarely inside the
directional-bias law, and the corpus itself calls it textbook broken-is-faster. M48 covers a case the
directional law does not (instances 1 and 3, where the degenerate value is the reported one), rather
than superseding it.

**AMENDED THE SAME DAY — the first implementation of this rule missed the next instance.** Within the
hour, the same storage harness produced zeros again, and the M48 guard I had just written **did not
fire**. The guard tested `[ -z "$bw" ]` — *did the parse return nothing?* — but the defect was a
parser reading the **wrong field**: `fio`'s JSON carries both a `read` and a `write` object per job,
and grepping the first `"bw"` returns the **read** object, which is a legitimate `0` for a write-only
job. The value was not missing. It was present, well-formed, and wrong.

Note the shape: **reads were correct** (1717 MB/s UFS, 3225 MB/s NVMe) while every write read zero. A
*partially*-correct harness is more dangerous than a dead one, because the correct half certifies the
broken half — the zeros looked like a real device finding, and they would have "confirmed" a known UFS
write weakness with a far more dramatic number than the truth (203 MB/s direct).

*The rule, amended:*
4. **Absence-checking is not enough. A zero that was never positively confirmed is as suspect as a
   missing value.** Do not merely ask "did I get a value?" — ask "did this value come from the field
   I think it did?" Parse structurally (`job['write']['bw']`), never positionally (`head -1`).
5. **A partially-correct result does not vouch for its other half.** When some rows of a run are
   plainly right and others are degenerate, the working rows are evidence the *tool* runs, not
   evidence the *broken rows are data*. Gate each measurand on its own control.

**CHECK — `results/bench_data/tools/null_result_guard.py`.** Clause 2 is the clause a machine can
hold, so that is the one mechanised. The guard walks every results JSON under `remeasure/` and
`campaign/`, finds every measurand-shaped field that reads `0` or `null`, and reports the ones whose
own object says nothing about it. It deliberately does NOT try to judge whether a zero is true —
nothing can, from the record alone — only whether it is **silent**, which is the exact property the
fio record had: eight `0.0 MB/s` values, `"tag": "MEASURED"`, correct units, immaculate provenance,
and not one word anywhere in the object saying the jobs had died.

Three things it will not catch, named here so the next reader does not mistake a green run for
compliance. It cannot see a wrong *non-zero* number (the amendment's real defect was a `0` in the
read section of a write-only job — caught, but only because the value was zero; had the read section
held a real number the guard would have passed it). It cannot verify that a disclosure is TRUE, only
that one is present. And it checks records, not runs: a harness that never wrote the zero down at all
is invisible to it. Clause 1 — *go run a positive control* — remains an instruction to a person.

That this rule's own first mechanism failed against its own next instance is the point, not an
embarrassment: a guard encodes the specific past it was written from. See the campaign's standing
lesson that a checker does not merely miss things — it teaches its blind spot to everyone who trusts
it.

---

**M49 — NEVER PIPE A COMMAND THAT WRITES THROUGH `head` OR `tail`. A viewing convenience can change
what the command DID, and it fails looking exactly like success.**

Earned 2026-08-25, on this file's own toolchain, and it is the second instance of the family in a
single session.

**Instance 1 — the register that was never written.** `single_board_check.py --md REGISTER.md` prints
a summary and then writes the artifact. Run as `… --md REGISTER.md 2>&1 | head -12`, `head` closed the
pipe after twelve lines, python took `SIGPIPE`, and the process died **before reaching the write**.
The summary had already been printed, so the console showed the new counts (229/50/179) while the
committed file still carried the old ones (164/48/116). The command appeared to succeed. Its visible
output was correct. The artifact was untouched, and it was committed in that state.

**Instance 2 — the bus watermark.** `bus.sh check` displays a batch of messages *and advances a
read watermark over everything it processed*. Piped through `tail`/`head`, it marks all of them read
while showing you N lines. This one already had a standing rule against it; I did it anyway, in this
same session, an hour before instance 1.

*The rule:*
1. **If a command writes, mutates, or advances anything, do not pipe it into a pager or a truncator.**
   Redirect the whole output to a file and read the file, or let it run to completion and read the
   artifact it produced. The truncation you wanted was of your *reading*, and you applied it to the
   *process*.
2. **`SIGPIPE` failure is invisible in the worst possible way.** The exit status you see belongs to
   `head`, which succeeded. The output you read is real — it is simply the output of a run that then
   died. Nothing anywhere says so.
3. **Reading a summary is never evidence about a file.** This is M44 restated, and instance 1 is its
   sharpest case: the console was not merely insufficient, it was *actively misleading*, because it
   was correct output from a process that never finished.

> **CHECK:** no pipeline in a harness, a builder, or a session transcript may place `head`/`tail`
> downstream of a command with side effects. Grep is the mechanism a person applies:
> `grep -nE '(--md|--record|--write|--out|check)\b[^|]*\|\s*(head|tail)'`. It is a linting heuristic,
> not a proof — a script whose side effect is not visible in its flags will pass it.

*Why this is its own rule and not a footnote to M44.* M44 says verify the rendered artifact. It
assumes a build that ran. M49 is about a build that **did not run**, while reporting as though it
had — the same relationship M48 has to M31. Three rules, one shape: the evidence you are looking at
is downstream of a step you never checked actually happened.

---

**M50 — A RESULT THAT INDICTS SOMEONE ELSE IS A HARNESS FINDING UNTIL IT REPRODUCES THROUGH THEIR
OWN KNOWN-GOOD PATH. And the review asymmetry is not "flattering vs unflattering" — it is
"expected vs unexpected."**

Earned twice inside a single audit, on two different boards, two days apart. The second one shipped.

**Instance 1 — caught.** Driving the IQ-9075's QNN context binaries with NCHW/uint8 tensors, where
the board's validated path is a TFLite delegate expecting NHWC, returned **zero class scores on every
image**. Read at face value: *every int8 model on the fleet's reference part is broken* — a BLOCKER
against a vendor. Running **the board's own documented path** returned 5 detections at 156 FPS. The
harness was mine. It is recorded in the audit's own `harness_near_miss` field.

**Instance 2 — not caught, and published.** The same audit concluded that the O6's CIX Zhouyi int8
path **over-detected 3.4×** (1152 detections against a 339-detection fp32 reference across 64
images). It became a **red headline in `O6_BOARD_DOSSIER.md`** and a **contribution in the paper**.
Re-measured two days later on the *same* 64 images with artefacts verified byte-identical by md5 and
mtime: **346 detections — 1.02×, faithful. Zero of 64 images reproduced their recorded count**, and
the per-image numbers track the fp32 reference (16→17, 17→16, 24→24, 7→6).

The record's own proof line was the evidence against it. It captured `out S8 scale=1.000 zp=0`, read
as "the classic missing-scale symptom". The tensor descriptor on the board reads
**`scale=256.148 zp=127`**. The runner dequantises `(raw + zp)/scale`: with the true constants that
maps int8 onto `[0,1]` — where a post-sigmoid class score must live — and with identity constants the
raw integers pass through untouched, so hundreds of anchors clear a 0.25 threshold and survive
class-agnostic NMS as spatially distinct boxes. **A failed descriptor read, published as a vendor
defect.**

*The rule:*
1. **Before writing down that someone else's toolchain is broken, reproduce it through THEIR
   documented path, on THEIR sample.** Two backends disagreeing is a harness finding until proven
   otherwise. This costs minutes; the alternative cost a retraction in two shipped documents.
2. **Check the values your proof line prints — do not merely print them.** A proof line is only proof
   if someone compares it against what it *should* say. `scale=1.000 zp=0` was sitting in the record
   the whole time, correctly captured and never checked against the descriptor.
3. **Prefer a physical-range check to a symptom story.** A post-sigmoid class score outside `[0,1]`
   is *impossible*, so it settles a scale question in one line and without a hypothesis. Reaching
   instead for "this looks like the classic missing-scale symptom" is how a plausible mechanism
   becomes a published cause.

> ## ⭐ **This narrows the directional-bias law, and the narrowing is the important part.**
> The standing law is that a broken measurement usually **flatters** the accelerator, because
> faster-and-wrong survives review. This error ran the **other way** — it made a vendor look worse —
> and survived anyway. So the asymmetry was never really about direction. **A finding that confirms a
> suspicion is scrutinised no harder than a finding that flatters you.** Both are *expected*, and
> expected results are the ones nobody re-runs. Ask of any result: *was I already prepared to believe
> this?* If yes, that is the one to reproduce.

*Corollary — do not let a suspect finding cross-flag a second claim.* On the strength of the 3.4×
result I flagged the O6's separate 12.6 fps ADAS figure as resting on a compromised detection gate,
and had to withdraw that the same day. **A cross-flag propagates a wrong finding into a claim that
was never wrong**, and the withdrawal costs twice: once for the original, once for the collateral.

> **CHECK:** any record whose verdict names a third party's component as defective must carry a
> `vendor_path_control` field — the vendor's own path, on the vendor's own sample, with its result —
> or the verdict is downgraded to "unreproduced". See `campaign/void_register.json` entry `1152`,
> whose `trap` field records the review asymmetry above.

---

**M51 — A CHECK THAT DID NOT RUN LOOKS EXACTLY LIKE A CHECK THAT PASSED. Prove the mechanism can
FIRE before you believe it is silent.**

M48 says a zero is a claim about the harness. M51 is the same claim about the *verifier*: a green
result means either "I looked and found nothing" or "I never looked", and nothing in the output
distinguishes them. Earned four times on 2026-08-25, in four different mechanisms, all reporting
clean.

**Instance 1 — a builder that never ran.** `build_bench_deck.py` acquired a SyntaxError from an
edit. Every subsequent rebuild failed, and every one was invoked as `python3 builder.py
>/dev/null 2>&1`. The shipped deck kept its pre-edit content while the source said otherwise. Then
`build_freshness_check --record` stamped that state as the baseline, so the staleness checker
reported **0 stale** over a deck that had never been built. *A build that never ran and a build
that ran and changed nothing leave the identical trace: an untouched file.*

**Instance 2 — a self-test that tested a copy of the code.** `count_sync`'s historical-marker regex
had been written with double-escaped backslashes and could never match anything. **The self-test
passed**, because the test had reimplemented the same logic with a correct regex. *A self-test that
reimplements the code under test proves only that the reimplementation works.*

**Instance 3 — a checker whose paths did not resolve.** `ungated_check` reported "0 ungated, 0
gated" — because its source-path resolver omitted the base directory the registries actually use,
so all 84 timings were unresolvable and none were classified. Zero of zero reads exactly like a
clean corpus. (`build_freshness_check`'s own first version failed the same way: 0 stale, 0
clobbered, entirely inert, because builders name paths as bare basenames.)

**Instance 4 — a gate that could not fail.** `presend.py` was called "the pre-send gate", ran 20
checkers, and always exited 0: it treated a checker's rc 1 as success and never read the finding
counts. A run with fifty silent zeros passed.

*The rule:*
1. **Read the exit code, never the silence.** `>/dev/null 2>&1` on a command whose success you are
   about to rely on is the same defect as `${x:-0}` in a parser (M48 clause 2). If a build must
   succeed, assert that it did.
2. **A self-test must call the production code path.** No reimplemented regex, no parallel
   helper, no copied constant. If the test and the code can disagree, the test is measuring the
   wrong thing.
3. **Every checker needs a NEGATIVE CONTROL: plant the defect it exists to catch and watch it
   fire.** This is M2 ("prove the gate can fail") applied to the checkers themselves, and it is the
   only thing that distinguishes the four instances above from a clean corpus. Each one was found
   by planting, never by reading the code.
4. **Suspect any all-or-nothing result.** "0 of 0", "none found", "everything passed" — these are
   the shapes an inert mechanism produces. Ask what a *non*-zero result would have looked like, and
   whether this run could have produced one.

> **CHECK:** every tool under `bench_data/tools/` exposes `--self-test`, `presend.py`'s own
> self-test asserts that every such tool is wired into the gate, and `presend.py` exits non-zero on
> any finding (verified by planting a silent zero: exit 1; removing it: exit 0). `rebuild_all.py`
> reads every builder's exit code and diffs deliverables semantically;
> `build_freshness_check.py --record` refuses to baseline a broken or stale tree.

> ## ⭐ **AMENDED 2026-08-25 — independently reproduced in another domain, and sharpened by it.**
>
> The `holobench` session, running a real-silicon networking lab that shares nothing with this
> corpus but the shape, arrived at the same law the same week from four instances of its own: *a
> claim that outruns the vantage that produced it*, where **four separate times a step that never
> ran was scored as a wire failure** — a crashed writer, a peer whose beacon never started, a field
> parsed from a log that had not ended, a credential never captured. In every case the wire was
> fine. Their generalisation: **every participant in a measurement must prove it participated.**
>
> **The polarity is the part neither of us had alone.** This corpus's four instances are *green
> verdicts from checks that never ran*. Theirs are *red verdicts from steps that never ran*. Same
> defect, opposite sign — and the two fail differently:
> - a **false green is invisible**; nobody investigates a pass;
> - a **false red is loud and MISDIRECTING** — it sent people to the wire while the fault sat in the
>   harness, which costs more than silence because it spends effort in the wrong place.
>
> **A third variant belongs beside them: the instrument that did not measure the thing.** Reading
> `tegrastats` GR3D_FREQ at 0% during a CUDA decode nearly put "the Orin GPU does nothing" into this
> corpus. GR3D is the *graphics* engine and does not count CUDA compute. The check ran, the number
> was real, and it was about something else. So the family is three — and they are **not** equally
> catchable. Ordered by difficulty (the other session's observation, and it is right):
>
> | variant | trace it leaves | catchable by |
> |---|---|---|
> | step never ran | a **red** that misdirects | the loudness itself, eventually |
> | check never ran | a **green** that is too quiet | an all-or-nothing result; a negative control |
> | instrument measured the wrong quantity | a number that is simply **true and irrelevant** | nothing automatic — only knowing what the instrument counts |
> | **claim decayed by repetition** | **a citation with no artifact under it any more** | **re-deriving it from the artifact at the moment of citation** |
>
> The third is bad because nothing about the reading is anomalous: no dispersion check and no
> negative control catches it, and the value survives every automated cross-check *because it is
> correct*. **The fourth is different in kind and was contributed by the other session from its own
> twelfth instance** — a "three consecutive clean runs" claim asserted five times across two days,
> unchallenged by three sessions, on exactly **one** preserved transcript. It fits none of the three
> catch-mechanisms: nothing was planted, no number looked wrong (333 and 307 were correct and
> "three" is unremarkable), and the only person who could have known was its author. What caught it
> was being **about to cite it** to someone who would act on it, and re-deriving from the artifacts
> instead of from their own earlier messages.
>
> **A claim decays by repetition.** Each restatement makes it more established and less examined,
> so the fifth telling has four citations behind it and still one transcript under it — which is
> the mechanism sentence again: *a claim that has survived four retellings has already survived
> every reading its author was going to give it*, for exactly the reason a working defect has.
>
> ⭐ **And the fourth row is a DISCIPLINE, not a DEFENCE.** The other three are things you build;
> this is something you *do*, at a moment identifiable in advance — **whenever you are about to hand
> a number to someone who will act on it.** It is also the cheapest: provocation costs a deliberate
> defect, a fresh reader costs another agent, an anomalous number costs luck. This costs re-reading
> your own evidence before spending someone else's trust on it.
>
> *We have an instance of it too, and it was caught the same way.* This corpus's own adversarial
> finding curve was quoted from memory across many messages and **never recorded**. It surfaced only
> when `claude-connect` was about to print it on a slide, found two of our restatements
> irreconcilable, and refused to pick one — citation-time re-derivation performed by the citer
> rather than the author. `tools/audit_curve.py` now generates it from commits, and the generated
> curve does not match either remembered version.
>
> **The claim worth publishing is about METHOD — and it took two narrowings to state correctly,
> which is the best evidence for it.** The first draft said *not one of these was found by reading
> code*. The other session audited its own commits against that and produced **counterexamples**:
> three defects it had caught prospectively, by reasoning about a `sudoers` rule and a spec before
> either was exercised. Its narrower form — *no defect that had **already fired** was found by
> reading* — is better: reading finds what you are about to do wrong; provocation finds what you are
> already doing wrong **and being rewarded for**.
>
> Auditing our own four against *that* produced one more counterexample, and it moves the variable.
> `presend.py` had been exiting zero on runs containing findings — already firing, already producing
> a plausible result — and it was caught by **reading**. But not by us: by an adversarial agent that
> had not written it.
>
> So the form that survives both audits is about **who reads**:
>
> > Across two independent sessions and sixteen instances, **no already-firing defect of this class
> > was found by its own author reading their own code.** Each was caught by exactly one of four
> > things: provocation, an anomalous *number*, a reader who had not written the code, or
> > **re-derivation from the artifact at the moment of citation**.
>
> And the mechanism is why this is not just "review is weak": **a defect already producing a
> plausible result has, by construction, already survived every reading its author was going to give
> it.** That is what makes the class invisible — it has *already passed one review*. A fresh reader
> has not yet been survived; a planted fault does not care who is looking. This sharpens the
> three-catcher division rather than replacing it: the author catches hazards **before** they fire;
> the independent reader and the mechanical gate catch what is **already** firing; the author
> re-reading their own work catches neither.
>
> *And the rule earned its keep on the artifact it was handed to.* Pointed at their own
> `prove-oracle-bites.sh` — the control that made their headline a result rather than a green — it
> asked what proves the CONTROL can detect a board whose oracle cannot refuse. Nothing had. It would
> have reported `controls_held=4/4` against a receiver accepting everything, provided that receiver
> stayed quiet, and it had done so across every clean run while being quoted as the evidence. ⚠️ RUN COUNT CORRECTED 2026-08-26: this sentence said "three clean runs". The other session corrected that number ON THE BUS on 2026-08-25 — first to "three observed, one preserved", then, after catching a SECOND decay of the same claim, to the accurate **four runs observed, two with preserved transcripts**. Neither correction propagated here, because they audited their own copies and I never checked mine. That is their own finding — "I audited the claim; I did not audit its copies" — extended one hop further: a correction has to cross SESSION boundaries too, and the citing session is the copy nobody owns. They
> planted a body-gate-stripped oracle; the control noticed. **And they meta-verified it against this
> rule's own instance #2** — substituting a healthy oracle makes the new test fail, so the test that
> proves a gate can fail is not itself a test that cannot.

---

**M52 — "THE ORIGINAL DATA IS UNRECOVERABLE" IS A CLAIM ABOUT AN ARTEFACT, NEVER A REASON NOT TO
HAVE THE NUMBER. It is also self-sealing: written into a record, it stops the re-run that would
have recovered it.**

Every other rule here is about a number being wrong. This one is about a *sentence* being wrong —
and about the specific damage a wrong sentence does when it is an excuse. Three instances, all in
this corpus, all discovered by ignoring the sentence and re-running anyway.

**Instance 1 — "the original engine no longer exists."** Two source blocks in
`colleague_yolo_llama_2026-08-14.json` asserted it about an Orin fp16 engine, so an 11% discrepancy
sat open for **three days** while nobody re-ran the artefact. The record's own correction log says
it plainly: *"it is what kept the discrepancy open for three days — nobody re-ran the artifact
because the record said it was gone."* The engine was on the board the whole time.

**Instance 2 — "the vendor runtime cannot load these models."** True, and irrelevant. The O6's
figures for Phi-4-mini and Qwen3-4B were filed as unrecoverable because the *self-build's*
`llama-cli` binary was missing from the board. The **source tree was intact**; `cmake --build`
took minutes, the rebuilt binary loaded both models, and both are now gated. What was missing was
a build artefact, and the record had generalised that into "cannot".

**Instance 3 — "those runs cannot be retro-gated."** Also true, and also not the end of it. The
ARA240 sweeps ran with `input_path:""` — random input, no outputs kept — so the *original* runs can
never be graded. But the models, the board and the harness all still exist: re-running with real
frames produced the same timings to within 0.07% **and** the detection gate the originals could
never have had. *Cannot be retro-gated* had been read as *cannot be gated*.

*The rule:*
1. **Distinguish three different statements, because they get collapsed into one.**
   - *The original artefact is gone* — often true, usually irrelevant.
   - *This specific run cannot be reconstructed* — true by definition once the output was discarded.
   - *This measurement cannot be obtained* — almost never true, and it is the only one that
     justifies leaving a hole in the corpus.
2. **A record may state that data is unrecoverable ONLY alongside what re-running would cost.**
   "Unrecoverable" with no re-run cost beside it is an unbounded excuse; "unrecoverable; a fresh
   run needs the board for 20 minutes" is a scheduling decision. Every instance above collapsed the
   moment somebody priced the re-run.
3. **Treat an unrecoverability claim in a record as UNVERIFIED until someone checks the artefact.**
   It is a factual assertion about a file, a board or a binary, and it decays exactly like any other
   claim (M51's fourth mechanism) — except this one decays into permanent silence, because its own
   content discourages the check that would refute it.
4. **When you cannot close a gap, name what would close it.** Not "no Q8_0 model exists" but "needs
   Qwen2.5-14B-Q8_0 (~15.7 GB) staged to /mnt/ssd/models, then re-run `gated_decode.sh`." The first
   is a wall; the second is a task.

> **CHECK:** any record asserting that data is lost, gone, unrecoverable, or un-re-runnable must
> carry a sibling field naming the artefact checked and when. `grep -rn "no longer exists\|cannot be
> retro\|unrecoverable\|harness lost" results/` enumerates the current claims; each one is a
> re-run someone has not yet priced.

*Why this is its own rule and not a note under M48.* M48 says a null is a claim about the harness.
M52 says **an EXCUSE is a claim about the world**, and it is the more dangerous of the two, because
a null still looks like a gap that wants filling while an excuse looks like a question already
answered. The corpus lost three days to instance 1 and would have shipped two permanent holes from
instances 2 and 3 — not because anyone measured anything wrong, but because a sentence said not to
bother trying.

---

**M53 — AN INPUT IS PART OF THE MEASUREMENT, AND WHICH INPUT IS THE USER'S CALL. Before running a
benchmark, establish whether it needs REAL data, whether synthetic is fine because only the pipeline
is under test, or whether noise IS the point because worst-case is the goal. Declare which, in the
record. A harness that generates its own input has silently chosen one of those three, and it will
choose wrong.**

Every mechanism in this corpus asks whether a number came from a real run of a real model on real
silicon. Not one of them asks whether the *input* was representative of the workload being claimed.
That is a whole class of defect with no guard, and it produced one here.

The SmolVLA precision campaign gated every stage against an fp32 reference computed from the same
input — the correct design for comparing precisions, and it worked. The input was uniform random
pixels. Worse, the int8 models were **calibrated on 64 real COCO frames and then evaluated on
noise**. The calibration set had been chosen with real care: named, hashed, drawn from a specific one
of the two near-disjoint COCO sets the corpus keeps, with held-out indices tracked. The evaluation
input was whatever `numpy.random` happened to emit, because no one ever decided it.

Calibrate on one distribution and test on another and the error does not merely add noise; it runs
in a *direction*. Noise drove larger ViT activations than natural images (max 32.7 vs 19.5), so it
was the harsher case, and the reported int8 cosine was 0.132 where the real-image figure is 0.465 —
pessimistic by 3.5×. The verdict survived (0.18–0.47 is unusable either way) but the headline number
was wrong, and it was wrong in the direction that made a vendor's quantiser look worse than it is.

The three cases are genuinely different and only the person who asked for the benchmark knows which
one they want:

- **Real data required.** The number will be read as "what this hardware does on this workload."
  Anything synthetic makes it a different claim wearing that sentence.
- **Synthetic is fine.** The pipeline is what is under test — plumbing, shapes, does-it-run,
  does-it-build. Latency on a fixed-shape network with no data-dependent control flow is genuinely
  input-independent, and *that property must be verified rather than assumed*. It was here: 12.14 ms
  on a real image against 12.20 on noise.
- **Noise IS the goal.** Worst-case stress, range-saturation, a deliberate hunt for the ugliest
  activation distribution the silicon will see. A legitimate and useful experiment — and the one
  thing that must never happen is arriving at it by accident and reporting it as the typical case.

So: **ask.** One question, before the run, at the only moment it is free. And write the answer into
the record next to the numbers, because a reader six months out cannot tell noise from a photograph
by looking at a latency.

`tools/input_provenance_check.py` enforces the declaration: any record carrying MEASURED timings
must name its input and say which of the three cases it is. It cannot tell a good choice from a bad
one — no checker can — but it can refuse to let the choice stay implicit.

⭐ The generalisation past inputs: **a gate can be perfectly sound and still be pointed at the wrong
thing.** M2 asks whether the gate can fail. M51 asks whether it ran. M53 asks what it was aimed at.
The three are independent, and only the last one needs a human, because only the human knows what
the number is going to be used to claim.

---

**M54 — CORRECTING A DECAYED CLAIM DOES NOT IMMUNISE IT. The counter resets and the drift resumes, in
the same direction, and the SECOND decay is harder to catch than the first — because you remember
having checked. Re-derive a corrected number at every citation, not once at the correction.**

From holobench, 2026-08-25, reporting on their own artefacts. They had said "three consecutive clean
runs" five times; checking, they held one transcript. They corrected it publicly — and within a day
the same claim had climbed to "four", without re-derivation. Their sub-finding is the part that
generalises: *"I already audited that number" is itself a decayed claim about a past act, and it
does exactly the work the original claim was doing — standing in for the artifact.*

Confirmed independently here the same day, and it cost more than it should have. Applying their test
to my own corrections found **two live re-drifts within hours**:

- The int8 ViT cosine was corrected from 0.132 (measured on random-noise input) to 0.465 (real
  held-out images). The **shipped deliverable** still stated 0.132 bare as the current figure —
  three paragraphs below its own note explaining the correction. One location was fixed; the claim
  survived in another.
- The "Orin fp16 anomaly" was resolved by the 5090 measurement (two of three CUDA devices agree at
  0.23; Thor is the outlier). The resolution was written into the 5090 record and never propagated
  back. The original block read `UNRESOLVED` for hours after it was resolved.

Neither was caught by any of the twenty-three checkers then in place. Both were caught by asking the
question `tools/redrift_check.py` now asks: *does the superseded form of a claim I already corrected
still stand anywhere as current?* The registry names each corrected claim, a pattern matching its
**superseded** form, and the guard words that distinguish a legitimate historical reference ("0.132
on noise, superseded") from a live re-assertion ("cosine 0.132 at 2.50x slower").

⚠️ **And state the registry's limit as a property, not an apology** (holobench's framing, adopted):
a hand-maintained registry catches drift only in claims *someone thought to register*. It cannot
catch the FIRST decay of an unregistered claim — only the re-decay of a known one. That is still the
harder half, because re-decay is the decay that has already survived being corrected. Do not read a
green `redrift_check` as "no claims have decayed"; read it as "no claim I registered has decayed
again."

⭐ **Two failure modes found on 2026-08-26 that the registry as first written could not see:**

1. **The ROUNDED form.** The registry matched `0.132139|cosine 0\.132\b` and reported *"holds, 0
   re-drifted"* while SIX live sites carried `0.13-0.22`, `cosine 0.13`, `0.13-0.47`. Rounding is
   the most natural thing a writer does when quoting a number into prose, so it is the form a
   correction is MOST likely to re-drift into — and it was the one form the pattern excluded.
   Register the rounded forms, then **plant the drift and confirm the checker fires** (M51).
   One of the six sites was in the file that RENDERS the deliverable, which no reviewer had listed.

2. **The correction has to cross SESSION boundaries.** holobench corrected their run count on the
   bus, twice, and audited their own copies. The superseded number was still sitting in *this* rules
   file, because they cannot grep my repo and I had no reason to re-grep theirs. Their line was "I
   audited the claim; I did not audit its copies" — the copies you did not audit include **the ones
   in other sessions' trees**. When you correct a load-bearing number, everyone you have already
   cited it to is a distribution list, not an audience.

⭐ **The composite form, arrived at 2026-08-26 when both halves failed in one exchange:**
**RE-DERIVE WHAT YOU CITE, AND RE-SEND WHAT YOU CORRECT.** Two obligations, different owners, and
each one's failure is invisible to the person best placed to fix it.

The demonstration is unusually clean because it happened in both directions at once. holobench
completed a load-bearing result (their leg1 crossing) and their "complete" message went to two
sessions — not to the one writing the paper. Meanwhile I ended a message to them by restating their
*previous* status as current, 21 hours after it was superseded, and committed that sentence into a
pushed commit body — inside a message that was itself *about* re-deriving at citation.

Neither of us could have caught our own half. **You cannot know who is holding your stale claim; the
holder cannot know your claim went stale.** A citer who re-derives catches a superseded number even
if nobody told them. A corrector who re-sends reaches a holder who would never have thought to ask.
Only the pair closes the loop — and the paper's example of the failure was produced by the two
sessions writing the paper about it.

⭐ **A HASH VERIFIES IDENTITY, NOT CONTENT — and it is the most convincing way to pass on nothing.**
Found 2026-08-26 re-deriving a collaborating session's evidence bundle. Five files, five published
md5s, all five verifying. One of them, `VERDICT.txt` — named in the bundle's own README as *"the
scorer's per-leg verdict"* — is **295 bytes: a title line and a box-drawing separator.** There is no
verdict in it, and the verdict quoted on the bus (`pass=2 fail=0 inconclusive=0`) appears nowhere in
the bundle.

Its hash is the *correct* hash of an empty verdict. A checksum proves a file is the one the author
meant to ship; it cannot notice that the file says nothing. So the strongest-looking integrity check
in the bundle passed on the only file with no content — **M51 wearing a cryptographic wrapper**, and
harder to doubt than a plain green because the hash *did* do exactly what it claims.

⭐ **The strongest evidence that "instrument pointed at the wrong quantity" has nothing automatic
reaching it:** in the same evidence bundle, three errors were found by re-derivation, and they
needed three different depths of looking.

| error | how it was reachable | passes to find |
|---|---|---|
| extraction broke, verdict file empty | open the file | 1st |
| headline quoted the guest-side total (673) where the load-bearing total is 771 | one subtraction | 1st |
| the guest's 673 printed under **each** leg as if per-leg | *no arithmetic reaches it* | **3rd** |

The third **survived two prior re-derivations of the same artifact by the same person.** Both earlier
passes checked whether 673 was correct, and both times it was — it is an exact count of the guest's
PASS lines. It fell only when the question changed from *"is this number right?"* to **"this number
counts what, exactly?"** The label was per-leg; the count was whole-console; nothing about the value
was wrong. The other session traced it to one line of scorer code interpolating a per-leg ethertype
beside a whole-console count, so it would have recurred on every future run.

*Act:* for every number beside a label, state what it counts and check the label can bear it. A
correct count under a wrong label is invisible to every dispersion check, every hash, and every
re-derivation that only re-computes the value.

*Act:* when an artifact is cited as evidence, open it and read the claim out of it. Verifying its
hash and moving on is checking that the envelope is sealed without checking there is a letter in it.
A companion check is cheap and mechanical: **assert that the artifact contains the string it is cited
for.** (The result itself was unaffected — it rested on two raw board logs whose counts re-derived
exactly. It was the *verdict artifact* that was empty, which is the point: the load-bearing evidence
and the impressive-looking evidence were different files.)

*And a scope can be crossed by the person who wrote it.* The same bundle's README states that the
emulated guest's log is CORROBORATION ONLY — a guest-side PASS is compatible with nothing leaving the
NIC — and the announcing message then quoted the **guest-side** count (673) as the headline total,
where the load-bearing board-side total is 771. The warning reached its readers and not its author,
because the author was not its reader. Lower, so nothing looked wrong.

⭐ **THE CLOSING LINE DECAYS LAST AND IS READ FIRST.** Contributed by the collaborating session
2026-08-26, from an instance of mine, and it is a variant neither of us had named.

I ended a message with *"good hunting on leg1"* — a thing that had been finished for a day — in the
**same message** whose body correctly described leg1 as complete, with its numbers. So this is not a
decayed belief, and not an unpropagated correction: the correct form and the stale form were in one
message, written by someone demonstrably holding the correct one. Their own instance is the mirror
image: they put a guest-side count in a headline while their own document said not to cite it.

*Why this slot specifically:* sign-offs, headlines and subject lines are written in a different mode
from the body — social rather than evidential, habitually reused from the previous message, and
exempted from the checking the body receives **precisely because they carry no numbers**. And it is
the slot a reader hits first, and often the only slot they read.

*Act:* before sending, re-read the FIRST line and the LAST line as if they were claims. They usually
are. This costs one re-read and catches the one thing the body's discipline structurally cannot.

*Disposition for a stale phrase already pushed:* do not rewrite public history for it. Rewriting a
branch other sessions have been told to cite trades a small stale phrase for a much larger hazard.
Record it as known-stale and dated, in the place a future reader would look.

⚠️ **A scoped negative is true at an INSTANT.** I reported "grepped for their identifiers across
every .md/.json/.py: zero hits" and it was thanked for being properly scoped. The same grep days
later returns hits in five files. Whether it was false when said or became false afterwards is not
recoverable — which is the point. A scoped negative needs a timestamp and a re-run at citation,
exactly like a count.

Note the shape of both failures: **the correction was written down correctly and did not
propagate.** Neither was a memory lapse. The corrected form and the stale form coexisted in one
document, and the stale one was the one a reader would quote, because it sat in the results table
while the correction sat in the notes.

⭐ The direction matters and it is not random. holobench's drifted twice, both times upward, both
times toward a stronger reproducibility claim — the second drift happening *while they were writing
to me about the first*. Mine drifted toward the more dramatic finding (0.132 is a better headline
than 0.465) and toward the unresolved mystery (an open anomaly is more interesting than a resolved
one). Correcting a claim changes the record; it does not change what you want to be true, and the
want is still there afterwards, still pulling.

---

**M55 — A TEST SET THAT CANNOT EXERCISE THE PARAMETER UNDER TEST IS NOT A CONTROL. Before trusting a
golden, check that its VALUE DISTRIBUTION spans the thing you are varying. A hash that agrees for the
right reason and a hash that agrees because the test never reached the interesting region are
indistinguishable from the outside.**

From the SGM campaign, 2026-08-28/29, found twice from opposite directions.

**Instance 1, mine.** I handed an agent a correctness check I was pleased with: *"D=128 must reproduce
the D=64 hash on this scene, so a different hash proves it broken."* Every true disparity in that
scene was under 64, so the two agree — but agreement is **also exactly what a kernel searching only
d<64 would produce**. My check could not tell a correct D=128 from a fake one, and I would have
accepted the fake. The agent built a discriminating scene instead (true disparities to 154, 27% of
pixels above 64) so every D value has a distinct golden.

**Instance 2, 95emulator's, and it reached further.** Their primary golden — the one *every non-CUDA
target in the corpus was accepted against, mine included* — had **max disparity 44 at SGM_D=64**.
Disparities 45–63 never win anywhere in it, so an implementation that only searches d<45 reproduces
`b1b407b5949f0cc1` byte-for-byte. Verified two ways: an independent numpy re-implementation
restricted to d<45 produced a byte-identical map, and the golden's histogram showed 21 distinct
values, max 44.

⭐ **The root cause is a property of the TOOL, not of a seed.** `gen_synthetic.c` assigns slab
disparity as `D/4 + rand%(D/2)`, so maximum true disparity is `3D/4 − 1`. **The generator can never
populate the top quarter of any range.** Every golden it has ever produced has a blind top quarter,
at every D. A `if (d > SGM_D-2) d = SGM_D-2` clamp sat there looking like a deliberate bound.

**The check, and it is one line:** histogram the golden and compare its support against the parameter
range. `max(golden) < D−1` means the top of the range is unverified. Where the corpus quotes a hash
as correctness evidence, that hash is only evidence for the region the scene actually reaches.

**Consequence for this corpus, stated rather than buried:** Hexagon figures taken on the old scene —
the 962 MDE/s D=64 number and the 18.7× → 12.8× → 1.45× trajectory — cite a hash that could not see
d≥45. The numbers survive, because the same kernel reproduces a full-range golden bit-exactly, which
is *stronger* evidence. But **the evidence had to be re-sourced, and an auditor deserves to be told
which hash proved what.**

---

**M56 — CORRECTNESS GATES CATCH WRONG ANSWERS. ONLY A PREDICTED COST CATCHES SLOW-BUT-RIGHT. Gate
every phase against its own op-count arithmetic, not against its share of the total.**

Two instances in one campaign, both with **perfect output and a silent hash**:

- My HVX census stepped 128 columns from x=4 and stopped at 1796, handing the last 124 columns of
  *every row* to a scalar 62-neighbour fallback. **6.7% of pixels consumed ~50% of the phase.**
  92.0M → 15.8M cycles with one overlapping tail block.
- `build_cost`'s first DPAD columns were scalar: 10% of the cost phase at D=64 but **46.4% at
  D=240**, where 13.3% of pixels did 5.6× the work. Fixing it took 10.1% off the whole frame.

Neither was findable by any correctness check, in principle: the kernels were bit-exact throughout.

⚠️ **Do not judge "is this phase done?" from its SHARE.** A share is a ratio against a total that also
moves, so a phase reads 6.9% and looks finished while hiding a 5.8×. Shares are the right way to
report a *change* and a bad instrument for judging *completion*. Use absolute per-phase cycles.

🚨 **And the data was already there.** 95emulator's harness had written absolute `census_ms` /
`cost_ms` / `aggregate_ms` into every JSON since its first commit. Nothing ever gated on them. The
lesson is not "we lacked an instrument" — it is **"we had it and reasoned from the ratio anyway."**

⭐ **A gate whose metric moves the WRONG WAY under the fault is worse than no gate**, because it
manufactures evidence of health. 95emulator first built the roofline as a between-phase *spread*
check; planting the census tail gave: healthy spread 1.62×, **planted spread 1.26×** — the defect made
the gate look *healthier*, exit 0, GOLDEN OK. Rebuilt against absolute per-phase budgets, calibrated
per impl+board, with the threshold **set by planting** (0.0819–0.0832 ns/op healthy; defect at 1.25×;
limit 1.15). Exit 2 = wrong answer, exit 3 = right answer produced too slowly. Keep them distinct.

---

**M57 — HAVING A NAME FOR A FAILURE MODE IS NOT HAVING CHECKED FOR IT. A check that exists but was
never AIMED at a given artefact provides zero coverage of it.**

95emulator's formulation, 2026-08-29, and it indicts both of us equally. Between us we had: named
*cannot-discriminate* as a failure class, written it into a report, hit it in a D-sweep, and built a
discriminating scene to fix it **there**. Neither of us then asked whether the *primary* golden — the
one the whole corpus was accepted against — had the same hole. I had the discriminating scene in hand
and never pointed it at their baseline. They had measured "max disparity present = 44" while
debugging and read it as a build-flag problem rather than an acceptance-model problem.

**The check existed. Nobody aimed it.**

🚨 **The same shape at the tooling layer, found the same day.** `distribution_sync.py` reported
`0 file(s) drifted` while the shipped workbook was two days stale. The generator writes to
`<the generator's output directory>`, and *nothing* copies that into `results/` — so the gate compared a stale repo
copy against an equally stale distribution copy and passed. **It was checking the wrong pair.** A
comparison between two things that move together is not a check.

**The practice:** when you name a failure mode, enumerate every artefact of that kind you own and
point the check at each one. A failure class with one confirmed instance and no sweep is a warning,
not a control.

---

**M58 — WHEN EVERY INPUT CHECK PASSES AND THE RESULT IS STILL WRONG, THE MISSING CHECK IS BY
DEFINITION THE ONE NOBODY LISTED. Only a PRE-REGISTERED EXPECTED VALUE notices that.**

The LIBERO campaign, 2026-08-28. Closed-loop evaluation of GR00T vs SmolVLA. Before any run I had
verified, each correctly:

- action scale against the dataset, per dimension, gripper at ±1 — matched
- state encoding against real data: `eef_pos(3) + quat2axisangle(3) + gripper_qpos(2)`
- camera identity by frame-to-frame motion (the wrist view moves 1.8× more)
- a **random-policy control** returning 0%, proving success detection does not spuriously fire
- the replan interval, swept 1 / 8 / 50
- the training loss, confirmed converged (last decile −0.25%, LR annealed to 2.5e-06)

**The pipeline was still wrong.** `robosuite` renders its offscreen cameras **rotated 180°** relative
to how the LeRobot dataset stores them — correlation between env frame and dataset frame was −0.2229
as-is and **+0.8952 after `[::-1,::-1]`**. Both policies were fed an orientation they had never
trained on. Images "obviously" come out of a renderer the right way up, so orientation was never on
the list.

⭐ **What caught it was a number written down in advance**, not any check: *"SmolVLA < 40% on
LIBERO-Spatial ⇒ harness broken, do not report a comparison."* It fired at 20%. A second
pre-registration — *"GR00T has no published number on this setup; if it lands far below SmolVLA,
wrong-mapping and genuinely-bad are indistinguishable"* — is why I went hunting for a bug instead of
writing up a finding.

🚨 **The counterfactual is the whole argument for the practice.** Pre-fix: SmolVLA 20%, GR00T 0/50.
The natural headline is *"SmolVLA crushes GR00T"*. Post-fix, at n=200/n=100: **GR00T 91.5% vs SmolVLA
52.0% on Spatial, 95.0% vs 17.0% on Long.** The uncorrected result was not merely imprecise — **it was
inverted, by 46 points, and it would have been published.**

⚠️ **The failure pattern was itself the clue.** GR00T collapsed to 0/50 while SmolVLA degraded to 20%.
A shared *input* defect explains both — a diffusion head given out-of-distribution vision fails
completely, a VLM backbone that has seen rotated imagery degrades gracefully. "GR00T is simply bad at
this" explains only one of the two numbers. **When two systems fail differently but both fall short
of their own published figures, suspect the input they share, not the models.**

---

**M59 — SAY WHICH KIND OF COMPARISON YOU RAN. Matched-BUDGET and matched-CEILING answer different
questions, and a normalised unit is valid for comparing implementations at a FIXED configuration and
invalid for choosing a configuration.**

Two forms, both from 2026-08-29.

**Training comparisons.** The LIBERO result — GR00T 91.5/95.0 vs SmolVLA 52.0/17.0 — is matched
**budget**: identical data, identical 10k steps, identical batch. It is *not* matched **ceiling**: our
SmolVLA sits below its own published 90/71, and at 10k steps the Long suite gets 3.15 epochs against
Spatial's 6.04. The defensible claim is **sample efficiency at a fixed budget**, not superiority at
convergence. Both are real findings; only one is supported by the run.

**Normalised units.** MDE/s divides out the disparity range as though D were free to choose. It is
not: `d = f·B/Z` with `f = (W/2)/tan(HFOV/2)` ties D to image width and inversely to field of view, so
work scales as **W²·H**. 95emulator's formulation, adopted verbatim in substance: *MDE/s is valid for
comparing implementations at a fixed configuration and invalid for choosing a configuration.* Every
cross-platform number in this corpus is the first kind, so nothing is retracted — the **sweeps** are
the second kind, and that is exactly where the unit misleads.

⚠️ **Corollary for cross-platform rows:** two cells measured at different configurations are not
comparable merely because the unit normalises. Our D=128 Hexagon figure and 95emulator's D=128 CUDA
figure use different scenes and different goldens; they are not a row until they share one.

---

**M60 — A WARNING NAMES A FAILURE MODE, NOT A LOCATION. Harden the INVARIANT everywhere it can
break, not the spot the warner pointed at. A port that fixes only the warned location ships the
warned failure with extra confidence.**

From the Configuration B port, 2026-08-30. 95emulator warned, correctly and specifically: *"with
P2=200 the aggregation bracket can exceed 255 — you must saturate the output add or you will wrap
and produce a plausible wrong map."* The mode was real. The location was not.

The aggregation add was **already saturating** — Config A's `step2` had been hardened long before.
What P2=200 actually broke was the **argmin key**, one stage downstream: the path-sum S now reaches
8×255 = 2040, silently overflowing the `(S<<6)|d` uint16 sort key. Same failure mode as predicted —
integer overflow producing a plausible wrong map — in a stage neither the warning nor the port plan
named. A port that had responded to the warning by auditing the aggregation add, found it already
safe, and moved on, would have shipped wrong maps **with the extra confidence of having "handled"
the warning**.

The port agent caught it by tracing the *invariant* ("what is the maximum value this quantity can
now reach, and does every consumer of it still have headroom?") through every stage downstream of
the changed parameter, then sim-proving the redesigned key on tie-storms at the cap.

⭐ **The practice:** when a parameter change comes with a warning, translate the warning from a
location into an invariant, and sweep every consumer of the affected quantity. The warner saw the
mode through the lens of *their* implementation; yours breaks in the stage *theirs* didn't have, or
had already hardened. This is the transfer-finding pattern (a finding crossing implementations lands
in a different place) applied prospectively.

⚠️ **And the epistemic trap that makes it dangerous:** "I checked the thing the warning said" *feels*
like diligence and *reads* as diligence in review. It is coverage of the messenger's example, not of
the failure class. Same family as M57 (a named failure is not a checked failure) — one step more
insidious, because here a check genuinely ran and genuinely passed, on the wrong stage.

---

**M61 — A CROSS-PLATFORM COMPARISON IS ONLY AS FAIR AS ITS LEAST-OPTIMISED SIDE. Name the TUNING
TIER of every row, and never let a tuned port beat an untuned oracle and call the result a property
of the hardware.**

From Configuration B, 2026-08-29/30, and the error is mine end to end. I measured a hand-optimised
HVX port (chain-slot diagonals, fused merge, 4-vector unroll — a day of tuning) at 276.26 ms, ran
the **plain scalar oracle** on the A78C at 908.60 ms, and published *"one NSP is 3.29× the 8-core
cluster on the harder configuration."* I knew the A78C row was the untuned oracle — my own note said
*"the oracle compiles as-is"* — and quoted the ratio anyway, because it was a strong number and both
rows were individually honest.

95emulator asked for tier parity before the deck pass. Their tuned NEON build on the same A78C:
**211.86 ms — faster than the NSP.** The headline did not sharpen; it **inverted** (cluster leads
1.30×). At matched tiers Config B looks like Config A, and the entire "this configuration is
DSP-shaped" narrative dissolved. What survives is the per-engine claim (one NSP ≈ 1.60× one A78C
core at parity) — a much smaller and different statement.

⭐ **Why this is its own rule and not M59:** M59 is about matched *configurations* (same D, same
scene). This is matched *effort*. Every row can be individually impeccable — hash-gated, correctly
sampled, honestly labelled — and the **ratio between rows is still meaningless** if one side got a
day of optimisation and the other got `gcc -O3`. The tier is invisible in the numbers themselves;
it lives in the provenance. So: every cross-platform row carries a tier tag (*oracle / tuned /
vendor-library / hand-optimised*), and a ratio may only be quoted between rows of the SAME tier.
A cross-tier ratio is not a comparison; it is a measurement of how much tuning one side received.

⚠️ **The seduction profile, for recognition:** a cross-tier ratio always flatters whichever platform
you just spent effort on — which is usually the one you are rooting for. It arrives at the exact
moment of maximum investment and pride in the port. Both times this campaign produced a
too-good-to-be-true platform headline (18.7× against the DSP, 3.29× for it), the number was real
arithmetic on honest rows and wrong as a *comparison* — in opposite directions, which is the tell
that the artifact tracks effort, not silicon.

---

**M62 — A LAUNCH THAT NEVER HAPPENED IS INDISTINGUISHABLE FROM ONE THAT IS STILL STARTING. Confirm a
background run from its ARTIFACT — file existence and mtime — never from a process check, and never
from the absence of an error.**

Three times in one session (2026-09-02) a detached run was reported as alive when it was dead, and
each diagnosis failed the same way:

- `pgrep -f run_sweep.py` **matched its own shell command**, which contained the string. The check
  returned "alive" while nothing was running. The same self-match had already occurred hours earlier
  with a different agent, in the same session, after being written up.
- `nohup … &` inside a tool call that later **timed out** took the child down with the process group.
  The launch printed no error because the shell that would have printed it was gone.
- An `ssh host '… & disown'` returned successfully and started nothing, because the remote command
  died with the terminated connection.

In all three the console said what a healthy start says: nothing.

⭐ **The reliable tell is the OUTPUT FILE.** `stat -c %y` on the results path, compared against the
clock, answers "is this running?" in one line and cannot self-match, cannot be fooled by a process
name, and cannot be satisfied by a launcher that exited. A run that has not written in a minute is
not running, whatever `ps` says.

⭐ **The fix for the launch itself is `setsid`**, plus a launcher script that returns immediately, so
the work is reparented away from the invoking connection before that connection can die.

⚠️ **Why this rates a rule rather than a note:** the failure is silent, it presents as patience, and
the natural check for it is the one that does not work. Every instance above cost real time, and one
of them was reported to the user as progress.

---

**M63 — A KNOB SET IN THE WRONG PLACE DOES NOTHING, SILENTLY, AND THAT IS INDISTINGUISHABLE FROM A
KNOB THAT DID NOT HELP. Before concluding "I tried X and it didn't fix it", prove X was actually
APPLIED.**

Cost on 2026-09-02: an Orin GPU row, twice abandoned.

`llama-mtmd-cli` aborted with `CUDA error: out of memory` at ~0.077 s on every image size, with
33 GB free and all 29 LLM layers already offloaded successfully. I tried `GGML_CUDA_NO_VMM=1` in
the environment, saw no change, and concluded the VMM pool was not the cause. On that basis I
wrote up a **defect in an old llama.cpp snapshot**, rebuilt from current upstream to confirm it,
watched it fail identically, and reported the GPU row as blocked.

⭐ **`GGML_CUDA_NO_VMM` IS A CMAKE OPTION, NOT A RUNTIME ENVIRONMENT VARIABLE.** Exporting it does
exactly nothing. The knob was never turned. Rebuilding with `-DGGML_CUDA_NO_VMM=ON` fixed it on
the first try, and the GPU row came back at 1196 t/s.

⚠️ **What made this expensive is that the failed attempt produced EVIDENCE.** "I disabled VMM and
it still failed" is a strong-looking exclusion that pointed the investigation away from the actual
cause and toward an invented one — a stale-snapshot defect I then spent a full rebuild confirming.
A test that never ran does not return "inconclusive"; it returns a confident wrong answer in
whichever direction you were already leaning.

🔴 **AND THE REAL CAUSE WAS READABLE THE WHOLE TIME, in the lines I was filtering out.** My grep
took `cuda error|out of memory` and dropped the two lines under them:

    in function alloc at ggml-cuda.cu:595
    cuMemAddressReserve(&pool_addr, CUDA_POOL_VMM_MAX_SIZE, 0, 0, 0)

That names the mechanism outright — reserving a large VIRTUAL ADDRESS RANGE, which Tegra unified
memory refuses. Not exhaustion, which is why it was size-independent and why free memory was
irrelevant. **A filter tuned to the symptom hid the diagnosis.**

⭐ **THE ACT:** for any setting that might be build-time — CMake options, compile flags, kernel
config, driver params — confirm it took (`grep` the CMakeCache, check the built artifact, read the
banner) BEFORE letting a null result become evidence. And when a run fails, read the WHOLE error
block once at full width before grepping it.

---

**M64 — THE POWER REGIME IS AN INPUT THE USER DECLARES, NOT A PROPERTY YOU INFER. Every run is
LUDICROUS SPEED, DYNAMIC, or LOW POWER — ask which, record it with the number, and if you believe
you are at ludicrous speed and see dispersion, YOUR CLOCKS ARE MOVING AND YOU ARE NOT.**

⭐ **THE THREE REGIMES, and the point is that they are a QUESTION FOR THE USER:**

| regime | what it means | how you get there |
|---|---|---|
| **LUDICROUS SPEED** | every clock pinned at maximum; the silicon's ceiling | `jetson_clocks` · `perf_profile: burst` · governor `performance` |
| **DYNAMIC** | DVFS free-running; what a real deployment usually does | the default, and almost never what a benchmark wants |
| **LOW POWER** | a capped mode chosen deliberately (thermal, battery, budget) | `nvpmodel -m <n>` · a capped profile |

**Which one a run should be in is a DECISION ABOUT THE QUESTION BEING ASKED, and it belongs to the
person asking it.** "Peak achievable throughput" and "what this does in a fanless enclosure" are
different questions with different right answers, and nothing in the hardware tells you which one
was meant. **Ask. Then record the answer next to the number**, the way a census already rides along.
An undeclared regime makes a number uninterpretable, not merely imprecise.

🔴 **AND THE SELF-CHECK, which is the part that catches you lying to yourself:**

> **IF YOU BELIEVE YOU ARE AT LUDICROUS SPEED AND THE RUN-TO-RUN SPREAD IS MORE THAN A COUPLE OF
> PERCENT, YOU ARE NOT AT LUDICROUS SPEED. THE CLOCKS ARE GOING UP AND DOWN.**

Dispersion is the signature of scaling clocks. The *value* tells you nothing — a throttled board and
a pinned one both return plausible medians. The **spread** is the instrument.

    Orin AGX, identical prompt, 5 reps
      schedutil free-running : 515.6 – 571.3 ms   → 10.8% spread
      jetson_clocks applied  : 434.2 – 437.8 ms   →  0.8% spread

Bought 2026-09-02 by a 20% error across every Orin number in the corpus. Our prefill ran 17–27%
behind a colleague team's with no explanation. I cleared every obvious cause — `nvpmodel` MAXN, 12
cores online, GPU sampled **pegged at its 1300 MHz ceiling** under load, 47 °C against an ~85 °C
limit, micro-batch no effect, clock ramp 56 ms and finished long before prefill — and told Kyle that
applying `jetson_clocks` "won't move much." It moved **19–20% at every point**, putting us level
with them at the short end and 5–10% ahead at the long end.

⭐ **WHAT IT CHANGED WAS EMC — THE MEMORY CLOCK — pinned to 3199 MHz.** Prefill is bandwidth-bound;
the GPU core clock I measured was never the binding constraint. **Checking the clock you thought of
is not checking the clocks that matter**, and a board can be simultaneously "at max clock" and
leaving 20% on the table. That is exactly why the regime must be DECLARED and VERIFIED rather than
inferred from whichever counter you happened to sample.

⚠️ **THE DETECTOR WAS IN MY DATA AND I READ PAST IT.** 10.8% spread was sitting in the run I was
medianing. The O6 notes already say this outright — "the tell is a 60% stddev, not the value" — so
this is the SECOND time the same detector has been bought on different silicon. A rule that has to
be learned twice was not written strongly enough the first time.

⚠️ **AND THE CORRECTION IS ITSELF A BIAS RISK.** The IQ-9075 CPU was unaffected — 2362 MHz against a
2361 max, already flat out. So fixing the Jetsons moves every Qualcomm-vs-NVIDIA ratio AGAINST
Qualcomm. The iq9's NPU has its own profiles (`/root/qnn/burst_*.json`; QNN's default is NOT
`burst`) and is still unchecked. **Re-measure every platform in a comparison or none of them** — a
half-applied correction looks like diligence and is worse than the original error.

⭐ **ENFORCEMENT — added 2026-09-11 after M64 was RE-BOUGHT a THIRD time. THE DEFAULT IS MAX. A
benchmark PINS CLOCKS (LUDICROUS SPEED) unless the user has EXPLICITLY authorized DYNAMIC.** "Peak
achievable" is the default question a benchmark answers; DYNAMIC (free-running) is opt-IN, with
permission, and TAGGED. Three failures made this necessary the third time:

1. **The rule lived in the doc but not in the WORK.** The Qwen2.5-VL-7B A16W4 Orin runs (2026-09-11)
   recorded `MAXN, DVFS free-running (not pinned)` -- honestly declared, and `power_regime_check`
   PASSED because the regime was *named*. But declared-DYNAMIC is not benchmarked-DYNAMIC-on-
   purpose; it was DYNAMIC-BY-OMISSION, because the agent briefs never said "pin." *A rule you do
   not put in the brief is a rule you do not run.*
2. **Same fingerprint as 09-02, missed again:** Orin TTFT ~1.7x a pinned reference (708 vs 419 ms)
   while DECODE MATCHED it (20.6 vs 20.7 t/s). Decode-matches-but-TTFT-doesn't is the signature --
   the short front-burst (ViT+prefill = time-to-first-token) rides the clock ramp / free EMC; the
   long steady decode phase does not, so it looks fine and hides the problem.
3. **Blast radius (M65):** the free-running TTFT nearly INVERTED a shipped verdict -- the A16W4 deck
   said "iq9 wins TTFT," comparing an NPU (fixed burst clock) against an unpinned-DVFS Orin.

THE ENFORCED FORM:
- Every benchmark brief carries the clock instruction -- pin to max (`jetson_clocks` /
  `perf_profile: burst` / governor `performance`), VERIFY EMC IS PINNED, not just the GPU core
  (EMC is the binding clock for bandwidth-bound prefill/decode), and record the regime + the
  run-to-run spread (spread > a couple % = clocks still moving).
- A MEASURED timing record whose regime is DYNAMIC/free-running is INVALID as a benchmark unless it
  carries an explicit `dynamic_authorized: <why>` field. `power_regime_check` must FAIL a free-
  running benchmark that lacks that authorization -- not merely require the regime be named.
- NPU-vs-GPU comparison: the NPU runs a fixed burst clock, so the GPU MUST be pinned too, or the
  comparison is rigged against whichever side is on DVFS. Re-measure every platform pinned, or none.

---

**M65 — A CHANGED VALUE HAS A BLAST RADIUS. NAME IT, SAY WHAT GOES INCONSISTENT IF IT IS NOT
FOLLOWED, AND LET THE USER DECIDE. Do not silently propagate, and do not silently skip.**

When you edit a measurement, a number, or a claim that other parts of a deliverable **depend on to
produce their own results or analysis**, that edit is not finished when the cell changes. Every
downstream table, ratio, fit, caption, cross-reference and prose sentence built on the old value is
now either stale or orphaned.

⭐ **THE OBLIGATION IS DISCLOSURE, NOT AUTOMATIC REPAIR.** Say plainly:

1. **what changed**, and
2. **what else depends on it** — name the specific sections, tables and derived figures, and
3. **what will be inconsistent if the rest is not updated**, and
4. **what it costs** to follow through.

Then **stop and let the user choose.**

🔴 **DO NOT ASSUME THEY WANT FULL PROPAGATION.** They may want exactly the one value changed —
because they are shipping in an hour, because they are only sending the summary, because the rest of
the document is being rewritten anyway, or because a partly-stale artifact they understand is worth
more than a consistent one that arrives too late. **That is their call and it is frequently the
right one.** Propagating unasked can cost hours and can churn sections they were about to discard.

🔴 **AND DO NOT SILENTLY SKIP.** An artifact whose parts disagree, handed over without warning, is
worse than either option — the reader finds the contradiction and stops trusting everything, and the
one number that WAS right is discredited along with the rest.

⚠️ **THE FAILURE IS NOT RARE — IT IS THE DEFAULT.** On 2026-09-02/03, one deliverable produced five
instances in a single evening:

| the edit | what it silently broke |
|---|---|
| Thor re-measured pinned | "green rows are like-for-like" became FALSE — regimes no longer matched |
| DYNAMIC rows purged | two notes told the reader to "recompute from Sheet 1" rows that no longer existed |
| a summary block added | **its own five rows were never in the results sheet at all** |
| image tokens 396 -> 394 | corrected in one sheet, still wrong in three other places |
| a ratio 342x -> 499x | corrected in the summary, stale everywhere else |

Two adversarial review passes caught most of these. **The worst one — a headline claim whose
supporting rows were absent from the results sheet — was caught by the USER asking "did you update
the results sheet too?"** Both reviewers had audited what was IN the workbook against the raw data;
neither asked whether the summary's own evidence was present. The blast radius of an ADDITION is as
real as that of a change, and it is easier to miss because nothing looks wrong.

⭐ **THE ACT:** before reporting an edit complete, grep the corpus for the old value, for anything
derived from it, and for prose that describes it. Then tell the user what you found and what you
propose. One sentence — *"this also affects X, Y and Z; leaving them costs an inconsistency between
A and B; fixing them costs N minutes; which do you want?"* — is the whole rule.

---

**M66 — A NORMALISED AXIS IS A FOOTGUN IN A COMPARISON CHART. If the reader must read the caption
to avoid the wrong conclusion, the CHART is wrong — not the reader.**

Normalising each series to its own peak (`% of own peak`, `÷N to share an axis`, "indexed to 100")
answers exactly one question — **"does this curve fall?"** — and destroys another the reader will
ask anyway: **"which one is bigger?"** The eye reads vertical position as magnitude. It will do that
before it reads the title, and it will never stop doing it.

⚠️ **MEASURED FAILURE, TWICE IN ONE SESSION, WITH THE CAVEAT ALREADY PRINTED ON THE CHART:**

| chart | what the caption said | what the user concluded | the truth |
|---|---|---|---|
| iq9 (int8) vs Orin (fp16), absolute | "heights are not comparable — precision differs" | *"NVIDIA is only a little bit more performant than iq9"* | Orin is **3.5×** faster at equal precision (fp16) |
| Thor vs Orin, each ÷ own peak | "this chart is about SHAPE, not speed" | *"there's no way Thor falls below Orin — it can't"* | Thor is **3.2–4.4× ABOVE** Orin at every point; it never falls below |

Both captions were correct, prominent, and ignored — **because the picture said otherwise.** In the
second case the reader was right on the physics and the chart was simply lying to them: Thor's 88%
was 66.5 TFLOP/s and Orin's 100% was 20.8.

⭐ **THE ACT — three parts, all of them:**

1. **Absolute comes first and carries the comparison.** Put it in the left/primary panel, on a
   **like-for-like basis** (same precision, same batch, same runtime). If no like-for-like basis
   exists, there is no comparison to draw — say so instead of drawing one.
2. **Shape goes in its own panel, titled as not-a-ranking**, with each series' **absolute peak
   printed in its own legend entry** so `100%` cannot be read as parity.
3. **A series with no fair basis is EXCLUDED from the absolute panel**, not included with a
   disclaimer. An int8 height beside fp16 heights is a mixed-tier comparison (LAW 1) whether or not
   a footnote admits it.

**Corollaries:**
- **Never draw a threshold band that does not apply.** Bands measuring *drop from peak* on a curve
  whose peak is the LAST point put a rising line inside a "cliff" band — the exact opposite of the
  truth. (Caught 2026-09-03 on the resolution ladder.)
- **`÷N to fit one axis` is the same footgun** and needs the same treatment.
- **Log axes compound it** — they flatten the divergence the chart exists to show. Kyle, 2026-09-03:
  *"keep away from log scales. humans don't read those very well."*

**THE TEST, before any chart ships:** cover the title, caption and footnotes, look only at the
plotted lines, and write down what you would conclude. If that differs from the claim, redraw it.

---

**M67 — ANSWER THE QUESTION IN THE WORDS IT WAS ASKED, BEFORE ANY TABLE. A results matrix is
evidence, not an answer.**

Kyle, 2026-09-04, on the first sheet of the int16 deliverable: *"I REALLY like the first sheet.
we need to make that a template of sorts. it explicitly writes it all down in clear language."*

Our workbooks are good at tables and bad at answers. Someone asks a question in their own words
and we hand back a matrix, leaving them to locate the answer inside it — which means the reader
does the synthesis, and every reader does it differently. **Sheet 0 of any deliverable is the
answer in prose.** Implemented and enforced by `tools/answer_sheet.py`.

⭐ **THE SIX PARTS, and the rule each one exists to enforce:**

| part | the rule |
|---|---|
| **YOU ASKED** | their question **VERBATIM**. Paraphrasing is where you quietly swap their question for the one you would rather answer |
| **SHORT ANSWER** | **ONE sentence**. If it needs two, you have two answers and must say so explicitly |
| **THE POINTS** | numbered CLAIM + EVIDENCE, never a claim alone. **Exactly one ⭐** — the thing they keep if they read nothing else. Caveats that CHANGE the answer are **⚠️ and live here**, not in a footnote |
| **WHAT WE SUGGEST** | an action they can take, naming the sheet that supports it |
| **WHAT WOULD CHANGE THIS** | what we did **not** establish, and what would settle it |
| **WHERE THE EVIDENCE IS** | sheet → what lives there, so they can **verify rather than trust** |

**Two rules are enforced in code, not in review** (`answer_sheet.py` raises):
- **exactly one ⭐** — two headlines is zero headlines
- **a one-sentence SHORT ANSWER** — a multi-sentence "short answer" is a summary wearing a
  disguise

Its `--self-test` plants four violations (two stars, zero stars, a three-sentence answer, and a
valid spec) and fails if any is accepted; it is wired into `presend.py`.

⚠️ **WHAT WOULD CHANGE THIS is the part most likely to be dropped, and the most valuable.** A
deliverable that cannot be wrong is a brochure. On the int16 workbook it is where "we ported AI
Hub's RESULT, not its ALGORITHM, so it will not generalise to another model" lives — the single
sentence that stops a reader over-applying the finding.

---

**M68 — A CROSS-DOCUMENT REFERENCE MUST NAME ITS TARGET. The test is whether the RECIPIENT can
resolve it, not whether the file is in the send set.**

Kyle, 2026-09-04, reading a finished deliverable: *"on the updates your sheet 6 tab, not sure
what this is? i haven't sent anything to my colleague yet. what is sheet 6?"*

"Sheet 6" meant tab `6. Accuracy (mAP)` of a **different** workbook shipped three weeks earlier.
Inside a standalone document it pointed at nothing — and it collided with the document in hand,
whose own tabs ran 1–5, so the reader went looking for a sixth tab. It was wrong three ways at
once: it **named nothing**, it said *"YOUR sheet 6"* about a workbook **we** sent **them**, and
it **collided** with the reader's own document.

⭐ **THE RULE IS RESOLVABILITY, NOT PRESENCE.** Kyle named the trap when he asked for this rule:

> *"we have 3 docs and we update a single one. the other 2 are already sent and we're not changing
> them. so if doc 1 references doc 2 or 3 and it's not in the corpus deliverable we are sending,
> then it'll flag 'i don't see the referenced document'"*

He is right, and that checker would be **wrong**. Referring to a document you are not resending is
normal and correct. **Never require the referenced document to exist, to be attached, or to be in
the send set.** Require only that the reference carries enough identity — a filename, a date, or
both — for the recipient to find it in their own inbox.

| | |
|---|---|
| ❌ | "as shown in sheet 6" |
| ✅ | "tab `6. Accuracy (mAP)` of `Foo.xlsx`, sent 2026-08-20" |

**and the ✅ form is identical whether or not `Foo.xlsx` is being resent.**

**Enforced by** `tools/cross_reference_check.py`, wired into `presend.py`. Its `--self-test` plants
nine cases including Kyle's exact false positive as a **must-not-fire**. Two further false-positive
classes it must not trip, both found by planting rather than reading:
- **"sheet N" where N IS one of this document's own tabs** is internal navigation, not a
  cross-reference. A checker that fires on correct internal pointers gets switched off.
- **FROZEN (already-shipped) artifacts** are reported but do **not** fail the gate — editing one is
  a deliberate re-ship, not a gate fix.

⚠️ **AN ADVERSARIAL REVIEW DOES NOT CATCH THIS CLASS.** A hostile expert pass over the same
deliverable found nine real defects and missed "sheet 6" entirely — because it read with **full
context** and could resolve the reference itself. The recipient cannot. **A hostile-expert check
is not a fresh-reader check**, and running the first while assuming it covers the second is how
this shipped.

---

## PART VII — POWER / EMULATION RULES (M69–M73, from the QEMU power-modeling corpus)

*Earned 2026-09-08/09 in the i.MX95 QEMU power-modeling work (95emulator session), all fitting the
same thesis: a broken run is a cheap run, and the surviving errors flatter the story you already told.
Every one is reconstructable from commits — the wrong versions are kept in history on purpose.*

**M69 — EXECUTION IS A MEASUREMENT PRECONDITION, NOT AN ASSUMPTION.**
Two of fifty apps drew ~324 mW vs ~500 typical and were published as the model's 52% worst case, with a
plausible mechanism ("the ALU proxy overstates stall-heavy code"). They carried unquoted shell
metacharacters and **died on every iteration** — the meter measured a shell failing in a tight loop. Power
was low because *nothing executed*. ⚠️ The dangerous part was the EXPLANATION, not the bug: a plausible
mechanism that fits the evidence is how a broken run survives review — it stops people looking. The two
apps were the only ones below 1200 mW — sitting on the idle floor, which is exactly what "nothing ran"
looks like. Re-run quoted: 6% and 11%, inside the normal band; the 52% vanished.
**CHECK:** record exit code, iteration count, and per-iteration duration for every run. A workload that
did not run is indistinguishable from one that ran cheaply — and a low power number is in the flattering
direction. Never let a mechanism-story substitute for proof the workload executed.

**M70 — A RATE THAT EXCEEDS THE CLOCK IS THE ONLY FREE ORACLE YOU GET.**
A calibration workload reported 2,687,121,103 Mops/s; `-O2` had elided the entire ALU loop (a local whose
only use was a dead branch), while the op *counter* still incremented — the model would have been fitted to
a workload that never ran. Caught ONLY because the rate exceeded the 1.8 GHz clock by six orders of
magnitude. A plausible-looking wrong number would have sailed straight through.
**CHECK:** bound every derived rate by a physical ceiling (clock, lane count, peak BW) and assert it. Kill
dead-code elimination with a volatile sink + asm barrier; verify the rate scales 1x/2x/3x with thread count.

**M71 — A RATIO NEEDS A DENOMINATOR FLOOR.**
A gate printed "ratio infx PASS" for the prediction "DRAM rails discriminate the two workloads by >=10x."
Its inputs were **both negative** (-0.29 and -0.57 mW — the memory workload's DRAM sat *below* the idle floor
because caches were disabled and it could not stream); dividing by a near-zero denominator gave infinity,
which passed >=10x. The prediction was also mis-worded: it asked for a ratio whose denominator the
prediction ITSELF expected to be ~zero.
**CHECK:** if a prediction expects the denominator to be ~zero, the ratio form is invalid — state it as
"A rises, B does not," and make the checker report NULL rather than compute. Never compare a magnitude that
can go negative as if it were a rate.

**M72 — A CONTROL MUST BE ABLE TO ENTER THE REGIME IT EXPLAINS.**
Fixing QEMU's L1D geometry (16 KB/8-way -> real 32 KB/4-way + L2) changed the miss count by 18 in 5.2 million
(0.0003%) — a 256 MiB stream misses at every level regardless of size or associativity. **The workload was
blind to the parameter being corrected**; it would have "confirmed" a correct geometry as happily as it
refuted the fix. (Real cause: no write-streaming model — QEMU counts line allocations the A55 skips for
full-line writes; a constant 1,048,981 excess = one memset over the buffer.)
**CHECK:** before trusting a null/negative result, prove the instrument CAN produce the positive one — that
the control can actually enter the regime it is supposed to discriminate. Relates to [[verify-the-variable-moved]].

**M73 — A HIGH R² ON COLLINEAR PREDICTORS IS NOT EVIDENCE.**
A power fit scored R²=0.9984 with **negative** coefficients on both ALU rate and bandwidth — more work
drawing less power — because a grid trimmed from 11 points to 7 reintroduced collinearity. A linear DRAM fit
scored a lower R²=0.9677 but with an intercept 98% above an independently measured idle floor (n=5).
**CHECK:** never read R² alone. Check the SIGNS of the coefficients against physical sense, and check the
intercept against any independently measured baseline. A great fit with impossible signs is a collinearity
artifact, not a model.

---

## PART VIII — CROSS-BOARD / DERIVATION RULES (M74–M75, from the VLA e2e + 6-camera corpus)

*Earned 2026-09-09 in the driving-VLA end-to-end and 6-camera scaling work (qualcomm session).*

**M74 — IF A RECORD DIRECTLY MEASURED THE QUANTITY, USE IT — DO NOT RE-DERIVE ACROSS A MISMATCHED BASE.**
A 6-camera end-to-end cost was shown as single-cam-e2e × the measured multiplier = 1.1 s on the 5090 — but
the 6-cam record had *directly measured* 1.7 s, and the single-cam base came from a *different* config
(vision-light 613 ms vs the vision-inclusive 996 ms of the 6-cam run). The re-derivation understated the
real number **in the flattering direction**, and it was committed by the person who wrote these rules.
**CHECK:** when a directly-measured value exists in the record, publish that — a DERIVED value multiplied
onto a base from a different configuration is not a substitute, and its error has a preferred direction.
Cross-condition multipliers are valid only within their own run.

**M75 — VERIFY THE WORLD BEFORE RECORDING AN ASSERTED FAILURE.**
A coordinator told a sub-agent a run had DIED and to record it as failed. The agent checked the actual board
first, found the output file present with the gate passed — the run had SUCCEEDED (the ssh *stream* had
timed out after a 21-minute compile warmup) — and refused to fabricate a failure. Had it obeyed, the record
would carry a false "DIED" for a run that worked.
**CHECK:** a "it failed / it died" claim — even from the coordinator — is a hypothesis, not a datum. Verify
the artifact on the machine before recording a failure. An instruction to record an outcome does not
override the outcome. Relates to [[never-sigkill-accelerator-process]], [[harness-indicts-the-vendor]].

---

## PART IX — GENERATED-ARTIFACT PROVENANCE (M76, from the rule-count self-audit corpus)

*Earned 2026-09-24 in a cross-session rule-count dispute. Two independent sessions disagreed on how many
rules this file held; one cited "count_sync says 68, and the document's preamble says 68, so 68." The
preamble's 68 had been WRITTEN BY count_sync. The generator and its output were treated as two witnesses
when they were one, and both were wrong: seven rules (M69–M75) used `###` headings the counter's regex
never matched — invisible to the generator, therefore invisible to the prose it generated, and — the same
drift — never cited by a single checker. The tie was broken only by an independent read of the file.*

**M76 — A GENERATED FIGURE IS VERIFIED ONLY AGAINST THE ARTIFACT IT DESCRIBES, NEVER AGAINST ITS
GENERATOR. If the generator is the figure's only witness, the figure is UNCHECKED.**

A count, a total, a caption, a summary line — any figure emitted by a program that reads a source — agrees
with that program by construction. That agreement feels like corroboration and is structurally the opposite:
*two halves of one program are one witness.* When the generator has a blind spot, the artifact it writes
inherits it silently, and every downstream copy of the figure carries the same blind spot wearing the
authority of a printed number. This is the same failure as a host and guest hashing with the same typo'd
basis: they agree perfectly and reproduce nothing anyone else can.
**CHECK:** the only thing that can falsify a generated figure is an INDEPENDENT read of the artifact it
claims to describe — by a different tool, a different regex, or a human — not a re-run of the generator.
A checker that both PRODUCES a figure and ASSERTS it is inert against its own blind spot; pair it with a
reader that does not share its code. And when one document is authored by another (a preamble written by a
counter), never quote the two to each other as agreement. Relates to [[m44-verify-the-rendered-artifact]],
[[gate-inert-by-wiring.md]], [[whole-tensor-cosine-is-blind]], [[inert-checker-law]].


## AMENDMENT

This document is amended by *finding a new way to be wrong*, not by opinion. Adding a rule requires
citing the defect that motivated it, in the Failure Register, with evidence. Rules are never removed
because they are inconvenient — only when the failure mode they prevent has become structurally
impossible (e.g. mechanised away).
