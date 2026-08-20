#!/usr/bin/env python3
"""VTCM sweep — does batch-4 lose on the Hexagon because of SILICON, or because of
how we COMPILED it?

The claim under test, which currently appears in several corpus documents:
    "a single 640x640 inference already saturates the HTP, so a batch just
     serialises four of them plus extra memory traffic"

That is an assertion with no mechanism. Reading the shipped context binaries shows
a different story: every graph was compiled at vtcmSize=4 MB, and the batch-4
graphs allocate far larger spill/fill buffers (v8n 0.13 -> 8.72 MB, v8L 7.73 ->
29.49 MB). That is a CAPACITY limit, not a saturation limit -- and capacity limits
are a build parameter until proven otherwise.

Every graph was built with vtcm_mb=8 requested, yet reports 4. So either the tool
capped it, or the device has 4. This sweep regenerates the context binaries across
a range of vtcm_mb, records what the compiler actually granted and how much it
spilled, and hands the surviving configs to the board for gating + timing.

Only the context-binary-generator step is re-run: the .dlc and quantised _int8.dlc
are unchanged, so the WEIGHTS are identical across every point in this sweep. That
matters -- it means any timing difference is attributable to the VTCM budget and
not to a requantisation.
"""
import json, os, subprocess, sys

SDK = "/home/kyle/qairt_2.47/qairt/2.47.0.260601"
X86 = f"{SDK}/bin/x86_64-linux-clang"
S = os.path.dirname(os.path.abspath(__file__))
OUT = f"{S}/qnn_split"
SWEEP = f"{S}/vtcm_sweep_out"
os.makedirs(SWEEP, exist_ok=True)

# ⚠️ The graph name is the one INSIDE the binary (== the dlc/binary_file stem),
# NOT the ONNX filename. build_split.py used the ONNX stem, which never matches, so
# every htp config it wrote was SILENTLY IGNORED and the default VTCM applied.
# Verified: binary reports graphName "v8n_sp_b4" while the config said
# "yolov8n_b4_split". A mismatched graph_names entry produces NO error.
MODELS = {"v8n_sp_b1": "v8n_sp_b1", "v8n_sp_b4": "v8n_sp_b4",
          "v8l_sp_b1": "v8l_sp_b1", "v8l_sp_b4": "v8l_sp_b4"}
VTCM = [int(x) for x in (sys.argv[1:] or ["2", "4", "8", "16"])]


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True)


def granted(binpath):
    """What the compiler ACTUALLY granted -- never trust the requested value."""
    j = binpath + ".info.json"
    r = sh(f"{X86}/qnn-context-binary-utility --context_binary {binpath} --json_file {j}")
    if not os.path.exists(j):
        return None, None, (r.stdout + r.stderr)[-160:]
    d = json.load(open(j))
    try:
        g = d["info"]["graphs"][0]["info"]["graphBlobInfo"]["info"]
        return g.get("vtcmSize"), g.get("spillFillBufferSize", 0), None
    except Exception as e:
        return None, None, str(e)


rows = []
for name, graph in MODELS.items():
    dlc = f"{OUT}/{name}_int8.dlc"
    if not os.path.exists(dlc):
        print(f"[{name}] SKIP - no quantised dlc"); continue
    for v in VTCM:
        tag = f"{name}_vtcm{v}"
        binp = f"{SWEEP}/{tag}.bin"
        if not os.path.exists(binp):
            json.dump({"devices": [{"dsp_arch": "v73", "pd_session": "unsigned"}],
                       "graphs": [{"graph_names": [graph], "vtcm_mb": v, "O": 3}]},
                      open(f"{SWEEP}/{tag}_htp.json", "w"))
            json.dump({"backend_extensions": {
                "shared_library_path": f"{SDK}/lib/x86_64-linux-clang/libQnnHtpNetRunExtensions.so",
                "config_file_path": f"{SWEEP}/{tag}_htp.json"}},
                open(f"{SWEEP}/{tag}_ext.json", "w"))
            r = sh(f"{X86}/qnn-context-binary-generator --dlc_path {dlc} "
                   f"--backend {SDK}/lib/x86_64-linux-clang/libQnnHtp.so "
                   f"--binary_file {tag} --output_dir {SWEEP} "
                   f"--config_file {SWEEP}/{tag}_ext.json")
        if not os.path.exists(binp):
            print(f"  {tag:24s} BUILD FAILED"); rows.append((name, v, None, None, "build failed"))
            continue
        vs, sf, err = granted(binp)
        note = ""
        if vs is not None and vs != v:
            note = f"REQUESTED {v}, GRANTED {vs}"
        print(f"  {tag:24s} granted_vtcm={vs} MB  spill={0 if sf is None else sf/1e6:8.2f} MB  {note}{err or ''}")
        rows.append((name, v, vs, sf, note))

json.dump([{"model": m, "requested_vtcm_mb": rq, "granted_vtcm_mb": g,
            "spill_fill_bytes": sf, "note": n} for m, rq, g, sf, n in rows],
          open(f"{SWEEP}/vtcm_sweep_build.json", "w"), indent=1)
print("VTCM_BUILD_SWEEP_DONE")
