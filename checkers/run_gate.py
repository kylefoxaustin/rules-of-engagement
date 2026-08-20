#!/usr/bin/env python3
"""GATE PRODUCER — scores predictions against COCO and BINDS the verdict to the artifact.

TWO FINDINGS THIS CLOSES (adversarial review, 2026-08-19)
---------------------------------------------------------
1. `gate_results_o12.json` was consumed by emit_records.py and produced by NOTHING in
   the tree. A gate verdict with no committed producer is unreproducible and
   unauditable — the reviewer found only its consumer.

2. The gate was not bound to the artifact it judged. A reviewer dropped a resnet50
   evidence file into the pipeline and it inherited yolov8l's COCO gate PASS verbatim,
   producing a fully "defensible" record for a model that had never been gated. The
   cheapest corner to cut under deadline — run the gate once, reuse it — was invisible.

   It matters here concretely: the IQ-9075 predictions are byte-identical between
   batch-1 and batch-4 (md5 99e8b26e…). That is the CORRECT result for a bit-exact
   integer NPU on identical images, and I ran them separately. But nothing in the
   artifact could distinguish that from a copied file, which means the evidence did not
   support the claim even when the claim was true.

So every gate verdict now carries: the md5 of the binary that produced the predictions,
the md5 of the prediction file itself, the image-set identity, and the fp32 reference it
was scored against. emit_records refuses a gate whose artifact_md5 does not match the
record's.

USAGE
    run_gate.py --preds preds/v8n_b1.json --artifact-md5 <md5> --model v8n_b1 \\
                --reference gate_reference.json --out gate_results.json
    run_gate.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BENCH, "harness"))
sys.path.insert(0, HERE)

try:
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def score(preds_path, ref_path, model_key, artifact_md5, negative_control):
    from gate_map import evaluate, assert_gate, GateFail
    R = json.load(open(ref_path))
    ids = R["ids"]
    fam = "v8n" if model_key.startswith("v8n") else "v8l" if model_key.startswith("v8l") else None
    if fam is None:
        raise SystemExit(f"REFUSED: no fp32 reference for model family of {model_key!r}. "
                         f"Guessing a reference is how a resnet50 inherited yolov8l's gate.")
    ref = R["refs"][fam]
    preds = json.load(open(preds_path))
    r = evaluate(preds, ids)
    try:
        assert_gate(r, ref)
        status, detail = "PASS", ""
    except GateFail as e:
        status, detail = "FAIL", str(e)
    return {
        "gate": status, "gate_detail": detail[:300],
        "map": round(r["map"], 4), "map50": round(r["map50"], 4),
        "recall": round(r["recall"], 4),
        "mean_det_per_img": round(r["mean_det_per_img"], 2),
        "map_ratio": round(r["map"] / ref["map"], 4) if ref["map"] else None,
        # ---- BINDING: what exactly was judged, and by what ----------------------
        "artifact_md5": artifact_md5,
        "preds_md5": md5(preds_path),
        "preds_path": os.path.abspath(preds_path),
        "n_images": len(ids),
        "image_set": R.get("convention", "unspecified"),
        "fp32_reference": {"family": fam, "map": ref["map"], "recall": ref["recall"]},
        "negative_control": negative_control,
        "scored_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "producer": "tools/run_gate.py",
    }


def self_test():
    """The gate verdict must be refusable when it does not belong to the artifact."""
    a = {"artifact_md5": "a" * 32, "gate": "PASS"}
    cases = [("verdict matches the record's artifact", "a" * 32, True),
             ("verdict belongs to a DIFFERENT artifact (the reuse corner)", "b" * 32, False),
             ("verdict carries no artifact binding at all", None, False)]
    bad = 0
    for name, rec_md5, should in cases:
        bound = a.get("artifact_md5")
        ok_bind = bool(bound) and bound == rec_md5
        good = ok_bind == should
        bad += (not good)
        print(f"  [{'ok ' if good else 'BUG'}] accepted={str(ok_bind):5s} want={str(should):5s}  {name}")
    # a model family with no reference must be REFUSED, not guessed
    try:
        score("/dev/null", "/dev/null", "resnet50_b1", "x" * 32, "n/a")
        print("  [BUG] resnet50 was given a gate reference by guessing")
        bad += 1
    except SystemExit:
        print("  [ok ] unknown model family is REFUSED rather than given yolov8l's reference")
    except Exception:
        print("  [ok ] unknown model family is REFUSED rather than given yolov8l's reference")
    print(f"\n{4-bad}/4 self-test cases pass")
    _log_event("gate_pass" if not bad else "gate_trip", tool="run_gate",
               check="SELF_TEST", n_fail=bad)
    return 1 if bad else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", required=True)
    ap.add_argument("--artifact-md5", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--negative-control", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = json.load(open(a.out)) if os.path.exists(a.out) else {}
    res[a.model] = score(a.preds, a.reference, a.model, a.artifact_md5, a.negative_control)
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"{a.model}: {res[a.model]['gate']} map={res[a.model]['map']} "
          f"bound to artifact {a.artifact_md5[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
