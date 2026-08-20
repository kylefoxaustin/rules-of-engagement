#!/usr/bin/env python3
"""IN-RUN OUTPUT GATE for TensorRT timing runs.  [M1/M2 — and the reason it exists]

On 2026-08-20 a timing run of ~/remeasure/yolov8n.int8.engine produced 1.5983 ms with
three replicates, a 0.5% spread, a clean porch, a recorded artifact md5 and status OK.
Every one of those is a property of the RUN. None looks at the OUTPUT. The engine detects
NOTHING (mAP 0.0021 over 5000 val2017 images) and it is 8.3% FASTER than the working
build, so the defect presented as a result and was recorded as one.

This closes that path: a timing run now scores its own engine on a small COCO slice in the
SAME invocation and refuses to emit a number if the model is not detecting.

The floor is not arbitrary. Measured on this fleet:
    working engines      mAP50-95 0.36 - 0.52   (n=5000)
    uncalibrated int8    mAP50-95 0.0021        (n=5000, "max class score 0.1575")
A floor of 0.10 sits ~3.6x below the worst working config and ~48x above the broken one.
It is a LIVENESS gate, not an accuracy measurement -- it answers "is this model detecting
at all", and it must never be quoted as the accuracy of anything.

KNOWN LIMIT, stated so nobody relies on more than this gives: the underlying evaluator
fills a batched engine by REPEATING one image (`np.repeat(chw[None], ishape[0], axis=0)`)
and scores slot 0. That genuinely exercises the batched execution path -- which is why b1
and b4 return identical mAP, as they should -- but it does NOT verify slots 1..N-1. A
batched engine that corrupted every slot except the first would pass this gate. The timing
would still be valid (the compute happens either way), so this is a correctness gap in the
OUTPUT check, not in the latency number. Closing it needs distinct images per slot.

Usage: gate_inline_trt.py <engine> [n_images]   -> JSON on stdout, exit 0 pass / 7 fail
"""
import json
import os
import subprocess
import sys

FLOOR_MAP = float(os.environ.get("GATE_MAP_FLOOR", "0.10"))
ACC = os.path.expanduser("~/acc")


def main(engine, n=64):
    out = f"/tmp/gate_inline_{os.getpid()}.json"
    try:
        p = subprocess.run([sys.executable, os.path.join(ACC, "orin_eval.py"),
                            engine, str(n), out],
                           capture_output=True, text=True, timeout=900)
        mp = None
        for line in p.stdout.splitlines():
            if line.startswith("RESULT") and "mAP50-95=" in line:
                mp = float(line.split("mAP50-95=")[1].split()[0])
        if mp is None:
            return emit(None, "gate could not score the engine -- no RESULT line; a timing "
                             "number with an unscored output is not a measurement", 7)
        if mp < FLOOR_MAP:
            return emit(mp, f"mAP50-95 {mp:.4f} < liveness floor {FLOOR_MAP} on n={n}: this "
                            f"engine is not detecting. A model that detects nothing is FASTER, "
                            f"so this timing must not be published.", 7)
        return emit(mp, "", 0)
    finally:
        if os.path.exists(out):
            os.remove(out)          # the gate cleans up after itself (M41 teardown)


def emit(mp, why, rc):
    print(json.dumps({
        "gate": "inline_trt_liveness",
        "status": "PASS" if rc == 0 else "FAIL",
        "mAP50_95": mp,
        "floor": FLOOR_MAP,
        "why": why,
        "_scope": "LIVENESS ONLY -- 'is this model detecting at all', scored on a small "
                  "slice in the same invocation as the timing. NOT an accuracy figure and "
                  "must never be quoted as one.",
    }))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 64))
