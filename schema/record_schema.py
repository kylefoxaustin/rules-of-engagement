#!/usr/bin/env python3
"""MEASUREMENT RECORD SCHEMA + VALIDATOR — Rules of Engagement, Part VI item 1.

Why this exists, concretely: an audit of MEASUREMENT_RULES_OF_ENGAGEMENT.md found
**22 of 25 rules have no mechanical check at all**. Not because they are unenforceable,
but because there was nowhere to put the evidence. You cannot check "the gate ran"
(M1), "tenancy was captured in the same log" (M10), or "the ceiling is device-bound"
(M16) against a bare float.

So: every measurement emits a RECORD, not a number. The record carries its own
evidence, and this validator refuses the ones that cannot defend themselves.

Each required field traces to a rule and to a defect that actually shipped:

  value/unit/provenance   M23   a DERIVED number quoted as MEASURED
  artifact + md5          M11   numbers whose engine no longer existed
  host + log              M9    an entire board's results living only in scrollback
  config requested/measured M4  vtcm_mb silently discarded; -c 8192 pinned across a
                                "context sweep"
  gate                    M1/M2 int8 YOLO detecting nothing for months
  tenancy                 M10   measured under a resident 8.2 GB model server
  stats                   M6/D1 a 17.5% noise floor discovered only by accident
  status                  M12   a runtime error recorded as a failed gate

Usage:
    from record_schema import Record, validate
    r = Record(value=1.699, unit="ms", what="yolov8n b1 int8 accel time", host="iq9", ...)
    validate(r)              # raises on an indefensible record

    record_schema.py FILE.json    # validate a file of records
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict, fields, MISSING
from typing import Any

PROVENANCE = ("MEASURED", "DERIVED", "SOURCED")

# --- ASSURANCE LEVELS --------------------------------------------------------
# Provenance says where a number CAME FROM. Assurance says HOW HARD ANYONE TRIED TO
# BREAK IT. They are independent: a MEASURED number can be A0, and this corpus is full
# of MEASURED numbers that were wrong.
#
# Prior art, because this wheel is round elsewhere: SLSA levels for build provenance
# (L1 provenance exists -> L3 non-falsifiable provenance from a hardened builder),
# MLPerf's peer review by rival submitters, SPEC's "estimated" vs "reviewed", GRADE
# for clinical evidence, ASIL/DO-178C for safety. Nobody appears to have applied it to
# benchmark numbers.
#
# The ladder is ordered by what each tier can actually catch:
ASSURANCE = {
    "A0": ("single run, ungated — the number exists and nothing else is known. "
           "May not be published as MEASURED."),
    "A1": ("gated — the output was checked against ground truth in the SAME run, with a "
           "negative control proving the gate can fail. Catches: it did not compute, it "
           "computed garbage. Does NOT catch: a systematically wrong method."),
    "A2": ("A1 + adversarially reviewed — someone actively tried to break the claim and "
           "failed. Catches: unstated assumptions, mislabelled measurands, confounds a "
           "reader would spot. Does NOT catch: an error the method and the reviewer share."),
    "A3": ("A2 + INDEPENDENTLY REPRODUCED by a path that differs in the thing that could "
           "be wrong (M17) — different instrument, harness, board, or day. Not a replicate: "
           "a replicate repeats the same path and only measures noise."),
}

# WHY A3 IS NOT CEREMONY, from this campaign:
# the 2026-08-18 opset defect passed A1 (every gate green on both builds) AND A2 (two
# independent adversarial reviews of the deliverable, neither caught it). It died only
# at A3 — reproducing the OLD result with the NEW instrument, same board, same session.
# A2 cannot catch an error the reviewer inherits from the method. A3 can.
ESTIMATORS = ("median", "mean", "min", "max", "trimmed_mean", "slope")
# Phrases that mean "the model computed nothing". An adversarial review on 2026-08-18
# submitted gate {status: PASS, observed: "0 detections, max class score 0.0000"} and
# it validated -- because `observed` was only required to be non-empty. The gate text
# literally described the A1 defect and the validator agreed it was a PASS.
DEAD_OUTPUT = (r"\b0 detections?\b", r"\bzero detections?\b", r"\bno detections?\b",
               r"max (class )?score[: =]+0\.0{3,}", r"\bnothing detected\b",
               r"\bdets?[: =]+0\b", r"\bn_det[a-z_]*[: =]+0\b")
CEILING_WORDS = ("ceiling", "saturat", "peak", "max throughput", "maximum throughput",
                 "best case", "upper bound", "sustained max")
STATUS = ("OK", "RUNTIME_ERROR", "CANNOT_RUN", "GATE_FAIL")


class RecordError(ValueError):
    """A record that cannot defend itself. The number does not exist."""


@dataclass
class Record:
    # --- what ------------------------------------------------------------
    value: float | str
    unit: str
    what: str                      # human description, e.g. "yolov8n b1 fp16 GPU compute median"
    provenance: str                # MEASURED | DERIVED | SOURCED
    status: str = "OK"             # M12: distinct from gate outcome

    # --- where it came from ----------------------------------------------
    host: str = ""                 # M9  the box it ran on
    log: str = ""                  # M9  path ON THAT BOX
    artifact: dict = field(default_factory=dict)   # M11 {path, md5}
    utc: str = ""

    # --- what was actually asked vs actually applied ----------------------
    config: dict = field(default_factory=dict)     # M4 {"requested": {...}, "measured": {...}}

    # --- evidence it computed something correct ---------------------------
    gate: dict = field(default_factory=dict)       # M1/M2 {status, observed, negative_control}

    # --- the environment at the moment of measurement ---------------------
    tenancy: dict = field(default_factory=dict)    # M10 {accel_util_pct, top_rss, power_mode, utc}

    # --- how well it is known --------------------------------------------
    stats: dict = field(default_factory=dict)      # M6 {n, estimator, spread_pct, noise_floor_pct}

    # --- comparability ----------------------------------------------------
    overhead_ratio: float | None = None            # M14 quoted / device-compute-only
    pct_of_peak: float | None = None               # M16 only meaningful on a "ceiling"
    limiter: str = ""                              # M16 named, if not device-bound

    run_provenance: dict = field(default_factory=dict)   # run_id / boot_id / content hash
    envelope: dict = field(default_factory=dict)         # M13 power mode, clocks, thermal
    compared_against: dict = field(default_factory=dict)  # M5 the other side of a comparison
    supersedes: str = ""                                  # M39 what this replaces
    board_identity: dict = field(default_factory=dict)   # M30 which carrier
    accelerator_identity: dict = field(default_factory=dict)  # M30 which silicon
    evaluated_at: float | None = None                    # M15 where on the swept axis
    assurance: str = "A0"          # A0..A3 -- see ASSURANCE above
    assurance_evidence: dict = field(default_factory=dict)
    notes: str = ""


def _require(cond: bool, msg: str, errs: list):
    if not cond:
        errs.append(msg)


def validate(r: Record | dict, *, strict: bool = True) -> list[str]:
    """Return a list of problems. Raises RecordError if strict and any are found."""
    if isinstance(r, Record):
        d = asdict(r)
    else:
        # A raw dict does not inherit the dataclass defaults, so `status` (and every
        # other optional field) could be absent and crash the validator. Normalise
        # against the dataclass so a hand-written record is validated identically to
        # a constructed one.
        d = {f.name: (f.default if f.default is not MISSING else
                      (f.default_factory() if f.default_factory is not MISSING else None))
             for f in fields(Record)}
        d.update(dict(r))
    e: list[str] = []

    _require(d.get("assurance") in ASSURANCE,
             f"assurance must be one of {sorted(ASSURANCE)}, got {d.get('assurance')!r}", e)
    _require(d.get("provenance") in PROVENANCE,
             f"provenance must be one of {PROVENANCE}, got {d.get('provenance')!r}  [M23]", e)
    _require(d.get("status") in STATUS,
             f"status must be one of {STATUS}, got {d.get('status')!r}  [M12]", e)
    _require(bool(d.get("what")), "what: a bare number is not a measurement", e)
    _require(bool(d.get("unit")), "unit missing", e)

    # A non-OK record is allowed to be thin -- that IS the point of M12. It just may
    # never carry a value that gets published.
    if d.get("status") != "OK":
        if d.get("value") not in (None, "", "n/a"):
            e.append(f"status={d['status']} but a value is present; a failed run has no value  [M12]")
        return _finish(e, strict)

    # Everything below applies only to a record claiming a usable number.
    if d.get("provenance") == "MEASURED":
        _require(bool(d.get("host")), "host missing  [M9]", e)
        _require(bool(d.get("log")), "log path missing -- stdout is not an artifact  [M9]", e)
        _require(d.get("value") not in (None, ""),
                 "an OK record with no value is not a measurement  [M23]", e)

        art = d.get("artifact") or {}
        _require(bool(art.get("path")) and bool(art.get("md5")),
                 "artifact.path and artifact.md5 required -- a number whose artifact is gone "
                 "is unverifiable  [M11]", e)
        md5 = str(art.get("md5", ""))
        if md5:
            _require(bool(re.fullmatch(r"[0-9a-fA-F]{32}", md5)),
                     f"artifact.md5 {md5!r} is not a 32-hex-digit hash -- a field that accepts "
                     f"any string proves nothing  [M11]", e)
        apath = str(art.get("path", ""))
        # Only checkable for host-local paths; board-local paths are validated on the board.
        if apath.startswith("/") and not d.get("host_is_remote", True):
            _require(os.path.exists(apath), f"artifact.path {apath} does not exist  [M11]", e)

        cfg = d.get("config") or {}
        _require("requested" in cfg and "measured" in cfg,
                 "config needs BOTH 'requested' and 'measured' -- the whole point is proving "
                 "the setting was applied  [M4]", e)
        # M4 was vacuous: omit the swept axis from `requested` (or leave both dicts
        # empty) and there is nothing to compare. An empty requested-config on a
        # MEASURED record means the run declared no settings at all.
        if isinstance(cfg.get("requested"), dict) and not cfg["requested"]:
            e.append("config.requested is empty -- state what was asked of the device "
                     "(precision, batch, vtcm_mb, streams, clocks), or the readback "
                     "check has nothing to verify  [M4]")
        if "requested" in cfg and "measured" in cfg:
            for k, want in (cfg["requested"] or {}).items():
                got = (cfg["measured"] or {}).get(k, "<absent>")
                if got == "<absent>":
                    e.append(f"config.requested[{k}]={want!r} was never read back  [M4]")
                elif got != want:
                    e.append(f"config MISMATCH {k}: requested {want!r}, device granted {got!r}  [M4]")

        g = d.get("gate") or {}
        _require(bool(g), "gate missing -- no gate object, no number  [M1]", e)
        if g:
            _require(g.get("status") in ("PASS", "FAIL"),
                     f"gate.status must be PASS/FAIL, got {g.get('status')!r}  [M1]", e)
            _require(g.get("status") != "FAIL",
                     "gate FAILED -- this number must not be published  [M1]", e)
            obs = str(g.get("observed") or "")
            _require(bool(obs),
                     "gate.observed missing -- record WHAT was detected, not just pass/fail  [M1]", e)
            for pat in DEAD_OUTPUT:
                if re.search(pat, obs, re.I):
                    e.append(f"gate.status=PASS but gate.observed says {obs!r} -- that text "
                             f"describes a model computing NOTHING. A gate whose own evidence "
                             f"is the defect is not a gate  [M1/A1]")
                    break
            _require(bool(g.get("negative_control")),
                     "gate.negative_control missing -- an always-passing gate is no gate  [M2]", e)

        # M30 -- the INSTRUMENT must be identified, not just the host. "AGX Thor" names a
        # board type, not a unit; two identical Thors are indistinguishable without this.
        _bi = d.get("board_identity") or {}
        _ai = d.get("accelerator_identity") or {}
        _require(bool(_bi.get("board_id")) or bool(_ai.get("accel_id")),
                 "no board_id or accel_id -- the record does not identify WHICH physical "
                 "unit produced it, and a board model name is shared across every unit of "
                 "that type  [M30]", e)
        _strength = _ai.get("identity_strength") or _bi.get("identity_strength")
        if _strength == "WEAK":
            e.append("identity_strength=WEAK (machine-id only). machine-id is CLONED across "
                     "boards flashed from one image, so it cannot distinguish identical "
                     "units. Record a hardware serial  [M30]")

        # A measurement with no run provenance cannot be shown to be its own -- it
        # could be a copy of another run's evidence. Warn-level today because records
        # predating tokens exist; becomes a hard failure once backfill completes.
        _rp = d.get("run_provenance") or {}
        if not _rp.get("run_id"):
            e.append("run_provenance.run_id missing -- nothing distinguishes this record "
                     "from a copy of another run's evidence  [chain of custody]")

        t = d.get("tenancy") or {}
        _require(bool(t), "tenancy missing -- captured in the SAME run, not once per session  [M10]", e)

        s = d.get("stats") or {}
        _require("n" in s, "stats.n missing  [M6]", e)
        _require("estimator" in s, "stats.estimator missing (median/mean) -- mixed estimators "
                                   "shipped once already  [D5]", e)
        if "estimator" in s:
            _require(s["estimator"] in ESTIMATORS,
                     f"stats.estimator {s['estimator']!r} is not one of {ESTIMATORS}  [D5]", e)
        if isinstance(s.get("n"), int):
            _require(s["n"] >= 1, "stats.n must be >= 1  [M6]", e)
        # RECOMPUTED, not believed. Nothing previously checked noise_floor_pct against the
        # replicates it summarises, so five identical cached values could carry any floor
        # the submitter liked.
        reps = s.get("reps_us") or s.get("reps") or s.get("replicates")
        _require(isinstance(reps, list) and len(reps) >= 2,
                 "stats must carry the raw replicates (reps_us) so the floor can be recomputed; "
                 "a summary statistic nobody can check is an assertion  [M6]", e)
        if isinstance(reps, list) and len(reps) >= 2 and all(
                isinstance(x, (int, float)) for x in reps):
            import statistics as _st
            _med = _st.median(reps)
            if _med:
                _actual = 100.0 * (max(reps) - min(reps)) / _med
                _claimed = s.get("noise_floor_pct")
                if isinstance(_claimed, (int, float)) and abs(_actual - _claimed) > 0.05:
                    e.append(f"stats.noise_floor_pct={_claimed} but the replicates give "
                             f"{_actual:.3f}% -- it must be COMPUTED from reps, not asserted  [M6]")
            if len({round(float(x), 9) for x in reps}) == 1:
                e.append(f"all {len(reps)} replicates are byte-identical ({reps[0]}) -- that is a "
                         f"cached or copied value, not a replicate  [M6]")

        nf = s.get("noise_floor_pct")
        if isinstance(nf, (int, float)):
            _require(nf > 0,
                     "stats.noise_floor_pct = 0 claims perfect repeatability. Measure it or "
                     "state it as unknown -- 0 silently licenses every difference as real  [M6]", e)
        # M28: a run faster than physically possible did not happen.
        #
        # THIS CHECK WAS STRUCTURALLY DEAD until 2026-08-19. It fired only when unit was
        # "ms" -- and every record this chain produces is in "us", because emit_records
        # hardcodes microseconds. An adversary submitted 1 us/image (100,000x too fast)
        # and it validated clean. Per the directional-bias law a short-circuited engine
        # returns instantly, so the one unit the check ignored is exactly where
        # broken-is-faster lands.
        _TIME_TO_MS = {"ms": 1.0, "millisecond": 1.0, "milliseconds": 1.0,
                       "us": 1e-3, "usec": 1e-3, "microsecond": 1e-3, "microseconds": 1e-3,
                       "\u00b5s": 1e-3, "s": 1000.0, "sec": 1000.0, "seconds": 1000.0,
                       "ns": 1e-6}
        if "min_plausible_ms" in s:
            _require(isinstance(s["min_plausible_ms"], (int, float))
                     and s["min_plausible_ms"] > 1e-4,
                     f"stats.min_plausible_ms={s.get('min_plausible_ms')} is implausibly small; "
                     f"a floor the submitter can set to zero bounds nothing  [M28]", e)
        if "min_plausible_ms" in s and isinstance(d.get("value"), (int, float)):
            u = str(d.get("unit", "")).lower().strip()
            if u in _TIME_TO_MS:
                v_ms = d["value"] * _TIME_TO_MS[u]
                _require(v_ms >= s["min_plausible_ms"],
                         f"value {d['value']} {u} = {v_ms:g} ms is below min_plausible_ms "
                         f"{s['min_plausible_ms']} ms -- the run did not execute  [M28]", e)
            else:
                e.append(f"stats.min_plausible_ms is set but unit {u!r} is not a time unit this "
                         f"validator recognises, so M28 cannot apply. Silently skipping is how "
                         f"this check stayed dead for two days.")
        _require("noise_floor_pct" in s,
                 "stats.noise_floor_pct missing -- without it no difference can be called a "
                 "finding  [M6]", e)

    if d.get("provenance") == "DERIVED":
        _note = str(d.get("notes") or "")
        _require(bool(_note),
                 "a DERIVED number must state what it was derived FROM  [M23]", e)
        # "derived" as the explanation of a DERIVED number is a tautology, not a source.
        _require(len(_note.split()) >= 4 and _note.strip().lower() not in
                 ("derived", "derived value", "computed", "calculated"),
                 f"notes={_note!r} does not say what this was derived FROM -- name the "
                 f"inputs and their conditions  [M23]", e)

    # The value, its description and its config must describe the SAME measurand.
    # An adversary relabelled a batch-4 number as batch-1 and nothing noticed.
    if d.get("status") == "OK" and d.get("provenance") == "MEASURED":
        _w = str(d.get("what") or "")
        _cb = ((d.get("config") or {}).get("measured") or {}).get("batch")
        _mm = re.search(r"batch\s*[_-]?(\d+)", _w, re.I) or re.search(r"_b(\d+)", _w)
        if _mm and _cb is not None and int(_mm.group(1)) != int(_cb):
            e.append(f"'what' says batch {_mm.group(1)} but config.measured.batch={_cb} -- the "
                     f"label and the configuration describe different measurands  [M30]")

    # --- assurance must be EARNED, not declared -------------------------------
    _a = d.get("assurance", "A0")
    _ae = d.get("assurance_evidence") or {}
    if d.get("status") == "OK" and d.get("provenance") == "MEASURED":
        _require(_a != "A0",
                 "a MEASURED number may not be A0 (single run, ungated). Gate it or "
                 "publish it as an observation, not a measurement", e)
    if _a in ("A2", "A3"):
        _require(bool(_ae.get("adversarial_review")),
                 f"assurance={_a} claims adversarial review; name the review and what it "
                 f"attacked in assurance_evidence.adversarial_review", e)
    if _a == "A3":
        _r = _ae.get("independent_reproduction") or {}
        _require(bool(_r.get("differs_in")),
                 "assurance=A3 requires independent_reproduction.differs_in — WHAT was "
                 "different about the second path. A repeat of the same path is a "
                 "replicate and measures only noise  [M17]", e)
        _require(_r.get("agreed") is not None,
                 "assurance=A3 requires independent_reproduction.agreed (true/false) and "
                 "the observed delta", e)

    # ---- M8: accuracy is measured at the configuration quoted for speed ------
    # A gate run at batch-1 does not license a batch-16 speed claim. The gate is already
    # bound to the artifact (emit_records); this binds it to the CONFIG too.
    if d.get("status") == "OK" and d.get("provenance") == "MEASURED":
        _g = d.get("gate") or {}
        _gc = _g.get("config_at_gate")
        _mc = ((d.get("config") or {}).get("measured") or {})
        if _gc is not None:
            for _k in ("batch", "precision"):
                if _k in _gc and _k in _mc and _gc[_k] != _mc[_k]:
                    e.append(f"gate was run at {_k}={_gc[_k]} but this number is quoted at "
                             f"{_k}={_mc[_k]} -- accuracy must be measured at the configuration "
                             f"quoted for speed  [M8]")

    # ---- M13: state the envelope --------------------------------------------
    # A number with no operating envelope is not comparable to anything. Which clocks,
    # which power mode, what thermal state.
    if d.get("status") == "OK" and d.get("provenance") == "MEASURED":
        _env = d.get("envelope") or {}
        _ten = d.get("tenancy") or {}
        _has_pm = bool(_env.get("power_mode")) or bool(
            (_ten.get("before") or {}).get("power_mode"))
        _require(_has_pm,
                 "envelope.power_mode missing (or tenancy.before.power_mode) -- a latency "
                 "without its power/clock state cannot be compared across boards  [M13]", e)

    # ---- M15: no extrapolation beyond the measured span ----------------------
    _span = (d.get("stats") or {}).get("measured_span")
    if _span and isinstance(_span, dict) and isinstance(d.get("value"), (int, float)):
        _lo, _hi = _span.get("min"), _span.get("max")
        _at = d.get("evaluated_at")
        if _at is not None and isinstance(_lo, (int, float)) and isinstance(_hi, (int, float)):
            if not (_lo <= _at <= _hi):
                e.append(f"evaluated_at={_at} lies outside the measured span [{_lo}, {_hi}] "
                         f"-- that is extrapolation, and it must be labelled EXTRAPOLATED "
                         f"rather than MEASURED  [M15]")

    # ---- M21: a config label is a measurement, not a caption -----------------
    # Every field the label CLAIMS must have been read back, not merely requested.
    if d.get("status") == "OK" and d.get("provenance") == "MEASURED":
        _cfg = d.get("config") or {}
        _req, _got = _cfg.get("requested") or {}, _cfg.get("measured") or {}
        _unverified = [k for k in _req if k not in _got]
        if _unverified:
            e.append(f"config keys {_unverified} were requested but never read back; a config "
                     f"label is a measurement, not a caption  [M21]")

    # ---- M24: build-to-build variance ---------------------------------------
    # Where the toolchain builds NON-DETERMINISTICALLY (TensorRT), one build is one
    # sample of a distribution. Run-to-run replicates do not measure that.
    _art = d.get("artifact") or {}
    if _art.get("build_nondeterministic"):
        _nb = (d.get("stats") or {}).get("n_builds")
        _require(isinstance(_nb, int) and _nb >= 2,
                 "artifact.build_nondeterministic is set, so stats.n_builds >= 2 is required: "
                 "run-to-run replicates do not measure build-to-build variance, which is the "
                 "larger term  [M24]", e)

    # ---- M27: the workload must outlast the sampling window ------------------
    _st = d.get("stats") or {}
    if "sample_window_s" in _st:
        _rd = _st.get("run_duration_s")
        _require(isinstance(_rd, (int, float)) and _rd >= _st["sample_window_s"],
                 f"sample_window_s={_st['sample_window_s']} exceeds run_duration_s={_rd} -- the "
                 f"sample includes time the workload was not running  [M27]", e)

    # ---- M5: sweep both sides with COMPARABLE effort -------------------------
    # The withdrawn CPU-interference table compared boards whose stimulus differed by 8x.
    # Effort asymmetry is invisible in the numbers themselves -- it has to be declared.
    _sw = (d.get("stats") or {}).get("configs_swept")
    _cmp = d.get("compared_against") or {}
    if _cmp:
        _osw = _cmp.get("configs_swept")
        _require(isinstance(_sw, int) and isinstance(_osw, int),
                 "a comparison requires stats.configs_swept on BOTH sides -- quoting each at "
                 "its own best is only fair if each was given comparable opportunity  [M5]", e)
        if isinstance(_sw, int) and isinstance(_osw, int) and min(_sw, _osw) > 0:
            _ratio = max(_sw, _osw) / min(_sw, _osw)
            if _ratio > 2.0:
                e.append(f"sweep effort is asymmetric: {_sw} configs here vs {_osw} on the "
                         f"other side ({_ratio:.1f}x). The less-swept side is quoted below its "
                         f"best and the comparison is not like-for-like  [M5]")

    # ---- M7: probe either side of a quantum ----------------------------------
    # Where the axis has a discontinuity (prefill chunk size, batch tiling), a model
    # fitted only to points far from the boundary will extrapolate straight through it.
    # The 128->129 token step was 2.006x and was originally EXTRAPOLATED, not probed.
    _q = (d.get("stats") or {}).get("quantum")
    if _q:
        _probes = (d.get("stats") or {}).get("probe_points") or []
        _qsize = _q.get("size") if isinstance(_q, dict) else None
        if isinstance(_qsize, (int, float)) and _qsize > 0:
            _ok = any(abs((p % _qsize)) < 1e-9 for p in _probes) and \
                  any(abs((p % _qsize) - 1) < 1e-9 or (p % _qsize) == 1 for p in _probes)
            _require(_ok,
                     f"stats.quantum={_qsize} is declared but probe_points {_probes} do not "
                     f"straddle a boundary. Probe k*q and k*q+1 directly rather than fitting "
                     f"through the step  [M7]", e)

    # ---- M39: the burden of proof is on the NEW measurement -------------------
    # A re-measurement that disagrees with a prior result must FIRST reproduce that prior
    # result with the new instrument. The 2026-08-18 rebuild was better in every
    # documented respect and wrong; only reproducing the old number exposed it.
    _sup = d.get("supersedes")
    if _sup:
        _ir = (d.get("assurance_evidence") or {}).get("independent_reproduction") or {}
        _require(bool(_ir.get("differs_in")) and _ir.get("agreed") is not None,
                 "this record supersedes a prior result, so it must show that the PRIOR "
                 "result was reproduced with the NEW instrument first (assurance_evidence."
                 "independent_reproduction). Methodological superiority is not evidence  [M39]", e)

    # M16 -- only applies where the record claims a ceiling
    _what = (d.get("what") or "").lower()
    if any(w in _what for w in CEILING_WORDS):
        _require(d.get("pct_of_peak") is not None,
                 "a 'ceiling' must show it is device-bound: pct_of_peak required  [M16]", e)
        if d.get("pct_of_peak") is not None and d["pct_of_peak"] < 30:
            _require(bool(d.get("limiter")),
                     f"pct_of_peak={d['pct_of_peak']}% is a FLOOR, not a ceiling -- name the "
                     f"limiter  [M16]", e)

    return _finish(e, strict)


def _finish(e: list[str], strict: bool) -> list[str]:
    if e and strict:
        raise RecordError("indefensible record:\n  - " + "\n  - ".join(e))
    return e


# --- A/B instrumentation (campaign_log) -------------------------------------
# Automatic on purpose: the hardest lesson of this project is that a rule enforced
# by remembering is enforced sometimes. The checker logs its own trips.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass


def validate_file(path: str) -> int:
    data = json.load(open(path))
    recs = data if isinstance(data, list) else data.get("records", [])
    if not recs:
        print(f"{path}: no records found (expected a list, or {{'records': [...]}})")
        return 1
    bad = 0
    for i, r in enumerate(recs):
        errs = validate(r, strict=False)
        if errs:
            bad += 1
            print(f"  [{i}] {r.get('what', '<no what>')!r}")
            for x in errs:
                print(f"        {x}")
    _log_event("gate_trip" if bad else "gate_pass", tool="record_schema",
               check="VALIDATE", n_fail=bad, n_records=len(recs), source=os.path.basename(path))
    print(f"\n{len(recs)} record(s), {bad} indefensible")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(validate_file(sys.argv[1]))
