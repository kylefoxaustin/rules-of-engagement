#!/bin/bash
# TTFT at a controlled prompt length, via llama-server /completion.
#
# ORPHAN SAFETY IS THE FIRST CONCERN, NOT AN AFTERTHOUGHT. A previous unbounded LLM run
# left two llama-cli processes alive for 43 and 59 minutes, pinning two cores of a Thor and
# blocking every later measurement. So: the server PID is captured, a trap kills it on EVERY
# exit path including INT/TERM, and the script verifies the port is free afterwards.
set -u
GGUF=${1:?gguf}; NTOK=${2:-128}; REPS=${3:-5}; PORT=${4:-18080}
BIN=$HOME/llama.cpp/build/bin/llama-server
SRV_PID=""

cleanup() {
  if [ -n "$SRV_PID" ]; then
    kill -TERM "$SRV_PID" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$SRV_PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$SRV_PID" 2>/dev/null && kill -KILL "$SRV_PID" 2>/dev/null
  fi
  # prove it -- but count by COMM, not by command line. `pgrep -f llama-server` SELF-MATCHES
  # the shell that is running this script (and any ssh command mentioning the string), which
  # reports a phantom orphan when the teardown actually worked. Worse, the obvious remedy
  # `pkill -f "llama-server.*--port $PORT"` matches that same shell and kills the session
  # doing the cleanup. Both happened here. COMM is the process's executable name and cannot
  # match a shell that merely mentions it.
  _left=$(ps -eo comm | grep -c '^llama-server$')
  _left=$(printf '%s' "${_left:-0}" | head -1)
  [ "$_left" -gt 0 ] && echo "WARNING: $_left llama-server survived teardown" >&2
  return 0
}
trap cleanup EXIT INT TERM

"$BIN" -m "$GGUF" --port "$PORT" -ngl 999 -c 4096 --no-webui >/tmp/srv_$PORT.log 2>&1 &
SRV_PID=$!
ntok() {
  python3 - "$1" "$PORT" <<'PYEOF'
import json,sys,urllib.request
p,port=sys.argv[1],sys.argv[2]
try:
    r=urllib.request.urlopen(urllib.request.Request(
        f"http://127.0.0.1:{port}/tokenize",
        data=json.dumps({"content":p}).encode(),
        headers={"Content-Type":"application/json"}),timeout=20)
    print(len(json.load(r)["tokens"]))
except Exception:
    pass
PYEOF
}

# READINESS MUST POLL THE ENDPOINT YOU ACTUALLY USE. /health answers 200 as soon as the
# SERVER is listening, while the model is still loading -- the first request then fails with
# {"error":{"message":"Loading model","code":503}}. An availability check that does not
# exercise the capability you depend on reports ready before it is.
READY=0
for i in $(seq 1 180); do
  if [ -n "$(ntok test)" ]; then READY=1; break; fi
  kill -0 "$SRV_PID" 2>/dev/null || { echo "server died while loading; see /tmp/srv_$PORT.log" >&2; exit 4; }
  sleep 1
done
[ "$READY" = 1 ] || { echo "server never became ready (model load timeout)" >&2; exit 4; }

# Build a prompt of exactly NTOK tokens AS THIS RUNTIME COUNTS THEM. Counting tokens with a
# different tokenizer is how "128 tokens" becomes 139 and silently crosses a chunk boundary.
WORD="benchmark "
P=""
for i in $(seq 1 400); do P="$P$WORD"; done
# binary-search the word count down to NTOK
LO=1; HI=400
while [ $LO -lt $HI ]; do
  MID=$(( (LO+HI)/2 ))
  P=""; for i in $(seq 1 $MID); do P="$P$WORD"; done
  N=$(ntok "$P")
  [ -z "$N" ] && { echo "tokenize failed: $(curl -s -m 5 http://127.0.0.1:$PORT/tokenize -H 'Content-Type: application/json' -d '{"content":"x"}' | head -c 200)" >&2; exit 3; }
  if [ "$N" -lt "$NTOK" ]; then LO=$((MID+1)); else HI=$MID; fi
done
P=""; for i in $(seq 1 $LO); do P="$P$WORD"; done
NFINAL=$(ntok "$P")

echo "prompt_tokens_as_runtime_counts=$NFINAL (target $NTOK)"
for r in $(seq 1 "$REPS"); do
  curl -s "http://127.0.0.1:$PORT/completion" \
    -d "$(python3 -c "
import json,sys
print(json.dumps({'prompt':'''$P''','n_predict':1,'cache_prompt':False,'temperature':0}))")" \
   | python3 -c "
import json,sys
d=json.load(sys.stdin)
t=d.get('timings',{})
print('%.2f' % t.get('prompt_ms', float('nan')))"
done
