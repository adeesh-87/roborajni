#!/usr/bin/env python3
"""Compare Parasoft (f1) unit tests against CppUTest (f2) unit tests.

Usage:  compare_tests.py <parent>/parasoft <parent>/cpputest
   or:  compare_tests.py <parent> <parent>

f1 files: <f1>/testcases/<module>/.../UnitTest_<file>[_cpp].cpp
          <f1>/testcases_target/<module>/.../UnitTest_<file>[_cpp].cpp
          (only these two folders are scanned, any depth below <module>)
          tests: CPPTEST_TEST(...) / CPPTEST_TEST_DISABLED(...)
f2 files: <f2>/testcases/<module>/test_<file>.cpp
          tests: TEST(<group>, <name>)

1. File pairing: each f1 file is paired with the f2 file that has the same
   <module> folder and <file>. If there is none, the single f2 file with
   that <file> in any module is used (if exactly one exists).
2. Test matching, only within a file pair:
   * f1 name: <module>_..._<MARKER>_<test_name>, marker = first of
     INTRF/CC/BV/EQ, else the first short ALL-CAPS part (e.g. PP), else
     <module>_x_x_x_<test_name> is assumed
   * names are split into lower-case words (on "_", camelCase, digits),
     weighted by how rare they are; score = weighted share of the f1
     test-name words found in the f2 name; covered if >= --threshold
   * numeric names (EQ_3): the number must be a separate word in the f2 name
   * one-to-one: each f2 test covers at most one f1 test
3. Mocks (matched pairs): functions mocked in f1 but not in f2.
   f1: CPPTEST_REGISTER_CALLBACK(<func>, ...) in the test, setUp() and
       same-file helpers they call
   f2: .expectOneCall("f") / .expectNCalls(n, "f") / .expectNoCall("f") in the
       TEST, its TEST_GROUP block (setup()) and same-file helpers
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
NOT_FOUND = "-- not found --"

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


# ---------------------------------------------------------------- C++ parsing

def read(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    return COMMENT_RE.sub("", text)


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
        end = match_close(body, open_i, "(", ")")
        args, depth, last, i = [], 0, open_i + 1, open_i + 1
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


# ---------------------------------------------------------------- files

def resolve_root(root, sub, subdirs):
    """Accept either <parent>/<sub> or <parent> itself."""
    if any((root / d).is_dir() for d in subdirs):
        return root
    if any((root / sub / d).is_dir() for d in subdirs):
        return root / sub
    sys.exit(f"error: none of {', '.join(subdirs)} found in {root} or {root / sub}")


def source_files(root, subdirs, prefix):
    """Yield (path, module, file_under_test); module = first folder below subdir."""
    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob(f"{prefix}*.cpp")):
            rel = path.relative_to(base).parts
            module = rel[0] if len(rel) > 1 else ""
            fut = path.stem[len(prefix):]
            if fut.lower().endswith("_cpp"):
                fut = fut[:-4]
            yield path, module, fut


def tokens(s):
    return [t.lower() for t in TOKEN_RE.findall(s)]


class F1Test:
    def __init__(self, full, disabled, path):
        self.full, self.disabled, self.path = full, disabled, path
        parts = [p for p in full.split("_") if p]
        rest = parts[1:]  # parts[0] is the module
        idx = next((i for i, p in enumerate(rest) if p.upper() in KNOWN_MARKERS), None)
        if idx is None:
            idx = next((i for i, p in enumerate(rest) if GUESS_MARKER_RE.match(p)), None)
        if idx is None:
            idx = 2 if len(rest) >= 4 else -1
        self.name = "_".join(rest[idx + 1:])
        self.name_tok, self.ctx_tok = tokens(self.name), tokens("_".join(rest[:idx + 1]))
        if not self.name_tok:  # nothing after the marker: use the context
            self.name_tok, self.ctx_tok = self.ctx_tok, []
        self.numeric = bool(self.name_tok) and all(t.isdigit() for t in self.name_tok)
        self.mocks = None


class F2Test:
    def __init__(self, group, name, path):
        self.group, self.name, self.path = group, name, path
        tok = tokens(name)
        self.tokset, self.joined = set(tok), "".join(tok)
        self.mocks = None

    def has(self, t):
        # exact word, or a longer word glued inside another (e.g. "checksvalue")
        return t in self.tokset or (not t.isdigit() and len(t) >= 4 and t in self.joined)


def collect_f1(root, mock_arg):
    files = []  # (path, module, fut, [F1Test])
    for path, module, fut in source_files(root, F1_DIRS, "UnitTest_"):
        text = read(path)
        src = SourceFile(text, f1_mocks, mock_arg)
        tests = []
        for m in F1_RE.finditer(text):
            t = F1Test(m.group(2), bool(m.group(1)), path)
            t.mocks = src.f1_test_mocks(t.full)
            tests.append(t)
        files.append((path, module, fut, tests))
    return files


def collect_f2(root):
    files = {}  # path -> (module, fut, [F2Test])
    for path, module, fut in source_files(root, F2_DIRS, "test_"):
        text = read(path)
        src = SourceFile(text, f2_mocks)
        tests = []
        for m in F2_RE.finditer(text):
            t = F2Test(m.group(1), m.group(2), path)
            t.mocks = src.f2_test_mocks(t.group, t.name)
            tests.append(t)
        files[path] = (module, fut, tests)
    return files


def pair_files(f1_files, f2_files):
    by_key, by_fut = {}, defaultdict(list)
    for path, (module, fut, _) in f2_files.items():
        by_key[(module.lower(), fut.lower())] = path
        by_fut[fut.lower()].append(path)
    pairs = {}
    for path, module, fut, _ in f1_files:
        f2 = by_key.get((module.lower(), fut.lower()))
        if f2 is None and len(by_fut[fut.lower()]) == 1:
            f2 = by_fut[fut.lower()][0]
        pairs[path] = f2
    return pairs


# ---------------------------------------------------------------- matching

def make_weight(f2_tests):
    df = Counter(t for f in f2_tests for t in f.tokset)
    n = len(f2_tests)
    return lambda t: math.log((n + 1) / (df[t] + 1)) + 1


def coverage(toks, f2, w):
    total = sum(w(t) for t in toks)
    return sum(w(t) for t in toks if f2.has(t)) / total if total else 0.0


def score(f1, f2, w):
    """(main, context) - compared as a tuple, higher is better."""
    if f1.numeric:
        main = 1.0 if all(t in f2.tokset for t in f1.name_tok) else 0.0
    else:
        main = coverage(f1.name_tok, f2, w)
    return (main, coverage(f1.ctx_tok, f2, w))


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


def match_tests(f1_tests, f2_tests, w, threshold, unique):
    """Return {f1.full: (F2Test, score)} for one f2 file. Identical f1 names
    (e.g. same test in testcases and testcases_target) share one match."""
    by_name = {}
    for t in f1_tests:
        by_name.setdefault(t.full, t)
    edges, best = {}, {}
    for name, f1 in by_name.items():
        scored = sorted(((score(f1, c, w), i, c) for i, c in enumerate(f2_tests)),
                        key=lambda x: (x[0], -x[1]), reverse=True)
        best[name] = scored[0][0] if scored else (0, 0)
        edges[name] = [c for s, _, c in scored if s[0] >= threshold and s[0] > 0]
    if unique:
        # strong text matches first, numeric-only names last
        order = sorted(edges, key=lambda n: (not by_name[n].numeric, best[n]), reverse=True)
        match = max_matching(order, edges)
    else:
        match = {n: e[0] for n, e in edges.items() if e}
    return {n: (f2, score(by_name[n], f2, w)[0]) for n, f2 in match.items()}


# ---------------------------------------------------------------- output

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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("f1", type=Path, help="<parent>/parasoft (or <parent>)")
    ap.add_argument("f2", type=Path, help="<parent>/cpputest (or <parent>)")
    ap.add_argument("--missing-only", action="store_true",
                    help="only list f1 tests with no f2 match or with missing mocks")
    ap.add_argument("--threshold", type=float, default=0.8,
                    help="min share (0-1) of f1 test-name words found in the f2 name "
                         "(default 0.8)")
    ap.add_argument("--no-unique", action="store_true",
                    help="let one f2 test cover several f1 tests")
    ap.add_argument("--f1-mock-arg", type=int, default=1,
                    help="which CPPTEST_REGISTER_CALLBACK argument (1-based) names "
                         "the mocked function (default 1)")
    ap.add_argument("--csv", action="store_true", help="one CSV table instead")
    args = ap.parse_args()

    f1_root = resolve_root(args.f1, "parasoft", F1_DIRS)
    f2_root = resolve_root(args.f2, "cpputest", F2_DIRS)
    f1_files = collect_f1(f1_root, args.f1_mock_arg - 1)
    f2_files = collect_f2(f2_root)
    pairs = pair_files(f1_files, f2_files)
    w = make_weight([t for _, _, ts in f2_files.values() for t in ts])

    # match per f2 file, pooling every f1 file paired with it
    f1_by_f2 = defaultdict(list)
    for path, _, _, tests in f1_files:
        if pairs[path] is not None:
            f1_by_f2[pairs[path]] += tests
    matches = {}
    for f2_path, f1_tests in f1_by_f2.items():
        matches[f2_path] = match_tests(f1_tests, f2_files[f2_path][2], w,
                                       args.threshold, not args.no_unique)

    stats = Counter()
    report = []  # (f1 file, f2 file, rows)
    for path, _, _, tests in f1_files:
        f2_path = pairs[path]
        found = matches.get(f2_path, {})
        rows = []
        for t in tests:
            stats["f1 tests"] += 1
            label = t.full + ("  [disabled]" if t.disabled else "")
            if t.full not in found:
                stats["not found"] += 1
                rows.append((label, NOT_FOUND, ""))
                continue
            f2, s = found[t.full]
            stats["matched"] += 1
            f2_label = f2.name + ("" if s >= 1 else f"  (~{s:.0%})")
            if t.mocks is None or f2.mocks is None:
                gap = "? (test body not found)"
            else:
                gap = ", ".join(sorted(t.mocks - f2.mocks))
                stats["mock gaps"] += bool(gap)
            if not args.missing_only or gap:
                rows.append((label, f2_label, gap))
        if f2_path is None:
            stats["f1 files without f2 file"] += 1
        if rows or not args.missing_only:
            report.append((path.relative_to(f1_root),
                           f2_path.relative_to(f2_root) if f2_path else NOT_FOUND, rows))

    headers = ["f1 test", "f2 match", "mocks missing in f2"]
    if args.csv:
        out = csv.writer(sys.stdout)
        out.writerow(["f1 file", "f2 file"] + headers)
        for f1_file, f2_file, rows in report:
            out.writerows([str(f1_file), str(f2_file), *r] for r in rows)
        return

    for f1_file, f2_file, rows in report:
        print(f"f1 file: {f1_file}")
        print(f"f2 file: {f2_file}")
        if rows:
            print_table(headers, rows)
        else:
            print("(no tests)")
        print()
    print(f"f1: {len(f1_files)} files, {stats['f1 tests']} tests   "
          f"f2: {len(f2_files)} files, "
          f"{sum(len(ts) for _, _, ts in f2_files.values())} tests")
    print(f"f1 files without f2 file: {stats['f1 files without f2 file']}   "
          f"tests matched: {stats['matched']}   not found: {stats['not found']}   "
          f"matched with missing mocks: {stats['mock gaps']}")


if __name__ == "__main__":
    main()
