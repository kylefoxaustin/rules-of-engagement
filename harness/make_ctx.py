#!/usr/bin/env python3
"""Build token-EXACT context-window prompts with a gradeable answer.

Why this exists: you cannot measure "TTFT at N tokens" with random filler, and you
cannot trust ANY latency from an LLM without evidence it read its input -- a broken
model is faster, so the error always flatters the accelerator.

Each prompt is:
    [instruction] + [real prose haystack, ONE invented fact planted at a known
                     TOKEN depth] + [question about that fact]

The haystack is contiguous public-domain prose, so prefill does representative work
on real language. The planted fact is invented and randomised, so it cannot be
answered from parametric knowledge or from having seen a previous trial.

=============================================================================
DEFECTS FIXED IN v2 (found by adversarial audit, 2026-08-16/17) — see
MEASUREMENT_RULES_OF_ENGAGEMENT.md failure classes B3 and the M6/M2 rules.
=============================================================================

B3  DEPTH WAS NOT WHAT IT CLAIMED.  v1 placed the needle at a *paragraph* index,
    round(len(body) * depth).  At 1024 tokens the body is ~5 paragraphs, so
    "depth 0.90" actually landed at 60% and "0.10" at 20%.  The end of the
    context -- the region a long-context test most needs to probe -- was never
    tested at the lengths that mattered.  v2 places by CUMULATIVE TOKEN COUNT and
    RECORDS the realised token depth, so the claim is checkable (M4).

PERF  THE GENERATOR TOOK 3.5 HOURS AND DID NOT CONVERGE.  v1 called llama-tokenize
    inside a 400-iteration refinement loop; each call reloads a 4.6 GB model.  v2
    memoises, counts each paragraph once, and converges with a bounded binary
    search over the tail word count -- ~12 tokenizer calls instead of ~400.  It
    also reports the residual instead of silently spinning.

S3  THE ANSWER WAS GUESSABLE ACROSS TRIALS.  v1 used three fixed values keyed to
    depth (47.3 / 88.6 / 23.9), reused at every length and on every board -- so
    depth and answer were perfectly confounded, and a value seen once could be
    reused.  v2 draws a fresh random value per (length, depth) from a seeded RNG:
    reproducible, but never repeated across trials.
"""
import json, os, re, subprocess, sys

TOKENIZE = os.environ.get("LLAMA_TOKENIZE",
                          os.path.expanduser("~/llama.cpp/build/bin/llama-tokenize"))

LENGTHS = [int(x) for x in os.environ.get("CTX_LENGTHS", "1024,2048,4096").split(",")]
DEPTHS = [float(x) for x in os.environ.get("CTX_DEPTHS", "0.10,0.50,0.90").split(",")]
SEED = int(os.environ.get("CTX_SEED", "20260817"))

NEEDLE = ("During the {yr} Kessler survey, the calibration constant recorded for the "
          "Halvorsen drift chamber was exactly {v} millivolts, and that figure was "
          "never revised.")
QUESTION = ("What was the calibration constant recorded for the Halvorsen drift "
            "chamber during the {yr} Kessler survey? Reply with only the number and "
            "its unit.")
PRE = ("You are given a long excerpt from a scientific text. Somewhere inside it a "
       "single specific measurement has been recorded. Read the excerpt carefully, "
       "then answer the question at the end using only information stated in the "
       "excerpt.\n\nEXCERPT BEGINS.\n")
POST = "\nEXCERPT ENDS.\n\n"

_cache = {}
_calls = [0]


def ntok(text):
    """Exact token count from the model's OWN tokenizer. Memoised: the uncached
    version made this script take hours."""
    if text in _cache:
        return _cache[text]
    _calls[0] += 1
    r = subprocess.run([TOKENIZE, "-m", MODEL, "-p", text, "--ids"],
                       capture_output=True, text=True)
    ids = re.search(r"\[[\d,\s]*\]", r.stdout)
    if not ids:
        raise SystemExit("tokenizer produced no ids:\n" + (r.stdout + r.stderr)[-600:])
    n = len(json.loads(ids.group(0)))
    _cache[text] = n
    return n


def clean(raw):
    s = raw
    m = re.search(r"\*\*\* START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", s, re.S)
    if m:
        s = s[m.end():]
    m = re.search(r"\*\*\* END OF (THE|THIS) PROJECT GUTENBERG", s, re.S)
    if m:
        s = s[:m.start()]
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", s)]
    return [p for p in paras if len(p) > 400 and not p.isupper()]


def build(paras, pcount, target, depth, rng):
    """Assemble EXACTLY `target` tokens with the needle at a true TOKEN depth."""
    yr = 1900 + rng.randrange(60, 99)
    val = f"{rng.randrange(100, 999) / 10:.1f}"           # fresh per trial (S3)
    needle = NEEDLE.format(yr=yr, v=val)
    question = QUESTION.format(yr=yr)
    fixed = ntok(PRE + POST + question) + ntok(needle)
    budget = target - fixed
    if budget <= 0:
        raise SystemExit(f"target {target} too small for scaffolding ({fixed} tok)")

    body, used, i = [], 0, 0
    while i < len(paras) and used + pcount[i] <= budget:
        body.append(paras[i]); used += pcount[i]; i += 1

    # Converge on the tail by BINARY SEARCH over word count (bounded, ~12 calls),
    # not by a 400-iteration nudge loop.
    if i < len(paras) and used < budget:
        words = paras[i].split()
        lo, hi, best = 0, len(words), None
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = " ".join(words[:mid])
            c = ntok(cand) if cand else 0
            if used + c <= budget:
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        if best:
            body.append(" ".join(words[:best])); used += ntok(" ".join(words[:best]))

    # Place the needle by CUMULATIVE TOKENS, not paragraph index (B3).
    cum, target_tok, pos = 0, depth * used, len(body)
    for j, p in enumerate(body):
        if cum >= target_tok:
            pos = j
            break
        cum += pcount[j] if j < len(pcount) and paras[j] is p else ntok(p)
    pos = max(0, min(len(body), pos))
    tokens_before = sum(ntok(p) for p in body[:pos])
    body_final = body[:pos] + [needle] + body[pos:]

    prompt = PRE + "\n\n".join(body_final) + POST + question
    actual = ntok(prompt)
    realised_depth = round(tokens_before / used, 4) if used else 0.0
    return {"target_tokens": target, "actual_tokens": actual,
            "requested_depth": depth, "realised_token_depth": realised_depth,
            "tokens_before_needle": tokens_before, "haystack_tokens": used,
            "expected_answer": val, "needle_year": yr,
            "needle": needle, "question": question, "prompt": prompt,
            "exact": actual == target}


if __name__ == "__main__":
    import random
    MODEL, SRC, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
    paras = clean(open(SRC, encoding="utf-8", errors="ignore").read())
    print(f"corpus: {len(paras)} prose paragraphs; counting once each...")
    pcount = [ntok(p) for p in paras]                 # counted ONCE, then reused
    print(f"  {_calls[0]} tokenizer calls for the corpus")
    os.makedirs(OUT, exist_ok=True)
    rng = random.Random(SEED)
    idx = []
    for L in LENGTHS:
        for D in DEPTHS:
            r = build(paras, pcount, L, D, rng)
            json.dump(r, open(os.path.join(OUT, f"ctx_{L}_d{int(D*100):02d}.json"), "w"))
            idx.append({k: r[k] for k in ("target_tokens", "actual_tokens",
                                          "requested_depth", "realised_token_depth",
                                          "expected_answer", "exact")})
            print(f"  {L:5d} tok  req_depth {D:.2f} -> REALISED {r['realised_token_depth']:.3f}"
                  f"  actual {r['actual_tokens']:5d} "
                  f"{'EXACT' if r['exact'] else 'OFF BY %+d' % (r['actual_tokens']-L)}"
                  f"  answer {r['expected_answer']}")
    json.dump(idx, open(os.path.join(OUT, "index.json"), "w"), indent=1)
    print(f"total tokenizer calls: {_calls[0]}")
    print("CTX_BUILD_DONE")
