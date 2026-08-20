#!/usr/bin/env python3
"""Detection gate v2 — built to MEASUREMENT_RULES_OF_ENGAGEMENT M1/M2/M3.

What v1 got wrong, and this fixes:

  M3a  v1 checked ONLY class scores. A model whose BOX branch collapsed -- the exact
       mirror of the int8 Concat bug we fixed -- passed with flying colours. v2
       asserts the boxes are non-degenerate and in-frame.
  M3b  v1 fed the SAME image to all N batch slots via np.repeat, so it could not
       distinguish a correct batch engine from one that computes slot 0 and
       replicates, or one whose slots alias each other. v2 feeds N DISTINCT images
       with different expected content and requires the slots to DIFFER.
  M2   v1 had no negative control: 24/24 PASS with no evidence the gate could ever
       fail. v2 has --self-test, which runs the assertions against deliberately
       broken tensors and FAILS the run if they pass.

Exit code 0 only if every assertion holds. The number does not exist without it.
"""
import os, sys, json, collections
import numpy as np
import tensorrt as trt
try:
    from cuda import cudart
except ImportError:
    from cuda.bindings import runtime as cudart
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yolo_eval import preprocess

LOG = trt.Logger(trt.Logger.ERROR)
SCORE_THR = 0.25
NAMES = {0: "person", 1: "bicycle", 2: "car", 5: "bus", 56: "chair", 60: "diningtable",
         62: "tv", 72: "tvmonitor", 73: "laptop", 75: "vase"}


def ck(e):
    if isinstance(e, tuple):
        c, *r = e
        if int(c) != 0:
            raise RuntimeError(f"CUDA error {c}")
        return r[0] if len(r) == 1 else r
    return e


# ── the assertions, isolated so the negative control can attack them directly ──
def assert_scores(raw):
    """raw: [84, A] for one image. Returns (ok, detail)."""
    m = raw[4:].max(0)
    n = int((m > SCORE_THR).sum())
    return (n > 0, {"n_det": n, "max_score": float(m.max())})


def assert_boxes(raw, imgsz=640):
    """A collapsed/quantisation-destroyed box branch is invisible to a score check.
    Boxes are xywh in pixels. Demand: finite, positive extent, plausibly in-frame,
    and NOT a constant-output branch.

    NOTE (corrected 2026-08-17): the constant-branch test MUST be computed over the
    FULL anchor grid, not over the surviving detections. An image containing one
    dominant object legitimately yields ~zero spread among its kept boxes -- yolov8l
    on COCO 000000000285 (single close-up animal) gave kept-x_std 0.53 and was
    FALSELY failed by the first version of this check, while its all-anchor x_std was
    184.6, identical to every healthy slot. Tuning the threshold would have hidden a
    bad criterion; the criterion itself was wrong."""
    b = raw[:4]
    m = raw[4:].max(0)
    keep = m > SCORE_THR
    if keep.sum() == 0:
        return False, {"reason": "no detections to check boxes on"}
    bb = b[:, keep]
    w, h = bb[2], bb[3]
    finite = bool(np.isfinite(b).all())
    pos_extent = float((w > 1).mean()), float((h > 1).mean())
    in_frame = float(((bb[0] > -imgsz * 0.5) & (bb[0] < imgsz * 1.5)).mean())
    grid_spread = float(np.std(b[0]))      # over ALL anchors: constant branch => ~0
    ok = (finite and pos_extent[0] > 0.9 and pos_extent[1] > 0.9
          and in_frame > 0.9 and grid_spread > 10.0)
    return ok, {"finite": finite, "frac_w_gt1": round(pos_extent[0], 3),
                "frac_h_gt1": round(pos_extent[1], 3),
                "frac_x_in_frame": round(in_frame, 3),
                "grid_x_std_px": round(grid_spread, 2),
                "kept_x_std_px": round(float(np.std(bb[0])), 2)}


def run(engine_path, images):
    rt = trt.Runtime(LOG)
    eng = rt.deserialize_cuda_engine(open(engine_path, "rb").read())
    ctx = eng.create_execution_context()
    names = [eng.get_tensor_name(i) for i in range(eng.num_io_tensors)]
    inp = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.INPUT][0]
    out = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT][0]
    ish, osh = tuple(ctx.get_tensor_shape(inp)), tuple(ctx.get_tensor_shape(out))
    # M4: read the binding dtype back rather than assuming float32
    idt, odt = eng.get_tensor_dtype(inp), eng.get_tensor_dtype(out)
    assert idt == trt.float32 and odt == trt.float32, f"unexpected binding dtype {idt}/{odt}"

    N = ish[0]
    picked = images[:N] if len(images) >= N else (images * N)[:N]
    batch = np.ascontiguousarray(np.stack([preprocess(p)[0] for p in picked]))

    d_in, d_out = ck(cudart.cudaMalloc(batch.nbytes)), ck(cudart.cudaMalloc(int(np.prod(osh) * 4)))
    ctx.set_tensor_address(inp, int(d_in)); ctx.set_tensor_address(out, int(d_out))
    st = ck(cudart.cudaStreamCreate())
    host = np.empty(osh, dtype=np.float32)
    ck(cudart.cudaMemcpyAsync(d_in, batch.ctypes.data, batch.nbytes,
                              cudart.cudaMemcpyKind.cudaMemcpyHostToDevice, st))
    ctx.execute_async_v3(st)
    ck(cudart.cudaMemcpyAsync(host.ctypes.data, d_out, int(np.prod(osh) * 4),
                              cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost, st))
    ck(cudart.cudaStreamSynchronize(st))
    ck(cudart.cudaFree(d_in)); ck(cudart.cudaFree(d_out))
    return host, [os.path.basename(p) for p in picked]


def gate(engine_path, images):
    host, used = run(engine_path, images)
    N = host.shape[0]
    rec = {"engine": os.path.basename(engine_path), "batch": N, "images": used, "slots": []}
    ok_all = True
    sigs = []
    for i in range(N):
        s_ok, s_d = assert_scores(host[i])
        b_ok, b_d = assert_boxes(host[i])
        cnt = collections.Counter(int(c) for c in host[i][4:].argmax(0)[host[i][4:].max(0) > SCORE_THR])
        top = [(NAMES.get(k, f"c{k}"), v) for k, v in cnt.most_common(3)]
        sigs.append(tuple(sorted(cnt.items())))
        ok_all &= (s_ok and b_ok)
        rec["slots"].append({"slot": i, "image": used[i], "scores_ok": s_ok, "boxes_ok": b_ok,
                             **s_d, "boxes": b_d, "top_classes": top})
    # M3b: distinct inputs must give distinct outputs, else the batch dim is a lie
    distinct = len(set(sigs)) if N > 1 else None
    if N > 1:
        rec["distinct_slot_outputs"] = distinct
        if distinct < 2:
            ok_all = False
            rec["batch_error"] = ("all slots produced identical detections from DIFFERENT images "
                                  "-- batch dimension is not being computed independently")
    rec["status"] = "PASS" if ok_all else "FAIL"
    return rec


def self_test():
    """M2 — prove the assertions can FAIL. Synthesise the two failure modes we have
    actually shipped, and require the gate to reject both."""
    A = 8400
    results = {}
    # 1. the int8 Concat bug: every class score crushed to zero, boxes fine
    bad = np.zeros((84, A), np.float32)
    bad[:4] = np.random.RandomState(0).uniform(10, 600, (4, A))
    ok, d = assert_scores(bad)
    results["dead_scores_rejected"] = (not ok, d)
    # 2. the mirror: scores fine, box branch collapsed to a constant
    bad2 = np.zeros((84, A), np.float32)
    bad2[4:] = np.random.RandomState(1).uniform(0, 1, (80, A))
    bad2[:4] = 5.0                                # constant box branch
    ok2, d2 = assert_boxes(bad2)
    results["dead_boxes_rejected"] = (not ok2, d2)
    # 2b. the false-positive we actually hit: ONE dominant object, so the kept boxes
    #     cluster tightly while the anchor grid is healthy. Must be ACCEPTED.
    single = np.zeros((84, A), np.float32)
    rs1 = np.random.RandomState(3)
    single[:4] = rs1.uniform(20, 600, (4, A))
    single[0] = rs1.normal(300, 184, A)          # healthy grid spread
    single[7, :10] = 0.9                          # 10 detections...
    single[0, :10] = 301.0                        # ...all on the same object
    single[2, :10] = 120.0; single[3, :10] = 200.0
    ok2b = assert_boxes(single)[0]
    results["single_object_accepted"] = (ok2b, {})

    # 3. a healthy tensor must still PASS, or the gate is merely paranoid
    good = np.zeros((84, A), np.float32)
    rs = np.random.RandomState(2)
    good[:4] = rs.uniform(20, 600, (4, A))
    good[4:] = rs.uniform(0, 0.2, (80, A)); good[7, ::97] = 0.9
    ok3 = assert_scores(good)[0] and assert_boxes(good)[0]
    results["healthy_accepted"] = (ok3, {})
    print("  NEGATIVE CONTROL (M2):")
    allok = True
    for k, (passed, d) in results.items():
        print(f"    {k:26s} {'OK' if passed else 'BROKEN'}   {d}")
        allok &= passed
    print(f"  SELF_TEST={'PASS' if allok else 'FAIL'}  "
          f"(the gate {'can' if allok else 'CANNOT'} distinguish broken from healthy)")
    return allok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not self_test():
        print("GATE_RESULT=SELF_TEST_FAILED -- refusing to gate anything")
        sys.exit(2)
    V = "/home/kyle/acc/val2017"
    imgs = [os.path.join(V, f) for f in sorted(os.listdir(V))[:8]]
    print(f"  gate images: {[os.path.basename(i) for i in imgs[:4]]}")
    recs, allok = [], True
    for e in args:
        r = gate(os.path.join("/home/kyle/acc", e), imgs)
        recs.append(r); allok &= (r["status"] == "PASS")
        for s in r["slots"]:
            print(f"  {r['engine']:28s} slot{s['slot']} {s['image']:16s} "
                  f"max={s['max_score']:.4f} n={s['n_det']:3d} "
                  f"box_ok={s['boxes_ok']} xstd={s['boxes'].get('grid_x_std_px')} "
                  f"{[t[0] for t in s['top_classes']]}")
        if r["batch"] > 1:
            print(f"       distinct slot outputs: {r['distinct_slot_outputs']}/{r['batch']}")
        print(f"       -> {r['status']}")
    json.dump(recs, open("/home/kyle/acc/gate_v2_result.json", "w"), indent=1)
    print("GATE_RESULT=" + ("ALL_PASS" if allok else "SOME_FAILED"))
    sys.exit(0 if allok else 1)
