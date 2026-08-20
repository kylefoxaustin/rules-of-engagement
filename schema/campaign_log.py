#!/usr/bin/env python3
"""CAMPAIGN EVENT LOG — the corpus redo, instrumented as an experiment.

This must be capturing BEFORE the first benchmark of the redo. The data is
prospective-only: defect escape rates cannot be reconstructed afterwards, because the
defects that never escaped leave no trace unless something logs them at the moment
they are caught.

WHAT WE ARE TRYING TO MEASURE
    Does mechanised verification actually reduce the rate at which defects reach a
    deliverable, and by how much? One data point exists already and it is striking:
    a 9-check gate its own author was confident in let **22 of 24** crafted defects
    through. That is an anecdote. ~746 claims across 7 boards is a sample.

THE HEADLINE NUMBER TO COLLECT
    defect ESCAPE RATE with gates on vs off, on a held-out slice that never ships.

WHY IT IS AUTOMATIC
    The single hardest-won lesson of the campaign that produced this file: a rule
    enforced by remembering is enforced sometimes. So the checkers log their own
    trips. Nobody has to decide whether a defect was "worth recording" -- and the
    boring ones are the data, because a defect that was trivial to fix still escaped
    detection until something caught it.

USAGE
    from campaign_log import log_event
    log_event("gate_trip", tool="deliverable_check", check="C1", detail="...", severity="fail")

    campaign_log.py summary          # escape rates, defect classes, harness bugs
    campaign_log.py note <type> ...  # append a manual event (harness bugs, audit findings)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
LOG = os.path.join(BENCH, "campaign", "events.jsonl")

# Event types, and what each is for. Keep this list short and stable -- a taxonomy
# that drifts mid-campaign cannot be aggregated at the end.
EVENT_TYPES = {
    "gate_trip":     "a checker refused something (the core escape-rate signal)",
    "gate_pass":     "a checker ran clean (needed as the denominator)",
    "harness_bug":   "a defect in the MEASURING code, not the thing measured",
    "measurement":   "a benchmark record was produced",
    "rebuild":       "a published number changed after first being recorded",
    "audit_finding": "an adversarial reviewer found something the gates did not",
    "ab_run":        "a held-out measurement deliberately run with gates DISABLED",
}


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BENCH,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def log_event(event_type: str, **fields) -> None:
    """Append one event. Never raises -- instrumentation must not break a run."""
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "type": event_type, "git": _git_sha(), **fields}
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _load() -> list[dict]:
    if not os.path.exists(LOG):
        return []
    out = []
    for line in open(LOG):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def summary() -> int:
    ev = _load()
    if not ev:
        print("No events yet. The log is at:", LOG)
        print("\nThis is expected before the corpus redo starts — but it MUST be")
        print("non-empty before the first benchmark, or the escape-rate data is lost.")
        return 0

    print("=" * 72)
    print(f"CAMPAIGN LOG — {len(ev)} events, {ev[0]['ts']} .. {ev[-1]['ts']}")
    print("=" * 72)

    by_type: dict[str, int] = {}
    for e in ev:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print("\nEvents by type:")
    for k in sorted(by_type):
        print(f"  {k:16s} {by_type[k]:5d}   {EVENT_TYPES.get(k, '')}")

    # A per-FINDING trip (one per violating file) and a per-RUN pass are not the same
    # unit. Mixing them produced a meaningless "96.9% of builds blocked". Runs are
    # counted only from SUMMARY-granularity events; findings are counted separately.
    trips = [e for e in ev if e["type"] == "gate_trip"]
    passes = [e for e in ev if e["type"] == "gate_pass"]
    run_trips = [e for e in trips if e.get("check") == "SUMMARY" or "n_fail" in e]
    finding_trips = [e for e in trips if e not in run_trips]
    if trips or passes:
        total_runs = len(run_trips) + len(passes)
        print(f"\nGATE ACTIVITY")
        print(f"  runs      : {total_runs} checker invocations, {len(run_trips)} blocked "
              f"= {100*len(run_trips)/max(total_runs,1):.1f}%")
        print(f"  findings  : {len(finding_trips)} individual defects refused "
              f"(one per offending file/value; NOT commensurable with runs)")
        by_check: dict[str, int] = {}
        for t in trips:
            k = f"{t.get('tool','?')}:{t.get('check','?')}"
            by_check[k] = by_check.get(k, 0) + 1
        print("  which check caught it:")
        for k, v in sorted(by_check.items(), key=lambda x: -x[1]):
            print(f"    {k:34s} {v:4d}")

    hb = [e for e in ev if e["type"] == "harness_bug"]
    if hb:
        print(f"\nHARNESS BUGS: {len(hb)} — defects in the measuring code itself")
        for e in hb[-8:]:
            print(f"    {e['ts'][:10]}  {e.get('detail','')[:88]}")

    af = [e for e in ev if e["type"] == "audit_finding"]
    if af:
        gate_missed = [e for e in af if e.get("gate_caught") is False]
        print(f"\nADVERSARIAL FINDINGS: {len(af)}, of which {len(gate_missed)} were "
              f"MISSED by the gates")
        if af:
            print(f"  -> gate blind-spot rate: {100*len(gate_missed)/len(af):.0f}%")
        by_class: dict[str, int] = {}
        for e in af:
            c = e.get("defect_class", "?")
            by_class[c] = by_class.get(c, 0) + 1
        for k, v in sorted(by_class.items()):
            print(f"    class {k}: {v}")

    ab = [e for e in ev if e["type"] == "ab_run"]
    if ab:
        on = [e for e in ab if e.get("gates") == "on"]
        off = [e for e in ab if e.get("gates") == "off"]
        eon = sum(1 for e in on if e.get("escaped"))
        eoff = sum(1 for e in off if e.get("escaped"))
        print(f"\nA/B HELD-OUT SLICE:")
        print(f"    gates ON : {eon}/{len(on)} escaped" if on else "    gates ON : no runs yet")
        print(f"    gates OFF: {eoff}/{len(off)} escaped" if off else "    gates OFF: no runs yet")
        if on and off:
            r_on, r_off = eon/len(on), eoff/len(off)
            print(f"    -> escape rate {100*r_on:.1f}% vs {100*r_off:.1f}%"
                  + (f", a {r_off/r_on:.1f}x reduction" if r_on else ""))

    rb = [e for e in ev if e["type"] == "rebuild"]
    if rb:
        print(f"\nREBUILDS: {len(rb)} published numbers changed after first being recorded")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] == "summary":
        return summary()
    if sys.argv[1] == "note":
        if len(sys.argv) < 3:
            print("usage: campaign_log.py note <type> [k=v ...]")
            print("types:", ", ".join(EVENT_TYPES))
            return 2
        t = sys.argv[2]
        kv = {}
        for a in sys.argv[3:]:
            if "=" in a:
                k, v = a.split("=", 1)
                kv[k] = (v.lower() == "true") if v.lower() in ("true", "false") else v
        log_event(t, **kv)
        print(f"logged {t}: {kv}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
