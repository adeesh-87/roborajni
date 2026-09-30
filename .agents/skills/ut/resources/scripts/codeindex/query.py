"""Queries on the index. card has the same text format as graphify_ut's card (the ut tool parses it);
deps / tests / impact run graphify_ut's code on the index through Index.to_graph()."""
import re
from .model import decisions, is_testside, norm


def decision_line(s):
    kind = {'if': 'if', 'switch': 'switch', '?:': '?:'}.get(s['t']) or {'for': 'for', 'range': 'for', 'while': 'while', 'do': 'do-while'}[s['k']]
    extra = ''
    if s['t'] == 'if' and s.get('else') is not None:
        extra = ' (has else)'
    if s.get('n', 1) > 1:
        extra += f" [{s['n']} sub-conditions: each must flip the outcome alone]"
    if s['t'] == 'switch':
        cases = [c['v'] for c in s['cases'] if c['v'] != 'default']
        cases = [x.strip() for v in cases for x in v.split(',') if x.strip() != 'default']
        extra += f" cases: {', '.join(cases)}{' + default' if s.get('default') else ' (NO default)'}"
    tag = f"   src: {s['src']}" if s.get('src') else ''
    return f"  L{s['l']:<5} {kind:<8} {s.get('c', '')}{extra}{tag}"


def card(ix, fid):
    n = ix.functions[fid]
    L = [f"## {n['name']}  ({n['file']}:{n['line']}-{n['end']}){'  static' if n.get('static') else ''}"
         f"{'  ' + n['access'] + ' (not callable from a test: reach it through a public caller)' if n.get('access') else ''}"]
    if n.get('sig'):
        L.append(f"Signature: {n['sig']}")
    if n.get('params'):
        L.append('Params: ' + '; '.join(f'{p} ({t})' for p, t in n['params']))
    if n.get('outline') is None:
        L.append('Decisions: not available (backend without a parser for this file)')
    else:
        seen, dl = set(), []
        for s in decisions(n['outline']):
            k = (s['l'], s['t'], s.get('c'))
            if k not in seen:
                seen.add(k); dl.append(decision_line(s))
        if dl:
            L.append('Decisions (drive each outcome; loops: 0, 1, many):')
            L += dl[:40]
            if len(dl) > 40:
                L.append(f'  ... {len(dl) - 40} more')
        else:
            L.append('Decisions: none (straight-line code)')
    if n.get('returns'):
        L.append('Returns: ' + ' | '.join(n['returns'][:8]))
    g = n.get('globals') or {}
    if g.get('read') or g.get('written'):
        L.append('Globals/statics: ' + ', '.join(sorted(f'{w} (written)' for w in g.get('written', [])) + sorted(f'{r} (read)' for r in g.get('read', []))))
    calls = []
    for c in ix.out.get(fid, []):
        if c['kind'] in ('pointer-target', 'virtual-target'):
            continue
        t = ix.node(c['to'])
        if t is None:
            continue
        if ix.is_ext(c['to']):
            where = t.get('declared_in') or ''
            if t.get('targets'):
                where = 'may call ' + ', '.join(ix.functions[x]['name'] if x in ix.functions else x for x, _ in t['targets'][:3])
            calls.append(f"{t['name']}() [{t['kind']}: {where}]")
        else:
            impls = [ix.functions[x['to']]['name'] for x in ix.out.get(c['to'], []) if x['kind'] == 'virtual-target']
            st = ' static' if t.get('static') else ''
            vt = f"; overridden by {', '.join(sorted(set(impls))[:3])}" if impls else ''
            pv = ' pure virtual' if t.get('pure') else ''
            calls.append(f"{t['name']}() ({t['file']}:L{t['line']}{st}{pv}{vt})")
    if calls:
        L.append('Calls: ' + '; '.join(sorted(set(calls))))
    callers = sorted({(f"via pointer {ix.label(c['from'])}" if ix.is_ext(c['from']) else f"{ix.label(c['from'])} ({ix.node(c['from'])['file']})")
                      for c in ix.inc.get(fid, []) if ix.node(c['from']) and ix.node(c['from']).get('kind') not in ('test', 'fixture')
                      and c['kind'] != 'virtual-target'})
    if callers:
        L.append('Callers: ' + '; '.join(callers[:8]))
    tests = sorted({f"{ix.label(c['from'])} ({ix.node(c['from'])['file']}:L{ix.node(c['from'])['line']})" for c in ix.inc.get(fid, [])
                    if not ix.is_ext(c['from']) and (ix.node(c['from']).get('kind') in ('test', 'fixture')
                                                     or re.search(r'(^|/)(test|tests)/', ix.node(c['from'])['file']))})
    L.append('Existing tests calling it directly: ' + ('; '.join(tests[:8]) if tests else 'none'))
    rr = ix.runtime_reach()
    if rr is not None:
        hit = rr.get(fid, [])
        L.append(f"Tests reaching it at run time (trace): {len(hit)}" + (f" e.g. {'; '.join(hit[:3])}" if hit else ' - no test executes it'))
    return '\n'.join(L)


def cmd_card(ix, target):
    t = norm(target)
    fids = ix.by_file(t)
    if fids:
        out = [f'# Cards for {t} ({len(fids)} functions)']
        for f in fids:
            out += ['', card(ix, f)]
        return '\n'.join(out)
    hits = [h for h in ix.find(t) if h in ix.functions]
    if not hits:
        return f'## {t}: definition not found in the index'
    return '\n\n'.join(card(ix, h) for h in hits[:3])


# ---------------------------------------------------------------------------------------------- lookups that replace grep/read
def flags(n):
    f = []
    for k, word in (('static', 'static'), ('pure', 'pure virtual'), ('virtual', 'virtual')):
        if k == 'static' and n.get('cls'):
            continue                          # members of classes in an anonymous namespace: not a test-visibility fact
        if n.get(k) and not (k == 'virtual' and n.get('pure')):
            f.append(word)
    if n.get('access'):
        f.append(n['access'])
    if n.get('kind') in ('test', 'fixture'):
        f.append(n['kind'])
    elif is_testside(n['file']):
        f.append('test-side (mock/fake/helper)')
    return ', '.join(f)


def select(ix, name, include_tests=True):
    """NAME, Class::NAME, a TEST label, or NAME@LINE (the overload whose body contains LINE) -> function ids"""
    name, _, line = name.partition('@')
    t = name[:-2] if name.endswith('()') else name
    hits = [h for h in ix.find(t, include_tests=include_tests) if h in ix.functions]
    if line.isdigit():
        inside = [h for h in hits if ix.functions[h]['line'] <= int(line) <= ix.functions[h]['end']]
        hits = inside or hits
    return hits


def cmd_find(ix, pattern, exact=False, limit=60):
    """functions, TEST blocks and externals whose name matches PATTERN (regex, case-insensitive)"""
    rx = re.compile('^' + re.escape(pattern) + '$' if exact else pattern, re.I)
    rows = []
    for i, n in ix.functions.items():
        nm = n.get('label') or n['name']
        if rx.search(nm) or (exact and rx.search(nm.split('::')[-1])):
            rows.append((n['file'], n['line'], nm, f"{n['file']}:{n['line']}-{n['end']}", flags(n) or 'function'))
    for i, e in ix.externals.items():
        if rx.search(e['name']) or (exact and rx.search(e['name'].split('::')[-1])):
            rows.append(('~', 0, e['name'], e.get('declared_in', ''), f"external {e['kind']}"))
    for i, s in ix.symbols.items():
        if rx.search(s['name']) or (exact and rx.search(s['name'].split('::')[-1])):
            rows.append((s['file'], s.get('at', s['line']), s['name'], f"{s['file']}:{s.get('at', s['line'])}", s['kind']))
    rows.sort()
    out = [f'# {len(rows)} match(es) for {pattern!r} in the index' + (f' (first {limit})' if len(rows) > limit else ''),
           '| Name | Where | Kind |', '|---|---|---|']
    out += [f'| {nm} | {where} | {kind} |' for _, _, nm, where, kind in rows[:limit]]
    return '\n'.join(out)


def cmd_list(ix, file):
    """the functions of one file with line ranges (a table of contents instead of reading the file)"""
    f = norm(file)
    ids = sorted((i for i, n in ix.functions.items() if n['file'] == f), key=lambda i: ix.functions[i]['line'])
    syms = sorted((s for s in ix.symbols.values() if s['file'] == f and s['kind'] != 'enumerator'), key=lambda s: s['line'])
    if not ids and not syms:
        return f'# {f}: nothing in the index (not in the scan paths?)'
    out = [f'# {f}: {len(ids)} functions / TEST blocks, {len(syms)} types / macros / globals']
    if syms:
        out += ['| Lines | Type / macro / global | Kind |', '|---|---|---|']
        out += [f"| {s['line']}-{s['end']} | {s['name']} | {s['kind']} |" for s in syms]
    if ids:
        out += ['| Lines | Function | Decisions | Notes |', '|---|---|---|---|']
    for i in ids:
        n = ix.functions[i]
        out.append(f"| {n['line']}-{n['end']} | {n.get('label') or n['name']} | {len(decisions(n.get('outline') or []))} | {flags(n)} |")
    return '\n'.join(out)


def cmd_source(ix, name, root=None, max_lines=200):
    """the source lines of one function / TEST block (all overloads, or NAME@LINE for one)"""
    hits = select(ix, name)
    root = root or ix.meta['root']
    if not hits:                                   # a type, enum, enumerator, typedef, macro or global
        t = name.split('@')[0]
        syms = [s for s in ix.symbols.values() if s['name'] == t] or \
               [s for s in ix.symbols.values() if s['name'].split('::')[-1] == t.split('::')[-1]]
        if not syms:
            return f'# {name}: not in the index (index.sh find "{name}" lists similar names)'
        out = []
        for s in syms[:3]:
            try:
                lines = open(f"{root}/{s['file']}", encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                continue
            b = min(s['end'], s['line'] + max_lines - 1)
            out.append(f"// {s['name']}  {s['kind']}  {s['file']}:{s['line']}-{s['end']}" + (f"  (in {s['parent']}, line {s['at']})" if s.get('parent') else ''))
            out += [f'{k:>5}  {lines[k - 1]}' for k in range(s['line'], b + 1) if k - 1 < len(lines)]
            out.append('')
        return '\n'.join(out)
    out = []
    for i in hits[:3]:
        n = ix.functions[i]
        try:
            lines = open(f"{root}/{n['file']}", encoding='utf-8', errors='replace').read().splitlines()
        except OSError:
            out.append(f"// {n['file']}: file not readable"); continue
        a, b = n['line'], min(n['end'], n['line'] + max_lines - 1)
        out.append(f"// {n.get('label') or n['name']}  {n['file']}:{n['line']}-{n['end']}" + (f'  {flags(n)}' if flags(n) else ''))
        out += [f'{k:>5}  {lines[k - 1]}' for k in range(a, b + 1) if k - 1 < len(lines)]
        if b < n['end']:
            out.append(f'  ... {n["end"] - b} more lines')
        out.append('')
    if len(hits) > 3:
        out.append(f'... {len(hits) - 3} more definitions: use NAME@LINE')
    return '\n'.join(out)


def cmd_refs(ix, name):
    """everything the index knows that uses or defines NAME: callers with call lines, TEST blocks, test doubles,
    pointer bindings, overrides. Replaces `grep -rn NAME` for code questions."""
    t = name[:-2] if name.endswith('()') else name
    tgts = select(ix, t) + [e for e in ix.find(t) if e in ix.externals]
    short = t.split('@')[0].split('::')[-1]
    if not tgts:
        return f'# {name}: not in the index (index.sh find "{short}" lists similar names)'
    out = [f'# References to {t}']
    for i in dict.fromkeys(tgts):
        n = ix.node(i)
        where = f"{n['file']}:{n['line']}-{n['end']}" if i in ix.functions else n.get('declared_in', '')
        out.append(f"\n## {ix.label(i)}  {where}" + (f'  {flags(n)}' if i in ix.functions and flags(n) else ''))
        callers, tests, via_ptr, impls = [], [], [], []
        for c in ix.inc.get(i, []):
            src = ix.node(c['from'])
            if src is None:
                continue
            if c['kind'] == 'virtual-target':
                continue
            if c['from'] in ix.externals:
                via_ptr.append(f"{src['name']} (a pointer; bound at {', '.join(s for t2, s in src.get('targets', []) if t2 == i) or '?'})")
            elif src.get('kind') in ('test', 'fixture'):
                tests.append(f"{ix.label(c['from'])}  {src['file']}:L{c.get('line')}")
            else:
                callers.append(f"{src['name']}  {src['file']}:L{c.get('line')}{'  (test-side)' if is_testside(src['file']) else ''}")
        for c in ix.out.get(i, []):
            if c['kind'] == 'virtual-target':
                impls.append(f"{ix.functions[c['to']]['name']}  {ix.functions[c['to']]['file']}:{ix.functions[c['to']]['line']}")
        for title, rows in (('Called by', callers), ('TEST blocks calling it', tests), ('Called through', via_ptr),
                            ('Overridden by', impls)):
            if rows:
                rows = sorted(set(rows))
                out.append(f'{title} ({len(rows)}):')
                out += [f'- {r}' for r in rows[:25]] + ([f'- ... {len(rows) - 25} more'] if len(rows) > 25 else [])
        if not (callers or tests or via_ptr):
            out.append('No calls to it in the index.')
    same = [(n['file'], n['line'], n['name']) for i, n in ix.functions.items()
            if n['name'].split('::')[-1] == short and i not in tgts]
    if same:
        out.append(f'\n## Other definitions named {short} (overloads, mocks, fakes)')
        out += [f'- {nm}  {f}:{l}' for f, l, nm in sorted(same)]
    out.append('\nThe index covers calls, definitions and pointer bindings. Uses inside macro bodies, strings, comments and '
               'build files are not in it: before DELETING code, confirm with a text search.')
    return '\n'.join(out)
