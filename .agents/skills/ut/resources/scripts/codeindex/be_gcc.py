"""GCC backend: the project's OWN compiler (also a cross gcc such as arm-none-eabi-gcc >= 10) writes the call graph
(-fcallgraph-info): exact call edges with call-site lines for everything it compiles, plus stack usage per function.
GCC gives no branches, so functions, outlines, virtual/pointer call targets and TEST blocks come from tree-sitter on
the preprocessed mirror (active #if code only). Indirect calls (__indirect_call) are named from the outline."""
import json, os, re, shlex, shutil, subprocess, tempfile
import graphify_ut as G
from .model import Index, fid, norm, is_testside, test_label, FRAMEWORK, TEST_LINE
from . import tsoutline as TS

NODE = re.compile(r'^node:\s*\{\s*title:\s*"((?:[^"\\]|\\.)*)"\s*label:\s*"((?:[^"\\]|\\.)*)"(.*)\}\s*$')
EDGE = re.compile(r'^edge:\s*\{\s*sourcename:\s*"((?:[^"\\]|\\.)*)"\s*targetname:\s*"((?:[^"\\]|\\.)*)"(?:\s*label:\s*"((?:[^"\\]|\\.)*)")?')
DROP_FLAGS = ('-c', '-MD', '-MMD', '-MP', '-M', '-MM', '--coverage', '-flto', '-g', '-g3', '-ggdb')


def compile_cmd(e, src, obj):
    args = e.get('arguments') or shlex.split(e['command'], posix=(os.name != 'nt'))
    while args and os.path.basename(args[0]).lower() in ('ccache', 'sccache', 'distcc', 'icecc'):
        args = args[1:]
    out, skip = [args[0]], False
    for a in args[1:]:
        if skip:
            skip = False; continue
        if a in ('-o', '-MF', '-MT', '-MQ'):
            skip = True; continue
        if a in DROP_FLAGS or re.match(r'^-O[0-9sgzfast]*$', a) or a.startswith(('-Wp,-M', '-o', '-fprofile', '-ftest-coverage',
                                                                                   '-fcallgraph-info', '-fstack-usage', '-Werror')):
            continue
        if os.path.realpath(os.path.join(e['directory'], a)) == src:
            continue
        out.append(a)
    # -O0: no inlining, so every call in the source stays a call in the graph
    return out + ['-O0', '-fcallgraph-info=su', '-c', src, '-o', obj]


def unescape(s):
    return s.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')


def parse_ci(path):
    nodes, edges = {}, []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = NODE.match(line.strip())
        if m:
            lab = unescape(m.group(2)).split('\n')
            loc = re.match(r'^(.*):(\d+):(\d+)$', lab[1]) if len(lab) > 1 else None
            nodes[m.group(1)] = {'sig': lab[0], 'file': loc.group(1) if loc else None, 'line': int(loc.group(2)) if loc else None,
                                 'defined': 'ellipse' not in m.group(3), 'stack': lab[2] if len(lab) > 2 else ''}
            continue
        m = EDGE.match(line.strip())
        if m:
            loc = re.match(r'^(.*):(\d+):(\d+)$', unescape(m.group(3) or ''))
            edges.append((m.group(1), m.group(2), loc.group(1) if loc else None, int(loc.group(2)) if loc else None))
    return nodes, edges


def split_sig(sig):
    """'const X* ns::Cls<int>::find(int) const' -> ['ns', 'Cls', 'find']"""
    s = re.sub(r'\s*\[with .*\]$', '', sig.strip())
    depth, cut = 0, None
    for i in range(len(s) - 1, -1, -1):          # the parameter list is the last top-level (...)
        if s[i] == ')':
            depth += 1
        elif s[i] == '(':
            depth -= 1
            if depth == 0:
                cut = i
                break
    head = s[:cut] if cut is not None else s
    if head.endswith('operator()'):
        head = head[:-2]
    flat, depth = '', 0                           # drop template arguments
    for ch in head:
        if ch == '<' and not flat.endswith('operator'):
            depth += 1; continue
        if ch == '>' and depth:
            depth -= 1; continue
        if depth == 0:
            flat += ch
    q = flat.split(' ')[-1] if ' ' in flat.strip() else flat.strip()
    q = q.lstrip('*&')
    return [c for c in q.split('::') if c]


def build(out_path, cdb_path, paths):
    root = G.repo_root(paths)
    scope = [os.path.realpath(p) for p in paths]
    ents = {}
    for e in json.load(open(cdb_path, encoding='utf-8')):
        ents.setdefault(os.path.realpath(os.path.join(e['directory'], e['file'])), e)
    work = os.path.join(os.path.dirname(os.path.abspath(out_path)), 'gcc-work')
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    # 1. tree-sitter facts on the preprocessed mirror (active code); test files parsed as written (TEST macros visible)
    G.cmd_mirror([os.path.join(work, 'scan'), '--cdb', cdb_path] + paths)
    lm = G.LineMap(os.path.join(work, 'linemap.json'))
    ix = Index.empty('gcc', root, [norm(os.path.relpath(s, root)) for s in scope], cdb_path)
    tsf = collect_ts(ix, work, root, lm)
    # 2. the compiler's call graph
    files = [f for f in G.collect(paths) if os.path.splitext(f)[1].lower() in G.SRC_EXTS]
    jobs, notes = [], []
    for k, f in enumerate(files):
        e = ents.get(f)
        if e is None:
            notes.append(f'no compile command (not in the call graph; tree-sitter calls used): {norm(os.path.relpath(f, root))}')
            continue
        jobs.append((compile_cmd(e, f, os.path.join(work, f'u{k}.o')), e['directory'], f, os.path.join(work, f'u{k}.ci')))
    from concurrent.futures import ThreadPoolExecutor

    def run(j):
        cmd, cwd, f, ci = j
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors='replace')
        return (f, ci, r.returncode, (r.stderr.strip().splitlines() or [''])[-1][:200])
    with ThreadPoolExecutor(max_workers=int(os.environ.get('UT_JOBS') or os.cpu_count() or 4)) as pool:
        results = list(pool.map(run, jobs))
    gnodes, gedges = {}, []
    for f, ci, rc, err in results:
        if rc != 0 or not os.path.exists(ci):
            notes.append(f"compile with -fcallgraph-info FAILED for {norm(os.path.relpath(f, root))}: {err}")
            continue
        n, e = parse_ci(ci)
        cwd = next(j[1] for j in jobs if j[2] == f)
        for t, d in n.items():
            if d['file']:
                d['file'] = os.path.realpath(os.path.join(cwd, d['file']))
            if t not in gnodes or (d['defined'] and not gnodes[t]['defined']):
                gnodes[t] = d
        gedges += [(s, t, os.path.realpath(os.path.join(cwd, lf)) if lf else None, ll) for s, t, lf, ll in e]
    ix.meta['notes'] = notes
    ix.meta['units'] = len(jobs)
    merge(ix, tsf, gnodes, gedges, root, scope)
    ix.symbols.update(TS.symbols_for(root, [norm(os.path.relpath(f, root)) for f in G.collect(paths)]))
    ix.save(out_path)
    for n in notes[:10]:
        print('  ' + n)
    return ix


def collect_ts(ix, work, root, lm):
    """index functions from tree-sitter; returns helper tables for call resolution"""
    scan = os.path.join(work, 'scan')
    pc, pcpp = TS.parsers()
    facts, spans, lines_cache = {}, {}, {}

    def orig_line(f, l):
        if f not in lines_cache:
            try:
                lines_cache[f] = open(os.path.join(root, f), encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                lines_cache[f] = []
        ls = lines_cache[f]
        return ls[l - 1] if 0 < l <= len(ls) else ''
    ts_calls = {}          # fid -> [(callee, line)] from graphify_ut.analyse (names, member:m|rec)
    locals_of = {}
    for d, _, fs in os.walk(scan):
        for fn in fs:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in G.EXTS:
                continue
            p = os.path.join(d, fn)
            rel = norm(os.path.relpath(p, scan))
            orig = os.path.join(root, rel)
            has_tests = os.path.exists(orig) and any(TEST_LINE.match(l) for l in open(orig, encoding='utf-8', errors='replace'))
            if has_tests:                     # test file: parse as written, the TEST(...) blocks are visible
                path, lof, fof = orig, (lambda l: l), (lambda r: (lambda l: r))(rel)
                rdo = (lambda r: (lambda l: orig_line(r, l)))(rel)
            else:
                path = p
                lof = (lambda r: (lambda l: lm.to_orig(r, l)[1]))(rel)
                fof = (lambda r: (lambda l: lm.to_orig(r, l)[0]))(rel)
                rdo = (lambda r: (lambda l: orig_line(*lm.to_orig(r, l))))(rel)
            text = open(path, 'rb').read()
            is_c = ext == '.c' and not has_tests      # TEST(G, N) { } parses as a function only with the C++ grammar
            try:
                funcs = TS.functions_of(text, is_c, lof, rdo)
                afuncs, avars, ax = G.analyse(path, pc if is_c else pcpp, is_c)
            except Exception as e:  # noqa: BLE001
                print(f'  tree-sitter failed on {rel}: {e}')
                continue
            facts[rel] = (ax, avars, fof, lof)
            amap = {(f['line'], f['name']): f for f in afuncs}
            for name, start, end, fx, node in funcs:
                ofile = fof(node.start_point[0] + 1)
                raw_line = node.start_point[0] + 1
                lab, kind = test_label(orig_line(ofile, start)) if name.split('::')[-1] in G.TEST_MACROS else (None, None)
                nm = lab or name
                i = fid(nm, ofile, start)
                if i in ix.functions:
                    continue
                d0 = {'name': nm, 'file': ofile, 'line': start, 'end': end, 'kind': kind or 'function'}
                if lab:
                    d0.update({'label': lab, 'sig': lab, 'outline': fx.get('outline', []), 'params': [], 'returns': [],
                               'globals': {'read': [], 'written': []}})
                else:
                    d0.update(fx)
                    if '::' in nm:
                        d0['cls'] = nm.rsplit('::', 1)[0]
                ix.functions[i] = d0
                spans.setdefault(ofile, []).append((start, end, i))
                af = amap.get((raw_line, name)) or amap.get((raw_line, name.split('::')[-1]))
                if af:
                    ts_calls[i] = [(c, lof(l)) for c, l in af['calls']]
                    locals_of[i] = af.get('locals', {})
            # pure virtual / virtual declarations in class bodies, inheritance
            tree = (pc if is_c else pcpp).parse(text)
            for n in G.walk(tree.root_node):
                if n.type == 'field_declaration':
                    dcl = n.child_by_field_name('declarator')
                    while dcl is not None and dcl.type in ('pointer_declarator', 'reference_declarator'):
                        dcl = dcl.child_by_field_name('declarator') or next((c for c in dcl.named_children if c.type.endswith('declarator')), None)
                    cls = G.enclosing_class(n, text)
                    t = G.txt(n, text)
                    if cls and dcl is not None and dcl.type == 'function_declarator' and re.search(r'=\s*0\s*;?\s*$', t):
                        nm = G.innermost_name(dcl, text)
                        if nm is None:
                            continue
                        q = f'{cls}::{G.txt(nm, text)}'
                        l0 = lof(n.start_point[0] + 1)
                        of = fof(n.start_point[0] + 1)
                        i = fid(q, of, l0)
                        ix.functions.setdefault(i, {'name': q, 'file': of, 'line': l0, 'end': lof(n.end_point[0] + 1), 'kind': 'function',
                                                    'cls': cls, 'pure': True, 'virtual': True, 'sig': TS.one_line(t, 140), 'params': [],
                                                    'outline': [], 'returns': [], 'globals': {'read': [], 'written': []}})
                    elif cls and dcl is not None and dcl.type == 'function_declarator' and re.search(r'\b(virtual|override)\b', t):
                        nm = G.innermost_name(dcl, text)
                        if nm is not None:
                            facts.setdefault('__virtual__', set()).add(f'{cls}::{G.txt(nm, text)}')
                elif n.type in ('class_specifier', 'struct_specifier'):
                    nmn = n.child_by_field_name('name')
                    base = next((c for c in n.children if c.type == 'base_class_clause'), None)
                    if nmn is not None and base is not None:
                        for b in base.named_children:
                            if b.type in ('type_identifier', 'qualified_identifier', 'template_type'):
                                bn = re.sub(r'<.*', '', G.txt(b, text)).split('::')[-1]
                                if not test_label(orig_line(fof(n.start_point[0] + 1), lof(n.start_point[0] + 1)))[0]:
                                    ix.inherits.append([G.txt(nmn, text), bn, fof(n.start_point[0] + 1)])
    for i, n in ix.functions.items():
        if n['name'] in facts.get('__virtual__', set()):
            n['virtual'] = True
    return {'facts': facts, 'spans': spans, 'ts_calls': ts_calls, 'locals': locals_of}


def merge(ix, tsf, gnodes, gedges, root, scope):
    spans = tsf['spans']
    in_repo = lambda f: f and f.startswith(root + os.sep)
    in_scope = lambda f: f and any(f == s or f.startswith(s + os.sep) for s in scope)
    rel = lambda f: norm(os.path.relpath(f, root))
    by_name = {}
    for i, n in ix.functions.items():
        by_name.setdefault(n['name'], []).append(i)
        by_name.setdefault(n['name'].split('::')[-1], []).append(i)

    def fn_at(f, line, short=None):
        best = None
        for s, e, i in spans.get(f, []):
            if s <= line <= e and (best is None or e - s < best[1] - best[0]):
                n = ix.functions[i]
                if short is None or n.get('kind') in ('test', 'fixture') or n['name'].split('::')[-1] == short or short.startswith('~'):
                    best = (s, e, i)
        return best[2] if best else None
    title2id, stack = {}, {}
    for t, d in gnodes.items():
        if d['defined'] and in_scope(d['file']):
            comps = split_sig(d['sig'])
            i = fn_at(rel(d['file']), d['line'], comps[-1] if comps else None) or fn_at(rel(d['file']), d['line'])
            if i:
                title2id[t] = i
                if re.match(r'^.+\.(c|cc|cpp|cxx|c\+\+):', t):     # GCC prefixes file-local symbols with their file
                    ix.functions[i]['static'] = True
                if d.get('stack'):
                    stack[i] = d['stack']
    for i, s in stack.items():
        ix.functions[i]['stack'] = s
    have_graph = set(title2id.values())
    indirect = {}
    for s, t, lf, ll in gedges:
        a = title2id.get(s)
        if a is None:
            continue
        if t == '__indirect_call':
            indirect.setdefault(a, set()).add(ll); continue
        b = title2id.get(t)
        if b == a and ix.functions[a].get('kind') in ('test', 'fixture'):
            continue
        if b is not None and (ix.functions[b].get('kind') == 'fixture' or ix.functions[b]['name'].split('::')[-1].startswith('~')):
            continue                   # implicit base-fixture constructors and destructor calls at scope exit: noise
        if b is None:
            d = gnodes.get(t)
            if d is None or not d.get('file'):
                continue
            comps = split_sig(d['sig'])
            if not comps:
                continue
            short = comps[-1]
            if in_scope(d['file']):
                cands = [x for x in by_name.get(short, []) if ix.functions[x]['file'] == rel(d['file'])]
                if not cands and len(comps) >= 2:         # declared in a header, defined elsewhere (ctor C1/C2 aliases, ...)
                    q = '::'.join(comps[-2:])
                    cands = sorted({x for x in by_name.get(q, []) if ix.functions[x].get('kind') == 'function'})
                b = cands[0] if cands else None
                if b is not None and ix.functions[b]['name'].split('::')[-1].startswith('~'):
                    continue
            if b is None:
                b = external(ix, comps, d, root, in_repo, rel)
            if b is None:
                continue
        ix.add_call(a, b, ll, rel(lf) if lf else ix.functions[a]['file'], 'direct')
    ix.reindex()
    # indirect sites + functions the compiler never emitted: named from tree-sitter
    resolve_ts_calls(ix, tsf, have_graph, indirect, by_name)
    ix.reindex()
    for i, n in ix.functions.items():
        if n.get('outline'):
            TS.attach_targets(n['outline'], ix.out.get(i, []), ix)
    ix.bind_virtual_targets()


def external(ix, comps, d, root, in_repo, rel):
    if 'operator' in d['sig'].split('(')[0] or any(not re.match(r'^[A-Za-z_~]\w*$', c) for c in comps if c != '{anonymous}'):
        return None                               # operators, lambdas and unparsable library signatures
    name = comps[-1] if len(comps) == 1 else '::'.join(comps[-2:]) if comps[-2][:1].isupper() else comps[-1]
    f = d['file']
    if not in_repo(f) and (len(comps) > 1 and comps[0] in ('std', '__gnu_cxx', '__cxxabiv1') or name.startswith(('operator', '__', '~'))):
        return None
    if 'operator' in name or comps[-1] == (comps[-2] if len(comps) > 1 else None):
        return None                               # operators, constructors
    r = rel(f) if in_repo(f) else None
    kind = 'test-framework' if FRAMEWORK.search(r or f) else 'function' if r else 'library'
    if kind == 'test-framework' and '::' in name:
        return None
    i = 'ext:' + name
    ix.externals.setdefault(i, {'name': name, 'kind': kind, 'declared_in': r or '(not in repo: system/library)'})
    return i


def resolve_ts_calls(ix, tsf, have_graph, indirect, by_name):
    facts = {k: v for k, v in tsf['facts'].items() if k != '__virtual__'}
    class_fields, bases = {}, {}
    for ax, _, _, _ in facts.values():
        for c, flds in ax['class_fields'].items():
            class_fields.setdefault(c, {}).update(flds)
    for d, b, _ in ix.inherits:
        bases.setdefault(d, []).append(b)
    all_vars = set()
    for _, v, _, _ in facts.values():
        all_vars |= v

    def member(i, callee):
        m, _, rec = callee[7:].partition('|')
        n = ix.functions[i]
        cls = n.get('cls')
        ty = cls if rec == 'this' else (tsf['locals'].get(i, {}).get(rec) or class_fields.get(cls, {}).get(rec)) if rec else None
        todo, seen = ([ty] if ty else []), set()
        while todo:
            t = todo.pop(0)
            if t in seen:
                continue
            seen.add(t)
            hit = [x for x in by_name.get(f'{t}::{m}', []) if x in ix.functions]
            if hit:
                return hit[0], 'EXTRACTED'
            todo += bases.get(t, [])
        cands = {x for x in by_name.get(m, []) if '::' in ix.functions[x]['name'] and ix.functions[x].get('kind') == 'function'}
        return (cands.pop(), 'INFERRED') if len(cands) == 1 else (None, None)
    ptr_calls = []
    for i, calls in tsf['ts_calls'].items():
        emitted = i in have_graph
        lines = indirect.get(i, set())
        direct_at = {(c['line']) for c in ix.out.get(i, [])}
        for callee, line in calls:
            if emitted and line not in lines:
                continue                         # the compiler already gave the exact edge for this call
            if callee.startswith('member:'):
                t, conf = member(i, callee)
                if t:
                    ix.add_call(i, t, line, ix.functions[i]['file'], 'virtual' if emitted else 'member', conf if not emitted else 'EXTRACTED')
                continue
            if '.' in callee or '->' in callee or callee in all_vars:
                name = callee
                e = 'ext:' + name
                ix.externals.setdefault(e, {'name': name, 'kind': 'pointer', 'declared_in': f'variable or parameter in {ix.functions[i]["file"]}'})
                ix.add_call(i, e, line, ix.functions[i]['file'], 'pointer')
                ptr_calls.append(e)
                continue
            if emitted and line in direct_at:
                continue
            if not emitted:
                cands = by_name.get(callee) or by_name.get(callee.split('::')[-1]) or []
                cands = [c for c in cands if ix.functions[c].get('kind') == 'function']
                if len(set(cands)) == 1:
                    ix.add_call(i, cands[0], line, ix.functions[i]['file'], 'direct', 'INFERRED')
    # function-pointer targets from the same facts Graphify uses (designated/positional initializers, assignments, registration)
    known = {n['name'] for n in ix.functions.values()} | {n['name'].split('::')[-1] for n in ix.functions.values()}
    fnptr_fields, structs = set(), {}
    for ax, _, _, _ in facts.values():
        fnptr_fields |= ax['fnptr_fields']
        for k, v in ax['structs'].items():
            structs.setdefault(k, v)
    binds = {}
    for rel_, (ax, _, fof, lof) in facts.items():
        for tyname, pos, fn, line in ax['positional']:
            fl = structs.get(tyname)
            if fl and pos < len(fl) and fl[pos]:
                ax['bindings'].append((('field', fl[pos]), fn, line))
        for key, fn, line in ax['bindings']:
            if fn in known or (key[0] == 'field' and key[1] in fnptr_fields):
                binds.setdefault(key, set()).add((fn, f'{fof(line)}:{lof(line)}'))
        for callee, idx, fn, line in ax['args']:
            if fn not in known:
                continue
            for _, (ax2, _, _, _) in facts.items():
                for key, pidx, _ in ax2['stores'].get(callee, []):
                    if pidx == idx:
                        binds.setdefault(key, set()).add((fn, f'{fof(line)}:{lof(line)}'))
    for e in set(ptr_calls):
        expr = ix.externals[e]['name']
        key = ('field', re.split(r'\.|->', expr)[-1]) if ('.' in expr or '->' in expr) else ('var', expr)
        tg = []
        for fn, site in sorted(binds.get(key, ())):
            hit = [x for x in by_name.get(fn, []) if ix.functions[x].get('kind') == 'function']
            if hit:
                tg.append([hit[0], site])
                ix.add_call(e, hit[0], ix.functions[hit[0]]['line'], ix.functions[hit[0]]['file'], 'pointer-target', 'INFERRED')
        if tg:
            ix.externals[e]['targets'] = tg
