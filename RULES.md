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
session*, that the model computed something *correct*. Never a proxy from Class A.
- Detector → detection count, max score, and class plausibility for a known image.
- LLM/VLM → a gradeable answer obtainable **only** from the supplied input.
- VLA → trajectory sanity against a reference.
> **CHECK:** the result record contains a `gate` object with a pass/fail and the observed values. No gate object → the number does not exist.

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
  "artifact": {"path": "/home/kyle/acc/yolov8n_b1.fp16.engine", "md5": "..."},
  "log": "/home/kyle/acc/thor_perf_20260816T084935Z.log",
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

---

## AMENDMENT

This document is amended by *finding a new way to be wrong*, not by opinion. Adding a rule requires
citing the defect that motivated it, in the Failure Register, with evidence. Rules are never removed
because they are inconvenient — only when the failure mode they prevent has become structurally
impossible (e.g. mechanised away).
