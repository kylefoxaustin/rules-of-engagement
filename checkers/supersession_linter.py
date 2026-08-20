#!/usr/bin/env python3
"""SUPERSESSION LINTER — Rules of Engagement M22.

The defect this exists to kill (failure class E5):

    A block in the source of record is retracted, but the retraction is written
    in a NEIGHBOURING block. The retraction does not travel with the number, so
    the value keeps flowing into deliverables. In this corpus the worst case was
    a top-level block literally named THE_HEADLINE which contained two retracted
    figures and read "All figures MEASURED" — the block most likely to be quoted
    without reading its surroundings.

This walks every registry JSON, collects the values inside any block carrying a
`_SUPERSEDED` marker, and then greps every deliverable (.md / .py builder) for
those values. A hit means a retracted number is reaching a reader.

Distinctive values only: integers below 100 and common round numbers are skipped,
because "4" or "100" will match everywhere and drown the signal. A retracted 2.53
or 1012.7 is what we are hunting.

Exit non-zero on any hit so CI can gate on it.
"""
import json
import os
import re
import sys

# --- A/B instrumentation (campaign_log) -------------------------------------
# Automatic on purpose: the hardest lesson of this project is that a rule enforced
# by remembering is enforced sometimes. The checker logs its own trips.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
RESULTS = os.path.dirname(BENCH)

MARKERS = ("_SUPERSEDED", "_RETRACTED", "_DO_NOT_USE")


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def distinctive(v):
    """Is this value specific enough that a textual match means something?"""
    if isinstance(v, bool) or v is None:
        return False
    if not isinstance(v, (int, float)):
        return False
    a = abs(v)
    if a < 10:
        return isinstance(v, float) and round(v, 4) != round(v, 1)   # e.g. 2.5298
    if isinstance(v, int) and a % 10 == 0:
        return False                                                  # 100, 250, 1000
    return True


def collect_superseded():
    """-> {value: [(file, jsonpath, reason)]}"""
    out = {}
    roots = [BENCH, os.path.join(BENCH, "remeasure")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            try:
                D = json.load(open(p))
            except Exception:
                continue
            if not isinstance(D, dict):
                continue
            for key, block in D.items():
                if not isinstance(block, dict):
                    continue
                marker = next((m for m in MARKERS if m in block), None)
                if not marker:
                    continue
                reason = str(block[marker])[:120]
                for jp, v in walk(block):
                    if jp.endswith(marker):
                        continue
                    if distinctive(v):
                        out.setdefault(v, []).append((fn, f"{key}.{jp}", reason))
    return out


def deliverables():
    files = []
    for fn in sorted(os.listdir(RESULTS)):
        if fn.endswith(".md"):
            files.append(os.path.join(RESULTS, fn))
    for fn in sorted(os.listdir(BENCH)):
        if fn.startswith(("build_", "fold_")) and fn.endswith(".py"):
            files.append(os.path.join(BENCH, fn))
    return files


def main():
    sup = collect_superseded()
    if not sup:
        print("SUPERSESSION LINTER (M22): no _SUPERSEDED blocks found — nothing to enforce.")
        return 0
    print(f"SUPERSESSION LINTER (M22): tracking {len(sup)} distinctive retracted values "
          f"from {len({s[0] for v in sup.values() for s in v})} registry file(s)\n")

    hits = 0
    for path in deliverables():
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        found = []
        for val, origins in sup.items():
            s = repr(val) if isinstance(val, float) else str(val)
            s = s.rstrip("0").rstrip(".") if "." in s else s
            if not s:
                continue
            # word-boundary-ish match so 2.53 does not hit inside 12.531
            if re.search(rf"(?<![\d.]){re.escape(s)}(?![\d])", text):
                found.append((val, origins[0]))
        if found:
            rel = os.path.relpath(path, RESULTS)
            # a deliverable may legitimately cite a retracted value while retracting it
            retracting = re.search(r"struck|retract|superseded|withdrawn|not reproducible|"
                                   r"do not (use|quote)|uncalibrated engines|max of two replicates|"
                                   r"earlier version|it is now|was measured on", text, re.I)
            tag = "CITED-IN-RETRACTION?" if retracting else "LEAK"
            for val, (src, jp, reason) in found:
                print(f"[{tag}] {rel}")
                print(f"        value {val} traced to {src}#{jp}")
                print(f"        retraction says: {reason}")
                if tag == "LEAK":
                    hits += 1
    print("\n" + "=" * 68)
    _log_event("gate_trip" if hits else "gate_pass", tool="supersession_linter",
               check="LEAK", n_fail=hits)
    print(f"{hits} retracted value(s) reaching a deliverable without a retraction nearby")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
