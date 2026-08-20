#!/usr/bin/env python3
"""ARTIFACT FINGERPRINT — mechanises M30 (measurand identity).

WHY THIS EXISTS, PRECISELY
--------------------------
M30 was written on 2026-08-18 and says: record "input shape, output shape, op count,
opset, and whether NMS is inside the graph". Two days later a rebuild of yolov8L ran
**21% slower** than the published build. The two binaries were identical by every
attribute anyone had recorded — same model, same 640x640, same split head, same w8a8,
same vtcm_mb=8, same O=3, same I/O shapes and dtypes. The distinguishing variable was
the **ONNX export opset** (17 vs 12), which changed the on-chip working set 9.5x
(31,850,496 vs 3,342,336 bytes of VTCM spill) at **bit-identical accuracy**.

So the rule was correct, on the page, and useless — because nothing computed it. That
is the whole argument for this file: an unmechanised rule is documentation, and
documentation does not fire at 2am.

WHAT IT CAPTURES
    onnx  : opset, producer + version, input/output names+shapes+dtypes, op histogram,
            whether NMS/Concat-head is inside the graph
    dlc   : graph name (M34: read back, never derived), I/O tensors
    bin   : graph name, spillFillBufferSize, vtcmSize, optimizationLevel, htpDlbc
            -- read from the DEPLOYED artifact, which outranks the build log (M38)

USAGE
    artifact_fingerprint.py <file> [...]        print fingerprints
    artifact_fingerprint.py --diff A B          show ONLY the fields that differ
    artifact_fingerprint.py --self-test         negative control
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import subprocess
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass

SDK = os.environ.get("QAIRT_SDK", "/home/kyle/qairt_2.47/qairt/2.47.0.260601")
X86 = f"{SDK}/bin/x86_64-linux-clang"


def md5(path, cap=None):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_onnx(path):
    import onnx
    m = onnx.load(path)
    g = m.graph
    ops = collections.Counter(n.op_type for n in g.node)
    dims = lambda v: [d.dim_value or d.dim_param
                      for d in v.type.tensor_type.shape.dim]
    return {
        "kind": "onnx", "path": path, "md5": md5(path),
        # THE field that cost 21% and was recorded nowhere:
        "opset": [{"domain": o.domain or "ai.onnx", "version": o.version}
                  for o in m.opset_import],
        "producer": f"{m.producer_name} {m.producer_version}".strip(),
        "ir_version": m.ir_version,
        "inputs": {i.name: dims(i) for i in g.input},
        "outputs": {o.name: dims(o) for o in g.output},
        "n_nodes": len(g.node),
        "op_histogram": dict(sorted(ops.items(), key=lambda kv: -kv[1])),
        "nms_in_graph": any(n.op_type in ("NonMaxSuppression",) for n in g.node),
        "concat_head": any(n.op_type == "Concat" and any(o in n.output for o in
                           [x.name for x in g.output]) for n in g.node),
    }


def _run(cmd, timeout=300):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = f"{SDK}/lib/x86_64-linux-clang:" + env.get("LD_LIBRARY_PATH", "")
    env["PYTHONPATH"] = f"{SDK}/lib/python:" + env.get("PYTHONPATH", "")
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, env=env)
    except Exception as e:
        return type("R", (), {"stdout": "", "stderr": str(e), "returncode": 1})()


def fingerprint_dlc(path):
    r = _run(f"{X86}/qairt-dlc-info -i {path}")
    gname = ""
    for line in r.stdout.splitlines():
        if line.startswith("Info of graph:"):
            gname = line.split(":", 1)[1].strip()
            break
    return {"kind": "dlc", "path": path, "md5": md5(path),
            "graph_name_READ_BACK": gname or None}


def fingerprint_bin(path):
    """Read the DEPLOYED artifact. M38: this outranks the build log."""
    tmp = f"/tmp/_fp_{os.getpid()}.json"
    _run(f"{X86}/qnn-context-binary-utility --context_binary {path} --json_file {tmp}")
    out = {"kind": "context_binary", "path": path, "md5": md5(path)}
    if os.path.exists(tmp):
        try:
            d = json.load(open(tmp))
            g = d["info"]["graphs"][0]["info"]
            b = g["graphBlobInfo"]["info"]
            out.update({
                "graph_name": g.get("graphName"),
                "spillFillBufferSize": b.get("spillFillBufferSize"),
                "vtcmSize": b.get("vtcmSize"),
                "optimizationLevel": b.get("optimizationLevel"),
                "htpDlbc": b.get("htpDlbc"),
                "numHvxThreads": b.get("numHvxThreads"),
                "inputs": {i["info"]["name"]: [i["info"].get("dimensions"),
                                               i["info"].get("dataType")]
                           for i in g.get("graphInputs", [])},
                "outputs": {o["info"]["name"]: [o["info"].get("dimensions"),
                                                o["info"].get("dataType")]
                            for o in g.get("graphOutputs", [])},
            })
        except Exception as e:
            out["error"] = str(e)[:160]
        finally:
            os.remove(tmp)
    return out


def fingerprint(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".onnx":
        return fingerprint_onnx(path)
    if ext == ".dlc":
        return fingerprint_dlc(path)
    if ext in (".bin", ".serialized"):
        return fingerprint_bin(path)
    return {"kind": "unknown", "path": path, "md5": md5(path)}


def diff(a, b):
    """Only the fields that DIFFER. The point is to make the invisible variable visible."""
    keys = sorted(set(a) | set(b))
    out = {}
    for k in keys:
        if k in ("path", "md5"):
            continue
        if a.get(k) != b.get(k):
            out[k] = {"A": a.get(k), "B": b.get(k)}
    return out


def self_test():
    """The regression case: two graphs identical everywhere the corpus was looking,
    differing only in opset. The fingerprint MUST surface it."""
    A = {"kind": "onnx", "opset": [{"domain": "ai.onnx", "version": 17}],
         "inputs": {"images": [1, 3, 640, 640]}, "n_nodes": 300,
         "outputs": {"boxes": [1, 4, 8400], "scores": [1, 80, 8400]}}
    B = dict(A); B["opset"] = [{"domain": "ai.onnx", "version": 12}]
    d = diff(A, B)
    ok1 = "opset" in d
    C = dict(A)
    ok2 = diff(A, C) == {}
    print(f"  [{'ok ' if ok1 else 'BUG'}] opset-only difference is surfaced: {list(d)}")
    print(f"  [{'ok ' if ok2 else 'BUG'}] identical fingerprints diff to empty")
    bad = (not ok1) + (not ok2)
    _log_event("gate_pass" if not bad else "gate_trip", tool="artifact_fingerprint",
               check="SELF_TEST", n_fail=bad)
    print(f"\n{2-bad}/2 self-test cases pass")
    return 1 if bad else 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--self-test" in sys.argv:
        return self_test()
    if not args:
        print(__doc__)
        return 2
    if "--diff" in sys.argv and len(args) == 2:
        a, b = fingerprint(args[0]), fingerprint(args[1])
        d = diff(a, b)
        print(f"A = {args[0]}\nB = {args[1]}\n")
        if not d:
            print("IDENTICAL on every recorded field.")
            print("If these two artifacts perform differently, the distinguishing")
            print("variable is one this fingerprint does not yet capture — that is a")
            print("finding, and this file needs a new field (M30).")
        else:
            print(json.dumps(d, indent=1)[:4000])
        return 0
    for p in args:
        print(json.dumps(fingerprint(p), indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
