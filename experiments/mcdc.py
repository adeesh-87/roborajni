#!/usr/bin/env python3
"""List every MC/DC decision in a C/C++ codebase (libclang based).

For each decision: its conditions, a minimal set of test vectors that achieves
MC/DC, and the independence pair that shows each condition's effect.

  mcdc.py -p build/compile_commands.json --exclude tests/
  mcdc.py --config analysis.json --detail            (truth tables + pairs)
  mcdc.py -p build --min-conditions 2 --csv > mcdc.csv

Decisions: conditions of if / while / do-while / for / ?: and (unless
--branch-only) any other boolean expression using && or || (DO-178C counts
`ok = a && b;` and `return a || b;` as decisions too).
Conditions: the operands left after splitting on &&, || and !
(with --bitwise also & | ^ between boolean operands, no short-circuit).

MC/DC flavour: unique-cause with C/C++ short-circuit evaluation - a condition
that was not evaluated is a don't-care ("-"). Two tests form an independence
pair for condition c when c differs, the outcome differs, and every other
condition evaluated in both tests has the same value. This is the definition
clang's -fcoverage-mcdc / llvm-cov uses, so results can be checked against it.

Notes flag: decisions from macros, coupled conditions (same expression twice),
constant conditions, and conditions that can't be shown independent.
"""
import argparse
import csv
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

import common

K = None


def _kinds():
    global K, FUNCS, CONTAINERS, STMT_KIND, LITERALS
    if K is None:
        K = common.ci.CursorKind
        FUNCS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR,
                 K.CONVERSION_FUNCTION, K.FUNCTION_TEMPLATE}
        CONTAINERS = {K.NAMESPACE, K.LINKAGE_SPEC, K.UNEXPOSED_DECL, K.CLASS_DECL,
                      K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE,
                      K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
        STMT_KIND = {K.IF_STMT: "if", K.WHILE_STMT: "while", K.DO_STMT: "do-while",
                     K.FOR_STMT: "for"}
        LITERALS = {K.INTEGER_LITERAL, K.CXX_BOOL_LITERAL_EXPR, K.FLOATING_LITERAL,
                    K.CHARACTER_LITERAL, K.CXX_NULL_PTR_LITERAL_EXPR}


LOGICAL = {"&&": "and", "||": "or"}
BITWISE = {"&": "band", "|": "bor", "^": "bxor"}
COMPARE = {"<", ">", "<=", ">=", "==", "!=", "&&", "||"}


# ---------------------------------------------------------------- per file

class FileText:
    """Source bytes per file, to cut out the exact text of an expression."""

    def __init__(self):
        self.cache = {}

    def get(self, path):
        if path not in self.cache:
            try:
                with open(path, "rb") as f:
                    self.cache[path] = f.read()
            except OSError:
                self.cache[path] = None
        return self.cache[path]

    def slice(self, path, a, b):
        data = self.get(path)
        if data is None or not 0 <= a < b <= len(data):
            return None
        return " ".join(data[a:b].decode("utf-8", "replace").split())


def analyze(entry, opts):
    _kinds()
    tu, info = common.parse(entry, opts["extra_args"], opts["resource_dir"], detailed=True)
    out = {"info": info, "decisions": []}
    if tu is None:
        return out
    pf, d = opts["filter"], entry.directory
    src = FileText()
    macros = defaultdict(list)  # abs path -> [(start, end)] of macro expansions

    def path_of(c):
        f = c.location.file
        return os.path.normpath(os.path.join(d, f.name)) if f else None

    for c in tu.cursor.get_children():
        if c.kind == K.MACRO_INSTANTIATION:
            p = path_of(c)
            if p and pf.rel(p):
                macros[p].append((c.extent.start.offset, c.extent.end.offset))

    def in_macro(c, path):
        s, e = c.extent.start.offset, c.extent.end.offset
        return s >= e or any(ms <= s and e <= me for ms, me in macros.get(path, ()))

    def text(c, path, prefer_source=True):
        if prefer_source:
            t = src.slice(path, c.extent.start.offset, c.extent.end.offset)
            if t:
                return t
        return show(c)

    def decision(cond, kind, func, path, rel):
        leaves, logical = [], []

        def build(c, macro_parent):
            u = unwrap(c)
            if u.kind == K.BINARY_OPERATOR:
                op = common.binop(u)
                kids = list(u.get_children())
                if len(kids) == 2 and (op in LOGICAL or (opts["bitwise"] and op in BITWISE and
                                                         boolish(kids[0]) and boolish(kids[1]))):
                    logical.append(u.hash)
                    m = in_macro(u, path)
                    return ((LOGICAL.get(op) or BITWISE[op]), build(kids[0], m), build(kids[1], m))
            if u.kind == K.UNARY_OPERATOR and common.unop(u) == "!":
                kids = list(u.get_children())
                if len(kids) == 1:
                    return ("not", build(kids[0], macro_parent))
            # leaf: exact source text unless it was produced inside a macro body
            from_source = not in_macro(u, path) or not macro_parent
            leaves.append((text(u, path, from_source), u.kind in LITERALS))
            return ("c", len(leaves) - 1)

        tree = build(cond, False)
        if len(leaves) < opts["min_conditions"]:
            return logical
        dtext = text(cond, path, True)
        rec = {"file": rel, "line": cond.location.line, "col": cond.location.column,
               "function": func, "kind": kind, "text": dtext,
               "conditions": [t for t, _ in leaves], "notes": []}
        if in_macro(unwrap(cond), path):
            rec["notes"].append("from macro")
        groups = defaultdict(list)  # identical expressions always have the same value
        for i, (t, const) in enumerate(leaves):
            groups[re.sub(r"\s+|^\(+|\)+$", "", t)].append(i)
            if const:
                rec["notes"].append(f"c{i + 1} is constant")
        coupled = [g for g in groups.values() if len(g) > 1]
        for g in coupled:
            rec["notes"].append(" and ".join(f"c{i + 1}" for i in g) +
                                " are the same expression (coupled; impossible combinations "
                                "left out - consider masking MC/DC)")
        rec.update(solve(tree, len(leaves), opts["max_conditions"], coupled))
        out["decisions"].append(rec)
        return logical

    def body(root, func, path, rel):
        consumed = set()
        stack = [root]
        while stack:
            n = stack.pop()
            k = n.kind
            if k in STMT_KIND:
                cond = condition_of(n, path, src)
                if cond is not None:
                    consumed.update(decision(cond, STMT_KIND[k], func, path, rel))
            elif k == K.CONDITIONAL_OPERATOR:
                kids = list(n.get_children())
                if len(kids) == 3:
                    consumed.update(decision(kids[0], "?:", func, path, rel))
            elif k == K.BINARY_OPERATOR and not opts["branch_only"] and n.hash not in consumed:
                op = common.binop(n)
                if op in LOGICAL or (opts["bitwise"] and op in BITWISE and
                                     all(boolish(x) for x in n.get_children())):
                    consumed.update(decision(n, "bool expr", func, path, rel))
            stack.extend(reversed(list(n.get_children())))

    def visit(parent):
        for c in parent.get_children():
            k = c.kind
            if k == K.MACRO_INSTANTIATION or k == K.MACRO_DEFINITION or \
                    k == K.INCLUSION_DIRECTIVE:
                continue
            path = path_of(c)
            rel = pf.rel(path) if path else None
            if rel is None:
                continue
            if k in CONTAINERS:
                visit(c)
            elif k in FUNCS and c.is_definition():
                body(c, common.qualified_name(c), path, rel)
            elif k == K.VAR_DECL:
                body(c, "<global " + c.spelling + ">", path, rel)

    visit(tu.cursor)
    return out


def unwrap(c):
    """Skip parentheses and implicit casts."""
    while c.kind in (K.PAREN_EXPR, K.UNEXPOSED_EXPR):
        kids = list(c.get_children())
        if len(kids) != 1:
            break
        c = kids[0]
    return c


def boolish(c):
    """Looks like a boolean (for --bitwise): comparison, !, && / || or bool type."""
    u = unwrap(c)
    if u.kind == K.BINARY_OPERATOR:
        op = common.binop(u)
        if op in COMPARE:
            return True
        if op in BITWISE:
            return all(boolish(x) for x in u.get_children())
    if u.kind == K.UNARY_OPERATOR and common.unop(u) == "!":
        return True
    return u.type.kind == common.ci.TypeKind.BOOL or u.kind == K.CXX_BOOL_LITERAL_EXPR


def condition_of(stmt, path, src):
    kids = list(stmt.get_children())
    if stmt.kind == K.DO_STMT:
        return kids[-1] if len(kids) == 2 else None
    if stmt.kind == K.FOR_STMT:
        semis = _for_semicolons(stmt, path, src)
        if semis:
            for k in kids:
                if semis[0] < k.extent.start.offset and k.extent.end.offset <= semis[1]:
                    return k
            return None  # for (;;) or no condition
        return kids[1] if len(kids) == 4 else None
    if stmt.kind == K.IF_STMT:
        data = src.get(path)
        s = stmt.extent.start.offset
        if data and re.match(rb"if\s+constexpr\b", data[s:s + 40]):
            return None  # compile-time, not a run-time decision
    for k in kids:  # if / while: first expression (or condition variable)
        if k.kind.is_expression() or k.kind == K.VAR_DECL:
            return k
    return None


def _for_semicolons(stmt, path, src):
    """Offsets of the two ';' in a for(...) header, from the source text."""
    data = src.get(path)
    s = stmt.extent.start.offset
    if not data or not data[s:s + 3] == b"for":
        return None
    depth, semis, i = 0, [], s + 3
    while i < len(data) and len(semis) < 2:
        ch = data[i:i + 1]
        if ch == b"(":
            depth += 1
        elif ch == b")":
            depth -= 1
            if depth == 0:
                break
        elif ch == b";" and depth == 1:
            semis.append(i)
        i += 1
    return semis if len(semis) == 2 else None


def show(c):
    """Rebuild an expression's text from the AST (for code inside macros)."""
    k = c.kind
    kids = list(c.get_children())
    if k == K.UNEXPOSED_EXPR and len(kids) == 1:
        return show(kids[0])
    if k == K.PAREN_EXPR and kids:
        return "(" + show(kids[0]) + ")"
    if k == K.DECL_REF_EXPR:
        return c.spelling
    if k == K.MEMBER_REF_EXPR:
        if kids:
            arrow = kids[0].type.kind == common.ci.TypeKind.POINTER
            return show(kids[0]) + ("->" if arrow else ".") + c.spelling
        return c.spelling
    if k in LITERALS:
        if k == K.CXX_NULL_PTR_LITERAL_EXPR:
            return "nullptr"
        v = common.evaluate(c)
        if k == K.CXX_BOOL_LITERAL_EXPR and v is not None:
            return "true" if v != "0" else "false"
        toks = [t.spelling for t in c.get_tokens()]
        return v if v is not None else (toks[0] if toks else "?")
    if k == K.BINARY_OPERATOR and len(kids) == 2:
        return f"{show(kids[0])} {common.binop(c)} {show(kids[1])}"
    if k == K.UNARY_OPERATOR and kids:
        return common.unop(c) + show(kids[0])
    if k == K.CALL_EXPR:
        if not kids:
            return c.spelling + "()"
        return show(kids[0]) + "(" + ", ".join(show(a) for a in kids[1:]) + ")"
    if k == K.CSTYLE_CAST_EXPR and kids:
        return "(" + c.type.spelling + ")" + show(kids[-1])
    if k == K.ARRAY_SUBSCRIPT_EXPR and len(kids) == 2:
        return f"{show(kids[0])}[{show(kids[1])}]"
    if k == K.CONDITIONAL_OPERATOR and len(kids) == 3:
        return f"{show(kids[0])} ? {show(kids[1])} : {show(kids[2])}"
    toks = [t.spelling for t in c.get_tokens()]
    return " ".join(toks) if toks else (c.spelling or "<expr>")


# ---------------------------------------------------------------- MC/DC maths

MAX_VECTORS = 512
SEARCH_BUDGET = 200000


def evaluations(node, a):
    """Yield (assignment, outcome) for every short-circuit evaluation path."""
    t = node[0]
    if t == "c":
        for v in (True, False):
            yield {**a, node[1]: v}, v
    elif t == "not":
        for a2, v in evaluations(node[1], a):
            yield a2, not v
    elif t == "and":
        for a2, v in evaluations(node[1], a):
            if v:
                yield from evaluations(node[2], a2)
            else:
                yield a2, False
    elif t == "or":
        for a2, v in evaluations(node[1], a):
            if v:
                yield a2, True
            else:
                yield from evaluations(node[2], a2)
    else:  # bitwise: both sides always evaluated
        fn = {"band": lambda x, y: x and y, "bor": lambda x, y: x or y,
              "bxor": lambda x, y: x != y}[t]
        for a2, v in evaluations(node[1], a):
            for a3, w in evaluations(node[2], a2):
                yield a3, fn(v, w)


def solve(tree, n, max_conditions, coupled=()):
    """Test vectors, independence pairs and a minimal MC/DC test set.
    coupled: groups of condition indexes that always have the same value."""
    if n > max_conditions:
        return {"n": n, "min_tests": None, "tests": [], "pairs": {},
                "notes_extra": [f"more than {max_conditions} conditions - not solved"]}
    vecs = []
    for a, out in itertools.islice(evaluations(tree, {}), MAX_VECTORS + 1):
        v = tuple(a.get(i) for i in range(n))
        if all(len({v[i] for i in g if v[i] is not None}) <= 1 for g in coupled):
            vecs.append((v, out))
    if len(vecs) > MAX_VECTORS:
        return {"n": n, "min_tests": None, "tests": [], "pairs": {},
                "notes_extra": ["too many evaluation paths - not solved"]}
    pairs = {i: [] for i in range(n)}
    for x, y in itertools.combinations(range(len(vecs)), 2):
        (vx, ox), (vy, oy) = vecs[x], vecs[y]
        if ox == oy:
            continue
        diff = [j for j in range(n) if vx[j] is not None and vy[j] is not None and vx[j] != vy[j]]
        if len(diff) == 1:
            pairs[diff[0]].append((x, y))
    need = [i for i in range(n) if pairs[i]]
    chosen, exact = _min_cover(len(vecs), need, pairs)
    order = sorted(chosen)
    pos = {v: k + 1 for k, v in enumerate(order)}
    tests = [{"values": ["-" if v is None else "TF"[not v] for v in vecs[x][0]],
              "outcome": "TF"[not vecs[x][1]]} for x in order]
    shown = {}
    for i in need:
        for x, y in pairs[i]:
            if x in pos and y in pos:
                shown[i + 1] = [pos[x], pos[y]]
                break
    notes = [f"c{i + 1} can't be shown independent (masked/coupled)"
             for i in range(n) if not pairs[i]]
    if not exact:
        notes.append("test set found greedily, may not be minimal")
    return {"n": n, "min_tests": len(order), "tests": tests, "pairs": shown,
            "notes_extra": notes}


def _min_cover(nvec, need, pairs):
    """Smallest set of vectors containing a pair for every condition in need."""
    if not need:
        return set(), True

    def ok(s):
        return all(any(x in s and y in s for x, y in pairs[i]) for i in need)

    budget = SEARCH_BUDGET
    for k in range(min(len(need) + 1, nvec), nvec + 1):
        combos = _ncr(nvec, k)
        if combos > budget:
            break
        budget -= combos
        for combo in itertools.combinations(range(nvec), k):
            if ok(set(combo)):
                return set(combo), True
    chosen, left = set(), set(need)  # greedy fallback
    while left:
        best = None
        for i in left:
            for x, y in pairs[i]:
                s = chosen | {x, y}
                gain = sum(1 for j in left if any(p in s and q in s for p, q in pairs[j]))
                score = (gain, -len({x, y} - chosen))
                if best is None or score > best[0]:
                    best = (score, s)
        chosen = best[1]
        left = {j for j in left if not any(p in chosen and q in chosen for p, q in pairs[j])}
    return chosen, False


def _ncr(n, k):
    from math import comb
    return comb(n, k)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_common_args(ap)
    g = ap.add_argument_group("decisions")
    g.add_argument("--min-conditions", type=int, default=1, metavar="N",
                   help="only decisions with at least N conditions (default 1 = all)")
    g.add_argument("--branch-only", action="store_true",
                   help="only if/while/for/do/?: conditions, not other && / || expressions")
    g.add_argument("--bitwise", action="store_true",
                   help="treat & | ^ between boolean operands as (non short-circuit) operators")
    g.add_argument("--max-conditions", type=int, default=16, metavar="N",
                   help="don't compute tests for bigger decisions (default 16)")
    g = ap.add_argument_group("output")
    g.add_argument("--detail", action="store_true",
                   help="per decision: conditions, minimal test vectors and independence pairs")
    g.add_argument("--csv", action="store_true", help="one CSV row per decision")
    g.add_argument("--json", action="store_true", help="JSON with everything")
    args = ap.parse_args()

    common.setup_libclang(args.libclang)
    root, pf, products = common.load_products(args)
    unique = {}
    for p in products:
        for e in p.entries:
            unique.setdefault(e.key(), e)
    opts = {"filter": pf, "extra_args": args.extra_arg, "resource_dir": args.resource_dir,
            "min_conditions": args.min_conditions, "branch_only": args.branch_only,
            "bitwise": args.bitwise, "max_conditions": args.max_conditions}
    results = common.run_all(list(unique.values()), analyze, opts, args)
    common.report_parse_problems([r["info"] for r in results], pf, args.show_errors)

    # same header code is seen by several files/configurations: keep one
    decisions = {}
    for r in results:
        for dcs in r["decisions"]:
            decisions.setdefault((dcs["file"], dcs["line"], dcs["col"], dcs["kind"]), dcs)
    decs = sorted(decisions.values(), key=lambda x: (x["file"], x["line"], x["col"]))
    for x in decs:
        x["notes"] += x.pop("notes_extra", [])

    if args.json:
        json.dump(decs, sys.stdout, indent=1)
        print()
        return
    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["file", "line", "col", "function", "kind", "conditions", "min_tests",
                    "decision", "condition_list", "notes"])
        for x in decs:
            w.writerow([x["file"], x["line"], x["col"], x["function"], x["kind"], x["n"],
                        x["min_tests"] if x["min_tests"] is not None else "",
                        x["text"], " | ".join(x["conditions"]), "; ".join(x["notes"])])
        return

    by_file = defaultdict(list)
    for x in decs:
        by_file[x["file"]].append(x)
    for f, items in by_file.items():
        print(f"file: {f}")
        if args.detail:
            print()
            for x in items:
                print_detail(x)
        else:
            common.print_table(
                ["Line", "Function", "Kind", "Conds", "Min tests", "Decision", "Notes"],
                [(x["line"], common.short(x["function"], 30), x["kind"], x["n"],
                  x["min_tests"] if x["min_tests"] is not None else "?",
                  common.short(x["text"], 60), "; ".join(x["notes"])) for x in items])
        print()

    hist = Counter(x["n"] for x in decs)
    print(f"Decisions: {len(decs)} in {len(by_file)} files   "
          f"by #conditions: " + ", ".join(f"{k}: {hist[k]}" for k in sorted(hist)))
    print(f"Conditions: {sum(x['n'] for x in decs)}   minimum MC/DC tests (sum over "
          f"decisions): {sum(x['min_tests'] or 0 for x in decs)}   "
          f"decisions with notes: {sum(1 for x in decs if x['notes'])}")


def print_detail(x):
    head = f"line {x['line']}  {x['kind']}  in {x['function']}  -  {x['n']} condition(s)"
    if x["min_tests"] is not None:
        head += f", {x['min_tests']} tests"
    print(head)
    print(f"  decision: {x['text']}")
    for i, c in enumerate(x["conditions"], 1):
        print(f"  c{i} = {c}")
    if x["tests"]:
        common.print_table(["Test"] + [f"c{i}" for i in range(1, x["n"] + 1)] + ["Outcome"],
                           [[k] + t["values"] + [t["outcome"]]
                            for k, t in enumerate(x["tests"], 1)])
        if x["pairs"]:
            print("  independence pairs: " + ", ".join(
                f"c{i}: tests {a}+{b}" for i, (a, b) in sorted(x["pairs"].items(),
                                                              key=lambda kv: int(kv[0]))))
    for note in x["notes"]:
        print(f"  note: {note}")
    print()


if __name__ == "__main__":
    main()
