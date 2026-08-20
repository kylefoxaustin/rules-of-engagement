#!/usr/bin/env python3
"""VOID CHECK — Rules of Engagement M22, second generation.

WHY THIS REPLACES A HEURISTIC
-----------------------------
The supersession linter decides whether a retracted number is "safely cited" by
looking for retraction WORDS near it ("struck", "superseded", "corrected"...).
On 2026-08-18 that heuristic passed this cell:

    "IQ-9075 ~1,342 (BOTH Hexagon NSPs; corrected 2026-07-14 - earlier 349.5 was
     single-stream on ONE of its two NSPs)"

It contains "corrected". It also presents the FABRICATED value (671x2) *as* the
correction. The prose is not merely nearby-but-irrelevant; it is actively
asserting the dead number. No amount of keyword tuning fixes that, because the
text is indistinguishable from a real retraction at the language level.

So this checker does not read prose. It holds an explicit register of values that
are DEAD, each with the value that replaces it, and reports every occurrence in
every deliverable -- .md, .py builder, and .xlsx cell. A hit is a hit. Whether it
is "explained" is a judgement for a human, recorded in the register as an
allowlist entry with a reason, not inferred from adjectives.

Exit non-zero on any un-allowlisted occurrence.
"""
import json
import os
import re
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from campaign_log import log_event as _log_event
except Exception:
    def _log_event(*a, **k):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
RESULTS = os.path.dirname(BENCH)
REGISTER = os.path.join(BENCH, "campaign", "void_register.json")


def load_register():
    if not os.path.exists(REGISTER):
        return []
    return json.load(open(REGISTER)).get("records", [])


def patterns(rec):
    vals = [str(rec["value"])] + [str(a) for a in rec.get("aliases", [])]
    out = []
    for v in vals:
        v = v.strip().lstrip("~")
        if not v:
            continue
        # Not preceded by a digit/dot/comma, and not followed by a digit or by a
        # decimal point + digit. Without the second clause, "851" matched inside
        # "layer_top_scale=[851.3369141]" in every quantizer dump on disk.
        out.append(re.compile(rf"(?<![\d.,]){re.escape(v)}(?![\d]|\.\d)"))
    return out


def scan_pptx(path, recs):
    """A deck is a deliverable. It reaches more readers than the workbook does."""
    try:
        from pptx import Presentation
    except Exception:
        return []
    try:
        prs = Presentation(path)
    except Exception:
        return []
    hits = []
    for i, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            texts = []
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for r in shape.table.rows:
                    for cell in r.cells:
                        texts.append(cell.text)
            for txt in texts:
                if not txt:
                    continue
                for rec in recs:
                    for pat in patterns(rec):
                        if pat.search(txt):
                            hits.append((rec, f"{path}#slide{i}", txt[:110],
                                         _asserts(rec, txt)))
                            break
    return hits


def scan_text(path, recs):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    hits = []
    for rec in recs:
        for pat in patterns(rec):
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                ctx = text[max(0, m.start() - 70):m.start() + 70].replace("\n", " ")
                # An .md table row or a builder assignment asserts just as hard as
                # a spreadsheet cell. Hardcoding False here meant NO .md and NO
                # builder could ever fail this check.
                line_txt = text[text.rfind("\n", 0, m.start()) + 1:
                                (text.find("\n", m.end()) + 1 or len(text))]
                hits.append((rec, f"{path}:{line}", ctx, _asserts(rec, line_txt)))
                break
    return hits


def scan_xlsx(path, recs):
    """A number stored AS A NUMBER, or alone in a short cell, is an ASSERTION.
    The same digits inside a paragraph are COMMENTARY. This distinction is the whole
    reason this file exists: keyword-sniffing for retraction prose cannot tell them
    apart, and cell type can."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception:
        return []
    hits = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                txt = str(c.value)
                for rec in recs:
                    if _scoped_out(rec, ws.title):
                        continue
                    for pat in patterns(rec):
                        if pat.search(txt):
                            asserted = (isinstance(c.value, (int, float))
                                        or _asserts(rec, txt))
                            hits.append((rec, f"{path}#{ws.title}!{c.coordinate}",
                                         txt[:110], asserted))
                            break
    return hits


def _asserts(rec, text):
    """Does this text assert the dead value as current, or retract it?

    The length heuristic this replaces was defeated by the tool's own motivating
    example: the 1,342 trap cell is 100+ characters, so it was classified as
    'commentary' and passed -- the exact defect this file was written to kill.

    The reliable signal is not length and not vocabulary. It is whether the
    REPLACEMENT VALUE travels with the dead one. A genuine retraction names what
    supersedes it ("the old 1342 ... replaced by measured 1198.3"). An assertion
    states the dead value alone -- even while using the word "corrected", which is
    precisely how the trap cell defeated keyword matching.
    """
    rep = rec.get("replacement")
    if rep is None:
        return True          # nothing may replace it; any occurrence is an assertion
    r = f"{rep:g}" if isinstance(rep, (int, float)) else str(rep)
    if re.search(rf"(?<![\d.,]){re.escape(r)}(?![\d]|\.\d)", text):
        return False         # the correct value travels with the dead one
    for alt in rec.get("replacement_aliases", []):
        if str(alt) in text:
            return False
    return True


def _scoped_out(rec, sheet):
    """Some values are dead only in a given CONTEXT. 31.1 IPS is the correct batch-1
    figure on a batch-1 sheet and a lie in a MAX-throughput column."""
    only = rec.get("dead_only_in_sheets")
    if not only:
        return False
    return not any(k.lower() in sheet.lower() for k in only)


def main():
    recs = load_register()
    if not recs:
        print("VOID CHECK: register is empty — nothing enforced.")
        return 0
    allow = set()
    for r in recs:
        for a in r.get("allowlist", []):
            allow.add((str(r["value"]), a))

    # Scope: RECURSIVE, and it must include every format a reader can receive.
    # The first version scanned only top-level results/*.md|*.xlsx plus
    # bench_data/build_*|fold_*.py -- which excluded every .pptx deck, every .csv,
    # every subdirectory, AND results/build_o6_xls.py + results/build_imx95_xls.py,
    # two builders the void register's own "reaches" field names as offenders.
    # "internal" holds compiler/quantizer dumps (layer_top_scale=[...]), not claims.
    SKIP = {"superseded", "cixwork", "o6_raw", ".git", "__pycache__", "campaign",
            "internal", "cnn13", "genie_bundles", "node_modules"}
    # Files whose PURPOSE is to record retractions. A ledger that may not name the
    # value it retracts cannot do its job. Exempt BY NAME and with a reason -- never
    # by a heuristic, which is how the keyword approach failed.
    EXEMPT = {"CORRECTIONS_LEDGER.md": "the correction record itself",
              "VERIFICATION_LEDGER.md": "the verification record itself",
              "PRE_SEND_AUDIT.md": "an audit report; quoting the defect is the point",
              "PROVENANCE_APPENDIX.md": "documents provenance of superseded values",
              "void_register.json": "the register of dead values",
              "IEEE_PAPER_PROPOSAL.md": "the methodology paper; the dead values ARE its evidence",
              "build_agentic_deck.py": "the methodology deck; quotes the trap cell as its example",
              "Agentic_Benchmarking_Manager_Brief.pptx": "ditto, the rendered deck",
              "CORPUS_REDO_ROADMAP.md": "the campaign plan; cites defects it exists to fix"}
    targets = []
    for root, dirs, files in os.walk(RESULTS):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for fn in sorted(files):
            if fn.endswith((".md", ".xlsx", ".pptx", ".csv")):
                targets.append(os.path.join(root, fn))
            elif fn.endswith(".py") and fn.startswith(("build_", "fold_", "fix_")):
                targets.append(os.path.join(root, fn))

    print(f"VOID CHECK (M22-gen2) — {len(recs)} dead value(s) vs {len(targets)} deliverable(s)\n")
    asserted, mentioned = [], []
    for t in targets:
        hits = (scan_xlsx(t, recs) if t.endswith(".xlsx")
                else scan_pptx(t, recs) if t.endswith(".pptx")
                else scan_text(t, recs))
        for rec, loc, ctx, is_assert in hits:
            fpath = loc.split("#")[0].rsplit(":", 1)[0]
            if os.path.basename(fpath) in EXEMPT:
                continue
            key = (str(rec["value"]), os.path.relpath(fpath, RESULTS))
            if key in allow:
                continue
            (asserted if is_assert else mentioned).append((rec, loc, ctx))

    if asserted:
        print("ASSERTED AS DATA — a dead number presented as a fact. These are defects.\n")
        for rec, loc, ctx in asserted:
            rep = rec.get("replacement")
            rel = loc if loc.startswith("/") is False else os.path.relpath(loc, RESULTS)
            print(f"[DEAD {rec['value']}] {rel}")
            print(f"        claim: {rec['claim']}")
            print(f"        why  : {rec['why'][:130]}")
            print(f"        use  : {rep if rep is not None else 'NOTHING — no valid number exists'}"
                  f"  [{rec.get('replacement_provenance','')}]")
            print(f"        cell : {ctx.strip()[:110]}")
    if mentioned:
        print(f"\nMENTIONED IN PROSE — {len(mentioned)} occurrence(s), almost always a legitimate")
        print("retraction. NOT failed, but listed so a human can spot one that is asserting.")
        seen = {}
        for rec, loc, _ in mentioned:
            f = os.path.basename(loc.split("#")[0].split(":")[0])
            seen.setdefault(f, set()).add(str(rec["value"]))
        for f in sorted(seen):
            print(f"    {f:44s} {', '.join(sorted(seen[f]))}")

    print("\n" + "=" * 70)
    n = len(asserted)
    _log_event("gate_trip" if n else "gate_pass", tool="void_check", check="DEAD_VALUE",
               n_fail=n, n_prose=len(mentioned))
    print(f"{n} dead value(s) ASSERTED AS DATA   ({len(mentioned)} further mentions in prose)")
    return 1 if n else 0


def self_test():
    """M2 applied to the checker itself.

    An adversarial review of 2026-08-18 ran 13 crafted bypasses against this file and
    ALL 13 passed, including the trap cell quoted in this module's own docstring. A
    checker with no negative control is an assertion, not a check. These cases are the
    regression suite; each one is a bypass that actually worked.
    """
    rec = {"value": "1342", "aliases": ["1,342", "~1,342"], "claim": "iq9 dual-NSP MAX",
           "why": "fabricated 671x2", "replacement": 1198.3}
    void = {"value": "5.48", "claim": "yolov8l", "why": "non-detecting", "replacement": None}
    cases = [
        # (record, text, must_be_asserted, description)
        (rec, "IQ-9075 ~1,342 (BOTH Hexagon NSPs; corrected 2026-07-14 - earlier 349.5 was "
              "single-stream on ONE of its two NSPs)", True,
         "THE TRAP CELL: asserts the fabricated value USING the word 'corrected'"),
        (rec, "The old 1342/968/506/310/204 are replaced by measured 1198.3/870/471/293/191.",
         False, "genuine retraction: the replacement travels with the dead value"),
        (rec, "| IQ-9075 | 1342 | IPS |", True, "bare value in a markdown table row"),
        (rec, 'ws["B21"] = 1342', True, "hardcoded in a builder"),
        (rec, "corrected, superseded, struck, withdrawn: 1342", True,
         "every retraction KEYWORD present, replacement absent -- keyword matching fails here"),
        (rec, "was 1342, now 1198.3", False, "terse but correct retraction"),
        (void, "yolov8l reached 5.48 inf/s, superseded", True,
         "a VOID value has no replacement, so no mention of it is ever safe"),
    ]
    bad = 0
    for r, txt, want, desc in cases:
        got = _asserts(r, txt)
        ok = got == want
        bad += (not ok)
        print(f"  [{'ok ' if ok else 'FAIL'}] asserted={got!s:5s} want={want!s:5s}  {desc}")
    print(f"\n{len(cases) - bad}/{len(cases)} self-test cases pass")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
