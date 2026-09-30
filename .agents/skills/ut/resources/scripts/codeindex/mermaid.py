"""Mermaid TEXT views of the index, written for an agent to read (never rendered): no styling, every node carries
its source line, branches are labelled T/F, coverage and test-double facts are written into the diagram.

  flow      INDEX FUNCTION [--no-cov]            flowchart of one function (coverage on the T/F edges if imported)
  seq       INDEX FUNCTION [--depth 1] [--max N] static sequence diagram: calls in order, alt/opt/loop from the
                                                 branches, participants marked with their test doubles
  scenarios INDEX OUT_DIR [--depth N]            one sequence per entry point + SCENARIOS.md (overview + catalog)
  diagrams  INDEX OUT_DIR [--min-decisions N]    flow/seq files for every function worth one + INDEX.md
"""
import os, re, sys
from .model import Index, decisions, flatten, is_testside
from . import coverage as COV

LEGEND_FLOW = '%% Lnn = source line. T/F = condition true/false. "Nx" = times taken in the imported coverage run; NOT HIT = never taken.'
LEGEND_SEQ = '%% Lnn = call site line. alt/opt/loop = the branch or loop around the calls. Participant notes name existing test doubles.'


def esc(t, n=70):
    t = ' '.join(str(t or '').split()).replace('"', "'")
    return t if len(t) <= n else t[:n - 3] + '...'


def ident(name):
    return re.sub(r'\W+', '_', name).strip('_') or 'x'


def slug(name):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', name.replace('::', '__')).strip('_')[:80] or 'fn'


# ---------------------------------------------------------------------------------------------- flowchart
class Flow:
    def __init__(self, ix, fid, fc):
        self.ix, self.fid, self.fc = ix, fid, fc
        self.nodes, self.edges, self.ids = [], [], set()

    def new(self, prefix, line, shape, text):
        base = f'{prefix}{line}'
        i, k = base, 1
        while i in self.ids:
            k += 1; i = f'{base}_{k}'
        self.ids.add(i)
        o, c = {'box': ('["', '"]'), 'dec': ('{"', '"}'), 'end': ('(["', '"])')}[shape]
        self.nodes.append(f'  {i}{o}{esc(text, 80)}{c}')
        return i

    def link(self, entries, target):
        for src, lab in entries:
            self.edges.append(f'  {src} -->|"{lab}"| {target}' if lab else f'  {src} --> {target}')

    def lab(self, base, n):
        if n is None:
            return base
        return f'{base} NOT HIT' if n == 0 else f'{base} {n}x'

    def build(self, items, entries, ctx):
        calls = []

        def flush(entries):
            if not calls:
                return entries
            txt = '; '.join(f"L{c['l']} {c['f']}()" for c in calls[:4]) + (f' +{len(calls) - 4} more' if len(calls) > 4 else '')
            b = self.new('c', calls[0]['l'], 'box', txt)
            self.link(entries, b)
            calls.clear()
            return [(b, '')]
        for s in items:
            t = s['t']
            if t == 'call':
                calls.append(s); continue
            entries = flush(entries)
            o = COV.outcome(self.fc, s) if self.fc is not None and t in ('if', '?:', 'loop', 'switch') else None
            if t in ('if', '?:'):
                cond = s.get('c', '')
                extra = f" [{s['n']} sub-conditions]" if s.get('n', 1) > 1 else ''
                d = self.new('d', s['l'], 'dec', f"L{s['l']} {'if' if t == 'if' else '?:'} {cond}{extra}")
                self.link(entries, d)
                tl = self.lab('T', o.get('T') if o else None)
                fl = self.lab('F', o.get('F') if o else None)
                if o and o.get('partial'):
                    tl, fl = f"T ({o['partial']})", 'F'
                elif o and o.get('all'):
                    tl, fl = f"T ({o['all']})", 'F'
                if t == '?:':
                    entries = [(d, tl), (d, fl)]; continue
                ex = self.build(s.get('then') or [], [(d, tl)], ctx)
                ex += self.build(s['else'], [(d, fl)], ctx) if s.get('else') is not None else [(d, fl)]
                entries = ex
            elif t == 'switch':
                d = self.new('d', s['l'], 'dec', f"L{s['l']} switch {s.get('c', '')}")
                self.link(entries, d)
                sw = {'brk': [], 'cont': ctx.get('cont')}
                out, ft = [], []
                cases = (o or {}).get('cases', {})
                for c in s['cases']:
                    ex = self.build(c['b'], [(d, self.lab('case ' + esc(c['v'], 30), cases.get(c['v'])))] + ft, sw)
                    ft = ex if c.get('ft', True) else []
                    if not c.get('ft', True):
                        out += ex
                out += ft + sw['brk']
                if not s.get('default'):
                    out.append((d, 'no case matches'))
                entries = out
            elif t == 'loop':
                d = self.new('d', s['l'], 'dec', f"L{s['l']} {s['k'] if s['k'] != 'range' else 'for'} {s.get('c', '')}")
                self.link(entries, d)
                lp = {'brk': [], 'cont': d}
                body = self.build(s.get('b') or [], [(d, self.lab('loop', o.get('body') if o else None))], lp)
                self.link(body, d)
                entries = [(d, self.lab('done', o.get('exit') if o else None))] + lp['brk']
            elif t in ('ret', 'throw', 'goto'):
                word = {'ret': 'return', 'throw': 'throw', 'goto': 'goto'}[t]
                r = self.new('r', s['l'], 'end', f"L{s['l']} {word} {s.get('v', '')}".strip())
                self.link(entries, r)
                entries = []
            elif t == 'brk':
                if ctx.get('brk') is not None:
                    ctx['brk'].extend(entries)
                entries = []
            elif t == 'cont':
                if ctx.get('cont'):
                    self.link(entries, ctx['cont'])
                entries = []
            elif t == 'try':
                start = entries
                entries = self.build(s.get('b') or [], entries, ctx)
                for h in s.get('h', []):
                    hd = self.new('h', s['l'], 'box', f"L{s['l']} catch {h.get('v', '')}")
                    self.link([(x, 'throws') for x, _ in start] or [('S', 'throws')], hd)
                    entries += self.build(h.get('b') or [], [(hd, '')], ctx)
        return flush(entries)

    def render(self):
        n = self.ix.functions[self.fid]
        head = [f"%% Flow of {n['name']}  {n['file']}:{n['line']}-{n['end']}", LEGEND_FLOW]
        gaps = COV.gaps_of(n, self.fc) if self.fc is not None else []
        if self.fc is not None:
            head.append(f"%% Coverage: {'missing outcomes: ' + '; '.join(f'L{l} {t}' for l, t in gaps) if gaps else 'every measured outcome was hit'}")
        self.ids.add('S')
        self.nodes.append('  S(["start"])')
        ex = self.build(n.get('outline') or [], [('S', '')], {})
        if ex:
            self.ids.add('E')
            self.nodes.append('  E(["end"])')
            self.link(ex, 'E')
        return '\n'.join(head + ['flowchart TD'] + self.nodes + self.edges) + '\n'


def flow(ix, fid, cov=None):
    n = ix.functions[fid]
    fc = cov['files'].get(n['file']) if cov else None
    return Flow(ix, fid, fc).render()


# ---------------------------------------------------------------------------------------------- sequence
class Seq:
    def __init__(self, ix, depth=1, max_msgs=60):
        self.ix, self.depth, self.max = ix, depth, max_msgs
        self.parts, self.lines, self.msgs, self.cut = {}, [], 0, 0
        self.doubles = self.test_doubles()

    def test_doubles(self):
        """class/interface -> test-side subclasses; function name -> test-side definitions"""
        cls, fns = {}, {}
        for d, b, f in self.ix.inherits:
            if is_testside(f):
                cls.setdefault(b.split('::')[-1], []).append(f'{d} ({f})')
        for i, n in self.ix.functions.items():
            if n.get('kind') == 'function' and is_testside(n['file']):
                fns.setdefault(n['name'].split('::')[-1], []).append(n['file'])
        return cls, fns

    def owner(self, nid):
        ix = self.ix
        if nid is None:
            return 'unresolved', 'unresolved call (see the card)'
        if nid in ix.externals:
            e = ix.externals[nid]
            if e['kind'] == 'pointer':
                tg = ', '.join(ix.functions[t]['name'] for t, _ in e.get('targets', [])[:3] if t in ix.functions)
                return f"ptr:{e['name']}", f"function pointer {e['name']}" + (f'; may call {tg}' if tg else '; no known target')
            if e['kind'] == 'library':
                return 'library', 'library code (runs for real in tests)'
            mod = os.path.splitext(os.path.basename(e.get('declared_in') or 'external'))[0]
            doubles = self.doubles[1].get(e['name'].split('::')[-1], [])
            return f'ext:{mod}', (f"{mod} (declared in {e.get('declared_in')}; no definition in scope" +
                                  (f"; test double in {', '.join(sorted(set(doubles)))})" if doubles else ': tests need a stub/mock)'))
        n = ix.functions[nid]
        if n.get('cls'):
            c = n['cls'].split('::')[-1]
            ds = self.doubles[0].get(c, [])
            pure = any(x.get('pure') and (x.get('cls') or '').split('::')[-1] == c for x in ix.functions.values())
            note = ('interface' if pure else 'class') + (f"; test doubles: {', '.join(ds[:3])}" if ds else '')
            if is_testside(n['file']):
                note = f"test double in {n['file']}"
            return f'cls:{c}', f'{c} ({note})'
        mod = os.path.splitext(os.path.basename(n['file']))[0]
        if is_testside(n['file']):
            return f'mod:{mod}', f"{mod} (test double / helper in {n['file']})"
        return f'mod:{mod}', f"{mod} ({n['file']})"

    def pid(self, key, label):
        if key not in self.parts:
            base = re.sub(r'\W+', '_', key.split(':', 1)[-1]).strip('_')[:30] or 'P'
            base = base if base[0].isalpha() else 'P' + base
            used = {v[0] for v in self.parts.values()}
            i, k = base, 1
            while i in used:
                k += 1; i = f'{base}{k}'
            self.parts[key] = (i, label)
        return self.parts[key][0]

    def emit(self, ind, text):
        self.lines.append('  ' * ind + text)

    def has_content(self, items, top=True):
        kinds = ('call', 'ret', 'throw') if top else ('call',)       # inside callees only calls matter
        return any(s['t'] in kinds for s in flatten(items))

    def items(self, items, me, depth, ind, stack, top):
        for s in items:
            t = s['t']
            if t == 'call':
                if self.msgs >= self.max:
                    self.cut += 1; continue
                tgt = s.get('to')
                key, label = self.owner(tgt)
                who = self.pid(key, label)
                self.msgs += 1
                self.emit(ind, f"{me}->>{who}: L{s['l']} {esc(s['f'], 50)}()")
                if tgt in self.ix.functions and depth > 0 and tgt not in stack:
                    n = self.ix.functions[tgt]
                    if n.get('outline') and self.has_content(n['outline'], False) and n.get('kind') == 'function':
                        self.items(n['outline'], who, depth - 1, ind, stack + [tgt], False)
                elif tgt in self.ix.externals and self.ix.externals[tgt].get('targets') and depth > 0:
                    tg = [t for t, _ in self.ix.externals[tgt]['targets'] if t in self.ix.functions]
                    if len(tg) == 1 and tg[0] not in stack:
                        n = self.ix.functions[tg[0]]
                        k2, l2 = self.owner(tg[0])
                        w2 = self.pid(k2, l2)
                        self.msgs += 1
                        self.emit(ind, f"{who}->>{w2}: {esc(n['name'], 50)}() (bound target)")
                        if n.get('outline') and self.has_content(n['outline'], False):
                            self.items(n['outline'], w2, depth - 1, ind, stack + [tg[0]], False)
            elif t == 'if':
                if not self.has_content((s.get('then') or []) + (s.get('else') or []), top):
                    continue
                if s.get('else') is not None and self.has_content(s['else'], top):
                    self.emit(ind, f"alt L{s['l']} {esc(s.get('c'))}")
                    self.items(s.get('then') or [], me, depth, ind + 1, stack, top)
                    self.emit(ind, f"else not ({esc(s.get('c'), 50)})")
                    self.items(s['else'], me, depth, ind + 1, stack, top)
                else:
                    self.emit(ind, f"opt L{s['l']} {esc(s.get('c'))}")
                    self.items(s.get('then') or [], me, depth, ind + 1, stack, top)
                self.emit(ind, 'end')
            elif t == 'switch':
                cs = [c for c in s['cases'] if self.has_content(c['b'], top)]
                if not cs:
                    continue
                for k, c in enumerate(cs):
                    self.emit(ind, f"{'alt' if k == 0 else 'else'} L{c['l']} case {esc(c['v'], 40)} (switch {esc(s.get('c'), 30)})")
                    self.items(c['b'], me, depth, ind + 1, stack, top)
                self.emit(ind, 'end')
            elif t == 'loop':
                if not self.has_content(s.get('b') or [], top):
                    continue
                self.emit(ind, f"loop L{s['l']} {s['k'] if s['k'] != 'range' else 'for'} {esc(s.get('c'))}")
                self.items(s.get('b') or [], me, depth, ind + 1, stack, top)
                self.emit(ind, 'end')
            elif t == 'try':
                self.emit(ind, f"critical L{s['l']} try")
                self.items(s.get('b') or [], me, depth, ind + 1, stack, top)
                for h in s.get('h', []):
                    self.emit(ind, f"option catch {esc(h.get('v'), 40)}")
                    self.items(h.get('b') or [], me, depth, ind + 1, stack, top)
                self.emit(ind, 'end')
            elif t in ('ret', 'throw') and top:
                word = 'return' if t == 'ret' else 'throw'
                if top and ind == 1 and t == 'ret':
                    self.emit(ind, f"{me}-->>Caller: L{s['l']} return {esc(s.get('v'), 40)}")
                else:
                    self.emit(ind, f"Note over {me}: L{s['l']} {word} {esc(s.get('v'), 40)}")

    def render(self, fid):
        n = self.ix.functions[fid]
        key, label = self.owner(fid)
        me = self.pid(key, label)
        self.emit(1, f"Caller->>{me}: {esc(n['name'], 60)}()")
        self.items(n.get('outline') or [], me, self.depth, 1, [fid], True)
        if self.cut:
            self.emit(1, f"Note over {me}: ... {self.cut} more calls not shown (limit {self.max}); see the cards")
        head = [f"%% Sequence of {n['name']}  {n['file']}:{n['line']}-{n['end']}  (callees expanded {self.depth} level(s) deep)", LEGEND_SEQ,
                'sequenceDiagram', '  participant Caller as Caller (the test)']
        for k, (i, lab) in self.parts.items():
            head.append(f'  participant {i} as {esc(lab, 140)}')
        return '\n'.join(head + self.lines) + '\n'


def seq(ix, fid, depth=1, max_msgs=60):
    return Seq(ix, depth, max_msgs).render(fid)


# ---------------------------------------------------------------------------------------------- catalogs
def entry_points(ix):
    out = []
    for i, n in ix.functions.items():
        if n.get('kind') != 'function' or is_testside(n['file']) or n.get('static') or n.get('pure') or '.lambda@' in n['name']:
            continue
        short = n['name'].split('::')[-1]
        if n.get('cls') and (short == n['cls'].split('::')[-1] or short.startswith('~')):
            continue
        prod_callers = [c for c in ix.inc.get(i, []) if c['from'] in ix.functions and ix.functions[c['from']].get('kind') == 'function'
                        and not is_testside(ix.functions[c['from']]['file']) and c['kind'] not in ('virtual-target',)]
        via_ptr = any(c['from'] in ix.externals for c in ix.inc.get(i, []))
        ncalls = sum(1 for s in flatten(n.get('outline') or []) if s['t'] == 'call')
        if (not prod_callers and not via_ptr and ncalls >= 1) or re.search(r'(^|_)(main|isr|irq|handler|task|thread)(_|$)', short, re.I):
            out.append(i)
    return sorted(out, key=lambda i: (ix.functions[i]['file'], ix.functions[i]['line']))


def module_of(ix, nid):
    s = Seq(ix)
    return s.owner(nid)[0].split(':', 1)[-1]


def scenarios(ix, out_dir, depth=3):
    os.makedirs(os.path.join(out_dir, 'scenarios'), exist_ok=True)
    rows, agg = [], {}
    for i in entry_points(ix):
        n = ix.functions[i]
        s = Seq(ix, depth, 60)
        text = s.render(i)
        f = os.path.join('scenarios', slug(n['name']) + '.md')
        open(os.path.join(out_dir, f), 'w', encoding='utf-8').write(text)
        parts = [lab.split(' (')[0] for _, lab in s.parts.values()]
        rows.append((n['name'], f"{n['file']}:{n['line']}", len(parts), s.msgs, f))
    for c in ix.calls:
        a, b = c['from'], c['to']
        if a in ix.functions and ix.functions[a].get('kind') == 'function' and not is_testside(ix.functions[a]['file']) \
                and c['kind'] not in ('virtual-target', 'pointer-target'):
            ma, mb = module_of(ix, a), module_of(ix, b)
            if ma != mb:
                agg[(ma, mb)] = agg.get((ma, mb), 0) + 1
    L = ['# Scenarios', f"Generated from the {ix.meta.get('backend')} index ({ix.meta.get('generated')}). One scenario per entry point "
         '(a public function no production code calls). Each file is a Mermaid sequence diagram written for reading, not rendering.', '',
         '## Module overview (production calls between modules; number = call sites)', '```mermaid', 'flowchart LR']
    for (a, b), k in sorted(agg.items()):
        L.append(f'  {ident(a)} -->|{k}| {ident(b)}')
    L += ['```', '', '## Catalog', '| Scenario (entry point) | Defined at | Participants | Messages | File |', '|---|---|---|---|---|']
    L += [f'| {a} | {b} | {c} | {d} | {e} |' for a, b, c, d, e in rows]
    open(os.path.join(out_dir, 'SCENARIOS.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return rows


def diagrams(ix, out_dir, cov=None, min_dec=2, depth=1):
    """flow for functions with >= min_dec decisions, seq for functions that call another participant; INDEX.md"""
    rows = []
    for i, n in sorted(ix.functions.items(), key=lambda kv: (kv[1]['file'], kv[1]['line'])):
        if n.get('kind') != 'function' or is_testside(n['file']) or not n.get('outline'):
            continue
        mod = os.path.splitext(os.path.basename(n['file']))[0]
        nd = len(decisions(n['outline']))
        f_flow = f_seq = ''
        if nd >= min_dec:
            f_flow = os.path.join('flow', mod, slug(n['name']) + '.md')
            os.makedirs(os.path.join(out_dir, os.path.dirname(f_flow)), exist_ok=True)
            open(os.path.join(out_dir, f_flow), 'w', encoding='utf-8').write(flow(ix, i, cov))
        s = Seq(ix, depth, 60)
        text = s.render(i)
        if len(s.parts) >= 2 or any(k.startswith(('ptr:', 'ext:')) for k in s.parts):
            f_seq = os.path.join('seq', mod, slug(n['name']) + '.md')
            os.makedirs(os.path.join(out_dir, os.path.dirname(f_seq)), exist_ok=True)
            open(os.path.join(out_dir, f_seq), 'w', encoding='utf-8').write(text)
        if f_flow or f_seq:
            rows.append((n['name'], n['file'], nd, f_flow, f_seq))
    sc = scenarios(ix, out_dir, depth + 2)
    L = ['# Diagrams (Mermaid text for the agent)', f"Index backend: {ix.meta.get('backend')}; coverage: {cov['source'] + ' ' + cov['generated'] if cov else 'not imported'}.",
         'flow = flowchart of one function (branches, T/F, coverage). seq = calls in order with the branches around them and '
         'the test doubles of each participant. SCENARIOS.md = one sequence per entry point.', '',
         '| Function | File | Decisions | Flow | Sequence |', '|---|---|---|---|---|']
    L += [f'| {a} | {b} | {c} | {d or "-"} | {e or "-"} |' for a, b, c, d, e in rows]
    open(os.path.join(out_dir, 'INDEX.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return rows, sc


# ---------------------------------------------------------------------------------------------- CLI
def pick(ix, name):
    """NAME, or NAME@LINE to choose the overload whose definition contains LINE"""
    name, _, line = name.partition('@')
    t = name[:-2] if name.endswith('()') else name
    hits = [h for h in ix.find(t, include_tests=True) if h in ix.functions]
    if not hits:
        sys.exit(f'function not found in the index: {name}')
    if line.isdigit():
        inside = [h for h in hits if ix.functions[h]['line'] <= int(line) <= ix.functions[h]['end']]
        return (inside or hits)[0]
    return hits[0]


def main(cmd, a):
    if not a:
        print(__doc__); sys.exit(2)
    ix = Index.load(a[0])
    cov = None if '--no-cov' in a else COV.load(a[0])

    def opt(k, d):
        return int(a[a.index(k) + 1]) if k in a else d
    if cmd == 'flow':
        print(flow(ix, pick(ix, a[1]), cov), end='')
    elif cmd == 'seq':
        print(seq(ix, pick(ix, a[1]), opt('--depth', 1), opt('--max', 60)), end='')
    elif cmd == 'scenarios':
        rows = scenarios(ix, a[1], opt('--depth', 3))
        print(f'{len(rows)} scenarios -> {a[1]}/SCENARIOS.md')
    elif cmd == 'diagrams':
        rows, sc = diagrams(ix, a[1], cov, opt('--min-decisions', 2), opt('--depth', 1))
        print(f"diagrams: {sum(1 for r in rows if r[3])} flowcharts, {sum(1 for r in rows if r[4])} sequences, {len(sc)} scenarios -> {a[1]}/INDEX.md")
