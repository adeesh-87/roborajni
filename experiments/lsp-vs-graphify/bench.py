#!/usr/bin/env python3
"""bench.py NAME GT.json GRAPHIFY_INDEX.json ROOT CDB_DIR OUT.json : score Graphify and clangd against the GCC call graph.

Questions per function defined in the repo (ground truth: gt.py, GCC -fcallgraph-info at -O0):
  callees       the repo functions it calls by name (what a test must mock or let run)
  callers-prod  production functions that call it
  callers-test  test functions / TEST blocks that call it (which tests already exercise it)
  ctor/dtor     constructor and destructor calls (implicit ones included), reported apart
  virtual       calls through an interface reference, adjudicated to the interface method (cvaccel)
  def           a unique function name looked up by name: is the definition found (file, line +-3)?
Both tools are asked at their best: Graphify by the node at the function's file and line, clangd by the call
hierarchy at the function name's position (documentSymbol). Tool answers are mapped to ground-truth functions by
file and line (+-3), else by a unique qualified name (header declarations). Unmapped answers count as false positives."""
import json, os, re, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clangd_cli import Client, uri, path_of   # noqa: E402

JUNK = re.compile(r'TEST_GROUP_CppUTestGroup\w*::~?TEST_GROUP|_TestShell::|__static_initialization|_GLOBAL__|lambda|'
                  r'^TEST_\w+_Test::~?TEST_\w+_Test$')
IFACE = {'hw_': ('include/cvaccel/hw_block.hpp', 'IAccelBlock'), 'dev_': ('include/cvaccel/device.hpp', 'IDevice'),
         'dev': ('include/cvaccel/device.hpp', 'IDevice'), 't_': ('client/include/cvclient/cvclient.hpp', 'ITransport')}


def is_test_file(f):
    return f.startswith(('tests/', 'test/')) or '/tests/' in f


def kind_of(name):
    parts = name.split('::')
    last = parts[-1]
    if len(parts) > 1 and (last == parts[-2] or last == '~' + parts[-2]):
        return 'ctor/dtor'
    if 'operator' in last:
        return 'operator'
    return 'named'


def namespaces(root):
    ns = set()
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(('build', '.', '_deps')) and d not in ('unity', 'cpputest')]
        for f in fn:
            if f.endswith(('.c', '.cc', '.cpp', '.h', '.hpp')):
                for m in re.findall(r'^[ \t]*(?:inline[ \t]+)?namespace[ \t]+([\w:]+)', open(os.path.join(dp, f), errors='replace').read(), re.M):
                    ns |= set(m.split('::'))
    return ns


def load_gt(path, root):
    g = json.load(open(path))
    ns = namespaces(root)
    lines = {}

    def text(f, l):
        if f not in lines:
            lines[f] = open(os.path.join(root, f), errors='replace').read().splitlines()
        return lines[f][l - 1] if 0 < l <= len(lines[f]) else ''

    def clean(name):
        parts = name.split('::')
        while len(parts) > 1 and parts[0] in ns:
            parts = parts[1:]
        return '::'.join(parts)
    for v in g['nodes'].values():
        v['name'] = clean(v['name'])
    for e in g['edges']:
        e[2] = clean(e[2])
    lam = {k: v for k, v in g['nodes'].items() if 'lambda' in v['name']}
    # implicitly defined members (compiler-generated constructors etc.) sit at the class line: not questions
    implicit = {k for k, v in g['nodes'].items() if k not in lam and not re.search(r'\b' + re.escape(v['name'].split('::')[-1].lstrip('~')) + r'\s*\(', text(v['file'], v['line']))
                and not re.match(r'^TEST_\w+_Test::', v['name'])}
    nodes = {k: v for k, v in g['nodes'].items() if not JUNK.search(v['name']) and k not in lam and k not in implicit}
    for k, v in g['nodes'].items():       # a TEST line key may be named after the macro's constructor: keep it as the TEST
        if k not in nodes and re.match(r'^TEST_\w+_Test::', v['name']):
            nodes[k] = dict(v, name='TEST@' + k)
    by_name, by_sig = collections.defaultdict(list), collections.defaultdict(list)
    for k, v in nodes.items():
        by_name[v['name']].append(k)
        by_sig[v.get('sig')].append(k)

    def canon(key, name, near_file, sig=None):
        if key in nodes:
            return key
        c = by_sig.get(sig, []) if sig else []
        if len(c) == 1:
            return c[0]
        c = by_name.get(name, [])
        if len(c) == 1:
            return c[0]
        c2 = [k for k in c if k.startswith(near_file + ':')]
        return c2[0] if len(c2) == 1 else None
    # calls written inside a lambda belong to the lambda for GCC and to the enclosing function for a reader: neutral
    def enclosing(k):
        f, l = lam[k]['file'], lam[k]['line']
        c = [(v['line'], x) for x, v in nodes.items() if v['file'] == f and v['line'] <= l]
        return max(c)[1] if c else None
    neutral = set()
    edges = set()
    for s, t, name, line, sig in g['edges']:
        if s in lam:
            t2 = canon(t, name, s.split(':')[0], sig)
            if t2 and enclosing(s):
                neutral.add((enclosing(s), t2))
            continue
        if s not in nodes or JUNK.search(name):
            continue
        t2 = canon(t, name, s.split(':')[0], sig)
        if t2 and t2 != s:
            edges.add((s, t2, kind_of(name)))
    # virtual calls: receiver member -> interface method declaration (adjudicated by the receiver's declared type)
    virt = set()
    seen = set()
    for i in g['indirect']:
        if (i['from'], i['line']) in seen or i['from'] not in nodes or is_test_file(i['from']):
            continue
        seen.add((i['from'], i['line']))
        m = re.search(r'\b(hw_|dev_|dev|t_)\.(\w+)\s*\(', i['text'])
        if not m or m.group(1) not in IFACE:
            continue
        hdr, cls = IFACE[m.group(1)]
        try:
            src = open(os.path.join(root, hdr)).read().splitlines()
        except OSError:
            continue
        ln = next((n + 1 for n, l in enumerate(src) if re.search(r'virtual\b.*\b' + m.group(2) + r'\s*\(', l)), None)
        if ln:
            key = f'{hdr}:{ln}'
            nodes.setdefault(key, {'file': hdr, 'line': ln, 'col': 1, 'name': f'{cls}::{m.group(2)}', 'pure': True})
            virt.add((i['from'], key))
    pointer_sites = len({(i['from'], i['line']) for i in g['indirect'] if i['from'] in nodes and not is_test_file(i['from'])
                         and not re.search(r'\b(hw_|dev_|dev|t_)\.', i['text'])})
    # dynamic dispatch: a call through IFoo::m may run any override Impl::m. GCC cannot say which, so a tool that
    # lists the call site as a caller of an override (or the override as a callee) is neither right nor wrong: neutral
    derived = collections.defaultdict(set)
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(('build', '.', '_deps'))]
        for f in fn:
            if f.endswith(('.cpp', '.hpp', '.h', '.cc')):
                for impl, base in re.findall(r'(?:class|struct)\s+(\w+)\s*(?:final\s*)?:\s*public\s+(?:\w+::)*(\w+)', open(os.path.join(dp, f), errors='replace').read()):
                    derived[base].add(impl)
    for caller, iface in virt:
        cls, meth = nodes[iface]['name'].split('::')
        for k, v in nodes.items():
            if v['name'] in {f'{d}::{meth}' for d in derived[cls]}:
                neutral.add((caller, k))
    return nodes, edges, virt, pointer_sites, neutral


class Resolver:
    """tool answer (file, line, name) -> ground-truth key, the same rule for both tools"""
    def __init__(self, nodes):
        self.nodes = nodes
        self.by_file = collections.defaultdict(list)
        self.by_q = collections.defaultdict(list)
        for k, v in nodes.items():
            self.by_file[v['file']].append((v['line'], k))
            self.by_q[v['name']].append(k)

    def __call__(self, f, line, name):
        near = [(abs(l - line), k) for l, k in self.by_file.get(f, []) if abs(l - line) <= 3]
        if near:
            last = name.split('::')[-1].split('(')[0]
            same = [x for x in near if self.nodes[x[1]]['name'].split('::')[-1] == last]
            return min(same or near)[1]
        q = '::'.join(name.split('::')[-2:])
        c = self.by_q.get(q, [])
        return c[0] if len(c) == 1 else f'?{f}:{line}:{name}'


# ------------------------------------------------------------------------------------------------ Graphify arm
class GraphifyArm:
    def __init__(self, path, root):
        ix = json.load(open(path))
        self.prefix = os.path.relpath(os.path.realpath(root), os.path.realpath(ix['meta']['root']))
        self.prefix = '' if self.prefix == '.' else self.prefix + '/'
        self.fn = {}
        self.by_file = collections.defaultdict(list)
        for i, v in ix['functions'].items():
            f = self.rel(v['file'])
            self.fn[i] = (f, v['line'], v['name'], v.get('end') or v['line'])
            self.by_file[f].append(i)
        self.out, self.inc = collections.defaultdict(set), collections.defaultdict(set)
        for c in ix['calls']:
            if c['kind'] != 'direct' or c['to'] not in self.fn:
                continue
            self.out[c['from']].add(c['to'])
            self.inc[c['to']].add(c['from'])
        self.by_name = collections.defaultdict(list)
        for i, (f, l, n, e) in self.fn.items():
            self.by_name[n].append(i)
            self.by_name[n.split('::')[-1]].append(i)

    def rel(self, f):
        return f[len(self.prefix):] if self.prefix and f.startswith(self.prefix) else f

    def node(self, f, line, name):
        c = [(abs(self.fn[i][1] - line), i) for i in self.by_file.get(f, []) if abs(self.fn[i][1] - line) <= 3
             or (name.startswith('TEST@') and self.fn[i][1] == line)]
        if not name.startswith('TEST@'):
            last = name.split('::')[-1]
            c = [x for x in c if self.fn[x[1]][2].split('::')[-1] == last] or [x for x in c if x[0] == 0]
        return min(c)[1] if c else None

    def ask(self, v, which):
        i = self.node(v['file'], v['line'], v['name'])
        if not i:
            return None
        return [self.fn[j][:3] for j in (self.out if which == 'callees' else self.inc)[i]]

    def define(self, qname):
        c = self.by_name.get(qname, [])
        return [self.fn[i][:2] for i in c]


# -------------------------------------------------------------------------------------------------- clangd arm
class ClangdArm:
    def __init__(self, root, cdb, with_refs=True):
        self.with_refs = with_refs
        self.c = Client(root, os.path.abspath(cdb))
        ents = json.load(open(os.path.join(cdb, 'compile_commands.json')))
        self.c.open(os.path.join(ents[0]['directory'], ents[0]['file']))
        self.c.wait_index(900)
        for _ in range(200):
            if self.c.request('workspace/symbol', {'query': 'a'}):
                break
            time.sleep(0.1)
        self.root = self.c.root
        self.syms = {}

    def containers(self, f):
        """(start, end, selection line, name) of every function-like symbol of a file, TEST blocks included"""
        if ('c', f) not in self.syms:
            self.doc_symbols(f)
            p = os.path.join(self.root, f)
            out, stack = [], list(self.c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri(p)}}) or [])
            while stack:
                s = stack.pop()
                if s.get('kind') in (6, 9, 12) or s['name'] in ('TEST', 'TEST_F', 'IGNORE_TEST', 'TEST_GROUP'):
                    r = s['range']
                    out.append((r['start']['line'] + 1, r['end']['line'] + 1,
                                (r if s['name'].startswith(('TEST', 'IGNORE')) else s['selectionRange'])['start']['line'] + 1, s['name']))
                stack += s.get('children', [])
            self.syms[('c', f)] = out
        return self.syms[('c', f)]

    def doc_symbols(self, f):
        if f not in self.syms:
            p = os.path.join(self.root, f)
            self.c.open(p)
            out, stack = [], list(self.c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri(p)}}) or [])
            while stack:
                s = stack.pop()
                if s.get('kind') in (6, 9, 12):          # method, constructor, function
                    out.append(s)
                stack += s.get('children', [])
            self.syms[f] = out
        return self.syms[f]

    def position(self, v):
        last = v['name'].split('::')[-1]
        best = None
        for s in self.doc_symbols(v['file']):
            sl = s['selectionRange']['start']['line'] + 1
            if abs(sl - v['line']) <= 3 or (v['name'].startswith('TEST@') and abs(s['range']['start']['line'] + 1 - v['line']) <= 1):
                score = (s['name'].split('::')[-1] != last and not v['name'].startswith('TEST@'), abs(sl - v['line']))
                if best is None or score < best[0]:
                    best = (score, s['selectionRange']['start'])
        return best[1] if best else {'line': v['line'] - 1, 'character': max(0, v.get('col', 1) - 1)}

    def ask(self, v, which):
        p = os.path.join(self.root, v['file'])
        items = self.c.request('textDocument/prepareCallHierarchy', {'textDocument': {'uri': uri(p)}, 'position': self.position(v)}) or []
        if not items:
            return None
        res = self.c.request('callHierarchy/incomingCalls' if which == 'callers' else 'callHierarchy/outgoingCalls', {'item': items[0]}) or []
        out = []
        if which == 'callers' and self.with_refs:
            # incomingCalls misses callers inside macro-generated functions (CppUTest TEST bodies): add every reference,
            # mapped to the innermost function-like symbol (documentSymbol) around it
            refs = self.c.request('textDocument/references', {'textDocument': {'uri': uri(p)}, 'position': self.position(v),
                                                               'context': {'includeDeclaration': False}}) or []
            for r in refs:
                f = self.c.rel(path_of(r['uri']))
                if f.startswith(('/', '..')):
                    continue
                ln = r['range']['start']['line'] + 1
                enc = [x for x in self.containers(f) if x[0] <= ln <= x[1]]
                if enc:
                    a, b, sel, name = min(enc, key=lambda x: x[1] - x[0])
                    out.append((f, sel, name))
        for r in res:
            it = r.get('from') or r.get('to')
            name = it.get('detail') if '::' in (it.get('detail') or '') else it['name']
            out.append((self.c.rel(path_of(it['uri'])), it['selectionRange']['start']['line'] + 1, name or it['name']))
        return out

    def define(self, qname):
        hit = self.c.locate(qname)
        if not hit:
            return []
        path, pos = hit
        return [(self.c.rel(path), pos['line'] + 1)]


class ClangdGraphArm(ClangdArm):
    """a call graph built once from clangd: every function symbol of every repo file -> its references -> the
    innermost function or TEST block around each reference. What an index built on clangd would hold."""
    def __init__(self, root, cdb, skip=('lib/unity',)):
        super().__init__(root, cdb, with_refs=False)
        t0 = time.time()
        files = set()
        for e in json.load(open(os.path.join(cdb, 'compile_commands.json'))):
            files.add(self.c.rel(os.path.join(e['directory'], e['file'])))
        for dp, dn, fn in os.walk(self.root):
            dn[:] = [d for d in dn if not d.startswith(('build', '.', '_deps'))]
            files |= {self.c.rel(os.path.join(dp, f)) for f in fn if f.endswith(('.h', '.hpp', '.hh'))}
        files = sorted(f for f in files if not f.startswith(('/', '..')) and not f.startswith(skip))
        self.out, self.inc, seen, self.names = collections.defaultdict(set), collections.defaultdict(set), set(), {}
        for f in files:
            for sym in self.doc_symbols(f):
                p = os.path.join(self.root, f)
                items = self.c.request('textDocument/prepareCallHierarchy', {'textDocument': {'uri': uri(p)}, 'position': sym['selectionRange']['start']}) or []
                if not items or items[0].get('data') in seen:
                    continue
                it = items[0]
                seen.add(it.get('data'))
                tu, tpos = it['uri'], it['selectionRange']['start']
                d = self.c.request('textDocument/definition', {'textDocument': {'uri': tu}, 'position': tpos}) or []
                d = d if isinstance(d, list) else [d]
                if d and not (d[0]['uri'] == tu and d[0]['range']['start']['line'] == tpos['line']) and \
                        not path_of(d[0]['uri']).endswith(('.h', '.hpp', '.hh')) or (d and path_of(tu).endswith(('.h', '.hpp', '.hh'))):
                    tu, tpos = d[0]['uri'], d[0]['range']['start']     # key the function by its definition
                tgt = (self.c.rel(path_of(tu)), tpos['line'] + 1, it.get('detail') or it['name'])
                refs = self.c.request('textDocument/references', {'textDocument': {'uri': it['uri']}, 'position': it['selectionRange']['start'],
                                                                   'context': {'includeDeclaration': False}}) or []
                for r in refs:
                    rf = self.c.rel(path_of(r['uri']))
                    if rf.startswith(('/', '..')) or rf.startswith(skip):
                        continue
                    ln = r['range']['start']['line'] + 1
                    enc = [x for x in self.containers(rf) if x[0] <= ln <= x[1]]
                    if not enc:
                        continue
                    a, b, sel, name = min(enc, key=lambda x: x[1] - x[0])
                    src = (rf, sel, name)
                    if src[:2] == tgt[:2]:
                        continue
                    self.names.setdefault(src[:2], name)
                    self.names.setdefault(tgt[:2], tgt[2])
                    self.out[src[:2]].add(tgt[:2])
                    self.inc[tgt[:2]].add(src[:2])
        self.build_s = time.time() - t0
        self.keys = collections.defaultdict(list)
        for k in set(self.out) | set(self.inc):
            self.keys[k[0]].append(k)

    def ask(self, v, which):
        last = v['name'].split('::')[-1]
        c = [(abs(k[1] - v['line']), k) for k in self.keys.get(v['file'], []) if abs(k[1] - v['line']) <= 3]
        c = [x for x in c if self.names[x[1]].split('::')[-1] == last] or [x for x in c if x[0] == 0] or \
            ([] if not v['name'].startswith('TEST@') else c)
        if not c:
            return []
        k = min(c)[1]
        return [(f, l, self.names[(f, l)]) for f, l in (self.out if which == 'callees' else self.inc).get(k, ())]


# ------------------------------------------------------------------------------------------------------ scoring
def score(nodes, edges, virt, neutral, arm, res):
    s = collections.defaultdict(lambda: [0, 0, 0])          # tp, fp, fn
    missing = collections.Counter()
    fails = collections.defaultdict(list)
    out_by = collections.defaultdict(lambda: collections.defaultdict(set))
    in_by = collections.defaultdict(lambda: collections.defaultdict(set))
    for a, b, k in edges:
        out_by[a][k].add(b)
        in_by[b][k].add(a)
    t0, nq = time.time(), 0
    for key, v in sorted(nodes.items()):
        if v.get('pure') or (v['name'] == 'main' and is_test_file(v['file'])):   # test runner boilerplate
            continue
        prod = not is_test_file(v['file'])
        # callees
        ans = arm.ask(v, 'callees'); nq += 1
        got = None if ans is None else {res(*x) for x in ans if not x[0].startswith(('/', '..', 'lib/unity/'))}
        if got is None:
            missing['callees'] += 1
            got = set()
        got -= {b for a, b in neutral if a == key}
        for cat in ('named', 'ctor/dtor'):
            want = out_by[key][cat]
            if cat == 'named':
                want = want | {b for a, b in virt if a == key}
            others = set().union(*[out_by[key][c] for c in out_by[key] if c != cat]) if cat == 'named' else set()
            g = {x for x in got if (kind_of(nodes[x]['name']) if x in nodes else 'named') == cat} if cat == 'ctor/dtor' \
                else {x for x in got if x not in others and (x not in nodes or kind_of(nodes[x]['name']) == 'named')}
            tag = ('callees-prod' if prod else 'callees-test') if cat == 'named' else 'ctor/dtor'
            tp, fp, fn = len(g & want), len(g - want), len(want - g)
            s[tag][0] += tp; s[tag][1] += fp; s[tag][2] += fn
            if fp or fn:
                fails[tag].append({'fn': v['name'], 'at': key, 'missed': sorted(nodes[x]['name'] + '@' + x for x in want - g),
                                   'extra': sorted((nodes[x]['name'] + '@' + x) if x in nodes else x for x in g - want)})
        vw = {b for a, b in virt if a == key}
        s['virtual'][0] += len(got & vw); s['virtual'][2] += len(vw - got)
        if not prod:
            continue
        ans = arm.ask(v, 'callers'); nq += 1
        got = None if ans is None else {res(*x) for x in ans if not x[0].startswith(('/', '..', 'lib/unity/'))}
        if got is None:
            missing['callers'] += 1
            got = set()
        got -= {a for a, b in neutral if b == key}
        want = in_by[key]['named']
        got -= (in_by[key]['ctor/dtor'] | in_by[key]['operator']) - want
        for tag, side in (('callers-prod', False), ('callers-test', True)):
            w = {x for x in want if is_test_file(nodes[x]['file']) == side}
            g = {x for x in got if (is_test_file(nodes[x]['file']) if x in nodes else is_test_file(x[1:])) == side}
            tp, fp, fn = len(g & w), len(g - w), len(w - g)
            s[tag][0] += tp; s[tag][1] += fp; s[tag][2] += fn
            if fp or fn:
                fails[tag].append({'fn': v['name'], 'at': key, 'missed': sorted(nodes[x]['name'] + '@' + x for x in w - g),
                                   'extra': sorted((nodes[x]['name'] + '@' + x) if x in nodes else x for x in g - w)})
    qtime = (time.time() - t0) / max(nq, 1)
    # def by name: production functions whose qualified name is unique
    cnt = collections.Counter(v['name'] for v in nodes.values() if not v.get('pure'))
    ok = tot = 0
    for key, v in nodes.items():
        if v.get('pure') or is_test_file(v['file']) or cnt[v['name']] != 1 or v['name'].startswith('TEST@'):
            continue
        tot += 1
        d = arm.define(v['name'])
        if len(d) >= 1 and d[0][0] == v['file'] and abs(d[0][1] - v['line']) <= 3:
            ok += 1
        else:
            fails['def'].append({'fn': v['name'], 'at': key, 'got': d[:3]})
    s['def'] = [ok, tot - ok, 0]
    return s, missing, fails, qtime


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main(name, gt, gix, root, cdb, out):
    nodes, edges, virt, psites, neutral = load_gt(gt, root)
    res = Resolver(nodes)
    report = {'codebase': name, 'functions': sum(1 for v in nodes.values() if not v.get('pure')),
              'edges': collections.Counter(k for _, _, k in edges), 'virtual_sites': len(virt), 'pointer_sites': psites, 'arms': {}}
    for arm_name in ('graphify', 'clangd', 'clangd-graph'):
        t0 = time.time()
        arm = GraphifyArm(gix, root) if arm_name == 'graphify' else ClangdArm(root, cdb) if arm_name == 'clangd' else ClangdGraphArm(root, cdb)
        load = time.time() - t0
        s, missing, fails, qt = score(nodes, edges, virt, neutral, arm, res)
        if arm_name != 'graphify':
            arm.c.close()
        report['arms'][arm_name] = {'load_s': round(load, 1), 'query_ms': round(qt * 1000, 1), 'no_answer': dict(missing),
                                    'scores': {k: {'tp': v[0], 'fp': v[1], 'fn': v[2],
                                                   **dict(zip(('precision', 'recall', 'f1'), (round(x, 3) for x in prf(*v))))}
                                               for k, v in s.items()},
                                    'failures': fails}
        print(f'== {name} / {arm_name}  (load {load:.1f}s, {qt * 1000:.1f} ms/question, no answer {dict(missing)})')
        for k, v in sorted(s.items()):
            p, r, f = prf(*v)
            print(f'  {k:13s} tp {v[0]:5d} fp {v[1]:5d} fn {v[2]:5d}   P {p:.3f}  R {r:.3f}  F1 {f:.3f}')
    json.dump(report, open(out, 'w'), indent=1, default=list)


if __name__ == '__main__':
    main(*sys.argv[1:7])
