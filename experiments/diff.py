#!/usr/bin/env python3
"""Report CPPTEST tests present under f1 but missing from f2's gtest TESTs.

f1: <f1>/{testcases,testcases_target}/**/UnitTest_<file>[_cpp].cpp
    CPPTEST_TEST(<module>_..._{INTRF|BV|CC}_<test_name>)  (also CPPTEST_TEST_DISABLED)
    test_name is everything after the first _INTRF_ / _BV_ / _CC_ marker.
f2: <f2>/testcases/**/test_<file>.cpp
    TEST(<module>, <anything containing test_name>)

A f1 test is "covered" if some f2 TEST has the same module and its name
contains the f1 test_name as a substring.
"""
import argparse
import re
import sys
from pathlib import Path

F1_DIRS = ("testcases", "testcases_target")
F2_DIRS = ("testcases",)

COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
F1_RE = re.compile(r"\bCPPTEST_TEST(_DISABLED)?\s*\(\s*([^,)\s]+)")
NAME_RE = re.compile(r"^([^_]+)_(?:.*?_)?(?:INTRF|BV|CC)_(.+)$")
F2_RE = re.compile(r"(?<![A-Za-z0-9_])TEST\s*\(\s*([^,\s)]+)\s*,\s*([^,)\s]+)")


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


def collect_f1(root):
    out = []  # (file_under_test, module, test_name, disabled, full_name, path)
    for path in files(root, F1_DIRS, "UnitTest_"):
        fut = file_under_test(path, "UnitTest_")
        for m in F1_RE.finditer(read(path)):
            full = m.group(2)
            nm = NAME_RE.match(full)
            if not nm:
                print(f"warning: {path}: '{full}' doesn't match "
                      "<module>_..._{INTRF|BV|CC}_<test_name>", file=sys.stderr)
                continue
            out.append((fut, nm.group(1), nm.group(2), bool(m.group(1)), full, path))
    return out


def collect_f2(root):
    out = []  # (file_under_test, module, test_name)
    for path in files(root, F2_DIRS, "test_"):
        fut = file_under_test(path, "test_")
        for m in F2_RE.finditer(read(path)):
            out.append((fut, m.group(1), m.group(2)))
    return out


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
    ap.add_argument("f1", type=Path)
    ap.add_argument("f2", type=Path)
    ap.add_argument("--same-file", action="store_true",
                    help="only match f2 tests from the same <file_under_test>")
    ap.add_argument("--csv", action="store_true", help="CSV output instead of table")
    args = ap.parse_args()

    for d in (args.f1, args.f2):
        if not d.is_dir():
            sys.exit(f"error: {d} is not a directory")

    t1 = collect_f1(args.f1)
    t2 = collect_f2(args.f2)

    by_module = {}
    for fut, module, name in t2:
        by_module.setdefault(module, []).append((fut, name))

    missing = []
    for fut, module, name, disabled, full, path in t1:
        cands = by_module.get(module, [])
        if args.same_file:
            cands = [c for c in cands if c[0] == fut]
        if not any(name in n for _, n in cands):
            missing.append((module, fut, name, "DISABLED" if disabled else "enabled",
                            path.relative_to(args.f1)))

    missing.sort(key=lambda r: (r[0], r[1], r[2]))
    print(f"f1 tests: {len(t1)}   f2 tests: {len(t2)}   in f1 but not f2: {len(missing)}\n")
    if not missing:
        return
    headers = ["Module", "File under test", "Test name", "State", "f1 file"]
    if args.csv:
        import csv
        w = csv.writer(sys.stdout)
        w.writerow(headers)
        w.writerows(missing)
    else:
        print_table(headers, missing)


if __name__ == "__main__":
    main()
