#!/usr/bin/env python3
"""hazards.py REPO --code DIR... --tests DIR... : places where a code change breaks tests silently or confusingly, found
by text scan (scenario IDs are rows of resources/change-impact.md). Prints Markdown for KB notes.md
"Change hazards"; every line has file:line so a later task can check it after a change.

  test source list   the test build lists production sources itself: a new source file links in the app, not in the tests (H3)
  count-sized table  an array/std::array sized by a count constant with an initializer list: grow the count, the new
                     entries are zero/nullptr (T6: crashed report())
  positional init    tests build structs with positional {a, b, c}: reordering same-typed fields compiles and fails confusingly (T3)
  literal constants  tests write a constant's value instead of its name: changing the constant fails tests that
                     reference analysis cannot find (T9)
  interface fakes    test classes deriving from production interfaces: every pure virtual change breaks them (V1, V3-V5)
"""
import os, re, sys

EXT = ('.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.hh')


def files(root, dirs, ext=EXT):
    for d in dirs:
        for dp, dn, fn in os.walk(os.path.join(root, d)):
            dn[:] = [x for x in dn if not x.startswith(('build', '.', '_deps'))]
            for f in fn:
                if f.endswith(ext):
                    yield os.path.join(dp, f)


def rel(root, p):
    return os.path.relpath(p, root)


def main(a):
    if len(a) < 1 or '--code' not in a or '--tests' not in a:
        print(__doc__); sys.exit(2)
    root = os.path.abspath(a[0])
    def opt(name):
        i = a.index(name) + 1
        out = []
        while i < len(a) and not a[i].startswith('--'):
            out.append(a[i]); i += 1
        return out
    code, tests = opt('--code'), opt('--tests')
    code_files = list(files(root, code))
    test_files = list(files(root, tests))
    out = ['## Change hazards (hazards.py, text scan)']

    # 1. test build lists production sources explicitly
    lists = []
    for bf in [p for d in tests + ['.'] for p in [os.path.join(root, d, 'CMakeLists.txt'), os.path.join(root, d, 'Makefile')] if os.path.exists(p)]:
        t = open(bf, errors='replace').read()
        srcs = set(re.findall(r'([\w./${}-]+\.(?:c|cc|cpp|cxx))\b', t))
        prod = {s for s in srcs if any(('/' + c.strip('/') + '/') in ('/' + s.replace('${CMAKE_SOURCE_DIR}/', '').replace('../', '')) for c in code)}
        globbed = re.search(r'GLOB|wildcard', t)
        if prod and not globbed:
            lists.append(f'- test source list: {rel(root, bf)} lists {len(prod)} production sources by name: a new production '
                         f'source file must be added there, or the test link fails (H3)')
    out += lists or ['- test source list: none found (the test build globs, or links a library)']

    # 2. tables sized by a count constant, initialised with a list
    tables = []
    for p in code_files:
        for n, line in enumerate(open(p, errors='replace'), 1):
            m = re.search(r'std::array<[^;>]*,\s*([A-Za-z_]\w*)\s*>\s*(\w+)\s*=\s*\{', line) or \
                re.search(r'\b(\w+)\s*\[\s*([A-Za-z_]\w*)\s*\]\s*=\s*\{', line)
            if m:
                size = m.group(1) if 'std::array' in line else m.group(2)
                if not size.isdigit():
                    tables.append(f'- count-sized table: {rel(root, p)}:{n} sized by `{size}`: when `{size}` grows, add the new entries (T6)')
    out += tables[:20] or ['- count-sized table: none found']

    # 3. positional aggregate init of project structs in tests
    structs = set()
    for p in code_files:
        structs |= set(re.findall(r'\bstruct\s+([A-Z]\w*)\s*\{', open(p, errors='replace').read()))
    pos = {}
    for p in test_files:
        for n, line in enumerate(open(p, errors='replace'), 1):
            for m in re.finditer(r'\b(?:\w+::)*([A-Z]\w*)\s+\w+\s*\{\s*([^{}]*,[^{}]*)\}', line):
                if m.group(1) in structs and not re.search(r'(^|,)\s*\.\w+\s*=', m.group(2)):
                    pos.setdefault(m.group(1), []).append(f'{rel(root, p)}:{n}')
    for s_, where in sorted(pos.items(), key=lambda kv: -len(kv[1])):
        out.append(f'- positional init: `{s_}` built with positional {{...}} in {len(where)} place(s), e.g. {where[0]}: a field '
                   f'reorder of the same type compiles and fails confusingly (T3); designated initialisers avoid it')
    if not pos:
        out.append('- positional init: none found')

    # 4. constants whose value the tests hard-code
    consts = {}
    for p in code_files:
        for n, line in enumerate(open(p, errors='replace'), 1):
            m = re.search(r'\bconstexpr\s+[\w:]+\s+(\w+)\s*=\s*(\d+)[uUlL]*\s*;', line) or \
                re.search(r'^\s*#\s*define\s+(\w+)\s+\(?(\d+)[uUlL]*\)?\s*$', line)
            if m and int(m.group(2)) >= 3:
                consts.setdefault(m.group(1), (int(m.group(2)), f'{rel(root, p)}:{n}'))
    ttext = {p: open(p, errors='replace').read() for p in test_files}
    lit = []
    for name, (val, where) in consts.items():
        by_name = sum(len(re.findall(r'\b' + re.escape(name) + r'\b', t)) for t in ttext.values())
        by_val = sum(len(re.findall(r'(?<![\w.])' + str(val) + r'(?![\w.])', t)) for t in ttext.values())
        if val < 16 and by_name == 0:           # small numbers are everywhere; only when the tests also use the name
            continue
        if by_val >= 3 and by_val > by_name:
            lit.append((by_val, f'- literal constant: `{name}` = {val} ({where}): tests write {val} {by_val} time(s), the name '
                                f'{by_name} time(s); a change of `{name}` fails tests no reference search finds (T9). Check which {val}s mean `{name}`'))
    out += [l for _, l in sorted(lit, reverse=True)[:12]] or ['- literal constant: none found']

    # 5. test classes deriving from production classes (fakes of interfaces)
    prod_classes = set()
    for p in code_files:
        prod_classes |= set(re.findall(r'\b(?:class|struct)\s+(\w+)\s*(?:final\s*)?[:{]', open(p, errors='replace').read()))
    fakes = []
    for p in test_files:
        for n, line in enumerate(open(p, errors='replace'), 1):
            for m in re.finditer(r'\b(?:class|struct)\s+(\w+)\s*(?:final\s*)?:\s*public\s+(?:[\w]+::)*(\w+)', line):
                if m.group(2) in prod_classes:
                    fakes.append(f'- interface fake: {rel(root, p)}:{n} `{m.group(1)}` implements `{m.group(2)}`: a pure virtual change '
                                 f'breaks it (V1, V3-V5); one shared fake per interface keeps the fix in one place')
    out += fakes[:30] or ['- interface fake: none found']
    print('\n'.join(out))


if __name__ == '__main__':
    main(sys.argv[1:])
