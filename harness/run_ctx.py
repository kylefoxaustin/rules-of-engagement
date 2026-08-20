#!/usr/bin/env python3
"""Run the context-window prompts against a llama-server and grade the answer.

The timing and the correctness check come out of the SAME request, so no number
here can survive without evidence that the model actually read its context.

Reports, per (context length, needle depth):
  prompt_n     tokens the runtime says it processed  (proves the length is real)
  ttft_ms      prompt eval time = time to first token
  prefill_tps  prompt tokens / prompt eval time
  decode_tps   generated tokens / generation time
  answer       what the model actually said
  PASS/FAIL    did it recover the planted value
"""
import json, os, sys, glob, urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
PDIR = sys.argv[2] if len(sys.argv) > 2 else "/home/kyle/ctx/prompts"
OUT  = sys.argv[3] if len(sys.argv) > 3 else "/home/kyle/ctx/results.json"
REPS = int(sys.argv[4]) if len(sys.argv) > 4 else 3

TPL = ("<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n{p}"
       "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n")


def post(path, obj):
    r = urllib.request.Request(HOST + path, data=json.dumps(obj).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=600))


results = []
for f in sorted(glob.glob(os.path.join(PDIR, "ctx_*.json"))):
    spec = json.load(open(f))
    body = {"prompt": TPL.format(p=spec["prompt"]), "n_predict": 24,
            "temperature": 0, "cache_prompt": False}
    reps = []
    for _ in range(REPS):
        d = post("/completion", body)
        t = d["timings"]
        reps.append({"ttft_ms": t["prompt_ms"],
                     "prefill_tps": t["prompt_per_second"],
                     "decode_tps": t["predicted_per_second"],
                     "prompt_n": t["prompt_n"],
                     "text": d["content"].strip()})
    # Median TTFT; correctness must hold on EVERY repetition, not just the best.
    tt = sorted(r["ttft_ms"] for r in reps)
    med = tt[len(tt) // 2]
    exp = spec["expected_answer"]
    ok = all(exp in r["text"] for r in reps)
    rec = {"target_tokens": spec["target_tokens"],
           "actual_tokens": spec["actual_tokens"],
           "runtime_prompt_n": reps[0]["prompt_n"],
           "depth": spec["depth"], "expected": exp,
           "answer": reps[0]["text"][:80],
           "needle_found": ok,
           "ttft_ms_median": round(med, 2),
           "ttft_ms_all": [round(r["ttft_ms"], 2) for r in reps],
           "prefill_tps": round(sum(r["prefill_tps"] for r in reps) / len(reps), 2),
           "decode_tps": round(sum(r["decode_tps"] for r in reps) / len(reps), 2)}
    results.append(rec)
    print(f"  {rec['target_tokens']:5d} tok  d{int(spec['depth']*100):02d}  "
          f"n={rec['runtime_prompt_n']:5d}  TTFT {rec['ttft_ms_median']:8.2f} ms  "
          f"prefill {rec['prefill_tps']:8.1f} t/s  decode {rec['decode_tps']:6.2f} t/s  "
          f"{'PASS' if ok else 'FAIL'}  answer={rec['answer'][:32]!r}", flush=True)

json.dump(results, open(OUT, "w"), indent=1)
npass = sum(1 for r in results if r["needle_found"])
print(f"CTX_RUN_DONE gated {npass}/{len(results)} PASS")
