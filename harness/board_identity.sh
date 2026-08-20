#!/bin/sh
# BOARD IDENTITY — a stable, per-UNIT fingerprint for the physical board.
#
# Kyle, 2026-08-19: "lots of same names flying around so we need a unique signature for
# the EVK itself especially if you have two identical thors."
#
# Correct, and the naive answers are all wrong:
#
#   hostname        "ubuntu" on the Jetsons. Shared by half the fleet. Already caused a
#                   record to be labelled with a name that identifies nothing.
#   device-tree model
#                   "NVIDIA Jetson AGX Thor Developer Kit" — the board TYPE, identical
#                   across every unit of that type. This is what we had.
#   /etc/machine-id THE DANGEROUS ONE. It looks unique and it is stable, but it is
#                   CLONED when two boards are flashed from the same image — exactly the
#                   two-identical-Thors case. It also changes on OS reinstall, so it is
#                   simultaneously not-unique-enough and not-stable-enough.
#   boot_id         changes every boot. Good for run provenance (it is used there),
#                   useless as board identity.
#
# What actually identifies a physical unit is a HARDWARE serial, and every board in this
# fleet exposes one somewhere different:
#
#   AGX Orin / Thor   /proc/device-tree/serial-number   1421023071894 / 1423425071125
#   IQ-9075           /sys/devices/soc0/serial_number   578746346
#   x86               /sys/class/dmi/id/product_serial
#
# So: take the strongest available source, RECORD WHICH ONE IT WAS, and grade the
# confidence. A board_id derived from machine-id alone is not a lie, but a reader must be
# able to see that it is weaker than one derived from silicon.

board_identity() {
  _model=$([ -r /proc/device-tree/model ] && tr -d "\0" < /proc/device-tree/model 2>/dev/null || echo "")
  [ -z "$_model" ] && _model=$(cat /sys/class/dmi/id/product_name 2>/dev/null)
  [ -z "$_model" ] && _model=$(uname -m)

  _serial=""; _src=""; _strength=""
  # 1. hardware serial from the device tree (Jetson, many ARM SoCs)
  if [ -z "$_serial" ] && [ -r /proc/device-tree/serial-number ]; then
    _serial=$(tr -d '\0' < /proc/device-tree/serial-number 2>/dev/null)
    [ -n "$_serial" ] && { _src="device-tree/serial-number"; _strength="STRONG"; }
  fi
  # 2. SoC serial (Qualcomm and others)
  if [ -z "$_serial" ] && [ -r /sys/devices/soc0/serial_number ]; then
    _serial=$(cat /sys/devices/soc0/serial_number 2>/dev/null)
    [ -n "$_serial" ] && { _src="soc0/serial_number"; _strength="STRONG"; }
  fi
  # 3. DMI product serial (x86)
  if [ -z "$_serial" ] && [ -r /sys/class/dmi/id/product_serial ]; then
    _serial=$(cat /sys/class/dmi/id/product_serial 2>/dev/null)
    case "$_serial" in ""|"None"|"To be filled by O.E.M."|*"Default"*) _serial="";; esac
    [ -n "$_serial" ] && { _src="dmi/product_serial"; _strength="STRONG"; }
  fi
  # 4. first real MAC — hardware, but administratively changeable
  if [ -z "$_serial" ]; then
    _serial=$(cat /sys/class/net/*/address 2>/dev/null \
              | grep -vE '^(00:00:00|02:42)' | head -1)
    [ -n "$_serial" ] && { _src="nic/mac"; _strength="MEDIUM"; }
  fi
  # 5. last resort. Say loudly that this does NOT distinguish cloned images.
  if [ -z "$_serial" ]; then
    _serial=$(cat /etc/machine-id 2>/dev/null)
    _src="machine-id"; _strength="WEAK"
  fi

  _bid=$(printf '%s|%s' "$_model" "$_serial" | sha256sum | cut -c1-16)
  _warn=""
  [ "$_strength" = "WEAK" ] && _warn=" — machine-id is CLONED across boards flashed from one image; two identical units may collide"
  [ "$_strength" = "MEDIUM" ] && _warn=" — a MAC can be administratively reassigned"

  printf '{"board_id":"%s","model":"%s","serial_source":"%s","identity_strength":"%s","note":"stable across boots, unique per physical unit%s"}' \
    "$_bid" "$_model" "$_src" "$_strength" "$_warn"
}

# ---------------------------------------------------------------------------
# ACCELERATOR IDENTITY — identify the INSTRUMENT, not merely its carrier.
#
# Kyle, 2026-08-19: "in the 5090 case can't we get a serial number for the GPU only?"
# Yes, and it is the better identity. The thing being measured is the GPU. On the 5090
# host the strongest BOARD id was the motherboard's NIC MAC (MEDIUM) -- but the GPU
# carries its own UUID, burned in, which:
#   * survives being moved to a different host,
#   * distinguishes two identical 5090s in one chassis,
#   * does not change when the OS is reinstalled.
# The motherboard identity is nearly irrelevant to a GPU measurement; it identifies the
# room the instrument was standing in, not the instrument.
#
# On integrated parts (Jetson, IQ-9075) the accelerator IS the SoC, so the board serial
# already identifies it and accel_id falls back to board_id -- correctly, not by accident.
# NOTE: GeForce cards report serial "0"; only UUID is usable. Datacenter cards give both.
accelerator_identity() {
  _auuid=""; _asrc=""; _aname=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    _auuid=$(nvidia-smi --query-gpu=uuid --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')
    _aname=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    case "$_auuid" in
      GPU-*) _asrc="nvidia-smi/gpu-uuid";;
      *)     _auuid="";;
    esac
  fi
  if [ -n "$_auuid" ]; then
    _aid=$(printf '%s' "$_auuid" | sha256sum | cut -c1-16)
    printf '{"accel_id":"%s","accel_name":"%s","accel_uuid":"%s","source":"%s","identity_strength":"STRONG","note":"the accelerator itself; survives a host swap and distinguishes two identical cards"}' \
      "$_aid" "$_aname" "$_auuid" "$_asrc"
  else
    # integrated accelerator: the SoC serial already identifies it
    _b=$(board_identity)
    _bid=$(printf '%s' "$_b" | sed -n 's/.*"board_id":"\([^"]*\)".*/\1/p')
    _bs=$(printf '%s' "$_b" | sed -n 's/.*"identity_strength":"\([^"]*\)".*/\1/p')
    printf '{"accel_id":"%s","accel_name":"integrated","source":"board (accelerator is on-SoC)","identity_strength":"%s","note":"integrated accelerator -- the board serial identifies it directly"}' \
      "$_bid" "$_bs"
  fi
}

# standalone: print it
if [ "${0##*/}" = "board_identity.sh" ]; then
  printf '{"board":'; board_identity; printf ',"accelerator":'; accelerator_identity; printf '}\n'
fi
