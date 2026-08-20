#!/bin/sh
# Sample INA3221 rails CONTINUOUSLY into a log, for the duration of a measured run.
#
# WHY THIS EXISTS SEPARATELY FROM read_rails.sh: read_rails.sh is a POINT sample. Wiring it
# into the collector produced GPU figures of ~3 W where the load actually draws ~48-96 W,
# because it was called AFTER the timing loop while the GPU was winding down. The INA3221
# switch fixed rail COVERAGE (tegrastats omits DRAM) and simultaneously destroyed the
# "during the run" property the tegrastats version had. Correct on one axis, wrong on the
# other, and the number still looked like a plausible power reading.
# Peak and mean are both reported: peak is comparable to the tegrastats figures, mean is
# the honest basis for energy-per-inference.
OUT=${1:?out}; INTERVAL=${2:-0.2}
: > "$OUT"
while :; do
  sh "$(dirname "$0")/read_rails.sh" >> "$OUT" 2>/dev/null
  sleep "$INTERVAL"
done
