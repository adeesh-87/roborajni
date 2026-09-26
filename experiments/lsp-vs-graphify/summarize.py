#!/usr/bin/env python3
"""summarize.py RESULTS.json : per codebase x arm (and per task) tables of the agent runs, in Markdown."""
import json, sys, statistics as st
from collections import defaultdict

rows = json.load(open(sys.argv[1]))


def agg(rs):
    n = len(rs)
    cov = [r['coverage'] for r in rs if r['coverage'] and r['coverage']['branches']]
    br = [c['branches_taken'] / c['branches'] for c in cov]
    brs = [((r['coverage'] or {}).get('branches_taken', 0) / r['coverage']['branches']) if r.get('coverage') and r['coverage']['branches'] else 0.0
           for r in rs]                                                  # a run with no building test counts as 0
    tools = defaultdict(int)
    for r in rs:
        for k, v in r['tools'].items():
            tools[k] += v
    q = sum(v for k, v in tools.items() if k.startswith('q '))
    return {'runs': n, 'done': sum(r['result'] == 'DONE' for r in rs), 'pass': sum(r['passes'] for r in rs),
            'branch_mean': st.mean(brs) if brs else 0, 'branch_full': sum(b >= 0.999 for b in brs),
            'cost': st.mean(r['cost_usd'] or 0 for r in rs), 'turns': st.mean(r['turns'] or 0 for r in rs),
            'time': st.mean(r['duration_s'] or 0 for r in rs), 'q_calls': q / n, 'builds_run': tools.get('ut_run', 0) / n,
            'denied': st.mean(r['denied'] for r in rs), 'tokens': st.mean(r['input_tokens'] + (r['output_tokens'] or 0) for r in rs)}


by = defaultdict(list)
for r in rows:
    by[(r['codebase'], r['arm'])].append(r)
    by[(r['codebase'], r['arm'], r['task'])].append(r)
    by[('all', r['arm'])].append(r)

print('| Codebase | Arm | Runs | Tests pass | RESULT: DONE | Branch cov. (mean) | 100% branches | Cost/run | Turns | Time/run | Tool queries | Builds | Denied |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for cb in sorted({r['codebase'] for r in rows}) + ['all']:
    for arm in ('graphify', 'clangd'):
        a = agg(by[(cb, arm)])
        print(f"| {cb} | {arm} | {a['runs']} | {a['pass']}/{a['runs']} | {a['done']}/{a['runs']} | {a['branch_mean']:.0%} | {a['branch_full']}/{a['runs']} | "
              f"${a['cost']:.2f} | {a['turns']:.0f} | {a['time']:.0f} s | {a['q_calls']:.1f} | {a['builds_run']:.1f} | {a['denied']:.1f} |")
print()
print('| Codebase | Task | Graphify: pass, branch cov. per run | clangd: pass, branch cov. per run | Graphify $ | clangd $ |')
print('|---|---|---|---|---|---|')
for cb, task in sorted({(r['codebase'], r['task']) for r in rows}):
    cells = []
    for arm in ('graphify', 'clangd'):
        rs = sorted(by[(cb, arm, task)], key=lambda r: r['run'])
        cells.append(' '.join(('✓' if r['passes'] else '✗') + (f"{r['coverage']['branches_taken']}/{r['coverage']['branches']}" if r.get('coverage') else '-')
                              for r in rs))
    costs = [agg(by[(cb, arm, task)])['cost'] for arm in ('graphify', 'clangd')]
    print(f'| {cb} | {task} | {cells[0]} | {cells[1]} | {costs[0]:.2f} | {costs[1]:.2f} |')
