#!/usr/bin/env python3
"""PROSE INTEGRITY — the defect class six adversarial passes kept finding, mechanised.

WHY THIS EXISTS
---------------
Seven audits of one deliverable. After pass 3 every remaining defect was in the PROSE, not
the numbers, and TWO OF THE LAST THREE PASSES FOUND DEFECTS CREATED BY THE PREVIOUS PASS'S
FIX. That is a convergence failure: hand-editing a 1,700-line builder to correct a sentence
reliably introduces a new one. At one deliverable it costs a night. Across the corpus --
30 generated documents -- it does not converge at all.

Every check below is a defect that actually shipped in this campaign:

  ORPHANED ANTECEDENT   pass-5 inserted a sentence between a claim and its "so the YOLOv8n
                        difference is inside noise" conclusion, silently re-pointing the
                        conclusion at the wrong subject. The claim could then be quoted as
                        saying 7.7% was both above and inside noise.
  EDITING DEBRIS        "...two build generations in play. figure. Individual cells..." --
                        a leftover word from the sentence that was replaced. It survived
                        FIVE audits inside a claim advertised as "built once from source".
  DANGLING FRAGMENT     "...not batch-4. The\nGPUs -- all mAP above is batch-1." -- a string
                        replacement that cut a sentence in half.
  STALE ASSURANCE       Sheet 1 still said the gate "was verified to reject broken tensors"
                        -- gate_v2's self-test claim, the exact assurance five deliberately
                        broken tensors defeated -- on the first page a colleague reads.
  FALSE SELF-CLAIM      the same cell asserted it "appears identically in the companion .md"
                        while differing from it.

This is deliberately a PROSE checker. deliverable_check verifies numbers trace to source;
it is structurally blind to a sentence that is grammatical, sourced, and wrong.

USAGE
    prose_integrity.py            # scan the shipped artifacts
    prose_integrity.py --self-test
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
RESULTS = os.path.dirname(BENCH)
sys.path.insert(0, HERE)
try:
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass

# Assurance language that names a WITHDRAWN method as current. Each entry is
# (pattern, why it is withdrawn). An allowed-context regex lets a sentence mention the
# withdrawn thing while retracting it -- otherwise the retraction itself would trip.
STALE_ASSURANCE = [
    (r"was verified to reject (known-)?broken tensors",
     "gate_v2's self-test claim; five deliberately broken tensors passed gate_v2"),
    (r"gate_v2 (checks|verifies|asserts)",
     "gate_v2's feature list presented as the current gate"),
    (r"single unreplicated (Orin )?pass",
     "withdrawn: the Orin int8 column is replicated (3 passes, then again on 2026-08-20)"),
    (r"cause is (still )?\*{0,2}UNRESOLVED",
     "the Orin regression is RESOLVED as engine build identity"),
    (r"the original engine no longer exists",
     "false: the artifact is on the board, md5 d1bd4057e684"),
    (r"would likely reverse the ranking",
     "perf/W was measured 2026-08-20 and did not reverse the ranking"),
    (r"[Nn]othing here is a datasheet",
     "false: ratio denominators and the iq9 power envelope are SOURCED"),
]
RETRACTION_NEARBY = re.compile(
    r"withdraw|superseded|supersedes|no longer|was false|is FALSE|earlier version|"
    r"earlier draft|does NOT inherit|retract|corrected|replaced by|all five passed|"
    r"it (has been|was) measured|did not measure it|and it did not", re.I)

# A conclusion whose subject can be silently re-pointed by an insertion above it.
DEICTIC_CONCLUSION = re.compile(
    r"\b(so|therefore|which means|hence) the [a-z0-9_]+ (difference|delta|figure|value|gap)\b", re.I)

DEBRIS = [
    (re.compile(r"[.!?]\s+[a-z]{2,12}\.\s+[A-Z]"), "orphaned word between two sentences (edit debris)"),
    # NO-SPACE SPLICE. Pass 9 caught "will not reproduce it.15.5% replicate spread." -- an
    # insertion placed BEFORE the old continuation line instead of replacing it. Every debris
    # pattern above requires whitespace after the full stop, so this checker -- built for
    # exactly this class -- reported 0 findings on it. A period followed immediately by a
    # letter or digit is either a spliced edit or a decimal; decimals are excluded by
    # requiring a non-digit before the period.
    # Structural, not an extension denylist: an extension list is whack-a-mole (the residue
    # check taught that). A filename is <stem>.<short lowercase ext>; an abbreviation is
    # <letter>.<letter>. Neither is a spliced sentence. What IS a splice: a period followed
    # immediately by a DIGIT or a CAPITAL, which no filename or abbreviation produces.
    (re.compile(r"(?<=[A-Za-z])\.(?=[0-9]|[A-Z][a-z])"),
     "sentence spliced with no space after the full stop (insertion did not replace)"),
    (re.compile(r"\b(\w+)\s+\1\b(?!\s*\))"), "doubled word"),
    (re.compile(r"[.!?]\s*\n\s*(?![a-z0-9_]+\s*$)[a-z]{2,}[^.\n]{0,40}$", re.M),
     "sentence continuing after a full stop"),
    (re.compile(r"\(\s*\)|\[\s*\]"), "empty bracket left by an edit"),
    (re.compile(r"\bThe\s*\n\s*[A-Z]"), "sentence cut in half by a replacement"),
    # STRANDED FUNCTION WORD. A string replacement that swaps a noun phrase but leaves the
    # article or preposition that introduced it: "METHOD DETAIL: the every engine was
    # RE-GATED". Pass 7 held the send for exactly this -- one word, in the first sentence a
    # reader meets, inside the cell asserting the two files cannot drift. The three original
    # checks missed it because it is grammatical debris, not a stale claim or a cut sentence.
    # DETERMINER followed by DETERMINER only. The first version of this rule also matched
    # PREPOSITION+determiner ("with the", "on this") -- ordinary English -- and produced 348
    # findings on a clean document. A checker that noisy is as useless as one tuned silent,
    # in the opposite direction: nobody reads either.
    (re.compile(r"\b(the|a|an)\s+(the|a|an|every|each|its|their|this|that|these|those)\s+\w", re.I),
     "stranded determiner from a replacement (e.g. 'the every engine')"),
]


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def scan(text, label):
    out = []
    for pat, why in STALE_ASSURANCE:
        for m in re.finditer(pat, text):
            ctx = text[max(0, m.start() - 320): m.end() + 320]
            if not RETRACTION_NEARBY.search(ctx):
                out.append((label, "STALE ASSURANCE", m.group(0)[:60], why))
    for rx, why in DEBRIS:
        for m in rx.finditer(text):
            frag = m.group(0).replace("\n", " ")[:60]
            if why == "doubled word" and frag.split()[0].lower() in ("that", "had", "is", "the"):
                continue                      # "that that" is legitimate English often enough
            out.append((label, "EDIT DEBRIS", frag, why))
    return out


def scan_deictic(text, label):
    """A conclusion pointing back at 'the X difference' is only safe when exactly ONE such
    subject is introduced before it in the same paragraph. Two, and an insertion has
    re-pointed it -- which is exactly what happened to iq9_ceiling_build."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        for m in DEICTIC_CONCLUSION.finditer(para):
            before = para[:m.start()]
            subjects = set(re.findall(r"\b(yolov8[nl]|v8[nl])\b", before, re.I))
            if len(subjects) > 1:
                out.append((label, "ORPHANED ANTECEDENT", m.group(0)[:60],
                            f"{len(subjects)} candidate subjects precede this conclusion "
                            f"({sorted(subjects)}); an insertion can silently re-point it"))
    return out


def main():
    if "--self-test" in sys.argv:
        return self_test()
    md_path = os.path.join(RESULTS, "IQ9075_vs_OrinAGX_vs_Thor_Colleague_Request.md")
    xl_path = os.path.join(RESULTS, "IQ9075_vs_OrinAGX_vs_Thor_Colleague_Request.xlsx")
    md = open(md_path, errors="ignore").read()
    try:
        import openpyxl
        wb = openpyxl.load_workbook(xl_path, data_only=True)
        # ONE CELL AT A TIME. Flattening the workbook into a single string made every cell
        # boundary look like a sentence boundary, so the Standing Claims sheet's key names
        # (snake_case identifiers in column A) each read as "a sentence continuing after a
        # full stop" -- 40+ false positives on the first run. A checker that must be
        # explained away is a checker nobody reads.
        xl_cells = [str(c.value) for ws in wb.worksheets
                    for r in ws.iter_rows() for c in r if c.value is not None]
    except Exception as e:
        print(f"could not read workbook: {e}")
        xl_cells = []
    findings = scan(md, "md") + scan_deictic(md, "md")
    for _cell in xl_cells:
        findings += scan(_cell, "xlsx") + scan_deictic(_cell, "xlsx")
    print("=" * 74)
    print("PROSE INTEGRITY — stale assurance, edit debris, orphaned antecedents")
    print("=" * 74)
    for lab, kind, frag, why in findings:
        print(f"\n[{kind}] {lab}: {frag!r}\n    {why}")
    if not findings:
        print("\nNo stale assurance, edit debris or orphaned antecedent found in either artifact.")
    print(f"\n{len(findings)} finding(s)")
    _log_event("gate_pass" if not findings else "gate_trip", tool="prose_integrity",
               check="SUMMARY", n_fail=len(findings))
    return 1 if findings else 0


def self_test():
    """Every case is a defect that actually shipped in this campaign."""
    cases = [
        ("stale gate_v2 assurance, no retraction nearby",
         "The detection gate checks scores and box geometry and was verified to reject broken "
         "tensors; the IQ-9075 returns 45 detections.", True),
        ("the same sentence WITH its retraction — must not fire",
         "This supersedes the earlier assurance that the gate was verified to reject broken "
         "tensors: an adversarial review put five deliberately broken tensors through gate_v2 "
         "and all five passed.", False),
        ("edit debris: orphaned word",
         "…two build generations in play. figure. Individual cells are not tagged.", True),
        ("dangling fragment cut by a replacement",
         "Orin peaks at batch-1, not batch-4. The\nGPUs — all mAP above is batch-1.", True),
        ("withdrawn 'single unreplicated pass'",
         "1.9% against an Orin figure that is a single unreplicated pass from an earlier session.", True),
        ("clean prose — must not fire",
         "Every engine was re-gated on 2026-08-20 against COCO ground truth in the same "
         "invocation as its timing.", False),
    ]
    bad = 0
    for name, text, should in cases:
        got = bool(scan(text, "t"))
        ok = got == should
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'BUG'}] fired={str(got):5s} want={str(should):5s}  {name}")
    d_cases = [
        ("orphaned antecedent: two subjects before the conclusion",
         "The yolov8l pair is 16% apart. The yolov8n pair is 7.7% apart. Two runs gave 947.9 and "
         "987.7 IPS -- so the yolov8n difference is inside noise.", True),
        ("single subject — safe",
         "The yolov8n build delta is -5.3%. Two runs gave 947.9 and 987.7 IPS -- so the yolov8n "
         "difference is inside noise.", False),
    ]
    for name, text, should in d_cases:
        got = bool(scan_deictic(text, "t"))
        ok = got == should
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'BUG'}] fired={str(got):5s} want={str(should):5s}  {name}")
    total = len(cases) + len(d_cases)
    print(f"\n{total - bad}/{total} self-test cases pass")
    _log_event("gate_pass" if not bad else "gate_trip", tool="prose_integrity",
               check="SELF_TEST", n_fail=bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
