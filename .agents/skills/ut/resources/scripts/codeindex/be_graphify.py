"""Graphify backend: convert the augmented graph.json (+ the preprocessed mirror) into the shared index.
The graph gives functions, calls, externals, pointer targets, inheritance and TEST blocks; tree-sitter on the
mirror gives each function's outline (lines mapped back to the original sources)."""
import json, os, re
import graphify_ut as G
from .model import Index, fid, norm, is_testside
from . import tsoutline as TS


def loc(x):
    m = re.search(r'L(\d+)', x.get('source_location') or '')
    return int(m.group(1)) if m else 0


def export(gdir, out_path):
    gpath = os.path.join(gdir, 'out', 'graph.json')
    scan = os.path.join(gdir, 'scan')
    root = open(os.path.join(gdir, 'SOURCE_ROOT')).read().strip()
    args = open(os.path.join(gdir, 'BUILD_ARGS')).read().splitlines()
    cwd = next((l[4:] for l in args if l.startswith('cwd=')), root)
    paths = [norm(os.path.relpath(os.path.realpath(os.path.join(cwd, l[5:])), root)) for l in args if l.startswith('path=')]
    cdb = next((l[4:] for l in args if l.startswith('cdb=')), '')
    lm = G.LineMap(os.path.join(gdir, 'linemap.json'))
    g = json.load(open(gpath, encoding='utf-8'))
    ix = Index.empty('graphify', root, paths, cdb)
    idmap = {}
    for n in g['nodes']:
        if not n.get('_callable'):
            continue
        if n.get('type') == 'external':
            name = n['label'][:-2] if n['label'].endswith('()') else n['label']
            ix.externals['ext:' + name] = {'name': name, 'kind': n.get('kind', 'function'), 'declared_in': n.get('declared_in', ''),
                                           '_targets': n.get('targets', [])}
            idmap[n['id']] = 'ext:' + name
            continue
        f = n.get('source_file')
        if not f:
            continue
        kind = n.get('kind') if n.get('kind') in ('test', 'fixture') else 'function'
        name = n['label'] if kind != 'function' else (n['label'][:-2] if n['label'].endswith('()') else n['label'])
        name = name.lstrip('.')
        i = fid(name, f, loc(n))
        d = {'name': name, 'file': f, 'line': loc(n), 'end': loc(n), 'kind': kind, 'static': bool(n.get('static')),
             'virtual': bool(n.get('virtual')), 'pure': bool(n.get('pure_virtual')), 'outline': None}
        if kind != 'function':
            d['label'] = name
        if '::' in name and kind == 'function':
            d['cls'] = name.rsplit('::', 1)[0]
        if n.get('declared_at'):
            d['decl'] = n['declared_at'].replace(':L', ':')
        ix.functions[i] = d
        idmap[n['id']] = i
    classes = {n['id']: n['label'] for n in g['nodes']}
    for e in g['links']:
        rel = e.get('relation')
        if rel == 'calls' and e['source'] in idmap and e['target'] in idmap:
            t = idmap[e['target']]
            kind = 'pointer-target' if e.get('context') == 'pointer-target' else \
                   (ix.externals[t]['kind'] if t in ix.externals and ix.externals[t]['kind'] in ('pointer', 'macro') else 'direct')
            ix.add_call(idmap[e['source']], t, loc(e), norm(e.get('source_file') or ''), kind, e.get('confidence', 'EXTRACTED'))
        elif rel == 'inherits' and e['source'] in classes and e['target'] in classes:
            src = next((n for n in g['nodes'] if n['id'] == e['source']), {})
            ix.inherits.append([classes[e['source']], classes[e['target']].split('::')[-1], src.get('source_file', '')])
    # pointer targets: 'fn (bound at f:L1, f:L2)' -> [[fn_id, 'f:1']]
    for e in ix.externals.values():
        tg = []
        for s in e.pop('_targets', []):
            m = re.match(r'(\S+) \(bound at ([^,) ]+)', s)
            if m:
                hits = [h for h in ix.find(m.group(1)) if h in ix.functions]
                if hits:
                    tg.append([hits[0], m.group(2).replace(':L', ':')])
        if tg:
            e['targets'] = tg
    ix.reindex()
    add_facts(ix, scan, root, lm)
    ix.bind_virtual_targets()
    ix.save(out_path)
    return ix


def add_facts(ix, scan, root, lm):
    """outline, signature, params, returns, globals from tree-sitter on the mirror (code) and the original files (tests)"""
    by_loc = {(n['file'], n['line']): i for i, n in ix.functions.items()}
    by_name = {}
    for i, n in ix.functions.items():
        by_name.setdefault((n['file'], n['name']), []).append(i)
    lines_cache = {}

    def orig_line(f, l):
        if f not in lines_cache:
            try:
                lines_cache[f] = open(os.path.join(root, f), encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                lines_cache[f] = []
        ls = lines_cache[f]
        return ls[l - 1] if 0 < l <= len(ls) else None

    for d, _, files in os.walk(scan):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in G.EXTS:
                continue
            p = os.path.join(d, fn)
            rel = norm(os.path.relpath(p, scan))
            line_of = (lambda r: (lambda l: lm.to_orig(r, l)[1]))(rel)
            file_of = (lambda r: (lambda l: lm.to_orig(r, l)[0]))(rel)
            read_orig = (lambda r: (lambda l: orig_line(*lm.to_orig(r, l))))(rel)
            try:
                funcs = TS.functions_of(open(p, 'rb').read(), ext == '.c', line_of, read_orig)
            except Exception as e:      # one bad file must not stop the export
                print(f'  outline skipped for {rel}: {e}')
                continue
            for name, start, end, facts, node in funcs:
                f0 = file_of(node.start_point[0] + 1)
                i = by_loc.get((f0, start))
                if i is None:
                    c = by_name.get((f0, name)) or [x for x in by_name.get((f0, name.split('::')[-1]), [])]
                    i = c[0] if len(c) == 1 else None
                if i is None:
                    continue
                n = ix.functions[i]
                if n.get('outline') is not None and n['kind'] == 'function':
                    continue
                n['end'] = max(end, n['line'])
                n.update({k: v for k, v in facts.items() if k != 'static'})
                n['static'] = n.get('static') or facts.get('static', False)
    # TEST blocks: tree-sitter sees TEST(G, N) { } as a function called TEST at that line (original test files)
    tfiles = {n['file'] for n in ix.functions.values() if n['kind'] in ('test', 'fixture')}
    for f in tfiles:
        try:
            text = open(os.path.join(root, f), 'rb').read()
        except OSError:
            continue
        for name, start, end, facts, node in TS.functions_of(text, f.endswith('.c')):
            i = by_loc.get((f, start))
            if i is not None and ix.functions[i]['kind'] in ('test', 'fixture'):
                ix.functions[i].update({'end': end, 'outline': facts.get('outline', []), 'sig': ix.functions[i]['name']})
    for i, n in ix.functions.items():
        if n.get('outline'):
            TS.attach_targets(n['outline'], ix.out.get(i, []), ix)
