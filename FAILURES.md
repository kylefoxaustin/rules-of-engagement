# Failure register

Every rule in `RULES.md` points back to one of these. They are recorded in the form that turned out to
matter: **what happened · why it survived · what finally caught it**. Hardware names are kept where the
behaviour is a property of that toolchain, because a reader on the same stack deserves the warning.

Note the pattern before you read them individually: **almost every entry made a number look better.**

---

## Class 1 — the measurement was not of what we thought

### An uncalibrated engine was 8.3% faster, and was recorded as a result
An INT8 detector was rebuilt and re-timed. It came back **8.3% faster** and went into a draft as an
improvement. It scored **mAP 0.0021** — it detected nothing. The missing work was the speedup.
**Survived because** timing and accuracy were separate steps, and only timing was run that day.
**Caught by** an accuracy pass run before publication, by luck of ordering rather than by design.
→ Gate the output in the *same invocation* as the timing. This is the founding rule.

### A detector returned zero detections on every anchor, for months
INT8 quantisation of a YOLOv8 graph whose final `Concat` joins boxes (range 0–640) with class scores
(range 0–1). Per-tensor quantisation gives that single output **one scale, sized for 640** — so every
score rounds to zero. The model ran at full speed and emitted perfectly plausible boxes.
**Survived** exit-code checks, tensor-shape checks, and "did it execute on the accelerator" checks, for
months. None of those look at whether anything was *detected*.
**Caught by** finally scoring against ground truth. **Fix:** delete the final `Concat` and promote its
two inputs to separate outputs so each gets its own scale. Slicing *after* the `Concat` does not work —
a `Slice` inherits the parent's quantisation parameters. 0 → 45 detections.
→ Worth checking on any accelerator whose single output tensor concatenates quantities of different
physical ranges.

### A memory-budget setting was silently discarded in every binary we ever built
A VTCM budget was passed to the compiler for months. The graph name it keyed on never matched the
binary's real graph name, so it was ignored — **with no error, no warning, no diagnostic**. Every
published number for that part understated it by 2.8–16.1%.
**Survived because** a silently-ignored config produces a *perfect null result*, and a non-experiment
is indistinguishable from a finding of "that setting doesn't help."
**Caught by** an unrelated investigation into why a number would not move.
→ Before reporting that something made no difference, prove the variable actually changed.

### A graph was fed half its input bytes and returned `status: OK`
An fp16 model received an input buffer sized for a different precision. The runtime accepted it,
executed, and reported success.
→ Byte-count assertions at the harness boundary, not trust in a status code.

### The export opset was never recorded, and was worth 21%
The same model exported at two different opsets differed by **21% in latency** and **9.5× in spilled
on-chip memory**, at **bit-identical accuracy**. Neither number was wrong. They were different
measurands wearing one name.
→ Hash the artifact. "The same model" is not an identity.

---

## Class 2 — the comparison was illegitimate although the arithmetic was right

### A latency reciprocal was ranked in a column of saturated throughputs
One board's single-stream latency was inverted into a throughput and sorted against other boards'
fully-saturated aggregate throughputs. Every value in the column was arithmetically correct. The
ranking was meaningless, and it flattered the board with the best latency.
→ Quote latency against latency and throughput against throughput; never convert between them.

### A vendor table mixed sparse and dense TOPS in one column
A supplied comparison table listed one part's **sparse** peak, another's **FP8** peak, and a third's
**dense INT8** peak, in a single "INT8 compute" row. Taken at face value it implied one part had ~10×
another's compute; on a consistent dense INT8 basis the true ratio was between 0.85× and 1.7×. The
error would have flattered one vendor by roughly **an order of magnitude** in every derived ratio.
**Caught by** normalising all three to one declared basis and watching the headline ranking invert.
→ A denominator needs its basis declared as loudly as the numerator.

### Every ratio was correct and the ranking inverted when precision was held constant
A compute-density sheet compared one board's INT8 result against another's FP16 result. Correct
arithmetic, incomparable operands. Holding precision constant reversed the conclusion.
→ Precision travels with the number, always, into every derived quantity.

---

## Class 3 — the numbers were right and the prose was not

### Stale prose beside a correct table, four separate times
The most common serious defect in the entire campaign. A number is corrected in a table; a sentence two
paragraphs away still describes the old value, still reads fluently, and now contradicts three other
places in the same file.
**Caught by** adversarial reading, never by a checker, because the prose contains no machine-checkable
claim. → This is why `checkers/prose_integrity.py` exists.

### Guidance prose lived in one artifact and not the other, invisibly
A workbook and a markdown file were generated from one source. Two rows of pure guidance prose — the
entire "how to quote these numbers" discipline, and the pointer to the rules document — existed only in
the workbook. The markdown was the file people paste from.
**Survived ten adversarial passes.** The md/xlsx parity gate compares **numbers**; both rows contained
none, so the gate was structurally blind and every reviewer who trusted it inherited that blindness.
**Caught by** a human asking, "did you update the README tab?"
→ **A checker does not merely miss things; it teaches its blind spot to everyone who trusts it.**

### A single-source mechanism enforced presence, not consistency
A gate required each standing claim to appear in both artifacts, and refused to build otherwise. The
source held both a claim **and its retraction**. The gate confirmed both were present in both files and
stamped the contradiction into the deliverable, twice, with a green build.
→ Presence is not consistency.

---

## Class 4 — the fix was reported and had not happened

### Three fixes reported complete had never rendered
Applied to the source JSON. Build succeeded. Changelog said done. Neither published artifact contained
them. **Caught by** grepping the rendered files instead of the source.

### A commit message asserted a reconciliation that was not applied
The script printed "1 optional item applied." The commit message described three.

### "VERIFIED IN THE RENDERED ARTIFACTS" was itself unverified
The verification consisted of grepping for the *presence* of a string. The surrounding sentence was
never read. A spliced sentence (`it.15.5%`) shipped **inside the passage that claimed to be verified**.
→ Read it; do not grep it. Grep cannot see the sentence a string landed in.

---

## Class 5 — the verification was the thing that was broken

### Our own gate passed 5 of 5 deliberately broken output tensors
A gate written specifically to reject broken model output was handed five crafted broken tensors. It
passed all five. Every claim resting on it was void — including claims about numbers that were, as it
happened, fine.

### 37 crafted defects were run against our checkers; 35 passed
Per checker: 13/13 passed, 5/5, 5/5, 6/7, 5/6, 1/1. Each checker caught faithful *replicas* of the
defect it was built from and missed nearly every *variation*. **One checker passed the exact trap case
quoted in its own docstring.** The single entry point reported ALL CLEAR over a fabricated record of
160,000 inferences/second.
→ **Self-written verification generalises badly.** Every gate ships with a negative control that
deliberately breaks it, and the control is re-run whenever the gate changes. A gate that has never
fired is not evidence.

### 29% of audit findings were created by the previous fix
Across seven adversarial passes, **22 of 76 findings were injected by the preceding fix round**, and
seven of nine passes contained at least one.
→ Late in a review, a cosmetic fix is a bad bet. Re-audit after every fix round.

---

## Class 6 — the instrument, not the measurement

### Changing the power instrument silently broke sampling
A switch to a better power sensor improved rail coverage and broke *during-run* sampling. The reported
figure fell from ~48 W to ~3 W. The number was implausible enough to notice — which is luck, not
method, and a 20% error would have shipped.

### Killing a wedged accelerator process made the board return plausible wrong numbers
`kill -9` on a runtime holding the DSP left it wedged. The board then ran **24× slow while returning
entirely plausible-looking numbers**, and later returned an absurd 160,000 IPS once fully dead. Neither
a runtime restart nor a reboot recovered it — it needed a physical power cycle.
→ The dangerous state is not the crash; it is the degraded state that still answers.

### Cross-board stimulus asymmetry was found at document-review time
One board was loaded 8× harder than another in a comparison that was presented as like-for-like. It
should have failed at run time.
→ Every check that *can* live in the harness must live in the harness.

### Three rebuilds agreed to 0.8% and understated real build variance twelvefold
Three rebuilds of one model, made in one session on one toolchain state, agreed to **0.8%** — and were
used to declare a historical figure "not reproducible." Running the historical artifact and a fresh
rebuild back-to-back on one board showed **10.0%** between build *families*, with 0.5% run-to-run
inside each. The three rebuilds were not independent samples; they selected the same tactics.
→ Replicate at the level that actually varies. Name the engine hash in every cell.

---

## What we would tell you to do first

1. **Gate output in the same run as timing.** Everything else is cheaper than this and matters less.
2. **Hash the artifact you measured**, and put the hash in the cell.
3. **Write down the noise floor of the level you replicated at**, before you compare anything.
4. **Have someone who did not write the checkers read the finished document.** They will find the
   defects your tooling is shaped not to see — and they will find them by asking naive questions.
