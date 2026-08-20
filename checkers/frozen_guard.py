#!/usr/bin/env python3
"""Refuse to silently diverge a SHIPPED artifact from the copy a recipient holds.

Why this exists: M44 says generate counts rather than typing them, which fixes
typed-count rot. It creates a different hazard. On 2026-08-20 adding M45 changed
the colleague deliverable's GENERATED rule count from 44 to 45. The rebuild was
correct, the count was correct, and the result would have been a repo copy that
disagreed with the document a colleague was already reading.

A shipped artifact is a snapshot in someone else's hands. It does not get to
change because the source grew. This guard makes that structural instead of
remembered.

  frozen_guard.py            -> report drift against the registry
  frozen_guard.py --self-test
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
REG  = os.path.join(HERE, "..", "campaign", "FROZEN.json")

def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

def check():
    reg = json.load(open(os.path.normpath(REG)))
    drift = []
    for a in reg["artifacts"]:
        p = os.path.join(ROOT, a["path"])
        if not os.path.exists(p):
            drift.append((a["path"], "MISSING", a["md5"], "-")); continue
        cur = md5(p)
        if cur != a["md5"]:
            drift.append((a["path"], "CHANGED", a["md5"], cur))
    print("=" * 70)
    print(f"FROZEN GUARD — {len(reg['artifacts'])} shipped artifact(s) registered")
    print("=" * 70)
    for path, what, was, now in drift:
        print(f"[{what}] {path}\n    shipped {was}\n    now     {now}")
    if drift:
        print(f"\n{len(drift)} shipped artifact(s) DIVERGED from what the recipient holds.")
        print("This is not automatically a defect -- a corrected artifact SHOULD change.")
        print("But it must be a DECISION: either re-send and update this registry, or")
        print("restore the snapshot. It must not happen as a side effect of a rebuild.")
    else:
        print("\n0 shipped artifact(s) diverged.")
    return len(drift)

def self_test():
    """A guard that has never fired is not evidence (M44)."""
    import tempfile, shutil
    reg = json.load(open(os.path.normpath(REG)))
    a = reg["artifacts"][0]; p = os.path.join(ROOT, a["path"])
    bak = tempfile.mktemp()
    shutil.copy(p, bak)
    try:
        before = check()
        with open(p, "a") as f: f.write("\n<!-- self-test perturbation -->\n")
        after = check()
        ok = after > before
        print(f"\nself-test: perturbed a frozen artifact -> drift {before} then {after}: "
              f"{'PASSES' if ok else 'FAILS'}")
        return 0 if ok else 1
    finally:
        shutil.copy(bak, p); os.unlink(bak)

if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else (1 if check() else 0))
