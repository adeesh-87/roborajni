#!/usr/bin/env python3
"""Report CPPTEST tests present under f1 but missing from f2's gtest TESTs.

f1: <f1>/{testcases,testcases_target}/**/UnitTest_<file>[_cpp].cpp
    CPPTEST_TEST(<module>_..._<MARKER>_<test_name>)  (also CPPTEST_TEST_DISABLED)
f2: <f2>/testcases/**/test_<file>.cpp
    TEST(<module>, <something containing test_name>)

Parsing an f1 name:
  1. split on "_"; first part is the module
  2. marker = first part in {INTRF, CC, BV, EQ}; if none, the first short
     ALL-CAPS part (e.g. PP); if none, assume <module>_x_x_x_<test_name>
  3. parts after the marker = test name, parts before it = context

Matching:
  * names are split into lower-case tokens (on "_", camelCase, digits);
    tokens are weighted by how rare they are among f2 names
  * score = weighted share of the f1 test-name tokens found in the f2 name
  * numeric names (e.g. EQ_3): the number must be an exact token in the f2
    name; context tokens and same file-under-test break ties
  * only f2 tests in the same module are considered (case-insensitive)
  * one-to-one maximum matching: each f2 test covers at most one f1 test,
    so EQ_1 / EQ_2 / EQ_3 can't all claim the same f2 test. Identical f1
    names (e.g. same test in testcases and testcases_target) count once.

Mock check (for matched pairs): functions mocked in f1 but not in f2.
  f1: CPPTEST_REGISTER_CALLBACK(<func>, ...) in the test body, setUp() and
      any same-file helper functions they call
  f2: .expectOneCall("func") / .expectNCalls(n, "func") / .expectNoCall("func")
      in the TEST body, its TEST_GROUP block (setup()) and same-file helpers
  Function names are compared by base name ("int ns::foo(int)" -> foo).
"""
import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

F1_DIRS = ("testcases", "testcases_target")
F2_DIRS = ("testcases",)
KNOWN_MARKERS = {"INTRF", "CC", "BV", "EQ"}

COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
F1_RE = re.compile(r"\bCPPTEST_TEST(_DISABLED)?\s*\(\s*([^,)\s]+)")
F2_RE = re.compile(r"(?<![A-Za-z0-9_])TEST\s*\(\s*([^,\s)]+)\s*,\s*([^,)\s]+)")
GUESS_MARKER_RE = re.compile(r"^[A-Z]{2,5}$")
TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

# mocks
F1_MOCK_RE = re.compile(r"\bCPPTEST_REGISTER_CALLBACK\s*\(")
F1_MOCK_PREFIXES = ("CppTest_StubCallback_", "CppTest_Stub_")
F2_MOCK_RE = re.compile(
    r"\.\s*expect(?:OneCall|NCalls|NoCall)\s*\(\s*(?:[^,()\"]+,\s*)?\"([^\"]+)\"")
CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
# headers of top-level { } blocks
TEST_HDR_RE = re.compile(r"(?<![\w])TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*$")
GROUP_HDR_RE = re.compile(r"\bTEST_GROUP\s*\(\s*(\w+)\s*\)\s*$")
CPPTEST_HDR_RE = re.compile(r"\bCPPTEST_TEST(?:_DISABLED)?\s*\(\s*(\w+)\s*\)\s*$")
FUNC_HDR_RE = re.compile(
    r"(\w+)\s*\((?:[^()]|\([^()]*\))*\)\s*(?:const|override|noexcept|\s)*$")
TRANSPARENT_HDR_RE = re.compile(r"(?:\bnamespace(?:\s+[\w:]+)?|\bextern\s*\"C\")\s*$")


def skip_literal(text, i):
    """i is at a quote; return the index just past the closing quote."""
    q, i = text[i], i + 1
    while i < len(text) and text[i] != q:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def match_close(text, i, open_ch, close_ch):
    """i is at open_ch; return the index of the matching close_ch."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = skip_literal(text, i)
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


def top_level_blocks(text):
    """Yield (header, body) for every top-level { } block. namespace and
    extern "C" blocks are looked into rather than returned."""
    start, i = 0, 0
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = skip_literal(text, i)
            continue
        if c == "{":
            header = text[start:i][-500:]
            if TRANSPARENT_HDR_RE.search(header):
                i = start = i + 1
                continue
            end = match_close(text, i, "{", "}")
            yield header, text[i + 1:end]
            i = start = end + 1
            continue
        if c in ";}":
            start = i + 1
        i += 1


def base_name(s):
    s = s.strip().strip('"').strip()
    m = re.search(r"(\w+)\s*\(", s)  # signature: "int ns::foo(int)" -> foo
    ids = [m.group(1)] if m else re.findall(r"\w+", s)
    if not ids:
        return None
    name = ids[-1]
    for p in F1_MOCK_PREFIXES:
        if name.startswith(p):
            name = name[len(p):]
    return name


def f1_mocks(body, arg_index):
    out = set()
    for m in F1_MOCK_RE.finditer(body):
        open_i = m.end() - 1
        args, depth, last = [], 0, open_i + 1
        end = match_close(body, open_i, "(", ")")
        i = open_i + 1
        while i < end:  # split on top-level commas
            c = body[i]
            if c in "\"'":
                i = skip_literal(body, i)
                continue
            depth += c in "([{"
            depth -= c in ")]}"
            if c == "," and depth == 0:
                args.append(body[last:i])
                last = i + 1
            i += 1
        args.append(body[last:end])
        if arg_index < len(args) and (name := base_name(args[arg_index])):
            out.add(name)
    return out


def f2_mocks(body, _arg_index=None):
    return {base_name(n) for n in F2_MOCK_RE.findall(body)} - {None}


class SourceFile:
    """Test bodies, TEST_GROUP blocks and helper functions of one file, so a
    test's mocks can be collected through the helpers it calls."""

    def __init__(self, text, mock_fn, arg_index=0):
        self.mock_fn, self.arg_index = mock_fn, arg_index
        self.tests, self.groups = {}, defaultdict(str)
        self.funcs = defaultdict(lambda: (set(), set()))  # name -> (mocks, calls)
        for header, body in top_level_blocks(text):
            if m := TEST_HDR_RE.search(header):
                self.tests[(m.group(1), m.group(2))] = body
            elif m := GROUP_HDR_RE.search(header):
                self.groups[m.group(1)] += body
            elif m := CPPTEST_HDR_RE.search(header):
                self.tests[m.group(1)] = body
            elif m := FUNC_HDR_RE.search(header):
                mocks, calls = self.funcs[m.group(1)]
                mocks |= mock_fn(body, arg_index)
                calls |= set(CALL_RE.findall(body))

    def mocks(self, body="", funcs=()):
        """Mocks in body and in the named functions, following helper calls."""
        found = set(self.mock_fn(body, self.arg_index))
        todo, seen = list(CALL_RE.findall(body)) + list(funcs), set()
        while todo:
            n = todo.pop()
            if n in seen or n not in self.funcs:
                continue
            seen.add(n)
            found |= self.funcs[n][0]
            todo += self.funcs[n][1]
        return found

    def f1_test_mocks(self, name):
        if name in self.tests:
            return self.mocks(self.tests[name], ["setUp"])
        if name in self.funcs:
            return self.mocks(funcs=[name, "setUp"])
        return None  # body not found

    def f2_test_mocks(self, group, name):
        if (group, name) not in self.tests:
            return None
        return self.mocks(self.tests[(group, name)]) | self.mocks(self.groups.get(group, ""))


def tokens(s):
    return [t.lower() for t in TOKEN_RE.findall(s)]


def read(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return COMMENT_RE.sub("", text)


def files(root, subdirs, prefix):
    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            print(f"warning: {base} not found", file=sys.stderr)
            continue
        yield from sorted(base.rglob(f"{prefix}*.cpp"))


def file_under_test(path, prefix):
    name = path.stem[len(prefix):]
    return name[:-4] if name.endswith("_cpp") else name


class F1Test:
    def __init__(self, full, fut, disabled, path):
        self.full, self.fut, self.disabled, self.path = full, fut, disabled, path
        parts = [p for p in full.split("_") if p]
        self.module, rest = parts[0], parts[1:]
        idx = next((i for i, p in enumerate(rest) if p.upper() in KNOWN_MARKERS), None)
        self.how = "marker"
        if idx is None:
            idx = next((i for i, p in enumerate(rest) if GUESS_MARKER_RE.match(p)), None)
            self.how = "guessed"
        if idx is None:
            idx = 2 if len(rest) >= 4 else -1
            self.how = "fallback"
        ctx, name = rest[:idx + 1], rest[idx + 1:]
        self.marker = rest[idx] if idx >= 0 and self.how != "fallback" else ""
        self.name = "_".join(name)
        self.name_tok, self.ctx_tok = tokens(self.name), tokens("_".join(ctx))
        if not self.name_tok:  # nothing after the marker: use the context
            self.name_tok, self.ctx_tok = self.ctx_tok, []
        self.numeric = bool(self.name_tok) and all(t.isdigit() for t in self.name_tok)

    @property
    def parsed(self):
        return f"{self.marker}:{self.name}" if self.marker else self.name


class F2Test:
    def __init__(self, module, name, fut, path):
        self.module, self.name, self.fut, self.path = module, name, fut, path
        tok = tokens(name)
        self.tokset, self.joined = set(tok), "".join(tok)

    def has(self, t):
        # exact token, or a longer word glued inside another (e.g. "checksvalue")
        return t in self.tokset or (not t.isdigit() and len(t) >= 4 and t in self.joined)


def collect_f1(root, mock_arg):
    out = []
    for path in files(root, F1_DIRS, "UnitTest_"):
        fut = file_under_test(path, "UnitTest_")
        text = read(path)
        src = SourceFile(text, f1_mocks, mock_arg)
        for m in F1_RE.finditer(text):
            t = F1Test(m.group(2), fut, bool(m.group(1)), path)
            t.mocks = src.f1_test_mocks(t.full)
            out.append(t)
    return out


def collect_f2(root):
    out = []
    for path in files(root, F2_DIRS, "test_"):
        fut = file_under_test(path, "test_")
        text = read(path)
        src = SourceFile(text, f2_mocks)
        for m in F2_RE.finditer(text):
            t = F2Test(m.group(1), m.group(2), fut, path)
            t.mocks = src.f2_test_mocks(t.module, t.name)
            out.append(t)
    return out


def make_weight(t2):
    df = Counter(t for f in t2 for t in f.tokset)
    n = len(t2)
    return lambda t: math.log((n + 1) / (df[t] + 1)) + 1


def coverage(toks, f2, w):
    total = sum(w(t) for t in toks)
    return sum(w(t) for t in toks if f2.has(t)) / total if total else 0.0


def score(f1, f2, w):
    """(main, context, same_file) - compared as a tuple, higher is better."""
    if f1.numeric:
        main = 1.0 if all(t in f2.tokset for t in f1.name_tok) else 0.0
    else:
        main = coverage(f1.name_tok, f2, w)
    return (main, coverage(f1.ctx_tok, f2, w), f1.fut.lower() == f2.fut.lower())


def max_matching(nodes, edges):
    """Maximum bipartite matching (BFS augmenting paths). Nodes are tried in
    the given order and edges in preference order, so strong matches win."""
    match_l, match_r = {}, {}
    for u in nodes:
        if not edges[u]:
            continue
        parent, seen, queue, found = {}, set(), [u], None
        while queue and found is None:
            x = queue.pop(0)
            for v in edges[x]:
                if id(v) in seen:
                    continue
                seen.add(id(v))
                parent[id(v)] = x
                if id(v) not in match_r:
                    found = v
                    break
                queue.append(match_r[id(v)])
        v = found
        while v is not None:  # flip the augmenting path
            x = parent[id(v)]
            prev = match_l.get(x)
            match_l[x], match_r[id(v)] = v, x
            v = prev
    return match_l


def print_table(headers, rows):
    widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    fmt = "| " + " | ".join(f"{{:<{w}}}" for w in widths) + " |"
    print(line)
    print(fmt.format(*headers))
    print(line)
    for r in rows:
        print(fmt.format(*[str(c) for c in r]))
    print(line)


def output(headers, rows, as_csv):
    if as_csv:
        w = csv.writer(sys.stdout)
        w.writerow(headers)
        w.writerows(rows)
    else:
        print_table(headers, rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("f1", type=Path)
    ap.add_argument("f2", type=Path)
    ap.add_argument("--threshold", type=float, default=0.8,
                    help="min share (0-1) of f1 test-name tokens found in the f2 name "
                         "(default 0.8)")
    ap.add_argument("--same-file", action="store_true",
                    help="only match f2 tests from the same <file_under_test>")
    ap.add_argument("--any-module", action="store_true",
                    help="ignore the module, compare against all f2 tests")
    ap.add_argument("--no-unique", action="store_true",
                    help="let one f2 test cover several f1 tests")
    ap.add_argument("--matches", action="store_true",
                    help="also print the matched pairs, to verify the matching")
    ap.add_argument("--f1-mock-arg", type=int, default=1,
                    help="which CPPTEST_REGISTER_CALLBACK argument (1-based) names "
                         "the mocked function (default 1)")
    ap.add_argument("--csv", action="store_true", help="CSV output instead of tables")
    args = ap.parse_args()

    for d in (args.f1, args.f2):
        if not d.is_dir():
            sys.exit(f"error: {d} is not a directory")

    t1, t2 = collect_f1(args.f1, args.f1_mock_arg - 1), collect_f2(args.f2)
    w = make_weight(t2)
    group = (lambda m: "") if args.any_module else str.lower

    f2_by_group = defaultdict(list)
    for f in t2:
        f2_by_group[group(f.module)].append(f)

    # identical f1 names (e.g. testcases vs testcases_target) share one node
    f1_by_key = defaultdict(list)
    for f in t1:
        f1_by_key[(group(f.module), f.full)].append(f)

    edges, closest = {}, {}
    for key, same in f1_by_key.items():
        f1 = same[0]
        cands = f2_by_group.get(key[0], [])
        if args.same_file:
            cands = [c for c in cands if c.fut.lower() == f1.fut.lower()]
        scored = sorted(((score(f1, c, w), i, c) for i, c in enumerate(cands)),
                        key=lambda x: (x[0], -x[1]), reverse=True)
        closest[key] = (scored[0][0], scored[0][2]) if scored else None
        edges[key] = [c for s, _, c in scored if s[0] >= args.threshold and s[0] > 0]

    if args.no_unique:
        match = {k: e[0] for k, e in edges.items() if e}
    else:
        # strong text matches first, numeric-only names last
        order = sorted(edges, key=lambda k: (not f1_by_key[k][0].numeric,
                                             closest[k][0] if closest[k] else (0, 0, False)),
                       reverse=True)
        match = max_matching(order, edges)
    owner = {id(v): k for k, v in match.items()}

    missing, matched, mock_gaps = [], [], []
    no_body = Counter()
    for key, same in f1_by_key.items():
        f1 = same[0]
        if key in match:
            f2 = match[key]
            s = score(f1, f2, w)
            flags = [x for x, on in (("numeric", f1.numeric), ("partial", s[0] < 1),
                                     ("other file", not s[2])) if on]
            matched.append((f1.module, f1.full, f1.parsed, f1.how, f2.name,
                            f"{s[0]:.2f}", ", ".join(flags)))
            bodies = [f.mocks for f in same if f.mocks is not None]
            if not bodies:
                no_body["f1"] += 1
            elif f2.mocks is None:
                no_body["f2"] += 1
            elif gap := set().union(*bodies) - f2.mocks:
                mock_gaps.append((f1.module, f1.full, f2.name, len(gap),
                                  ", ".join(sorted(gap)), f2.path.relative_to(args.f2)))
            continue
        if closest[key] is None:
            sc, best = "0.00", "-"
        else:
            s, c = closest[key]
            sc, best = f"{s[0]:.2f}", c.name
            if id(c) in owner:
                best += f"  (used by {owner[id(c)][1]})"
        for f in same:
            missing.append((f.module, f.fut, f.full, f.parsed, f.how,
                            "DISABLED" if f.disabled else "enabled", sc, best,
                            f.path.relative_to(args.f1)))

    hows = Counter(f.how for f in t1)
    print(f"f1 tests: {len(t1)} ({len(f1_by_key)} unique)   f2 tests: {len(t2)}   "
          f"matched: {len(match)}   in f1 but not f2: {len(missing)}")
    print(f"f1 name parsing: known marker {hows['marker']}, guessed marker "
          f"{hows['guessed']}, fallback {hows['fallback']}")
    print(f"mock check: {len(match) - sum(no_body.values())} matched pairs compared, "
          f"{len(mock_gaps)} with mocks missing in f2, test body not found: "
          f"f1 {no_body['f1']}, f2 {no_body['f2']}\n")

    if args.matches and matched:
        print("Matched pairs:")
        output(["Module", "f1 test", "Parsed", "How", "f2 test", "Score", "Flags"],
               sorted(matched), args.csv)
        print()
    if missing:
        print("In f1 but not in f2:")
        output(["Module", "File under test", "f1 test", "Parsed", "How", "State",
                "Score", "Closest f2 test", "f1 file"],
               sorted(missing, key=lambda r: tuple(map(str, r))), args.csv)
        print()
    if mock_gaps:
        print("Mocks in f1 but not in f2 (matched tests):")
        output(["Module", "f1 test", "f2 test", "#", "Missing mocks", "f2 file"],
               sorted(mock_gaps, key=lambda r: tuple(map(str, r))), args.csv)


if __name__ == "__main__":
    main()
