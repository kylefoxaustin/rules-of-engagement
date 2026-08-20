#!/usr/bin/env python3
"""BUILDER GUARD — Rules of Engagement M20.

The defect this exists to kill (failure class E2):

    A builder declares  "Source of every number: <file>.json"  in its header,
    then hardcodes every value and never opens that file. Correcting the data
    therefore does NOT correct the deliverable. This is exactly how six struck
    numbers reached a file that was about to be sent to an external colleague.

A builder is COMPLIANT when:
  1. it opens the data source it declares (or any registry JSON), and
  2. the numeric values it writes come from that data, not from literals baked
     into the script.

Rule 2 cannot be proved perfectly by static analysis, so the guard uses a
proxy that is deliberately biased toward FALSE POSITIVES: it counts float
literals that look like measurements sitting inside data-carrying constructs.
Styling numbers (column widths, row heights, RGB, font sizes) are excluded.

Exit non-zero on any violation so CI can gate on it.

Usage:
    builder_guard.py                 # scan all builders
    builder_guard.py path/to/x.py    # scan one
    builder_guard.py --list-clean    # also list compliant builders
"""
import ast
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

# Attributes/kwargs whose numbers are presentation, not data.
STYLE_KW = {"width", "widths", "height", "size", "vsize", "space_after", "row", "column", "col", "start_row", "end_row",
            "start_column", "end_column", "row_offset", "col_offset", "indent",
            "left", "right", "top", "bottom", "rotation", "wrap_text", "shrink",
            "min_col", "max_col", "min_row", "max_row", "idx", "index", "anchor",
            "fgColor", "bgColor", "color", "font_size", "zoom", "scale"}
STYLE_CALL = {"Font", "PatternFill", "Alignment", "Border", "Side", "Color",
              "get_column_letter", "range", "enumerate", "round", "len", "Inches",
              "Pt", "Emu", "Cm", "RGBColor",
              # This codebase's own layout helpers. Their arguments are column
              # widths and header LABELS -- presentation, never measurements. The
              # width idiom [40, 22, 24, 20, 16, 62] was the single largest source
              # of false "hardcoded measurement" hits across every deck and
              # workbook builder.
              #
              # ⚠ DELIBERATELY ABSENT: rows(). rows(ws, start, data) carries the
              # actual table DATA, so excluding it would hide exactly what this
              # checker exists to find. Adding a helper here must be justified by
              # what it CARRIES, not by how noisy it is.
              "header", "hdr", "W",
              # pptx geometry helpers: tb(slide,x,y,w,h) and panel(slide,x,y,w,h)
              # take nothing but inches. Every argument is layout.
              "tb", "panel", "Inches", "Emu",
              # matplotlib presentation. Figure sizes, font sizes, dpi, alpha, axis
              # limits and grid styling are all layout. The DATA plotted by bar()/
              # plot() arrives in variables, not literals, so those are left alone.
              "subplots", "set_title", "set_xlabel", "set_ylabel", "set_ylim",
              "set_xlim", "set_yscale", "set_xscale", "grid", "savefig", "legend",
              "tick_params", "axhline", "axvline", "subplots_adjust", "tight_layout",
              "set_xticks", "set_yticks", "set_xticklabels", "set_yticklabels"}

# Calls where SOME positional arguments are layout and others are DATA. Blanket
# exclusion would hide real numbers, so only the listed positions are skipped.
#   put(tf, text, size, ...)                  -> arg 2 is a font size; arg 1 is TEXT
#   bignum(slide, x, y, w, value, label, ...) -> args 1-3 are geometry; arg 4 is the VALUE
# Found 2026-08-20: build_agentic_deck.py flagged 235 "hardcoded measurements" that
# were almost entirely slide coordinates and font sizes. Excluding these calls whole
# would have hidden bignum's value -- the one argument on a deck that IS a result.
POSITIONAL_STYLE = {"put": {2}, "bignum": {1, 2, 3},
                    # ax.text(x, y, s, ...) and ax.annotate(s, xy=...) -- the leading
                    # numbers are axes coordinates. The STRING is still inspected,
                    # because a label is exactly where a hardcoded figure hides.
                    "text": {0, 1}}


def declared_sources(src):
    """JSON paths the file mentions anywhere (header comment, docstring, code)."""
    return set(re.findall(r"[\w./\-]+\.json", src))


def _code_only(src):
    """Source with comments and docstrings removed.

    An adversarial review on 2026-08-18 satisfied opens_json() with a COMMENT reading
    `# json.load(open(...))`. The regex ran on raw source, so a builder could claim to
    read its data source in prose and hardcode every value.
    """
    import io, tokenize
    out = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return src
    prev_type = tokenize.INDENT
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (
                tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT):
            continue                      # bare string expression == docstring
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.NEWLINE):
            prev_type = tok.type
    return " ".join(out)


def opens_json(tree, src):
    """Does the module actually READ a json file at run time?"""
    src = _code_only(src)
    if re.search(r"json\.loads?\s*\(", src) and re.search(r"open\s*\(", src):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("load", "loads"):
            if isinstance(node.value, ast.Name) and node.value.id == "json":
                return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # load_figs is THIS CODEBASE'S actual loader (provenance.py:141) -- it
            # opens the path, json.loads it, and RAISES on a missing file or an
            # untagged figure. It was absent from this list, so 15 of 21 builders
            # that genuinely read their sources were being reported as VIOLATION
            # "never opens a JSON". The backlog read 30-to-fix when the true figure
            # was far smaller.
            #
            # Found 2026-08-20 while converting builders: the second one on the list
            # turned out to load its source on line 8. An inflated backlog is not a
            # safe error -- it sends someone to "fix" code that is already correct,
            # and 29% of this campaign's defects came from unnecessary fixes.
            if node.func.id in ("read_json", "load_registry", "load_data", "load_figs"):
                return True
    return False


def writes_json(tree, src):
    """Does this module PRODUCE a json file rather than consume one?

    Category error found 2026-08-20: builder_guard assumes every build_*.py consumes
    data to render a deliverable. Some are MEASUREMENT SCRIPTS that produce it --
    build_5090_adas_bench.py runs models on the GPU and json.dumps the results;
    build_iq9_dualnsp_models.py compiles context binaries and writes their metadata.

    Judging a producer by "does it read its declared source" is backwards: it declares
    that file because it WRITES it. Both were reported as VIOLATION for not reading a
    file they create, and their "hardcoded measurements" were input resolutions (224,
    520, 640), iteration counts and unit conversions.

    A producer is not exempt from scrutiny -- it is simply a different KIND of thing,
    and the honest label is PRODUCER, not VIOLATION.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "attr", None) or getattr(f, "id", None)
            if name in ("dump", "dumps"):
                v = getattr(f, "value", None)
                if isinstance(v, ast.Name) and v.id == "json":
                    return True
    return False


def suspicious_literals(tree):
    """Float literals that look like measurements, outside styling contexts."""
    hits = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_Call(self, node):
            name = (node.func.id if isinstance(node.func, ast.Name)
                    else node.func.attr if isinstance(node.func, ast.Attribute) else "")
            self.stack.append(name)
            for kw in node.keywords:
                if kw.arg in STYLE_KW:
                    continue
                self.visit(kw.value)
            skip = POSITIONAL_STYLE.get(name, set())
            for i, a in enumerate(node.args):
                if i in skip:
                    continue
                self.visit(a)
            self.stack.pop()

        def visit_Subscript(self, node):
            # A slice bound is syntax and a subscript KEY is an ADDRESS -- neither is
            # a measurement. PRG["orin_tok_s"]["139"] hardcodes WHICH figure to read,
            # not the figure itself; the value still comes from the source. Counting
            # those as hardcoded data made every builder that correctly indexes its
            # own records look like it was inlining them.
            #
            # This is a narrow exemption: only the key expression is skipped. The
            # container and everything else is still walked.
            self.visit(node.value)

        def visit_Assign(self, node):
            # Layout only: row_dimensions[r].height = 26, column_dimensions["A"].width = 34.
            # These are presentation, and they made up the bulk of the flagged
            # "measurements" in every deck and workbook builder.
            tgt = node.targets[0] if node.targets else None
            if isinstance(tgt, ast.Attribute) and tgt.attr in ("height", "width"):
                return
            self.generic_visit(node)

        def visit_Constant(self, node):
            if any(s in STYLE_CALL for s in self.stack):
                return
            v = node.value
            # Numbers hidden in strings ("349.5", "1,342 IPS") were invisible before.
            if isinstance(v, str):
                # The trailing group is a UNIT ("ms", "IPS", "fps", "%"), so it must
                # not be able to absorb digits or superscripts. With \w{0,6} it did:
                # the board name "5090" parsed as 509 + "0", and the input resolution
                # "224²" as 224, so board identifiers and image sizes were being counted
                # as hardcoded measurements. An inflated backlog is not a safe error --
                # it makes the real work look bigger than it is and invites bulk edits.
                # ⚠ \d{1,3} silently excluded EVERY 4+ digit figure without a
                # thousands separator: "1198.3 IPS", "2072.2", "1458.0" were all
                # invisible to this checker. Found 2026-08-20 by a negative control
                # that a hardcoded 1198.3 in a chart label was NOT caught.
                #
                # The three accepted shapes, and why:
                #   \d{1,3}(,\d{3})+   grouped -> "1,342"   unambiguously a quantity
                #   \d+\.\d+           decimal -> "1198.3"  a bare integer that long
                #                                            is usually an identifier,
                #                                            but a DECIMAL that long
                #                                            is a measurement
                #   \d{1,3}            short   -> "296"
                # A bare 4+ digit integer ("5090", "8550") stays excluded on purpose:
                # those are part numbers, and shape alone cannot separate them from a
                # 5090-IPS result. That is a known blind spot, stated rather than fixed.
                m = re.fullmatch(r"\s*~?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{1,3})\s*[a-zA-Z%/]{0,6}\s*", v)
                if m:
                    try:
                        num = float(m.group(1).replace(",", ""))
                    except ValueError:
                        return
                    dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
                    # "1.0" is a version string; "349.5" and "1,342" are measurements.
                    if num >= 10 or dec >= 2:
                        hits.append((node.lineno, v))
                return
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return
            a = abs(v)
            if a == 0 or a == 1:
                return
            # ints count too: 1342 and 851 are measurements, and were both invisible
            # while the check was floats-only.
            if isinstance(v, float) and v != int(v):
                hits.append((node.lineno, v))
            elif a >= 10:
                hits.append((node.lineno, v))

    V().visit(tree)
    return hits


def scan(path):
    src = open(path, encoding="utf-8", errors="ignore").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"path": path, "status": "UNPARSEABLE", "detail": str(e)}
    decl = declared_sources(src)
    reads = opens_json(tree, src)
    produces = writes_json(tree, src) and not reads
    lits = suspicious_literals(tree)
    if produces:
        # Checked FIRST: a producer declares its file because it WRITES it, so
        # "never opens its declared source" is the wrong question to ask of it.
        status = "PRODUCER"
        detail = (f"WRITES its data ({sorted(decl) or 'unnamed'}) rather than reading it — this is a "
                  f"measurement script, not a deliverable builder. Judged by a different standard: it "
                  f"must GATE and RECORD, not read.")
    elif not reads and lits:
        status = "VIOLATION"
        detail = (f"declares {sorted(decl) or 'no source'} but never opens a JSON; "
                  f"{len(lits)} measurement-shaped literals hardcoded "
                  f"(first at line {lits[0][0]}: {lits[0][1]})")
    elif not reads and decl:
        status = "VIOLATION"
        detail = f"declares {sorted(decl)} in its text but never opens it"
    elif not reads:
        status = "NO-DATA"
        detail = "reads no JSON and carries no measurement-shaped literals (styling/util only)"
    elif lits:
        status = "MIXED"
        detail = (f"reads JSON, but still has {len(lits)} measurement-shaped literals "
                  f"(first at line {lits[0][0]}: {lits[0][1]}) — verify each is not data")
    else:
        status = "OK"
        detail = f"reads {sorted(decl) or 'a registry'}; no hardcoded measurements"
    return {"path": path, "status": status, "detail": detail, "n_literals": len(lits)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_clean = "--list-clean" in sys.argv
    # Scope must include results/ -- build_o6_xls.py and build_imx95_xls.py live
    # there and are the two worst offenders the triage named, yet were never scanned.
    _roots = [BENCH, os.path.dirname(BENCH)]
    targets = args or sorted(
        os.path.join(rt, f) for rt in _roots for f in os.listdir(rt)
        if f.startswith(("build_", "fold_", "fix_")) and f.endswith(".py"))

    results = [scan(t) for t in targets]
    order = {"VIOLATION": 0, "UNPARSEABLE": 1, "MIXED": 2, "NO-DATA": 3, "OK": 4}
    results.sort(key=lambda r: (order.get(r["status"], 9), r["path"]))

    bad = 0
    for r in results:
        if r["status"] in ("OK", "NO-DATA") and not show_clean:
            continue
        # MIXED now FAILS: "reads a JSON" was satisfiable by opening an unrelated file
        # while hardcoding every value, so rule 2 ("values come from the data") was
        # enforced nowhere.
        if r["status"] in ("VIOLATION", "UNPARSEABLE", "MIXED"):
            bad += 1
        print(f"[{r['status']:11s}] {os.path.relpath(r['path'], BENCH)}")
        print(f"              {r['detail']}")

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + "=" * 68)
    print("BUILDER GUARD (M20) — " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    for _r in results:
        if _r["status"] in ("VIOLATION", "UNPARSEABLE", "MIXED"):
            _log_event("gate_trip", tool="builder_guard", check=_r["status"],
                       detail=f"{os.path.basename(_r['path'])}: {_r['detail'][:220]}",
                       severity="fail")
    _log_event("gate_pass" if not bad else "gate_trip", tool="builder_guard",
               check="SUMMARY", n_fail=bad, n_scanned=len(results))
    _viol = sum(1 for r in results if r["status"] == "VIOLATION")
    _mixed = sum(1 for r in results if r["status"] == "MIXED")
    # Report the two severities SEPARATELY. Lumping them produced a single
    # "30 must be fixed" that read as 30 rewrites, when 22 of those already read
    # their source and only carry stray literals. An inflated backlog sends someone
    # to fix code that is already correct.
    print(f"scanned {len(results)} builders; {_viol} NEVER read their declared source "
          f"(full conversion needed), {_mixed} read it but still carry hardcoded "
          f"literals (partial cleanup)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
