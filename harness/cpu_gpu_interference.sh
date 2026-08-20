#!/bin/bash
# Does a heavy CPU-side memory workload steal from GPU inference?
# This is the deployment question: in an ADAS stack the A-cores are NOT idle.
# It cannot by itself separate "shared last-level cache eviction" from "shared DRAM
# bandwidth contention" -- both are real and both are the integrator's problem --
# so it is reported as total observed interference, not attributed to a mechanism.
cd /home/kyle/acc
LOG=/home/kyle/acc/cpu_gpu_interference_$(date -u +%Y%m%dT%H%M%SZ).log
{
T=/usr/src/tensorrt/bin/trtexec
NPROC=$(nproc)
echo "== TENANCY =="; date -u; nvpmodel -q 2>/dev/null | tr '\n' ' '; echo "cores=$NPROC"
run() { $T --loadEngine=$1 --iterations=300 --warmUp=2000 --avgRuns=100 --noDataTransfers --useSpinWait 2>&1 \
        | grep 'GPU Compute Time' | head -1 | sed 's/.*median = //; s/ ms.*//'; }

# A memory-streaming hog: large working set, touches far more than any LLC, on every core.
cat > /tmp/hog.c <<'EOF'
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
int main(int argc,char**argv){
  size_t n = 256UL*1024*1024;           /* 256 MB per worker: blows past any LLC */
  char *a = malloc(n), *b = malloc(n);
  if(!a||!b) return 1;
  memset(a,1,n); memset(b,2,n);
  volatile long s=0;
  while(1){ memcpy(a,b,n); s+=a[rand()%n]; }
  return (int)s;
}
EOF
gcc -O2 -o /tmp/hog /tmp/hog.c 2>/dev/null || cc -O2 -o /tmp/hog /tmp/hog.c

for m in yolov8n yolov8l; do
  E=${m}_b1.fp16.engine
  BASE=$(run $E)
  echo "  $m b1  CPU IDLE          : $BASE ms"
  for i in $(seq 1 $((NPROC-2))); do /tmp/hog & done
  HOGS=$(jobs -p | wc -l); sleep 5
  LOAD=$(run $E)
  kill $(jobs -p) 2>/dev/null; sleep 3
  echo "  $m b1  CPU LOADED ($HOGS hogs): $LOAD ms  -> $(awk -v a=$BASE -v b=$LOAD 'BEGIN{printf "%+.1f%%", 100*(b/a-1)}')"
done
rm -f /tmp/hog /tmp/hog.c
echo INTERFERENCE_DONE
} 2>&1 | tee -a $LOG
