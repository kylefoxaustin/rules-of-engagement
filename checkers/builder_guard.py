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
STYLE_KW = {"width", "height", "size", "row", "column", "col", "start_row", "end_row",
            "start_column", "end_column", "row_offset", "col_offset", "indent",
            "left", "right", "top", "bottom", "rotation", "wrap_text", "shrink",
            "min_col", "max_col", "min_row", "max_row", "idx", "index", "anchor",
            "fgColor", "bgColor", "color", "font_size", "zoom", "scale"}
STYLE_CALL = {"Font", "PatternFill", "Alignment", "Border", "Side", "Color",
              "get_column_letter", "range", "enumerate", "round", "len", "Inches",
              "Pt", "Emu", "Cm", "RGBColor"}


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
            if node.func.id in ("read_json", "load_registry", "load_data"):
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
            for a in node.args:
                self.visit(a)
            self.stack.pop()

        def visit_Constant(self, node):
            if any(s in STYLE_CALL for s in self.stack):
                return
            v = node.value
            # Numbers hidden in strings ("349.5", "1,342 IPS") were invisible before.
            if isinstance(v, str):
                m = re.fullmatch(r"\s*~?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*\w{0,6}\s*", v)
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
    lits = suspicious_literals(tree)
    if not reads and lits:
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
    print(f"scanned {len(results)} builders; {bad} must be fixed before their "
          f"deliverables can be trusted to reflect the data")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
