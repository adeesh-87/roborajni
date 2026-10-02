#!/usr/bin/env python3
"""Find dead and unreachable code in a C/C++ codebase (libclang based).

Reports:
  1. Dead functions        - not reachable from the entry points via the call graph
  2. Unreachable statements - clang -Wunreachable-code-aggressive (after return,
                              break, impossible branches...)
  3. Never-compiled code   - #if / #ifdef blocks that are inactive in EVERY
                              configuration analysed (all products, all files)

One product:
  dead_code.py -p build/compile_commands.json --entry main --exclude tests/
  dead_code.py -p build --public-headers client/include/ --exclude tests/
Several products sharing code (daemon, client libs, shared component...):
  dead_code.py --config analysis.json          (see example_config.json)

What counts as an entry point (per product):
  * entry_points / --entry: function names, e.g. main
  * public_headers / --public-headers: every function declared there (library API)
  * neither given: main if it exists, else every function with external linkage
    (conservative library mode; externals nobody calls are then listed as
    "no callers" instead of "dead")
  always: extra_roots / --extra-root regexes (ISRs, asm callers, dlsym...),
  __attribute__((constructor|destructor|used|interrupt)), constructors and
  destructors, overrides of virtual methods declared outside the project, and
  globals with external linkage or dynamic initialisation.
Followed through: direct calls, address-taken functions (callbacks, function
pointers, dispatch tables in global initialisers), virtual overrides, template
instantiations, and unresolved calls in templates (matched by name).

Shared code: a function is "dead" only if it is dead in every product that
contains it; otherwise it is reported as "unused in <product>".
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

import common

UNREACHABLE_FLAGS = ["-Wunreachable-code-aggressive"]
ROOT_ATTRS = {"constructor", "destructor", "used", "interrupt", "dllexport"}
K = None


def _kinds():
    global K, FUNCS, CONTAINERS, PP_KINDS, REFS
    if K is None:
        K = common.ci.CursorKind
        FUNCS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR,
                 K.CONVERSION_FUNCTION, K.FUNCTION_TEMPLATE}
        CONTAINERS = {K.NAMESPACE, K.LINKAGE_SPEC, K.UNEXPOSED_DECL, K.CLASS_DECL,
                      K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE,
                      K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
        PP_KINDS = {K.MACRO_DEFINITION, K.MACRO_INSTANTIATION, K.INCLUSION_DIRECTIVE}
        REFS = {K.DECL_REF_EXPR, K.MEMBER_REF_EXPR, K.CALL_EXPR, K.OVERLOADED_DECL_REF}


# ---------------------------------------------------------------- per file

def analyze(entry, opts):
    """Parse one translation unit and extract functions, references, warnings."""
    _kinds()
    tu, info = common.parse(entry, opts["extra_args"] + UNREACHABLE_FLAGS,
                            opts["resource_dir"], detailed=True)
    res = {"info": info, "funcs": {}, "decls": defaultdict(set), "roots": defaultdict(set),
           "edges": set(), "vars": {}, "unreachable": [], "skipped": defaultdict(list),
           "files": set()}
    if tu is None:
        return _plain(res)
    pf, d = opts["filter"], entry.directory
    ext = common.ci.LinkageKind.EXTERNAL

    def rel_of(c):
        f = c.location.file
        return pf.rel(os.path.join(d, f.name)) if f else None

    def refs(c, owner):
        stack = list(c.get_children())
        while stack:
            n = stack.pop()
            if n.kind in REFS:
                r = n.referenced
                if r is not None and r.kind in FUNCS:
                    res["edges"].add((owner, r.get_usr()))
                    t = common.specialized_template(r)
                    if t is not None and t.kind in FUNCS:
                        res["edges"].add((owner, t.get_usr()))
                elif r is not None and r.kind == K.VAR_DECL:
                    u = r.get_usr()
                    if u and "@F@" not in u and "@FT@" not in u:  # not a local
                        res["edges"].add((owner, u))
                elif (r is None or n.kind == K.OVERLOADED_DECL_REF) and n.spelling:
                    res["edges"].add((owner, "name:" + n.spelling))  # unresolved (templates)
            stack.extend(n.get_children())

    def func(c, rel):
        usr = c.get_usr()
        if not usr:
            return
        res["decls"][usr].add(rel)
        for b in common.overridden(c):
            res["edges"].add((b.get_usr(), usr))
            if rel_of(b) is None:
                res["roots"][usr].add("overrides an external virtual")
        if c.kind in (K.CONSTRUCTOR, K.DESTRUCTOR):
            res["roots"][usr].add("constructor/destructor")
        for a in c.get_children():
            if a.kind.is_attribute():
                words = {t.spelling for t in a.get_tokens()} & ROOT_ATTRS
                if words:
                    res["roots"][usr].add("__attribute__((%s))" % ", ".join(sorted(words)))
        if c.is_definition():
            res["funcs"].setdefault(usr, (common.qualified_name(c), rel, c.location.line,
                                          c.linkage == ext))
            refs(c, usr)

    def visit(parent):
        for c in parent.get_children():
            k = c.kind
            if k in PP_KINDS:
                continue
            rel = rel_of(c)
            if rel is None:
                continue
            if k in CONTAINERS:
                visit(c)
            elif k in FUNCS:
                func(c, rel)
            elif k == K.VAR_DECL:
                usr = c.get_usr()
                dynamic = any(n.kind == K.CALL_EXPR for n in c.walk_preorder())
                res["vars"].setdefault(usr, (c.spelling, rel, c.location.line,
                                             c.linkage == ext, dynamic))
                refs(c, usr)
            elif k == K.FIELD_DECL:
                refs(c, "<root>")  # in-class member initialisers

    visit(tu.cursor)

    for diag in tu.diagnostics:
        if diag.option.startswith("-Wunreachable-code") and diag.location.file:
            rel = pf.rel(os.path.join(d, diag.location.file.name))
            if rel:
                res["unreachable"].append((rel, diag.location.line, diag.location.column,
                                           diag.spelling))
    for name, a, b in common.skipped_ranges(tu):
        rel = pf.rel(os.path.join(d, name))
        if rel:
            res["skipped"][rel].append((a, b))
    main_rel = pf.rel(entry.file)
    if main_rel:
        res["files"].add(main_rel)
    for inc in tu.get_includes():
        if inc.include:
            rel = pf.rel(os.path.join(d, inc.include.name))
            if rel:
                res["files"].add(rel)
    return _plain(res)


def _plain(res):
    """Sets/defaultdicts -> picklable plain containers."""
    res["decls"] = {k: sorted(v) for k, v in res["decls"].items()}
    res["roots"] = {k: sorted(v) for k, v in res["roots"].items()}
    res["edges"] = sorted(res["edges"])
    res["skipped"] = dict(res["skipped"])
    res["files"] = sorted(res["files"])
    return res


# ---------------------------------------------------------------- whole program

def simple_name(qname):
    return qname.rsplit("::", 1)[-1]


def analyze_product(p, results, args):
    """-> (owned usr set, dead usr set, roots description, funcs, edges, vars)."""
    funcs, decls, root_reasons, edges, gvars = {}, defaultdict(set), defaultdict(set), set(), {}
    for r in results:
        for usr, f in r["funcs"].items():
            funcs.setdefault(usr, f)
        for usr, files in r["decls"].items():
            decls[usr].update(files)
        for usr, why in r["roots"].items():
            root_reasons[usr].update(why)
        edges.update(map(tuple, r["edges"]))
        for usr, v in r["vars"].items():
            gvars.setdefault(usr, v)

    owned = {u for u, f in funcs.items() if p.owns(f[1])}
    by_name = defaultdict(set)
    for u, f in funcs.items():
        by_name[simple_name(f[0])].add(u)

    entry_points = list(p.entry_points)
    mode = []
    if not entry_points and not p.public_headers:
        if any(simple_name(funcs[u][0]) == "main" for u in owned):
            entry_points = ["main"]
        else:
            mode.append("all external functions (no entry points / public headers given)")
    roots = set(root_reasons)
    if entry_points:
        mode.append("entry points: " + ", ".join(entry_points))
        for u in owned:
            q = funcs[u][0]
            if q in entry_points or simple_name(q) in entry_points:
                roots.add(u)
    if p.public_headers:
        mode.append("public headers: " + ", ".join(p.public_headers))
        for u, files in decls.items():
            if any(common.match_path(f, pat) for f in files for pat in p.public_headers):
                roots.add(u)
    conservative = not entry_points and not p.public_headers
    if conservative:
        roots.update(u for u in owned if funcs[u][3])
    for rx in p.extra_roots:
        rc = re.compile(rx)
        roots.update(u for u, f in funcs.items() if rc.search(f[0]))
    roots.update(u for u, v in gvars.items() if v[3] or v[4])
    roots.add("<root>")

    adj = defaultdict(set)
    for s, t in edges:
        adj[s].add(t)
    seen, todo = set(roots), list(roots)
    while todo:
        n = todo.pop()
        for t in adj.get(n, ()):
            for x in (by_name.get(t[5:], ()) if t.startswith("name:") else (t,)):
                if x not in seen:
                    seen.add(x)
                    todo.append(x)

    dead = owned - seen
    uncalled = set()
    if conservative:  # externals are roots here; flag the ones nobody references
        referenced = {t for _, t in edges}
        uncalled = {u for u in owned if funcs[u][3] and u not in referenced and
                    "name:" + simple_name(funcs[u][0]) not in referenced and
                    simple_name(funcs[u][0]) != "main"} - set(root_reasons)
    return {"owned": owned, "dead": dead, "uncalled": uncalled, "mode": "; ".join(mode),
            "funcs": funcs, "edges": edges, "vars": gvars}


def caller_index(prods):
    """-> callers(usr) giving display names of everything that references usr."""
    rev, label = defaultdict(set), {}
    for pr in prods:
        for s, t in pr["edges"]:
            rev[t].add(s)
        for u, f in pr["funcs"].items():
            label[u] = f[0]
        for u, v in pr["vars"].items():
            label.setdefault(u, v[0] + " (variable)")

    def callers(usr):
        srcs = rev.get(usr, set()) | rev.get("name:" + simple_name(label.get(usr, "")), set())
        return sorted({label[s] for s in srcs if s != usr and s in label})
    return callers


def inactive_code(all_results, root):
    """Lines skipped by the preprocessor in every TU that includes the file."""
    inter = {}
    for r in all_results:
        sk = r["skipped"]
        for rel in r["files"]:
            lines = set()
            for a, b in sk.get(rel, ()):
                lines.update(range(a, b + 1))
            inter[rel] = lines if rel not in inter else inter[rel] & lines
    out = defaultdict(list)
    for rel, lines in inter.items():
        if not lines:
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                text = f.read().splitlines()
        except OSError:
            continue
        for a, b in _runs(sorted(lines)):
            for first, last, cond in _blocks(text, a, b):
                if "__cplusplus" not in cond:  # extern "C" guards
                    out[rel].append((first, last, cond))
    return out


COND_RE = re.compile(r"\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b")


def _blocks(text, a, b):
    """Split skipped lines a..b into top-level #if/#elif/#else blocks:
    yield (first code line, last code line, controlling directive)."""
    line = lambda n: text[n - 1] if 0 < n <= len(text) else ""
    cond, depth, first, last = None, 0, None, None
    if not COND_RE.match(line(a)):  # starts mid-block: find the directive above
        j = a - 1
        while j > 0 and not COND_RE.match(line(j)):
            j -= 1
        cond, depth = line(j).strip(), 1
    for n in range(a, b + 1):
        m = COND_RE.match(line(n))
        kw = m.group(1) if m else None
        if kw and kw.startswith("if"):
            depth += 1
            if depth == 1:
                cond, first, last = line(n).strip(), None, None
                continue
        elif kw in ("elif", "else") and depth == 1:
            if first:
                yield first, last, cond
            cond, first, last = line(n).strip(), None, None
            continue
        elif kw == "endif":
            depth -= 1
            if depth == 0:
                if first:
                    yield first, last, cond
                first = last = None
                continue
        if depth >= 1:
            first = first or n
            last = n
    if first and depth >= 1:
        yield first, last, cond


def _runs(lines):
    start = prev = lines[0]
    for x in lines[1:]:
        if x != prev + 1:
            yield start, prev
            start = x
        prev = x
    yield start, prev


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_common_args(ap)
    g = ap.add_argument_group("entry points (without --config)")
    g.add_argument("--entry", action="append", default=[], metavar="NAME",
                   help="entry point function (repeatable), e.g. main")
    g.add_argument("--public-headers", action="append", default=[], metavar="PATTERN",
                   help="functions declared in these headers are API (repeatable)")
    g.add_argument("--extra-root", action="append", default=[], metavar="REGEX",
                   help="treat matching functions as used, e.g. '^isr_' (repeatable)")
    g = ap.add_argument_group("output")
    g.add_argument("--skip", action="append", default=[],
                   choices=["functions", "statements", "inactive"],
                   help="leave out a report section (repeatable)")
    g.add_argument("--csv", action="store_true", help="one CSV table")
    g.add_argument("--json", action="store_true", help="JSON")
    args = ap.parse_args()

    common.setup_libclang(args.libclang)
    root, pf, products = common.load_products(args)
    if not args.config:
        p = products[0]
        p.entry_points, p.public_headers, p.extra_roots = \
            args.entry, args.public_headers, args.extra_root
    for p in products:
        if not p.entries:
            print(f"warning: product '{p.name}' matched no compile_commands entries",
                  file=sys.stderr)

    unique = {}
    for p in products:
        for e in p.entries:
            unique.setdefault(e.key(), e)
    opts = {"filter": pf, "extra_args": args.extra_arg, "resource_dir": args.resource_dir}
    keys = list(unique)
    results = dict(zip(keys, common.run_all([unique[k] for k in keys], analyze, opts, args)))
    common.report_parse_problems([r["info"] for r in results.values()], pf, args.show_errors)

    # dead functions, merged over products
    prods = {p.name: analyze_product(p, [results[e.key()] for e in p.entries], args)
             for p in products}
    func_rows = defaultdict(list)
    all_funcs = {}
    for pr in prods.values():
        all_funcs.update(pr["funcs"])
    callers_of = caller_index(prods.values())
    for usr, f in all_funcs.items():
        containing = [n for n, pr in prods.items() if usr in pr["owned"]]
        dead_in = [n for n in containing if usr in prods[n]["dead"]]
        uncalled = [n for n in containing if usr in prods[n]["uncalled"]]
        if dead_in:
            callers = callers_of(usr)
            why = ("only referenced from unused code: " + ", ".join(callers)) if callers \
                else "never referenced"
            if len(dead_in) == len(containing):
                status = "dead" + (f" (in all: {', '.join(containing)})" if len(containing) > 1
                                   else "")
            else:
                status = "unused in " + ", ".join(dead_in)
                why = "used only by " + ", ".join(n for n in containing if n not in dead_in)
            func_rows[f[1]].append((f[2], f[0], status, why))
        elif uncalled and len(uncalled) == len(containing):
            func_rows[f[1]].append((f[2], f[0], "no callers (external)",
                                    "not called in analysed code - API or dead?"))

    stmt_rows = defaultdict(set)
    for r in results.values():
        for rel, line, col, msg in r["unreachable"]:
            stmt_rows[rel].add((line, col, msg))
    inactive = inactive_code(list(results.values()), root)

    sections = []
    if "functions" not in args.skip:
        sections.append(("Dead functions", ["Line", "Function", "Status", "Why"],
                         {f: sorted(r) for f, r in func_rows.items()}))
    if "statements" not in args.skip:
        sections.append(("Unreachable statements (clang -Wunreachable-code-aggressive)",
                         ["Line", "Col", "Message"],
                         {f: sorted(r) for f, r in stmt_rows.items()}))
    if "inactive" not in args.skip:
        sections.append(("Never compiled (#if blocks inactive in every configuration analysed)",
                         ["Lines", "Condition"],
                         {f: [(f"{a}-{b}" if a != b else str(a), cond) for a, b, cond in sorted(r)]
                          for f, r in inactive.items()}))

    if args.json:
        json.dump({"products": {n: pr["mode"] for n, pr in prods.items()},
                   "sections": {title: {f: rows for f, rows in data.items()}
                                for title, _, data in sections}}, sys.stdout, indent=1)
        print()
        return
    if args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["section", "file", "line(s)", "name/col", "status/message", "detail"])
        for title, headers, data in sections:
            for f in sorted(data):
                for row in data[f]:
                    w.writerow([title.split(" (")[0], f] + list(row) + [""] * (4 - len(row)))
        return

    print("Products:")
    for n, pr in prods.items():
        print(f"  {n}: {len(pr['owned'])} functions; used = reachable from {pr['mode']}")
    for title, headers, data in sections:
        print(f"\n=== {title} ===\n")
        if not data:
            print("(none)")
        for f in sorted(data):
            print(f"file: {f}")
            common.print_table(headers, data[f])
            print()
    print("Summary: " + ", ".join(f"{title.split(' (')[0].lower()}: "
                                  f"{sum(len(r) for r in data.values())}"
                                  for title, _, data in sections))


if __name__ == "__main__":
    main()
