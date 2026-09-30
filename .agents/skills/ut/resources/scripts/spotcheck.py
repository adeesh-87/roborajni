#!/usr/bin/env python3
"""spotcheck.py KB_DIR REPO NAME [NAME...] : does the code index know every caller of these functions?
Compares, per function, the call sites the index has (production callers and TEST blocks) with the lines that look
like calls in the code and test paths of the KB profile (a text search: `name(` not preceded by a definition).
Prints one line per function for KB notes.md `## Index spot-check`; a large gap means the index misses callers
(in C++ typically calls on objects of a class whose method name also exists in another class)."""
import json, os, re, subprocess, sys


def main(a):
    if len(a) < 3:
        print(__doc__); sys.exit(2)
    kb, repo, names = a[0], os.path.abspath(a[1]), a[2:]
    ix = json.load(open(os.path.join(kb, 'index', 'index.json')))
    prof = json.load(open(os.path.join(kb, 'kb.json'))).get('profile', {})
    paths = [p for k in ('code_paths', 'header_paths', 'test_paths', 'mock_paths') for p in prof.get(k, [])]
    pre = os.path.relpath(repo, ix['meta']['root'])
    pre = '' if pre == '.' else pre + '/'
    for name in names:
        ids = [i for i, f in ix['functions'].items() if f['name'] == name and f['kind'] == 'function']
        if not ids:
            print(f'- {name}: not in the index'); continue
        sites = {(c['file'], c['line']) for c in ix['calls'] if c['to'] in ids}
        prod = {s for s in sites if not any(s[0].startswith(pre + t) for t in prof.get('test_paths', []))}
        short = name.split('::')[-1]
        r = subprocess.run(['grep', '-rnE', r'(\.|->|::|\b)' + re.escape(short) + r'\s*\(', '--include=*.c', '--include=*.cc',
                            '--include=*.cpp', '--include=*.h', '--include=*.hpp'] + [p for p in paths if os.path.exists(os.path.join(repo, p))],
                           cwd=repo, capture_output=True, text=True)
        lines = []
        for l in r.stdout.splitlines():
            f, ln, text = l.split(':', 2)
            if re.search(r'^\s*(?:[\w:<>*&\s]+\s)?(?:\w+::)*' + re.escape(short) + r'\s*\([^;]*\)\s*(?:const\s*)?(?:override\s*)?\{?\s*$', text):
                continue                      # a definition or declaration line
            if re.match(r'^\s*(//|\*)', text):
                continue
            lines.append((f, int(ln)))
        units = {}                                   # enclosing function / TEST of each text hit (index line ranges)
        for i, f in ix['functions'].items():
            units.setdefault(f['file'], []).append((f['line'], f.get('end') or f['line'], i))
        found = set()
        for f, ln in lines:
            enc = [u for u in units.get(pre + f, []) if u[0] <= ln <= u[1]]
            if enc:
                found.add(min(enc, key=lambda u: u[1] - u[0])[2])
        callers = {c['from'] for c in ix['calls'] if c['to'] in ids}
        extra = sorted(found - callers - set(ids))
        is_test = lambda i: ix['functions'][i]['kind'] == 'test'
        verdict = 'OK' if len(extra) <= 2 else ('INDEX MAY MISS CALLERS: read these (some can be same-named methods of '
                                                'another class): ' + ', '.join(ix['functions'][i]['name'][:60] for i in extra[:3]))
        print(f"- {name}: index callers {len(callers)} ({sum(1 for c in callers if is_test(c))} TESTs); text search finds "
              f"{len(extra)} more ({sum(1 for c in extra if is_test(c))} TESTs) -> {verdict}")


if __name__ == '__main__':
    main(sys.argv[1:])
