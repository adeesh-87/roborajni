"""compare A.json B.json [--limit N]: where two backends disagree (functions, call edges, tests per function).
Edges are compared by name (caller -> callee), so ids and line shifts do not matter."""
import sys
from .model import Index, is_testside


def edges(ix):
    out = set()
    for c in ix.calls:
        if c['kind'] in ('pointer-target', 'virtual-target'):
            continue
        a, b = ix.node(c['from']), ix.node(c['to'])
        if a and b:
            out.add((a['name'], b['name']))
    return out


def funcs(ix):
    return {n['name'] for n in ix.functions.values() if n.get('kind') == 'function'}


def direct_tests(ix):
    res = {}
    for i, n in ix.functions.items():
        if n.get('kind') != 'function' or is_testside(n['file']):
            continue
        res[n['name']] = res.get(n['name'], 0) + len({c['from'] for c in ix.inc.get(i, [])      # overloads summed
                                                      if ix.functions.get(c['from'], {}).get('kind') in ('test', 'fixture')})
    return res


def main(a):
    if len(a) < 2:
        sys.exit('usage: compare A_INDEX B_INDEX [--limit N]')
    lim = int(a[a.index('--limit') + 1]) if '--limit' in a else 25
    A, B = Index.load(a[0]), Index.load(a[1])
    na, nb = A.meta.get('backend'), B.meta.get('backend')
    ea, eb = edges(A), edges(B)
    fa, fb = funcs(A), funcs(B)
    print(f'# Backend comparison: {na} vs {nb}')
    print(f'| | {na} | {nb} |\n|---|---|---|')
    for k in ('functions', 'tests', 'externals', 'calls', 'with_outline'):
        print(f'| {k} | {A.stats()[k]} | {B.stats()[k]} |')
    print(f'| call edges by name | {len(ea)} | {len(eb)} |')
    print(f'| edges in both | {len(ea & eb)} | |')
    for title, s in ((f'Functions only in {na}', fa - fb), (f'Functions only in {nb}', fb - fa)):
        print(f'\n## {title} ({len(s)})')
        for x in sorted(s)[:lim]:
            print(f'- {x}')
    for title, s in ((f'Call edges only in {na}', ea - eb), (f'Call edges only in {nb}', eb - ea)):
        print(f'\n## {title} ({len(s)})')
        prod = sorted(e for e in s if not e[0].startswith(('TEST', 'IGNORE_TEST')))
        tests = len(s) - len(prod)
        for x, y in prod[:lim]:
            print(f'- {x} -> {y}')
        if len(prod) > lim:
            print(f'- ... {len(prod) - lim} more')
        if tests:
            print(f'- plus {tests} edges from TEST blocks')
    ta, tb = direct_tests(A), direct_tests(B)
    diff = sorted((k, ta.get(k, 0), tb.get(k, 0)) for k in set(ta) | set(tb) if ta.get(k, 0) != tb.get(k, 0))
    print(f'\n## Functions whose number of directly calling TEST blocks differs ({len(diff)})')
    if diff:
        print(f'| Function | {na} | {nb} |\n|---|---|---|')
        for k, x, y in diff[:lim]:
            print(f'| {k} | {x} | {y} |')
