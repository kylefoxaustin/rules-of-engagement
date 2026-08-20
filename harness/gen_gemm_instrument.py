"""Pure GEMM instruments for a precision sweep.

WHY A GEMM: YOLOv8 mixes convolutions, activations, resizes and NMS-adjacent ops.
A precision effect on the tensor cores gets diluted by everything else in the graph.
A single large MatMul is close to a direct read of tensor-core throughput, which is
the quantity the "does this part have native FP8" question is actually about.
"""
import numpy as np, onnx
from onnx import helper, TensorProto as TP, numpy_helper

N = 4096
rng = np.random.default_rng(0)          # fixed seed: the weights are part of the measurand
W = rng.standard_normal((N, N), dtype=np.float32) * 0.02

def save(g, path):
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 21)])
    m.ir_version = 10
    onnx.checker.check_model(m)
    onnx.save(m, path)
    print("wrote", path)

# ---- 1. plain float GEMM: the fp16 / bf16 / tf32 instrument --------------------
g = helper.make_graph(
    [helper.make_node("MatMul", ["A", "W"], ["Y"])],
    "gemm_fp",
    [helper.make_tensor_value_info("A", TP.FLOAT, [N, N])],
    [helper.make_tensor_value_info("Y", TP.FLOAT, [N, N])],
    [numpy_helper.from_array(W, "W")])
save(g, "gemm4096_fp.onnx")

# ---- 2. FP8 E4M3 explicitly quantised GEMM ------------------------------------
# TensorRT's FP8 path is EXPLICIT: --fp8 on a plain float network does not
# necessarily produce an fp8 kernel. Q/DQ pairs in FLOAT8E4M3FN are what actually
# request it, so this is the instrument that can distinguish "supports the flag"
# from "runs the math".
s_a = numpy_helper.from_array(np.array(0.05, np.float32), "s_a")
z_a = numpy_helper.from_array(np.array(0.0, np.float32).astype(np.float32), "z_a")
s_w = numpy_helper.from_array(np.array(0.02, np.float32), "s_w")
nodes = [
    helper.make_node("QuantizeLinear",   ["A", "s_a", "z_a8"], ["Aq"]),
    helper.make_node("DequantizeLinear", ["Aq", "s_a", "z_a8"], ["Ad"]),
    helper.make_node("QuantizeLinear",   ["W", "s_w", "z_w8"], ["Wq"]),
    helper.make_node("DequantizeLinear", ["Wq", "s_w", "z_w8"], ["Wd"]),
    helper.make_node("MatMul", ["Ad", "Wd"], ["Y"]),
]
z8_a = helper.make_tensor("z_a8", TP.FLOAT8E4M3FN, [], [0.0])
z8_w = helper.make_tensor("z_w8", TP.FLOAT8E4M3FN, [], [0.0])
g8 = helper.make_graph(
    nodes, "gemm_fp8",
    [helper.make_tensor_value_info("A", TP.FLOAT, [N, N])],
    [helper.make_tensor_value_info("Y", TP.FLOAT, [N, N])],
    [numpy_helper.from_array(W, "W"), s_a, s_w, z8_a, z8_w])
save(g8, "gemm4096_fp8.onnx")
