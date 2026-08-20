#!/bin/sh
# Read EVERY INA3221 rail from sysfs. Matches the method the published perf/W used.
#
# WHY NOT tegrastats: the colleague deliverable's own Perf-per-Watt sheet states it --
# "INA3221 channels read directly from sysfs (NOT tegrastats, which on Orin reports only
# 3 of 4 rails and omits DRAM)". Confirmed on the board: a second INA3221 device carries
# VDDQ_VDD2_1V8AO, the DRAM rail, which tegrastats never reports. I introduced tegrastats
# sampling earlier today and it would have made this rerun's perf/W quietly incomparable
# with the figures it is meant to reproduce -- an M35 shared-context break created by
# "improving" the instrument mid-campaign.
sum=0; out=""
for h in /sys/bus/i2c/drivers/ina3221/*/hwmon/hwmon*; do
  [ -d "$h" ] || continue
  i=1
  while [ $i -le 3 ]; do
    lf="$h/in${i}_label"; pf="$h/curr${i}_input"; vf="$h/in${i}_input"
    if [ -r "$lf" ] && [ -r "$pf" ] && [ -r "$vf" ]; then
      lab=$(cat "$lf"); ma=$(cat "$pf"); mv=$(cat "$vf")
      mw=$(( ma * mv / 1000 ))
      sum=$(( sum + mw ))
      out="$out${out:+,}\"$lab\":$mw"
    fi
    i=$((i+1))
  done
done
printf '{"rails_mW":{%s},"sum_mW":%s,"source":"INA3221 sysfs, ALL rails incl DRAM","utc":"%s"}\n' \
  "$out" "$sum" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
