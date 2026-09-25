"""The code index: ONE file (index.json) that every backend writes and every query reads.

Schema (version 1):
  meta       {schema, backend, root, paths, cdb, generated, stats, notes}
  functions  {id: {name, file, line, end, kind (function|test|fixture), cls, static, virtual, pure,
                   sig, params [[name, type]], returns [text], globals {read: [], written: []},
                   outline [..statement tree..], decl (file:line of a separate declaration), label (tests)}}
  externals  {id: {name, kind (function|library|pointer|macro|test-framework|interface), declared_in, targets [[fn_id, 'file:line']]}}
  calls      [{from, to, line, file, kind (direct|virtual|member|pointer|macro|pointer-target|virtual-target), conf}]
  inherits   [[derived_class, base_class, file]]

Outline statement tree (ordered as executed; only control flow, calls and exits are kept):
  {t: if,     l, c (condition), n (sub-conditions), then [..], else [..] | None, src?}
  {t: switch, l, c, cases [{v (labels), l, b [..], ft (falls through)}], default (bool)}
  {t: loop,   l, k (for|while|do|range), c, b [..]}
  {t: '?:',   l, c, n}
  {t: call,   l, f (callee as written), x (call text), to (resolved id or None)}
  {t: ret | throw, l, v}     {t: brk | cont, l}     {t: goto, l, v}
  {t: try,    l, b [..], h [{v, b [..]}]}
Function ids: name@file:line (readable and stable); external ids: ext:name.
"""
import json, os, re

SCHEMA = 'ut-index/1'
TESTSIDE = re.compile(r'(^|/)(test|tests|unittest|unittests|ut|utest|mocks?|stubs?|fakes?)(/|$)|(^|/)test_[^/]*$|_test\.[^/]*$'
                      r'|(^|/)[^/]*Test[^/]*\.[^/]*$|[Mm]ock|[Ss]tub|[Ff]ake')
FRAMEWORK = re.compile(r'(^|/)(unity|cmock|cpputest|cppumock|gtest|gmock|googletest|googlemock|catch2?|doctest|fff|ceedling)(/|[._-]|$)', re.I)
TEST_MACROS = ('TEST', 'TEST_F', 'TEST_P', 'TYPED_TEST', 'TYPED_TEST_P', 'IGNORE_TEST', 'TEST_GROUP', 'TEST_GROUP_BASE',
               'TEST_CASE', 'TEST_CASE_METHOD', 'SCENARIO', 'FIXTURE_TEST_CASE')
TEST_LINE = re.compile(r'^\s*(' + '|'.join(sorted(TEST_MACROS, key=len, reverse=True)) + r')\s*\(([^()]*)\)')


def norm(p):
    return p.replace('\\', '/') if p else p


def is_testside(path):
    return bool(TESTSIDE.search(path or ''))


def fid(name, file, line):
    return f'{name}@{file}:{line}'


def test_label(src_line):
    """'TEST(Group, Name) {' -> 'TEST(Group, Name)' ; kind test|fixture"""
    m = TEST_LINE.match(src_line or '')
    if not m:
        return None, None
    label = f"{m.group(1)}({', '.join(a.strip() for a in m.group(2).split(','))})"
    return label, ('fixture' if m.group(1).startswith('TEST_GROUP') else 'test')


class Index:
    def __init__(self, d):
        self.d = d
        self.meta = d.setdefault('meta', {})
        self.functions = d.setdefault('functions', {})
        self.externals = d.setdefault('externals', {})
        self.calls = d.setdefault('calls', [])
        self.inherits = d.setdefault('inherits', [])
        self.reindex()

    @staticmethod
    def empty(backend, root, paths, cdb=''):
        import datetime
        return Index({'meta': {'schema': SCHEMA, 'backend': backend, 'root': root, 'paths': paths, 'cdb': cdb or '',
                               'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}})

    @staticmethod
    def load(path):
        d = json.load(open(path, encoding='utf-8'))
        if d.get('meta', {}).get('schema') != SCHEMA:
            raise ValueError(f'{path} is not a {SCHEMA} file')
        ix = Index(d)
        ix.path = os.path.abspath(path)
        return ix

    def runtime_reach(self):
        """function id -> tests that reached it in the last `trace` run (traces.json next to the index)"""
        p = os.path.join(os.path.dirname(getattr(self, 'path', '') or '.'), 'traces.json')
        if not os.path.exists(p):
            return None
        out = {}
        for test, fns in json.load(open(p, encoding='utf-8')).items():
            for f in fns:
                out.setdefault(f, []).append(test)
        return out

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.meta['stats'] = self.stats()
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(self.d, fh, separators=(',', ':'))

    def reindex(self):
        self.out, self.inc = {}, {}
        seen, keep = set(), []
        for c in self.calls:
            k = (c['from'], c['to'], c.get('line'), c.get('kind'))
            if k in seen or c['from'] == c['to'] and c.get('kind') not in ('direct',):
                continue
            seen.add(k); keep.append(c)
            self.out.setdefault(c['from'], []).append(c)
            self.inc.setdefault(c['to'], []).append(c)
        self.calls[:] = keep

    def node(self, nid):
        return self.functions.get(nid) or self.externals.get(nid)

    def label(self, nid):
        n = self.node(nid) or {}
        if n.get('kind') in ('test', 'fixture'):
            return n.get('label') or n['name']
        return n.get('name', nid) + '()'

    def is_ext(self, nid):
        return nid in self.externals

    def add_call(self, frm, to, line, file, kind='direct', conf='EXTRACTED'):
        self.calls.append({'from': frm, 'to': to, 'line': line, 'file': file, 'kind': kind, 'conf': conf})

    def find(self, name, include_tests=False):
        """functions called NAME / Class::NAME / NAME() ; externals too when no function matches"""
        t = name[:-2] if name.endswith('()') else name
        hits = [f for f, n in self.functions.items()
                if (include_tests or n.get('kind') not in ('test', 'fixture'))
                and (n['name'] == t or n['name'].split('::')[-1] == t or n.get('label') == t)]
        if not hits:
            hits = [e for e, n in self.externals.items() if n['name'] == t or n['name'].split('::')[-1] == t]
        return hits

    def by_file(self, file):
        f = norm(file)
        return sorted((i for i, n in self.functions.items() if n['file'] == f and n.get('kind') not in ('test', 'fixture')
                       and '.lambda@' not in n['name']),                  # lambdas: in the index, not test targets
                      key=lambda i: self.functions[i]['line'])

    def tests(self):
        return [i for i, n in self.functions.items() if n.get('kind') in ('test', 'fixture')]

    def stats(self):
        kinds = {}
        for e in self.externals.values():
            kinds[e['kind']] = kinds.get(e['kind'], 0) + 1
        return {'functions': sum(1 for n in self.functions.values() if n.get('kind') == 'function'),
                'tests': len(self.tests()), 'externals': len(self.externals), 'external_kinds': kinds,
                'calls': len(self.calls), 'with_outline': sum(1 for n in self.functions.values() if n.get('outline') is not None),
                'inherits': len(self.inherits)}

    # ------------------------------------------------------------------ classes / virtual dispatch
    def subclasses(self, cls):
        out, todo = [], [cls]
        while todo:
            c = todo.pop()
            for d, b, _ in self.inherits:
                if b.split('::')[-1] == c.split('::')[-1] and d not in out:
                    out.append(d); todo.append(d)
        return out

    def bind_virtual_targets(self):
        """a call to a virtual/pure method may run any override in a subclass: add virtual-target edges"""
        by_name = {}
        for i, n in self.functions.items():
            if n.get('cls'):
                by_name.setdefault((n['cls'].split('::')[-1], n['name'].split('::')[-1]), []).append(i)
        added = 0
        for i, n in list(self.functions.items()):
            if not (n.get('virtual') or n.get('pure')) or not n.get('cls'):
                continue
            for sub in self.subclasses(n['cls']):
                for tgt in by_name.get((sub.split('::')[-1], n['name'].split('::')[-1]), []):
                    if tgt != i and not any(c['to'] == tgt and c['from'] == i for c in self.out.get(i, [])):
                        self.add_call(i, tgt, self.functions[tgt]['line'], self.functions[tgt]['file'], 'virtual-target', 'INFERRED')
                        added += 1
        self.reindex()
        return added

    # ------------------------------------------------------------------ graph adapter
    def to_graph(self):
        """the index in Graphify's graph.json shape, so the existing deps/tests/impact code runs on any backend"""
        nodes, links = [], []
        for i, n in self.functions.items():
            g = {'id': i, 'label': self.label(i), 'source_file': n['file'], 'source_location': f"L{n['line']}", '_callable': True,
                 'type': 'code', 'static': bool(n.get('static')), 'virtual': bool(n.get('virtual')), 'pure_virtual': bool(n.get('pure'))}
            if n.get('kind') in ('test', 'fixture'):
                g['kind'] = n['kind']
            nodes.append(g)
        for i, e in self.externals.items():
            nodes.append({'id': i, 'label': e['name'] + '()', 'type': 'external', 'external': True, 'kind': e['kind'], '_callable': True,
                          'declared_in': e.get('declared_in', ''), 'source_file': '', 'source_location': '',
                          'targets': [f"{self.functions[t]['name'] if t in self.functions else t} (bound at {site})" for t, site in e.get('targets', [])]})
        classes = {}
        for d, b, f in self.inherits:
            for c in (d, b):
                classes.setdefault(c, f if c == d else '')
            links.append({'source': 'class:' + d, 'target': 'class:' + b, 'relation': 'inherits'})
        for c, f in classes.items():
            nodes.append({'id': 'class:' + c, 'label': c, 'source_file': f, 'type': 'code'})
        for c in self.calls:
            links.append({'source': c['from'], 'target': c['to'], 'relation': 'calls', 'source_file': c.get('file'),
                          'source_location': f"L{c.get('line')}", 'confidence': c.get('conf', 'EXTRACTED'), 'context': c.get('kind')})
        return {'nodes': nodes, 'links': links, 'graph': {'ut_index': self.meta.get('backend')}}


# ---------------------------------------------------------------------- outline helpers
def flatten(outline):
    """every statement of an outline, depth first"""
    for s in outline or []:
        yield s
        for k in ('then', 'else', 'b'):
            if s.get(k):
                yield from flatten(s[k])
        for c in s.get('cases', []) + s.get('h', []):
            yield from flatten(c.get('b'))


def decisions(outline):
    return [s for s in flatten(outline) if s['t'] in ('if', 'switch', 'loop', '?:')]


def outline_calls(outline):
    return [s for s in flatten(outline) if s['t'] == 'call']
