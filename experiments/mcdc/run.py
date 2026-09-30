#!/usr/bin/env python3
"""run.py: can Haiku raise MC/DC with clang 18 as the measuring tool? Two arms, same task, same permissions (code may be
read and grepped); they differ only in what ./mcdc.sh prints after each build:
  suggest   the ut index's MC/DC gap list: per missing condition, the condition values of the test that completes a pair
  raw       plain llvm-cov show -show-mcdc blocks of the decisions below 100%
  run.py prepare | run [--runs 3] [--jobs 3] | score
"""
import glob, json, os, re, shutil, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, '..', '..'))
SCRIPTS = os.path.join(REPO, '.agents', 'skills', 'ut', 'resources', 'scripts')
BASE = os.environ.get('MCDC_EXP_DIR', '/tmp/claude-0/mcdc-exp')
MODEL = 'claude-haiku-4-5-20251001'
STARTER = ('// MC/DC tests. Include project and standard headers ABOVE the CppUTest include (CppUTest redefines new/delete).\n'
           '#include "CppUTest/TestHarness.h"\n')
VIEW_TEXT = {
    'suggest': 'for each condition not yet shown independent, the condition values of a test that would complete an '
               'independence pair (and the existing run it pairs with)',
    'raw': 'the llvm-cov MC/DC report (conditions, executed test vectors, covered pairs) of every decision below 100%',
}


def sh(cmd, cwd=None, env=None, timeout=1800):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=True, text=True, env=env, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def prepare():
    base = os.path.join(BASE, 'base')
    shutil.rmtree(BASE, ignore_errors=True)
    shutil.copytree(os.path.join(REPO, 'examples', 'cvaccel'), base, ignore=shutil.ignore_patterns('build*', '.cache'))
    open(os.path.join(base, 'tests', 'mcdc_test.cpp'), 'w').write(STARTER)
    cm = os.path.join(base, 'tests', 'CMakeLists.txt')
    t = open(cm).read().replace('  ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp\n', '  ${CMAKE_CURRENT_SOURCE_DIR}/mcdc_test.cpp\n  ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp\n')
    open(cm, 'w').write(t)
    shutil.copy(os.path.join(HERE, 'mcdc.sh'), base)
    sh('git init -q && git add -A && git -c user.email=s@s -c user.name=s commit -qm base', base)
    rc, out = sh('./mcdc.sh', base, env=dict(os.environ, UT_SCRIPTS=SCRIPTS, MCDC_VIEW='raw'))
    print(out.splitlines()[0] if out else rc)


def prompt(view):
    return f'''You are improving MC/DC coverage (modified condition/decision coverage) of the production code in src/ of
this C++17 project, tested with CppUTest. The current directory is the repository.

Write new tests in tests/mcdc_test.cpp (already part of the test build). Do not change src/, include/, client/ or the
existing test files.

Measure with: ./mcdc.sh
It builds the tests with clang 18 MC/DC instrumentation, runs all tests, and prints the MC/DC gaps of src/: {VIEW_TEXT[view]}.

MC/DC: every condition of a decision (like `a > 0` and `b > 0` in `if (a > 0 && b > 0)`) must be shown to affect the
decision's outcome on its own: two test runs in which that condition changes and the outcome changes, while every other
condition stays the same (a condition that was not evaluated because of && / || short-circuiting does not matter).

Goal: every condition in src/ shown independent, and all tests passing. You may read and grep any file.
Finish with one line: RESULT: DONE or RESULT: PARTIAL, followed by the last MC/DC summary line ./mcdc.sh printed.
'''


def run_one(view, k):
    d = os.path.join(BASE, 'runs', view, str(k))
    if os.path.exists(os.path.join(d, 'done')):
        return
    shutil.rmtree(d, ignore_errors=True)
    repo = os.path.join(d, 'repo')
    shutil.copytree(os.path.join(BASE, 'base'), repo, ignore=shutil.ignore_patterns('build-mcdc', '.ix'))
    s = open(os.path.join(repo, 'mcdc.sh')).read().replace('cd "$(dirname "$0")"\n', f'cd "$(dirname "$0")"\nexport MCDC_VIEW={view} UT_SCRIPTS={SCRIPTS}\n', 1)
    open(os.path.join(repo, 'mcdc.sh'), 'w').write(s)
    allow = ['Read', 'Edit', 'Write', 'MultiEdit', 'Grep', 'Glob', 'Bash(./mcdc.sh)', 'Bash(./mcdc.sh:*)'] + \
        [f'Bash({x}:*)' for x in ('grep', 'cat', 'ls', 'head', 'tail', 'find', 'sed -n', 'wc')]
    deny = ['WebFetch', 'WebSearch', 'Task', f'Read(/{BASE}/base/**)']
    p = prompt(view)
    open(os.path.join(d, 'prompt.txt'), 'w').write(p)
    cmd = ['claude', '-p', p, '--model', MODEL, '--session-id', str(uuid.uuid4()), '--output-format', 'stream-json', '--verbose',
           '--max-turns', '60', '--permission-mode', 'acceptEdits', '--allowedTools', ','.join(allow), '--disallowedTools', ','.join(deny)]
    t0 = time.time()
    with open(os.path.join(d, 'stream.jsonl'), 'w') as out:
        try:
            subprocess.run(cmd, cwd=repo, stdout=out, stderr=subprocess.STDOUT, timeout=1800)
            status = 'ok'
        except subprocess.TimeoutExpired:
            status = 'timeout'
    open(os.path.join(d, 'done'), 'w').write(json.dumps({'status': status, 'wall_s': round(time.time() - t0, 1)}))
    print(f'{view}/{k}: {status} {time.time() - t0:.0f}s', flush=True)


def run(runs, jobs):
    todo = [(v, k) for k in range(1, runs + 1) for v in ('suggest', 'raw')]
    with ThreadPoolExecutor(jobs) as pool:
        list(pool.map(lambda a: run_one(*a), todo))


def score():
    rows = []
    for d in sorted(glob.glob(os.path.join(BASE, 'runs', '*', '*'))):
        view, k = d.split(os.sep)[-2:]
        repo = os.path.join(d, 'repo')
        res = {}
        for l in open(os.path.join(d, 'stream.jsonl'), errors='replace'):
            try:
                m = json.loads(l)
            except ValueError:
                continue
            if m.get('type') == 'result':
                res = m
        rc, out = sh('./mcdc.sh', repo, env=dict(os.environ, UT_SCRIPTS=SCRIPTS))
        _, rep = sh('llvm-cov report build-mcdc/tests/unit_tests -instr-profile=build-mcdc/ut.profdata -show-mcdc-summary src/*.cpp | tail -1', repo)
        t = rep.split()
        m = re.match(r'(\d+) (\d+)', f'{t[-3]} {t[-2]}') if len(t) >= 3 else None
        tests = re.search(r'^(OK|Errors) \((\d+) tests?[^)]*\)', out, re.M)
        changed = sh('git status --porcelain -- src include client tests', repo)[1].split('\n')
        illegal = [c for c in changed if c.strip() and 'tests/mcdc_test.cpp' not in c]
        n_new = len(re.findall(r'^\s*TEST\s*\(', open(os.path.join(repo, 'tests', 'mcdc_test.cpp')).read(), re.M))
        rows.append({'view': view, 'run': int(k), 'conditions': int(m.group(1)) if m else None,
                     'missing': int(m.group(2)) if m else None, 'build': 'BUILD FAILED' not in out,
                     'pass': rc == 0, 'tests': tests.group(0) if tests else None, 'new_tests': n_new, 'illegal_changes': illegal,
                     'cost_usd': res.get('total_cost_usd'), 'turns': res.get('num_turns'),
                     'duration_s': round((res.get('duration_ms') or 0) / 1000), 'result': (re.findall(r'RESULT: (DONE|PARTIAL)', res.get('result') or '') or ['none'])[-1]})
        r = rows[-1]
        print(f"{view:8s} {k} build {r['build']!s:5s} pass {r['pass']!s:5s} missing {r['missing']}/{r['conditions']} new TESTs {n_new:3d} "
              f"${r['cost_usd'] or 0:.2f} {r['turns']} turns {r['duration_s']}s {r['result']} illegal={illegal}", flush=True)
    json.dump(rows, open(os.path.join(BASE, 'results.json'), 'w'), indent=1)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if cmd == 'prepare':
        prepare()
    elif cmd == 'run':
        run(int(sys.argv[sys.argv.index('--runs') + 1]) if '--runs' in sys.argv else 3,
            int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else 3)
    else:
        score()
