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
