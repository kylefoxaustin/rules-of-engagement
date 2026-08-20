#!/usr/bin/env python3
"""LLM GATE — output correctness for decode/prefill throughput claims.  [M1/M2/M31]

THE COVERAGE GAP THIS FILLS
---------------------------
`gate_map.py` gates detection models against COCO. The corpus is full of LLM numbers —
decode tok/s, prefill rates, TTFT — measured with `llama-bench`, which NEVER LOOKS AT
THE TEXT. Per the campaign's own law (verify the OUTPUT, not just the run), a tok/s
figure from a model emitting garbage is worth nothing, and a broken model is faster.

WHY A NEEDLE ANSWER IS NOT ENOUGH (the M31 problem)
---------------------------------------------------
`make_ctx.py` + `run_ctx.py` already plant a value in a long context and grade whether
the model recovers it, from the SAME request that produced the timing. That is a real
A1 gate and it is more than most published LLM benchmarks do.

But it is BINARY, and M31 exists because the real failure mode is DEGRADATION. A 4-bit
quantisation that halves task accuracy will still answer one easy needle. So this gate
takes two tiers:

  TIER 1 (needle)   : did the model read its context at all?  Cheap, per-run, mandatory.
  TIER 2 (task set) : how much accuracy did this artifact LOSE against its own fp32/higher
                      precision reference?  Expensive, per-artifact, required before any
                      cross-precision or cross-board comparison.

Tier 1 alone may support "this configuration ran". Only tier 2 supports "int4 is X% the
speed of fp16" — because without it the accuracy axis of that trade is unmeasured, and
per the directional-bias law the degraded model is the faster one.

USAGE
    from gate_llm import evaluate, assert_gate
    r = evaluate(trials)             # trials: [{prompt_n, answer, expected, ...}]
    assert_gate(r, ref)              # ref: the reference artifact's task accuracy

    gate_llm.py --self-test
"""
from __future__ import annotations

import json
import os
import re
import sys

try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass


class GateFail(Exception):
    """The number this run produced must not be published."""


DEFAULTS = dict(
    needle_pass_rate=1.0,        # tier 1: every trial must recover its planted value
    task_rel_floor=0.85,         # tier 2: >= 85% of the reference artifact's task accuracy
    min_answer_chars=1,
    max_repeat_ratio=0.5,        # degenerate looping output ("the the the ...")
)


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _repeat_ratio(text):
    """Fraction of the output made of the single most common token. Catches a decoder
    that has collapsed into a loop while still emitting tokens at full speed."""
    w = _norm(text).split()
    if len(w) < 8:
        return 0.0
    from collections import Counter
    return Counter(w).most_common(1)[0][1] / len(w)


def evaluate(trials, task_score=None):
    """trials: [{'answer': str, 'expected': str, 'prompt_n': int}]"""
    n = len(trials)
    hits, degenerate, empty = 0, 0, 0
    for t in trials:
        a, e = _norm(t.get("answer", "")), _norm(t.get("expected", ""))
        if not a:
            empty += 1
        if e and e in a:
            hits += 1
        if _repeat_ratio(t.get("answer", "")) > DEFAULTS["max_repeat_ratio"]:
            degenerate += 1
    return {
        "n_trials": n,
        "needle_pass_rate": (hits / n) if n else 0.0,
        "empty_answers": empty,
        "degenerate_answers": degenerate,
        "max_repeat_ratio": max([_repeat_ratio(t.get("answer", "")) for t in trials] or [0.0]),
        "task_score": task_score,          # tier 2; None if not measured
        "sample_answers": [str(t.get("answer", ""))[:80] for t in trials[:3]],
    }


def assert_gate(r, ref=None, **kw):
    t = dict(DEFAULTS); t.update(kw)
    fails = []
    if r["n_trials"] == 0:
        fails.append("no trials — a throughput number with no output check is not a measurement")
    if r["needle_pass_rate"] < t["needle_pass_rate"]:
        fails.append(f"needle pass rate {r['needle_pass_rate']:.2f} < {t['needle_pass_rate']} "
                     f"— the model did not reliably read its own context; sample answers "
                     f"{r['sample_answers']}")
    if r["empty_answers"]:
        fails.append(f"{r['empty_answers']} empty answer(s) — tokens/s with no tokens of content")
    if r["degenerate_answers"]:
        fails.append(f"{r['degenerate_answers']} degenerate answer(s) (repeat ratio up to "
                     f"{r['max_repeat_ratio']:.2f}) — a looping decoder emits tokens at full "
                     f"speed and is exactly the broken-is-faster case")

    # TIER 2 — only assertable when a reference task score exists.
    if ref and ref.get("task_score") is not None:
        if r.get("task_score") is None:
            fails.append("a reference task accuracy exists but this artifact has none; a "
                         "cross-precision or cross-board speed claim needs the accuracy axis "
                         "measured, not assumed  [M31]")
        else:
            floor = t["task_rel_floor"] * ref["task_score"]
            if r["task_score"] < floor:
                fails.append(f"task accuracy {r['task_score']:.3f} < floor {floor:.3f} "
                             f"({t['task_rel_floor']:.0%} of reference {ref['task_score']:.3f}) "
                             f"— this artifact is degraded, and degraded is faster  [M31]")
    if fails:
        raise GateFail("; ".join(fails))
    tier = 2 if r.get("task_score") is not None else 1
    return {"status": "PASS", "tier": tier,
            "needle_pass_rate": r["needle_pass_rate"], "task_score": r.get("task_score"),
            "note": ("tier 1 only: supports 'this configuration ran'. It does NOT support a "
                     "cross-precision speed comparison — that needs tier 2." if tier == 1 else
                     "tier 2: accuracy measured against a reference artifact")}


def self_test():
    """Every case is a way an LLM throughput number has been wrong in this corpus."""
    good = [{"answer": "The access code is 41762.", "expected": "41762"},
            {"answer": "It is 88301, stated in the passage.", "expected": "88301"}]
    cases = [
        ("healthy: needles recovered", good, None, None, True),
        ("empty answers — tok/s with no content",
         [{"answer": "", "expected": "41762"}], None, None, False),
        ("wrong answer — model did not read the context",
         [{"answer": "I don't know.", "expected": "41762"}], None, None, False),
        ("degenerate loop at full speed",
         [{"answer": "the the the the the the the the the the", "expected": "41762"}],
         None, None, False),
        ("tier 2: artifact at 55% of reference accuracy",
         good, 0.42, {"task_score": 0.76}, False),
        ("tier 2: artifact within tolerance",
         good, 0.70, {"task_score": 0.76}, True),
        ("tier 2 required but missing when a reference exists",
         good, None, {"task_score": 0.76}, False),
    ]
    bad = 0
    for name, trials, score, ref, should in cases:
        r = evaluate(trials, task_score=score)
        try:
            assert_gate(r, ref); ok = True; why = ""
        except GateFail as e:
            ok = False; why = str(e)
        good_ = ok == should
        bad += (not good_)
        print(f"  [{'ok ' if good_ else 'BUG'}] pass={str(ok):5s} want={str(should):5s}  {name}")
        if not ok and good_:
            print(f"        caught: {why[:96]}")
    print(f"\n{len(cases)-bad}/{len(cases)} self-test cases pass")
    _log_event("gate_pass" if not bad else "gate_trip", tool="gate_llm",
               check="SELF_TEST", n_fail=bad)
    return 1 if bad else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    print(__doc__)
    sys.exit(2)
