#!/usr/bin/env python3
"""bench_sites.py NAME GT.json GRAPHIFY_INDEX.json ROOT CDB_DIR OUT.json DIR... : "which lines call F?" for every
production function F, answered by grep (the baseline), Graphify and clangd, scored against GCC's call sites.

  grep -w      grep -rnw NAME DIR...            (the first thing an agent types)
  grep call    grep -rnE '\\bNAME\\s*\\(' DIR...   (a careful agent: only lines that look like calls)
  graphify     index.json calls into F, with their call lines
  clangd       textDocument/references at F (what `clangd_cli.py refs` prints)
Scored per call-site line (file, line; +-2 lines, see match()). Precision is also what the agent must read: every returned line that is not
a call of F is noise. NAME is the last component (method name without class), as an agent would grep it."""
import json, os, re, subprocess, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import load_gt, GraphifyArm, ClangdArm, is_test_file, kind_of   # noqa: E402
from clangd_cli import uri, path_of   # noqa: E402

SRC = ['--include=*.c', '--include=*.h', '--include=*.cpp', '--include=*.hpp', '--include=*.cc']


def truth_sites(gt_path, nodes):
    """F key -> {(file, line)} of every direct call of F in the repo (GCC)"""
    g = json.load(open(gt_path))
    by_sig, by_name = collections.defaultdict(list), collections.defaultdict(list)
    for k, v in nodes.items():
        by_sig[v.get('sig')].append(k)
        by_name[v['name']].append(k)
    sites = collections.defaultdict(set)
    for s, t, name, line, sig in g['edges']:
        if not line:
            continue
        if t in nodes:
            k = t
        else:
            c = by_sig.get(sig, [])
            if len(c) != 1:                       # declaration only in this unit: a unique name finds the definition
                c = [x for x in nodes if nodes[x]['name'].split('::')[-1] == name.split('::')[-1] and name.endswith(nodes[x]['name'])]
            if len(c) != 1:
                continue
            k = c[0]
        sites[k].add((s.split(':')[0], line))
    return sites


def match(got, want, tol=2):
    """returned lines that are a call of F: same file, within tol lines of a GCC call site (GCC reports a call inside a
    multi-line macro argument at the macro's first line). Each true site is matched once."""
    free = set(want)
    tp = 0
    for f, l in sorted(got):
        best = min((abs(l - wl), (wf, wl)) for wf, wl in free if wf == f and abs(l - wl) <= tol) if any(wf == f and abs(l - wl) <= tol for wf, wl in free) else None
        if best:
            free.discard(best[1])
            tp += 1
    return tp, set(want) - free


def grep_sites(root, dirs, pattern, fixed_word):
    cmd = ['grep', '-rn'] + (['-w', '-F', '-e', pattern] if fixed_word else ['-E', '-e', pattern]) + SRC + [d for d in dirs if os.path.exists(os.path.join(root, d))]
    out = subprocess.run(cmd, cwd=root, capture_output=True, text=True).stdout
    res = set()
    for l in out.splitlines():
        m = re.match(r'^(.+?):(\d+):', l)
        if m:
            res.add((os.path.normpath(m.group(1)), int(m.group(2))))
    return res


def main(name, gt, gix, root, cdb, out, *dirs):
    nodes, edges, virt, psites, neutral = load_gt(gt, root)
    sites = truth_sites(gt, nodes)
    qs = {k: v for k, v in nodes.items() if not v.get('pure') and not is_test_file(v['file']) and kind_of(v['name']) == 'named'
          and not v['name'].startswith('TEST@') and v['name'] != 'main'}
    gfy = GraphifyArm(gix, root)
    ix = json.load(open(gix))
    calls_to = collections.defaultdict(set)
    for c in ix['calls']:
        if c['to'] in gfy.fn and c.get('line'):
            calls_to[c['to']].add((gfy.rel(c['file']), c['line']))
    cl = ClangdArm(root, cdb, with_refs=False)
    score = {a: [0, 0, 0, 0] for a in ('grep -w', 'grep call', 'graphify', 'clangd')}   # tp fp fn returned
    per = []
    t = collections.defaultdict(float)
    for k, v in sorted(qs.items()):
        want = sites.get(k, set())
        short = v['name'].split('::')[-1]
        ans = {}
        t0 = time.time(); ans['grep -w'] = grep_sites(root, dirs, short, True); t['grep -w'] += time.time() - t0
        t0 = time.time(); ans['grep call'] = grep_sites(root, dirs, r'\b' + re.escape(short) + r'\s*\(', False); t['grep call'] += time.time() - t0
        i = gfy.node(v['file'], v['line'], v['name'])
        ans['graphify'] = calls_to.get(i, set()) if i else set()
        t0 = time.time()
        p = os.path.join(cl.root, v['file'])
        refs = cl.c.request('textDocument/references', {'textDocument': {'uri': uri(p)}, 'position': cl.position(v),
                                                         'context': {'includeDeclaration': False}}) or []
        ans['clangd'] = {(cl.c.rel(path_of(r['uri'])), r['range']['start']['line'] + 1) for r in refs}
        t['clangd'] += time.time() - t0
        row = {'fn': v['name'], 'at': k, 'calls': len(want)}
        for a, got in ans.items():
            got = {x for x in got if not x[0].startswith(('/', '..', 'lib/unity'))}
            tp, hit = match(got, want)
            fp, fn = len(got) - tp, len(want) - len(hit)
            s = score[a]
            s[0] += tp; s[1] += fp; s[2] += fn; s[3] += len(got)
            row[a] = {'tp': tp, 'fp': fp, 'fn': fn, 'missed': sorted(f'{f}:{l}' for f, l in want - hit)[:8]}
        per.append(row)
    cl.c.close()
    n = len(qs)
    print(f'== {name}: {n} production functions, {sum(len(sites.get(k, ())) for k in qs)} call sites (GCC)')
    print(f"  {'':10s} {'precision':>9s} {'recall':>7s} {'F1':>6s} {'lines returned/question':>24s} {'ms/question':>12s}")
    rep = {}
    for a, (tp, fp, fn, ret) in score.items():
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 1.0
        f = 2 * p * r / (p + r) if p + r else 0
        rep[a] = {'tp': tp, 'fp': fp, 'fn': fn, 'precision': round(p, 3), 'recall': round(r, 3), 'f1': round(f, 3),
                  'returned_per_q': round(ret / n, 1), 'ms_per_q': round(1000 * t[a] / n, 1)}
        print(f'  {a:10s} {p:9.3f} {r:7.3f} {f:6.3f} {ret / n:24.1f} {1000 * t[a] / n:12.1f}')
    json.dump({'codebase': name, 'questions': n, 'scores': rep, 'per_function': per}, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:7], *sys.argv[7:])
