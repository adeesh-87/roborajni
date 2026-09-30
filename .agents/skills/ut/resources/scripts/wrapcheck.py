#!/usr/bin/env python3
"""wrapcheck.py REPO BUILD_DIR [--stubs DIR ...] [--link-cmd FILE ...] : consistency of --wrap stubs (the shared
__wrap_fn / __real_fn pattern) with the link flags and the compiled code. Each finding names the failure it prevents
(the IDs are the scenarios of experiments/change-impact/STUDY.md).

  flag without stub      --wrap=fn but no __wrap_fn definition           -> link error: undefined __wrap_fn   (W4)
  stub without flag      __wrap_fn defined but fn not wrapped           -> link error on __real_fn, or the stub never runs (W5)
  stale name             wrapped symbol defined in no object            -> the C++ signature changed: link error on __real_ (W2)
  inline / weak          wrapped symbol is weak (inline or template) in -> calls inside that object bypass the wrap
                         an object that also calls it                     silently (W3)
  unguarded C stub       __real_fn declared by hand, not __typeof__(fn) -> a changed C signature compiles, links and
                                                                          passes garbage (X1, X3)
Link flags come from the build dir's real link commands (build.ninja, **/link.txt), so flags built from CMake
variables are seen; --link-cmd adds a file holding a link command line (e.g. a make log)."""
import glob, os, re, subprocess, sys

SRC_EXT = ('.c', '.cc', '.cpp', '.cxx', '.h', '.hpp')


def link_units(build, extra):
    """[(label, text holding the --wrap flags, object files of that link)] from build.ninja link statements,
    **/link.txt (CMake Makefiles) and extra command files"""
    units = []
    nin = os.path.join(build, 'build.ninja')
    if os.path.exists(nin):
        text = open(nin, errors='replace').read()
        for m in re.finditer(r'^build ([^:\n]+): (\S*LINKER\S*) ([^\n|]*)[^\n]*\n((?:  .*\n)*)', text, re.M):
            body = m.group(4)
            if '--wrap' in body:
                objs = [os.path.join(build, o) for o in m.group(3).split() if o.endswith(('.o', '.obj'))]
                units.append((m.group(1).strip(), body, objs))
    for f in glob.glob(os.path.join(build, '**', 'link.txt'), recursive=True) + list(extra):
        try:
            text = open(f, errors='replace').read()
        except OSError:
            continue
        if '--wrap' in text:
            base = os.path.dirname(os.path.dirname(os.path.dirname(f))) if f.endswith('link.txt') else build
            objs = [o if os.path.isabs(o) else os.path.join(base, o) for o in text.split() if o.endswith(('.o', '.obj'))]
            units.append((os.path.relpath(f, build), text, objs))
    return units


def wrap_flags(units):
    names, where, objs = set(), {}, {}
    for label, text, o in units:
        for m in re.finditer(r'--wrap[=,]([A-Za-z_][A-Za-z0-9_]*)', text):
            names.add(m.group(1))
            where.setdefault(m.group(1), label)
            objs.setdefault(m.group(1), set()).update(o)
    return names, where, objs


def stubs(dirs, root):
    defs, reals, files = {}, {}, {}
    for d in dirs:
        for dp, dn, fn in os.walk(d):
            dn[:] = [x for x in dn if not x.startswith(('build', '.'))]
            for f in fn:
                if not f.endswith(SRC_EXT):
                    continue
                p = os.path.join(dp, f)
                text = open(p, errors='replace').read()
                rel = os.path.relpath(p, root)
                for m in re.finditer(r'\b__wrap_([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{]*\)\s*(?:const\s*)?\{', text):
                    defs.setdefault(m.group(1), rel)
                for m in re.finditer(r'\b__real_([A-Za-z_][A-Za-z0-9_]*)\b', text):
                    reals.setdefault(m.group(1), rel)
                if '__wrap_' in text or '__real_' in text:
                    files[rel] = text
    return defs, reals, files


def symbols(build, objs=None):
    """{symbol: [(object, type letter)]} over the given object files (default: every object of the build dir)"""
    objs = [o for o in objs if os.path.exists(o)] if objs else \
        glob.glob(os.path.join(build, '**', '*.o'), recursive=True) + glob.glob(os.path.join(build, '**', '*.obj'), recursive=True)
    out = {}
    for i in range(0, len(objs), 200):
        r = subprocess.run(['nm', '-A'] + objs[i:i + 200], capture_output=True, text=True)
        for l in r.stdout.splitlines():
            m = re.match(r'^(.*?):\s*(?:[0-9a-fA-F]+)?\s+([A-Za-z])\s+(\S+)$', l)
            if m:
                out.setdefault(m.group(3), []).append((os.path.relpath(m.group(1), build), m.group(2)))
    return out, len(objs)


def demangle(n):
    if not n.startswith('_Z'):
        return n
    r = subprocess.run(['c++filt', n], capture_output=True, text=True)
    return r.stdout.strip() or n


def main(a):
    if len(a) < 2:
        print(__doc__); sys.exit(2)
    root, build = os.path.abspath(a[0]), os.path.abspath(a[1])
    sdirs = [os.path.join(root, x) for i, x in enumerate(a) if i and a[i - 1] == '--stubs'] or [root]
    extra = [x for i, x in enumerate(a) if i and a[i - 1] == '--link-cmd']
    flags, fwhere, fobjs = wrap_flags(link_units(build, extra))
    defs, reals, sfiles = stubs(sdirs, root)
    syms, nobj = symbols(build)
    per_link = {}                               # the objects of the link that carries each flag (stale objects of other targets excluded)
    for n in flags:
        key = tuple(sorted(fobjs.get(n, ())))
        if key and key not in per_link:
            per_link[key] = symbols(build, list(key))[0]
    find = []
    for n in sorted(flags - set(defs)):
        find.append(('flag without stub', n, f'--wrap={n} in {fwhere[n]}, no __wrap_{n} definition: link error "undefined __wrap_{n}"'))
    for n in sorted(set(defs) - flags):
        how = f'calls __real_{n}: link error "undefined __real_{n}"' if n in reals else 'never runs (the real function is called)'
        find.append(('stub without flag', n, f'__wrap_{n} in {defs[n]} but no --wrap={n} in the link: {how}'))
    for n in sorted(flags):
        key = tuple(sorted(fobjs.get(n, ())))
        where = (per_link.get(key) or syms).get(n, [])
        defined = [(o, t) for o, t in where if t in 'TtWwVv']
        if not defined and nobj:
            find.append(('stale name', n, f'{demangle(n)}: wrapped, but no object of {os.path.relpath(build, root)} defines it '
                                          f'(renamed, or its C++ signature changed: the mangled name is old)'))
        weak = [o for o, t in defined if t in 'WwVv']
        callers = {o for o, t in where if t == 'U'}
        inline_bypass = [o for o in weak if o not in callers]
        if inline_bypass:
            find.append(('inline / weak', n, f'{demangle(n)} is weak (inline or template) in {", ".join(sorted(inline_bypass)[:3])}: '
                                             f'calls compiled in those objects bypass the wrap'))
    for n in sorted(reals):
        if n.startswith('_Z'):
            continue
        f = reals[n]
        text = sfiles.get(f, '')
        if re.search(r'__typeof__\s*\(\s*' + re.escape(n) + r'\s*\)', text) is None and re.search(r'\b__real_' + re.escape(n) + r'\s*\([^)]*\)\s*;', text):
            find.append(('unguarded C stub', n, f'{f}: __real_{n} declared by hand; declare it (and __wrap_{n}) with '
                                                f'`extern "C" __typeof__({n}) __real_{n}, __wrap_{n};` so a signature change fails to compile'))
    print(f'# wrapcheck: {len(flags)} wrapped symbols (link commands), {len(defs)} stubs, {nobj} objects scanned')
    for n in sorted(flags):
        print(f'- wrapped: {demangle(n)}' + (f'  (stub: {defs[n]})' if n in defs else ''))
    if not find:
        print('OK: flags, stubs and objects agree')
    for kind, n, msg in find:
        print(f'{kind.upper()}: {msg}')
    return 1 if any(k != 'unguarded C stub' for k, _, _ in find) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
