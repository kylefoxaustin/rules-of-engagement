#!/usr/bin/env python3
"""M35 shared-context diff + M19 caveat-debt scan — the last two buildable rules.

M35 — EVERYTHING EXCEPT THE VARIABLE UNDER STUDY MUST ACTUALLY BE THE SAME
    Every comparison carries a context that is in no config file: calibration set,
    dataset, driver and firmware, harness version, preprocessing convention, power
    envelope. These ride along invisibly and nothing errors when they diverge.

    Instance that bought the rule: a batch-knee table compared batch-1 (quantised on
    500 COCO images) against batch-4 (quantised on 8 crops of one JPEG). The table's
    entire purpose was to isolate batch size, and batch size was not the only thing
    that changed. Both facts sat in the source of record one block apart.

    This diffs the shared context of every pair of records claiming to be comparable
    and fails when a field differs that is NOT the declared variable. "Not recorded"
    fails the same as "different", because an unrecorded condition is one nobody checked.

M19 — IF A CAVEAT NAMES A MEASUREMENT THAT WOULD CHANGE THE RANKING, MAKE IT
    A caveat saying "a perf/W comparison would likely REVERSE this ranking and has NOT
    been measured" is an admission that the headline may be backwards. Left in place it
    reads as diligence while the load-bearing measurement never happens.

    This scans deliverables for caveats that name an unmade measurement AND assert it
    could change the conclusion, and reports them as DEBT with the claim they threaten.

USAGE
    context_and_caveat_check.py [--self-test]
"""
from __future__ import annotations

import glob
import json
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

# Fields that must match between two records being compared, unless one of them IS the
# declared variable under study.
CONTEXT_FIELDS = [
    ("calibration", lambda r: (r.get("config", {}).get("requested", {}) or {}).get("calibration")),
    ("precision",   lambda r: (r.get("config", {}).get("measured", {}) or {}).get("precision")),
    ("power_mode",  lambda r: (r.get("envelope") or {}).get("power_mode")),
    ("governor",    lambda r: (r.get("envelope") or {}).get("cpu_governor")),
    ("gate_image_set", lambda r: (r.get("gate") or {}).get("image_set")),
    ("metric",      lambda r: (r.get("stats") or {}).get("metric")
                    or (r.get("notes") or "")[:0] or None),
    ("unit",        lambda r: r.get("unit")),
    ("accel_id",    lambda r: (r.get("accelerator_identity") or {}).get("accel_id")
                    or (r.get("board_identity") or {}).get("board_id")),
]

# Context fields that must be POSITIVELY stated. Absent on both sides is a finding, not
# a pass -- see diff_context.
REQUIRED_CONTEXT = {"calibration", "precision", "gate_image_set"}

# A caveat that both (a) names something unmeasured and (b) says it could change the
# answer is debt, not diligence.
UNMEASURED = re.compile(
    r"(has NOT been measured|was not measured|not measured here|no replicate|single build|"
    r"single pass|unverified|cannot be measured|we could not measure|never re-run)", re.I)
WOULD_CHANGE = re.compile(
    r"(would likely REVERSE|would reverse|could reverse|changes the ranking|"
    r"would change the (ranking|conclusion|verdict)|is a floor, not|"
    r"treat (it|this) as a floor|may be backwards|not a settled number)", re.I)


def diff_context(a, b, variable):
    out = {}
    for name, get in CONTEXT_FIELDS:
        if name == variable:
            continue
        va, vb = get(a), get(b)
        # BOTH-MISSING IS A FINDING. The docstring above has always claimed that "not
        # recorded" fails the same as "different" -- but this compared va != vb, and
        # None != None is False, so a field NOBODY recorded produced silence. That is
        # backwards: the check reported clean in exactly the case where the context is
        # least known. Found when all 8 batch-curve records turned out to name no
        # calibration set at all, while TWO near-disjoint 500-image COCO sets (3 tensors
        # in common) were in play on disk, indistinguishable by shape or size.
        if va is None and vb is None:
            if name in REQUIRED_CONTEXT:
                out[name] = {"A": None, "B": None, "unrecorded": True,
                             "why": "neither record states it; an unrecorded condition "
                                    "is one nobody checked"}
        elif va != vb:
            out[name] = {"A": va, "B": vb,
                         "unrecorded": (va is None or vb is None)}
    return out


def scan_records(variable="batch"):
    recs = []
    for f in glob.glob(os.path.join(BENCH, "campaign", "records", "*.json")):
        recs += json.load(open(f)).get("records", [])
    recs = [r for r in recs if r.get("status") == "OK"]
    findings = []
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            a, b = recs[i], recs[j]
            # only compare records of the same measurand family
            fa = re.search(r"(v8[nl])", a.get("what", "") or "")
            fb = re.search(r"(v8[nl])", b.get("what", "") or "")
            if not fa or not fb or fa.group(1) != fb.group(1):
                continue
            d = diff_context(a, b, variable)
            if d:
                findings.append((a.get("what", "")[:44], b.get("what", "")[:44], d))
    return findings, len(recs)


def scan_caveats():
    """Scans .md AND .xlsx. The first version read only markdown -- and the caveat that
    motivated this rule ("a perf/W comparison would likely REVERSE the ranking and has
    NOT been measured") lives in a spreadsheet cell. A checker pointed at the wrong
    surface reports clean and means nothing."""
    debts = []
    for fn in sorted(os.listdir(RESULTS)):
        path = os.path.join(RESULTS, fn)
        if fn.endswith(".md"):
            for ln, line in enumerate(open(path, errors="ignore"), 1):
                if UNMEASURED.search(line) and WOULD_CHANGE.search(line):
                    debts.append((fn, f"line {ln}", line.strip()[:190]))
        elif fn.endswith(".xlsx"):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(path, data_only=True)
            except Exception:
                continue
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if c.value is None:
                            continue
                        t = str(c.value)
                        if UNMEASURED.search(t) and WOULD_CHANGE.search(t):
                            debts.append((fn, f"{ws.title}!{c.coordinate}", t.strip()[:190]))
    return debts


def main():
    if "--self-test" in sys.argv:
        return self_test()
    print("=" * 74)
    print("M35 SHARED-CONTEXT DIFF — everything except the variable must be the same")
    print("=" * 74)
    f, n = scan_records()
    if not f:
        print(f"\n{n} records compared pairwise; no context field differs except the "
              f"declared variable.")
    for a, b, d in f[:8]:
        print(f"\n[CONTEXT MISMATCH]\n  A: {a}\n  B: {b}")
        for k, v in d.items():
            tag = "NOT RECORDED" if v["unrecorded"] else "DIFFERS"
            print(f"     {k:16s} {tag}: {v['A']!r} vs {v['B']!r}")

    print("\n" + "=" * 74)
    print("M19 CAVEAT DEBT — a caveat naming an unmade, ranking-changing measurement")
    print("=" * 74)
    debts = scan_caveats()
    if not debts:
        print("\nNo caveat both names something unmeasured and says it could change the answer.")
    for fn, ln, txt in debts:
        print(f"\n[DEBT] {fn}:{ln}\n   {txt}")
        print(f"   M19: this admits the conclusion may be wrong. Make the measurement, or")
        print(f"   withdraw the claim it threatens. A caveat is not a substitute for either.")
    total = len(f) + len(debts)
    print("\n" + "=" * 74)
    print(f"{len(f)} context mismatch(es), {len(debts)} caveat debt(s)")
    _log_event("gate_trip" if total else "gate_pass", tool="context_and_caveat_check",
               check="M35_M19", n_fail=total)
    return 1 if total else 0


def self_test():
    A = {"what": "iq9 v8n_b1", "status": "OK", "unit": "us",
         "config": {"requested": {"calibration": "500 COCO"}, "measured": {"precision": "int8"}},
         "envelope": {"power_mode": "burst", "cpu_governor": "schedutil"},
         "gate": {"image_set": "coco_val2017_500"},
         "accelerator_identity": {"accel_id": "abc"}}
    B = json.loads(json.dumps(A)); B["what"] = "iq9 v8n_b4"
    C = json.loads(json.dumps(B)); C["config"]["requested"]["calibration"] = "8 crops of busy.jpg"
    D = json.loads(json.dumps(B)); D["envelope"]["power_mode"] = None
    E = json.loads(json.dumps(A)); E["config"]["requested"].pop("calibration")
    F = json.loads(json.dumps(B)); F["config"]["requested"].pop("calibration")
    cases = [
        ("identical context -> no finding", A, B, False),
        ("THE REAL EVENT: calibration differs across a batch comparison", A, C, True),
        ("a context field NOT RECORDED on one side", A, D, True),
        ("THE BLIND SPOT: calibration absent on BOTH sides -- the state every real "
         "record was in while this checker reported clean", E, F, True),
    ]
    bad = 0
    for name, x, y, should in cases:
        d = diff_context(x, y, "batch")
        got = bool(d)
        ok = got == should
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'BUG'}] mismatch={str(got):5s} want={str(should):5s}  {name}")
        if d and ok:
            print(f"        {list(d)}")
    cav = [("names unmeasured + would reverse",
            "A perf/W comparison would likely REVERSE the ranking and has NOT been measured.", True),
           ("ordinary caveat, no ranking claim",
            "Thor was run at MAXN to match Orin.", False),
           ("names unmeasured but harmless",
            "Sustained thermal behaviour beyond 20 s was not measured.", False)]
    for name, line, should in cav:
        got = bool(UNMEASURED.search(line) and WOULD_CHANGE.search(line))
        ok = got == should
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'BUG'}] debt={str(got):5s} want={str(should):5s}  {name}")
    print(f"\n{len(cases)+len(cav)-bad}/{len(cases)+len(cav)} self-test cases pass")
    _log_event("gate_pass" if not bad else "gate_trip", tool="context_and_caveat_check",
               check="SELF_TEST", n_fail=bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
