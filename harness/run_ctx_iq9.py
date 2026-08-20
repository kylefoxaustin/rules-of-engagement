#!/usr/bin/env python3
"""Same context-window test, but against the IQ-9075's Genie/QNN NPU runtime.

Identical prompt files as the llama.cpp boards, so the comparison is real. Genie
reports its own TTFT and token counts; the needle check reads the generated text
from the SAME invocation that produced the timing.

NOTE: the Genie bundle is compiled with a FIXED context size (2048 here). A
prompt that leaves no room to generate cannot be run -- that is a real property
of the deployed bundle, not a harness failure, and it is reported as such.
"""
import json, os, re, subprocess, sys, glob

# genie-t2t-run needs these or it dies with "Failed to create device: 1008",
# which looks exactly like a wedged NPU. It is not -- it is a missing skel path.
ENV = dict(os.environ,
           LD_LIBRARY_PATH="/root/qnn247/lib:" + os.environ.get("LD_LIBRARY_PATH", ""),
           ADSP_LIBRARY_PATH="/root/qnn247/skel")

BUNDLE = "/root/llama31_bundle"
GENIE = "/root/qnn247/bin/genie-t2t-run"
PDIR = sys.argv[1] if len(sys.argv) > 1 else "/root/ctx/prompts"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/root/ctx/iq9_ctx.json"
REPS = int(sys.argv[3]) if len(sys.argv) > 3 else 3
NPRED = 24

TPL = ("<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{p}"
       "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")

CFG = f"{BUNDLE}/genie_config_greedy.json"   # temp=0, top-k=1 -- matches the temp-0
                                             # decoding used on Thor and Orin. The stock
                                             # bundle samples at temp 0.8, which would make
                                             # this board the only non-deterministic one.
ctx_size = json.load(open(CFG))["dialog"]["context"]["size"]
# Genie reserves headroom below the nominal context: MEASURED, a 1930-token prompt fails
# with "Context Size was exceeded" while 1868 runs. Budget accordingly.
USABLE = 1868
print(f"genie bundle context size = {ctx_size}")

results = []
for f in sorted(glob.glob(os.path.join(PDIR, "ctx_*.json"))):
    spec = json.load(open(f))
    tgt = spec["target_tokens"]
    if tgt + NPRED > USABLE:
        results.append({"target_tokens": tgt, "depth": spec["depth"],
                        "status": "CANNOT_RUN",
                        "reason": f"prompt {tgt} tok + {NPRED} generated exceeds this bundle's "
                                  f"MEASURED usable budget of {USABLE} (nominal context {ctx_size}; "
                                  f"Genie reserves the difference). Raising it requires recompiling "
                                  f"the bundle, not a runtime flag."})
        print(f"  {tgt:5d} tok  d{int(spec['depth']*100):02d}  CANNOT_RUN "
              f"(needs {tgt+NPRED} > ctx {ctx_size})", flush=True)
        continue

    pf = "/dev/shm/ctx_prompt.txt"
    open(pf, "w").write(TPL.format(p=spec["prompt"]))
    reps = []
    for _ in range(REPS):
        # genie-t2t-run REFUSES to overwrite an existing --profile file, so a
        # stale one from the previous repetition silently kills the run.
        if os.path.exists("/dev/shm/ctx_prof.json"):
            os.remove("/dev/shm/ctx_prof.json")
        r = subprocess.run([GENIE, "-c", CFG,
                            "--prompt_file", pf, "--profile", "/dev/shm/ctx_prof.json"],
                           capture_output=True, text=True, cwd=BUNDLE,
                           timeout=1800, env=ENV)
        out = r.stdout + r.stderr
        err = re.search(r"\[ERROR\]\s*\"([^\"]+)\"", out)
        m = re.search(r"\[BEGIN\]:(.*?)\[END\]", out, re.S)
        text = m.group(1).strip() if m else ""
        if err or not m:
            # A runtime failure is NOT a wrong answer. Never let one be recorded
            # as a failed needle -- that would read as "the model got it wrong".
            reps.append({"text": "", "prof": {},
                         "runtime_error": (err.group(1) if err else
                                           "no [BEGIN]/[END]; raw tail: " + out.strip()[-200:])})
            continue
        prof = {}
        try:
            prof = json.load(open("/dev/shm/ctx_prof.json"))
        except Exception:
            pass
        reps.append({"text": text, "prof": prof})

    errs = [x.get("runtime_error") for x in reps if x.get("runtime_error")]
    if errs:
        results.append({"target_tokens": tgt, "depth": spec["depth"],
                        "status": "RUNTIME_ERROR", "error": errs[0],
                        "note": "NOT a model-accuracy failure -- the runtime never produced output."})
        print(f"  {tgt:5d} tok  d{int(spec['depth']*100):02d}  RUNTIME_ERROR: {errs[0]}", flush=True)
        continue
    exp = spec["expected_answer"]
    ok = all(exp in x["text"] for x in reps)
    rec = {"target_tokens": tgt, "actual_tokens": spec["actual_tokens"],
           "depth": spec["depth"], "expected": exp,
           "answer": reps[0]["text"][:80], "needle_found": ok,
           "raw_profiles": [x["prof"] for x in reps], "status": "RAN"}
    results.append(rec)
    print(f"  {tgt:5d} tok  d{int(spec['depth']*100):02d}  "
          f"{'PASS' if ok else 'FAIL'}  answer={rec['answer'][:40]!r}", flush=True)

json.dump(results, open(OUT, "w"), indent=1)
print("IQ9_CTX_RUN_DONE")
