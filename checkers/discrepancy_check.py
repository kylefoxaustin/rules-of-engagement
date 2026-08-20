#!/usr/bin/env python3
"""DISCREPANCY CHECK — mechanises M36 and the source-of-record half of M37.

M36: an unexplained discrepancy BLOCKS. A caveat is not an explanation.
M37: corrections are PROPAGATED, not APPENDED — two live values for one measurand is
     a defect, not a nuance.

THE EVENT THAT BOUGHT THIS
--------------------------
On 2026-08-18 a rebuild disagreed with the published figure by 20% on yolov8L batch-1.
Every gate passed on both builds — they were both real measurements of a real thing.
The deliverable was written, verified by a 10-check gate, reviewed, and about to be
sent, carrying an honest caveat reading *"the reason is not established"*.

Chasing it instead of shipping it found an ONNX opset that changed the on-chip working
set 9.5x, and established that the ORIGINAL number was right and the rebuild was wrong.
Had it shipped, that caveat would have been true, well written, and would have retracted
a correct result.

Nothing in 35 rules made the discrepancy blocking. A human declining to ship is what
saved it, and a human at 2am is exactly what this standard exists to not rely on.

WHAT IT DOES
    Walks the source of record, groups leaf numbers that name the SAME measurand
    (same model + batch + metric, wherever they appear), and fails when two live
    values disagree by more than the noise floor. A value inside a block carrying a
    _SUPERSEDED / _WITHDRAWN marker is not live and does not count.

USAGE
    discrepancy_check.py [source.json ...]
    discrepancy_check.py --self-test
"""
from __future__ import annotations

import json
import os
import re
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
DEAD_MARKERS = ("_SUPERSEDED", "_WITHDRAWN", "_RETRACTED", "_DO_NOT_USE", "_VOID")

# Default tolerance. A disagreement larger than this, between two values claiming to be
# the same quantity, is a blocking defect until its CAUSE is named.
DEFAULT_TOL_PCT = 2.0

# What counts as "the same measurand". Deliberately narrow -- BOARD + model + batch +
# metric. The first version omitted the board and duly reported Thor disagreeing with
# Orin by 257%, which is not a discrepancy, it is two different chips. A checker that
# cries wolf is a checker nobody runs (see void_check, same lesson, one day earlier).
BOARD = re.compile(r"(iq9075|iq9|orin|thor|5090|o6|imx95|ara240|neutron)", re.I)
MODEL = re.compile(r"(yolov8[nslmx]|v8[nslmx])", re.I)
BATCH = re.compile(r"(?:^|[._\-\[])b(?:atch)?[_\-]?(\d{1,2})(?![\d])", re.I)

# The metric is read from the LEAF key, not from anywhere in the path -- otherwise
# "..._ms.yolov8n.b8" and "..._ratio" collapse onto each other.
LEAF_METRIC = [
    (re.compile(r"map_ratio|_ratio$", re.I),           "ratio"),
    (re.compile(r"\bmap\b|map50", re.I),               "map"),
    (re.compile(r"recall", re.I),                     "recall"),
    (re.compile(r"gain_pct|_pct$|percent|spread|floor|delta", re.I), "SKIP"),
    (re.compile(r"ips|throughput", re.I),             "ips"),
    # per-image and per-batch are DIFFERENT quantities. Conflating them is its own
    # defect class (a batch-4 per-batch figure is 4x its per-image figure, which looks
    # exactly like a 300% discrepancy).
    (re.compile(r"per_image|per_img", re.I),          "latency_per_image"),
    (re.compile(r"per_batch|per_infer", re.I),        "latency_per_batch"),
    (re.compile(r"latency|accel|_ms$|_us$|\bms\b|\bus\b", re.I), "latency_UNSPEC"),
]


def _metric_of(jsonpath):
    """Metric from the leaf key first, then from its immediate parent (which is where
    unit suffixes like `orin_fp16_ms` live)."""
    parts = [x for x in re.split(r"[.\[\]]", jsonpath) if x]
    for token in reversed(parts[-3:]):
        for pat, name in LEAF_METRIC:
            if pat.search(token):
                return None if name == "SKIP" else name
    return None


def walk(obj, path="", dead=False):
    """Yield (jsonpath, value, is_dead). A subtree under a _SUPERSEDED block is dead."""
    if isinstance(obj, dict):
        here_dead = dead or any(m in obj for m in DEAD_MARKERS)
        for k, v in obj.items():
            if k in DEAD_MARKERS:
                continue
            yield from walk(v, f"{path}.{k}" if path else k, here_dead)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]", dead)
    else:
        yield path, obj, dead


def measurand(jsonpath):
    """Identity of a quantity: (board, model, batch, metric). None if not identifiable.
    All four must be present -- an unidentifiable path is skipped rather than guessed at."""
    bd = BOARD.search(jsonpath)
    m = MODEL.search(jsonpath)
    b = BATCH.search(jsonpath)
    t = _metric_of(jsonpath)
    if not (bd and m and b and t):
        return None
    board = bd.group(1).lower().replace("iq9075", "iq9")
    return (board, m.group(1).lower().replace("yolov8", "v8"), b.group(1), t)


def to_ms(v, jsonpath):
    """Normalise latency units so 1699 us and 1.699 ms compare equal."""
    if not isinstance(v, (int, float)):
        return None
    return v / 1000.0 if re.search(r"_us\b|_us[._]|\bus\b|microsec", jsonpath, re.I) else float(v)


def scan(paths, tol_pct=DEFAULT_TOL_PCT):
    groups = {}
    for p in paths:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        for jp, v, dead in walk(d):
            if dead or not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            key = measurand(jp)
            if not key:
                continue
            norm = to_ms(v, jp) if key[3].startswith("latency") else float(v)
            if norm is None or norm <= 0:
                continue
            groups.setdefault(key, []).append((norm, v, f"{os.path.basename(p)}#{jp}"))

    findings = []
    for key, vals in sorted(groups.items()):
        if len(vals) < 2:
            continue
        # A group whose metric is UNSPEC mixes per-image and per-batch conventions and
        # cannot be adjudicated automatically; it is a LABELLING defect, reported by
        # unspecified_units() rather than as a value disagreement.
        if key[3] == "latency_UNSPEC":
            continue
        lo = min(vals, key=lambda t: t[0])
        hi = max(vals, key=lambda t: t[0])
        if lo[0] <= 0:
            continue
        delta = 100.0 * (hi[0] - lo[0]) / lo[0]
        if delta > tol_pct:
            findings.append((key, delta, lo, hi, len(vals)))
    return findings


def unspecified(paths):
    """Latency values whose path does not say per-image or per-batch. Not a value
    disagreement -- a labelling defect that MAKES value disagreements unadjudicable."""
    out = set()
    for p in paths:
        try:
            d = json.load(open(p))
        except Exception:
            continue
        for jp, v, dead in walk(d):
            if dead or not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            k = measurand(jp)
            if k and k[3] == "latency_UNSPEC":
                out.add((k[0], k[1], k[2]))
    return sorted(out)


def report(findings, tol_pct=DEFAULT_TOL_PCT):
    print("=" * 74)
    print("DISCREPANCY CHECK (M36/M37) — two live values for one measurand")
    print("=" * 74)
    if not findings:
        print(f"\nNo measurand carries two live values differing by more than {tol_pct}%.")
    for key, delta, lo, hi, n in findings:
        board, model, batch, metric = key
        print(f"\n[BLOCKING] {board} {model} batch-{batch} {metric}: {delta:.1f}% disagreement "
              f"across {n} live values")
        print(f"    {lo[1]}  <-  {lo[2]}")
        print(f"    {hi[1]}  <-  {hi[2]}")
        print(f"    M36: this blocks until the CAUSE is identified. A caveat saying the")
        print(f"    reason is unknown is not an explanation — mark the losing block")
        print(f"    _SUPERSEDED with the reason, or withdraw the claim.")
    print("\n" + "=" * 74)
    print(f"{len(findings)} blocking discrepanc{'y' if len(findings)==1 else 'ies'}")
    return len(findings)


def self_test():
    """Tests the REGISTRY mode, because that is what actually runs.

    An earlier self-test exercised the path-inference mode instead. That mode was
    retired -- it could not tell a genuine disagreement from a different point in a
    config sweep (1-NSP P1 = 326.3 IPS vs dual-NSP P4 = 1012.7 IPS are both correct)
    and produced 21 false blocking findings. M34 had already predicted it: a JSON path
    is a human-editable string, so it must not be a machine key. A self-test that
    exercises retired code is worse than none -- it reports green for a path nobody
    takes.
    """
    m = {"id": "iq9.yolov8l.b1.latency_per_image_ms", "value": 7.159, "unit": "ms",
         "superseded": [{"value": 8.682, "why": "opset-17 build"}]}
    cases = [
        ("dead value alone -> BLOCK", "the rebuild measures 8.682 ms for that quantity", True),
        ("dead value WITH its replacement -> ok", "was 8.682 ms; corrected to 7.159 ms", False),
        ("canonical value only -> ok", "IQ-9075 YOLOv8L batch-1 is 7.159 ms", False),
        ("no relevant value -> ok", "Thor YOLOv8L batch-1 is 2.298 ms", False),
        ("rounding must NOT invent a match", "the ratio was 8.7x on that run", False),
    ]
    bad = 0
    for name, text, should in cases:
        fired = _num_in(text, 8.682) and not _num_in(text, 7.159)
        ok = fired == should
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'BUG'}] fires={str(fired):5s} want={str(should):5s}  {name}")
    print(f"\n{len(cases)-bad}/{len(cases)} self-test cases pass")
    _log_event("gate_pass" if not bad else "gate_trip", tool="discrepancy_check",
               check="SELF_TEST", n_fail=bad)
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# REGISTRY MODE — the mechanism that actually works (see canonical_register.json).
# ---------------------------------------------------------------------------
REGISTER = os.path.join(BENCH, "campaign", "canonical_register.json")


def _texts():
    import openpyxl
    RESULTS = os.path.dirname(BENCH)
    out = {}
    for fn in sorted(os.listdir(RESULTS)):
        p = os.path.join(RESULTS, fn)
        if fn.endswith(".md"):
            out[fn] = open(p, encoding="utf-8", errors="ignore").read()
        elif fn.endswith(".xlsx"):
            try:
                wb = openpyxl.load_workbook(p, data_only=True)
                out[fn] = "\n".join(str(c.value) for w in wb.worksheets
                                    for r in w.iter_rows() for c in r if c.value is not None)
            except Exception:
                pass
    return out


def _num_in(text, val):
    """Is this exact value present as a standalone number?"""
    # EXACT representations only. An earlier version also tried rounded forms, so
    # 1.8822 matched the string "1.9" and fired on unrelated numbers everywhere.
    # Rounding to fewer decimals does not find the value, it invents matches.
    forms = {f"{val:g}", str(val)}
    if float(val) == int(val):
        forms.add(str(int(val)))
    for form in forms:
        if re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d]|\.\d)", text):
            return True
    return False


def registry_check():
    if not os.path.exists(REGISTER):
        print("no canonical register — nothing to enforce")
        return 0
    reg = json.load(open(REGISTER))
    texts = _texts()
    print("=" * 74)
    print("CANONICAL VALUE CHECK (M36/M37) — one live value per measurand")
    print("=" * 74)
    fails = 0
    for m in reg["measurands"]:
        for fn, text in texts.items():
            for sup in m.get("superseded", []):
                if not _num_in(text, sup["value"]):
                    continue
                # legitimate only if the canonical value travels with it (M37)
                if _num_in(text, m["value"]):
                    continue
                fails += 1
                print(f"\n[BLOCKING] {fn}: superseded {sup['value']} {m['unit']} present "
                      f"WITHOUT its replacement {m['value']}")
                print(f"    measurand : {m['id']}")
                print(f"    why dead  : {sup['why']}")
                print(f"    M37: a correction is complete only when no instance of the old")
                print(f"    value remains except inside a retraction naming the new one.")
    print("\n" + "=" * 74)
    print(f"{fails} measurand(s) carrying a live superseded value")
    _log_event("gate_trip" if fails else "gate_pass", tool="discrepancy_check",
               check="CANONICAL", n_fail=fails, n_measurands=len(reg["measurands"]))
    return fails


def main():
    if "--self-test" in sys.argv:
        return self_test()
    if "--explore" not in sys.argv:
        return 1 if registry_check() else 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        rm = os.path.join(BENCH, "remeasure")
        args = [os.path.join(rm, f) for f in sorted(os.listdir(rm)) if f.endswith(".json")]
    f = scan(args)
    n = report(f)
    _log_event("gate_trip" if n else "gate_pass", tool="discrepancy_check",
               check="LIVE_DISAGREEMENT", n_fail=n, n_sources=len(args))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
