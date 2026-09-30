"""trace INDEX_JSON --run "CMD" [--cmake SRC_DIR --build-dir DIR [--cmake-args "..."] [--target T] | --build "CMD {cflags} {ldflags}"]
                  [--out DIR] [--max N] [--threads main|all]
Dynamic sequence diagrams: build the TEST binary with -finstrument-functions plus a tiny recorder (ut_trace.c), run
one test (or all), turn the recorded addresses into functions (addr2line) and write one Mermaid sequence per TEST
block: what the test REALLY called, in order, including virtual dispatch and callbacks (no guessing).
  --cmake      configure + build a separate build tree with the trace flags (your normal build is untouched)
  --build      your own build command; {cflags} and {ldflags} are replaced by the trace flags
  (neither)    the binary is already built with the flags printed by: trace INDEX --flags
  --run        the test command, e.g. "{build}/tests/unit_tests -sg Dispatcher" ({build} = --build-dir)
Output: <out>/<Group>.<Test>.md (default KB_DIR/diagrams/traces, or <index dir>/diagrams/traces outside a KB), <index dir>/traces.json (functions each test reached).
Linux + glibc; binutils addr2line. A crashing test loses the unflushed part of the trace."""
import json, os, re, shlex, subprocess, sys
from .model import Index, is_testside
from . import mermaid as M

HERE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE = '/usr/,/opt/,CppUTest,cpputest,gtest,gmock,googletest,unity,cmock,catch2,doctest'


def flags(work):
    obj = os.path.join(work, 'ut_trace.o')
    cflags = f'-finstrument-functions -finstrument-functions-exclude-file-list={EXCLUDE} -O0 -g -fno-inline'
    return cflags, obj


def compile_runtime(work):
    os.makedirs(work, exist_ok=True)
    obj = os.path.join(work, 'ut_trace.o')
    cc = os.environ.get('CC') or 'cc'
    r = subprocess.run([cc, '-O2', '-c', os.path.join(HERE, 'ut_trace.c'), '-o', obj], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('trace: cannot compile the recorder: ' + r.stderr[-400:])
    return obj


def sh(cmd, cwd=None, env=None):
    r = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True, errors='replace')
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def elf_is_exec(path):
    try:
        with open(path, 'rb') as f:
            h = f.read(18)
        return h[:4] == b'\x7fELF' and int.from_bytes(h[16:18], 'little') == 2
    except OSError:
        return False


def parse_trace(path):
    maps, events = [], []
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if line.startswith('M '):
                p = line[2:].split()
                if len(p) >= 6:
                    a, b = p[0].split('-')
                    maps.append((int(a, 16), int(b, 16), int(p[2], 16), ' '.join(p[5:])))
            elif line.startswith('E '):
                p = line.split()
                if len(p) == 4:
                    events.append(('E', int(p[1], 16), int(p[2], 16), p[3]))
            elif line.startswith('X '):
                p = line.split()
                if len(p) == 3:
                    events.append(('X', int(p[1], 16), 0, p[2]))
    return maps, events


def resolver(maps):
    bases = {}
    for s, e, off, path in maps:
        if off == 0 and (path not in bases or s < bases[path]):
            bases[path] = s

    def where(addr):
        for s, e, off, path in maps:
            if s <= addr < e and path.startswith('/'):
                return path, (addr if elf_is_exec(path) else addr - bases.get(path, s))
        return None, None
    return where


def addr2line(module, addrs):
    out = {}
    addrs = sorted(set(addrs))
    for k in range(0, len(addrs), 2000):
        chunk = addrs[k:k + 2000]
        r = subprocess.run(['addr2line', '-f', '-C', '-e', module] + [hex(a) for a in chunk], capture_output=True, text=True, errors='replace')
        lines = r.stdout.splitlines()
        for i, a in enumerate(chunk):
            fn = lines[2 * i] if 2 * i < len(lines) else '??'
            loc = lines[2 * i + 1] if 2 * i + 1 < len(lines) else '??:0'
            m = re.match(r'^(.*):(\d+)', loc)
            out[a] = (fn, m.group(1) if m else None, int(m.group(2)) if m else 0)
    return out


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); sys.exit(2)
    ix = Index.load(a[0])
    idx_dir = os.path.dirname(os.path.abspath(a[0]))
    work = os.path.join(idx_dir, 'trace')

    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d
    cflags, obj = flags(work)
    if '--flags' in a:
        compile_runtime(work)
        print(f'CFLAGS/CXXFLAGS: {cflags}\nlink the test binary with: {obj}')
        return
    run = opt('--run')
    if not run:
        sys.exit('trace: --run "test command" is required')
    compile_runtime(work)
    build_dir = opt('--build-dir', os.path.join(work, 'build'))
    if opt('--cmake'):
        src = opt('--cmake')
        cfg = (f"cmake -S {shlex.quote(src)} -B {shlex.quote(build_dir)} {opt('--cmake-args', '')} "
               f"-DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS={shlex.quote(cflags)} -DCMAKE_CXX_FLAGS={shlex.quote(cflags)} "
               f"-DCMAKE_EXE_LINKER_FLAGS={shlex.quote(obj)}")
        rc, out = sh(cfg)
        if rc == 0:
            rc, out = sh(f"cmake --build {shlex.quote(build_dir)} -j" + (f" --target {opt('--target')}" if opt('--target') else ''))
        if rc != 0:
            sys.exit('trace: instrumented build FAILED:\n' + out[-1500:])
    elif opt('--build'):
        rc, out = sh(opt('--build').replace('{cflags}', cflags).replace('{ldflags}', obj))
        if rc != 0:
            sys.exit('trace: instrumented build FAILED:\n' + out[-1500:])
    tfile = os.path.join(work, 'trace.txt')
    if os.path.exists(tfile):
        os.remove(tfile)
    env = dict(os.environ, UT_TRACE_FILE=tfile)
    rc, out = sh(run.replace('{build}', build_dir), env=env)
    if not os.path.exists(tfile):
        sys.exit('trace: no trace written. Is the binary built with the trace flags and linked with ' + obj + '?\n' + out[-800:])
    maps, events = parse_trace(tfile)
    kb_layout = os.path.basename(idx_dir) == 'index'      # KB_DIR/index -> KB_DIR/diagrams/traces
    out_dir = opt('--out', os.path.join(os.path.dirname(idx_dir) if kb_layout else idx_dir, 'diagrams', 'traces'))
    rows = render(ix, maps, events, out_dir, int(opt('--max', 80)), opt('--threads', 'main'), idx_dir)
    print(f"trace: {len(events)} events, {len(rows)} tests -> {out_dir} (test command exit {rc})")


def render(ix, maps, events, out_dir, max_msgs, threads, idx_dir):
    where = resolver(maps)
    by_mod = {}
    for kind, fn, site, tid in events:
        for addr in ((fn, site - 1) if kind == 'E' else (fn,)):      # site-1: inside the call instruction, not after it
            mod, off = where(addr)
            if mod:
                by_mod.setdefault(mod, set()).add(off)
    names = {}
    for mod, offs in by_mod.items():
        for off, v in addr2line(mod, offs).items():
            names[(mod, off)] = v
    root = ix.meta['root']
    spans = {}
    for i, n in ix.functions.items():
        spans.setdefault(n['file'], []).append((n['line'], n['end'], i))

    def fid_of(addr):
        mod, off = where(addr)
        if not mod:
            return None, None
        fn, f, l = names.get((mod, off), ('??', None, 0))
        if not f or f == '??':
            return None, fn
        f = os.path.realpath(f)
        if not f.startswith(root + os.sep):
            return None, fn
        rel = os.path.relpath(f, root).replace(os.sep, '/')
        best = None
        for s, e, i in spans.get(rel, []):
            if s <= l <= e and (best is None or e - s < best[1] - best[0]):
                best = (s, e, i)
        return (best[2] if best else None), fn

    def site_line(addr):
        mod, off = where(addr)
        v = names.get((mod, off)) if mod else None
        return v[2] if v else 0
    # call trees per thread (unmapped frames are transparent: their children hang on the nearest mapped frame)
    main_tid = events[0][3] if events else None
    trees, stacks = {}, {}
    cache = {}
    for kind, fn, site, tid in events:
        if threads == 'main' and tid != main_tid:
            continue
        st = stacks.setdefault(tid, [{'fid': None, 'kids': [], 'line': 0}])
        if kind == 'E':
            if fn not in cache:
                cache[fn] = fid_of(fn)
            f, raw = cache[fn]
            node = {'fid': f, 'raw': raw, 'kids': [], 'line': site_line(site - 1) if f else 0}
            parent = next((x for x in reversed(st) if x['fid'] is not None or x is st[0]), st[0])
            if f is not None:
                parent['kids'].append(node)
            st.append(node)
        elif len(st) > 1:
            st.pop()
    for tid, st in stacks.items():
        trees[tid] = st[0]
    # split into tests: every mapped frame of a TEST node is one test; fixture frames go to the nearest test
    tests, by_test = [], {}

    def collect(node, pending):
        # a TEST shows up as several frames (registration at start-up, constructor, body, destructor): merge them;
        # fixture frames (setup/teardown of the TEST_GROUP) seen before a body belong to that test
        for k in node['kids']:
            n = ix.functions.get(k['fid'], {})
            if n.get('kind') == 'test':
                if not k['kids']:
                    continue
                t = by_test.get(k['fid'])
                if t is None:
                    t = by_test[k['fid']] = {'fid': k['fid'], 'node': {'fid': k['fid'], 'kids': []}, 'setup': []}
                    tests.append(t)
                t['setup'] += [x for x in pending if x['kids']]
                t['node']['kids'] += k['kids']
                pending.clear()
            elif n.get('kind') == 'fixture':
                pending.append(k)
            else:
                collect(k, pending)
    for tid, t in trees.items():
        collect(t, [])
    os.makedirs(out_dir, exist_ok=True)
    reach, rows = {}, []
    for t in tests:
        n = ix.functions[t['fid']]
        s = M.Seq(ix, 0, max_msgs)
        me = s.pid('test', f"{n['name']} ({n['file']}:{n['line']})")
        lines = []

        def sig(node):
            return (node['fid'], node.get('line'), tuple(sig(k) for k in visible(node['kids'])))

        def visible(kids):
            """drop the test objects' own frames (keep what they call) and empty destructors"""
            out = []
            for k in kids:
                n2 = ix.functions[k['fid']]
                if n2.get('kind') in ('test', 'fixture'):
                    out += visible(k['kids'])
                elif n2['name'].split('::')[-1].startswith('~') and not k['kids']:
                    continue
                else:
                    out.append(k)
            return out

        def walk(node, who, ind):
            kids = visible(node['kids'])
            i = 0
            while i < len(kids):
                w_, reps = 1, 1
                for w in (1, 2, 3):                        # repeated groups of 1-3 calls become one loop
                    r = 1
                    while i + (r + 1) * w <= len(kids) and [sig(x) for x in kids[i + r * w:i + (r + 1) * w]] == [sig(x) for x in kids[i:i + w]]:
                        r += 1
                    if r > 1 and r * w > reps * w_:
                        w_, reps = w, r
                if reps > 1:
                    lines.append('  ' * ind + f'loop {reps} times (same calls)')
                for k in kids[i:i + w_]:
                    key, lab = s.owner(k['fid'])
                    w2 = s.pid(key, lab)
                    reach.setdefault(n['name'], set()).add(k['fid'])      # ids: overloads stay apart
                    if s.msgs >= max_msgs:
                        s.cut += 1; continue
                    s.msgs += 1
                    lines.append('  ' * (ind + (reps > 1)) + f"{who}->>{w2}: L{k['line']} {M.esc(ix.functions[k['fid']]['name'], 60)}()")
                    walk(k, w2, ind + 1 + (reps > 1))
                if reps > 1:
                    lines.append('  ' * ind + 'end')
                i += w_ * reps

        for fx in t['setup']:
            walk({'kids': [fx]}, me, 1)
        walk(t['node'], me, 1)
        if s.cut:
            lines.append(f'  Note over {me}: ... {s.cut} more calls not shown (limit {max_msgs})')
        head = [f"%% Runtime sequence of {n['name']}  {n['file']}:{n['line']}  (recorded by index.sh trace; only code in the index is shown)",
                '%% Lnn = line of the call site. Every arrow happened in this run, in this order; loops are repeated identical calls.',
                'sequenceDiagram']
        for key, (pid, lab) in s.parts.items():
            head.append(f'  participant {pid} as {M.esc(lab, 140)}')
        fname = M.slug(re.sub(r'^\w+\((.*)\)$', r'\1', n['name']).replace(', ', '.')) + '.md'
        open(os.path.join(out_dir, fname), 'w', encoding='utf-8').write('\n'.join(head + lines) + '\n')
        rows.append((n['name'], fname, s.msgs))
    json.dump({k: sorted(v) for k, v in reach.items()}, open(os.path.join(idx_dir, 'traces.json'), 'w', encoding='utf-8'), indent=1)
    L = ['# Runtime traces (Mermaid sequence text)', '| Test | Messages | File |', '|---|---|---|']
    L += [f'| {a} | {c} | {b} |' for a, b, c in rows]
    open(os.path.join(out_dir, 'INDEX.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return rows
