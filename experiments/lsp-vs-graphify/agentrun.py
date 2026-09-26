#!/usr/bin/env python3
"""agentrun.py - the agent half of the experiment: Haiku writes unit tests, once with the Graphify index tool and once
with a plain clangd (LSP) tool. Everything else is identical: task text, test framework, build script, permissions
(code files can be neither read nor grepped in either arm: the tool is the only window on the code).

  agentrun.py prepare                      stripped base copies (all existing tests removed), both indexes, wrappers
  agentrun.py run [--runs 3] [--jobs 4] [--only CB/ARM/TASK]   the agent runs (skips finished ones)
  agentrun.py score                        rebuild every run's tests, gcov branch coverage of the target -> results.json
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, '..', '..'))
SKILL = os.path.join(REPO, '.agents', 'skills', 'ut', 'resources', 'scripts')
BASE = os.environ.get('EXP_AGENT_DIR', '/tmp/claude-0/exp/agent')
MODEL = 'claude-haiku-4-5-20251001'

CODEBASES = {
    'cvaccel': {
        'src': os.path.join(REPO, 'examples', 'cvaccel'), 'cdb': 'build-ut/compile_commands.json',
        'strip': ['tests/*_test.cpp'], 'keep': ['tests/main.cpp', 'tests/CMakeLists.txt'],
        'index_paths': ['include', 'src', 'client/include', 'client/src', 'sim', 'apps'],
        'hidden': ['src', 'include', 'client', 'sim', 'apps'],
        'test_file': 'tests/agent_test.cpp',
        'run': r'''#!/bin/bash
# build tests/agent_test.cpp with the code under test and run it (CppUTest)
cd "$(dirname "$0")" && mkdir -p .ut && cd .ut && rm -f *.gcda agent_tests
if ! g++ -std=c++17 -O0 -g --coverage -w -I../include -I../client/include -I../tests/mocks ../tests/agent_test.cpp ../tests/main.cpp \
     ../src/*.cpp ../client/src/cvclient.cpp -lCppUTestExt -lCppUTest -lpthread -o agent_tests > build.log 2>&1; then
  echo "BUILD FAILED"; grep -E "error|undefined" build.log | head -40; exit 1; fi
timeout 60 ./agent_tests -v > run.log 2>&1; rc=$?; tail -40 run.log; exit $rc
''',
        'lang': 'C++17 project tested with CppUTest',
        'how': 'Write the tests in tests/agent_test.cpp (a new file; tests/main.cpp already has the CppUTest main). The build '
               'compiles tests/agent_test.cpp together with every file of src/ and client/src/ and links CppUTest and CppUTestExt. '
               'Collaborators behind interfaces need test doubles that you write in the test file.',
        'tasks': [('MemoryPool::allocate', 'src/memory_pool.cpp'), ('CvAccelService::postConfig', 'src/service.cpp'),
                  ('RequestQueue::enqueue', 'src/request_queue.cpp'), ('Dispatcher::onCompletion', 'src/dispatcher.cpp'),
                  ('Dispatcher::pump', 'src/dispatcher.cpp'), ('Dispatcher::cancelSession', 'src/dispatcher.cpp')],
    },
    'libcanard': {
        'src': '/tmp/claude-0/exp/libcanard', 'cdb': 'build/compile_commands.json',
        'strip': ['tests/src/test_*.c', 'tests/src/test_*.cpp'], 'keep': ['tests/src/helpers.h'],
        'index_paths': ['libcanard', 'lib/cavl2', 'tests/src'],
        'hidden': ['libcanard', 'lib'],
        'test_file': 'tests/src/agent_test.c',
        'run': r'''#!/bin/bash
# build tests/src/agent_test.c (which includes canard.c) with Unity and run it
cd "$(dirname "$0")" && mkdir -p .ut && cd .ut && rm -f *.gcda agent_tests
if ! gcc -std=c11 -O0 -g --coverage -w -DUNITY_INCLUDE_DOUBLE=1 -DUNITY_SHORTHAND_AS_RAW=1 -DUNITY_SUPPORT_64=1 \
     -I../libcanard -I../tests/src -isystem ../lib/cavl2 -isystem ../lib/unity/src ../tests/src/agent_test.c ../lib/unity/src/unity.c \
     -o agent_tests > build.log 2>&1; then
  echo "BUILD FAILED"; grep -E "error|undefined" build.log | head -40; exit 1; fi
timeout 60 ./agent_tests > run.log 2>&1; rc=$?; tail -40 run.log; exit $rc
''',
        'lang': 'C11 embedded library tested with Unity',
        'how': 'Write the tests in tests/src/agent_test.c (a new file). This project reaches static functions by including the '
               'source file: start the file with #include "canard.c" then #include "helpers.h" and #include <unity.h> '
               '(tests/src/helpers.h has test allocators and helpers; you may read it). Define setUp(), tearDown() and main() '
               'with UNITY_BEGIN(), RUN_TEST(...) and UNITY_END(). Do not add other source files.',
        'tasks': [('tx_push', 'libcanard/canard.c'), ('rx_parse', 'libcanard/canard.c'), ('rx_session_update', 'libcanard/canard.c'),
                  ('rx_filter_configure', 'libcanard/canard.c'), ('rx_session_complete_slot', 'libcanard/canard.c'),
                  ('node_id_occupancy_update', 'libcanard/canard.c')],
    },
}

HELP = {
    'graphify': '''q card NAME          test-planning card: signature, decisions (branches) with lines, calls, callers, types
q source NAME        the lines of one function, type, macro or constant (NAME@LINE picks an overload)
q deps NAME          what it calls outside itself: mock/stub candidates first
q refs NAME          callers with call lines, function pointers, overrides, test doubles
q find PATTERN       functions, types, macros, globals whose name matches
q defs NAME          every definition of NAME (overloads)
q list FILE          a file's types, macros, globals and functions with line ranges''',
    'clangd': '''q source NAME        the lines of NAME's definition (function, type, macro)
q def NAME           where NAME is defined
q hover NAME         signature and type information
q callees NAME       functions NAME calls, with call lines
q callers NAME       functions that call NAME, with call lines
q refs NAME          every reference to NAME
q find PATTERN       symbols whose name contains PATTERN
q symbols FILE       the symbols of one file with line ranges
NAME may be qualified (Class::method) and may carry @FILE:LINE to pick one overload.''',
}


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, **kw)


def prepare():
    for cb, c in CODEBASES.items():
        d = os.path.join(BASE, cb)
        base = os.path.join(d, 'base')
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        shutil.copytree(c['src'], base, symlinks=True, ignore=shutil.ignore_patterns('.git', 'build*', '.cache', '.ut'))
        for pat in c['strip']:
            for f in glob.glob(os.path.join(base, pat)):
                if os.path.relpath(f, base) not in c['keep']:
                    os.remove(f)
        ents = json.load(open(os.path.join(c['src'], c['cdb'])))
        out = []
        for e in ents:
            e = json.loads(json.dumps(e).replace(c['src'], base))
            f = os.path.join(e['directory'], e['file'])
            if os.path.exists(f):
                os.makedirs(e['directory'], exist_ok=True)
                out.append(e)
        cdb_dir = os.path.join(base, 'build')
        os.makedirs(cdb_dir, exist_ok=True)
        json.dump(out, open(os.path.join(cdb_dir, 'compile_commands.json'), 'w'), indent=1)
        t0 = time.time()
        r = sh([os.path.join(SKILL, 'index.sh'), 'build', '--cdb', os.path.join(cdb_dir, 'compile_commands.json'), os.path.join(d, 'gfy')]
               + c['index_paths'], cwd=base)
        gt = time.time() - t0
        t0 = time.time()
        r2 = sh([sys.executable, os.path.join(HERE, 'clangd_cli.py'), base, cdb_dir, 'warm'])
        ct = time.time() - t0
        print(f'{cb}: graphify {gt:.1f}s ({r.stdout.strip()[-160:]}), clangd {ct:.1f}s ({r2.stdout.strip()})')
        for arm in ('graphify', 'clangd'):
            b = os.path.join(d, 'bin-' + arm)
            os.makedirs(b)
            if arm == 'graphify':
                body = f'exec "{SKILL}/index.sh" "$1" "{d}/gfy" "${{@:2}}"'
            else:
                body = f'exec "{sys.executable}" "{HERE}/clangd_cli.py" "{base}" "{cdb_dir}" "$@"'
            open(os.path.join(b, 'q'), 'w').write('#!/bin/bash\n[ $# -ge 1 ] || { cat <<\'EOF\'\n' + HELP[arm] + '\nEOF\nexit 2; }\n' + body + '\n')
            os.chmod(os.path.join(b, 'q'), 0o755)
        open(os.path.join(d, 'ut_run.sh'), 'w').write(c['run'])
        os.chmod(os.path.join(d, 'ut_run.sh'), 0o755)


def prompt(cb, arm, fn, file):
    c = CODEBASES[cb]
    hidden = ', '.join(h + '/' for h in c['hidden'])
    q = os.path.join(BASE, cb, 'bin-' + arm, 'q')
    return f'''You are writing unit tests for a {c['lang']}. The current directory is the repository.

Target: {fn} in {file}.
Goal: every branch outcome of {fn} (each side of every if, loop, ?: and switch case) is executed by at least one
passing test. Keep each test small and name it after the behaviour it checks.

{c['how']}

Build and run the tests with: ./ut_run.sh   (prints only the compiler errors or the test results; do not pipe it)

You cannot read, grep or list the code files ({hidden}). The ONLY way to learn about the code is this command
(run it with Bash, exactly as shown, full path):
{q} COMMAND ARG
{HELP[arm].replace('q ', q + ' ')}

Fix the tests until ./ut_run.sh builds and every test passes. Never change the code under test.
Finish with one line: RESULT: DONE (tests build and pass) or RESULT: PARTIAL <reason>.
'''


def run_one(cb, arm, fn, file, k):
    c = CODEBASES[cb]
    tag = re.sub(r'\W+', '_', fn)
    d = os.path.join(BASE, 'runs', cb, arm, tag, str(k))
    if os.path.exists(os.path.join(d, 'done')):
        return
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    repo = os.path.join(d, 'repo')
    base = os.path.join(BASE, cb, 'base')
    shutil.copytree(base, repo, symlinks=True, ignore=shutil.ignore_patterns('build', '.cache'))
    shutil.copy(os.path.join(BASE, cb, 'ut_run.sh'), repo)
    q = os.path.join(BASE, cb, 'bin-' + arm, 'q')
    deny = ['Grep', 'Glob', 'LS', 'WebFetch', 'WebSearch', 'Task'] + [f'Bash({x}:*)' for x in ('grep', 'rg', 'find', 'cat', 'head', 'tail', 'sed', 'awk', 'less', 'more', 'ls', 'strings', 'nl', 'od', 'xxd')] \
        + [f'Read(./{h}/**)' for h in c['hidden']] + [f'Read(/{repo}/{h}/**)' for h in c['hidden']] + [f'Read(/{base}/**)', f'Read(/{BASE}/{cb}/gfy/**)']
    allow = ['Read', 'Edit', 'Write', 'MultiEdit', f'Bash({q}:*)', 'Bash(./ut_run.sh)', 'Bash(./ut_run.sh:*)']
    p = prompt(cb, arm, fn, file)
    open(os.path.join(d, 'prompt.txt'), 'w').write(p)
    cmd = ['claude', '-p', p, '--model', MODEL, '--session-id', str(uuid.uuid4()), '--output-format', 'stream-json', '--verbose',
           '--max-turns', '80', '--permission-mode', 'acceptEdits', '--allowedTools', ','.join(allow), '--disallowedTools', ','.join(deny)]
    t0 = time.time()
    with open(os.path.join(d, 'stream.jsonl'), 'w') as out:
        try:
            subprocess.run(cmd, cwd=repo, stdout=out, stderr=subprocess.STDOUT, timeout=1500)
            status = 'ok'
        except subprocess.TimeoutExpired:
            status = 'timeout'
    open(os.path.join(d, 'done'), 'w').write(json.dumps({'status': status, 'wall_s': round(time.time() - t0, 1)}))
    print(f'{cb}/{arm}/{tag}/{k}: {status} {time.time() - t0:.0f}s', flush=True)


def run(runs, jobs, only):
    todo = []
    for k in range(1, runs + 1):                      # round-robin: every task/arm gets run 1 before any run 2
        for cb, c in CODEBASES.items():
            for fn, file in c['tasks']:
                for arm in ('graphify', 'clangd'):
                    if only and not f'{cb}/{arm}/{fn}'.startswith(only):
                        continue
                    todo.append((cb, arm, fn, file, k))
    with ThreadPoolExecutor(jobs) as pool:
        list(pool.map(lambda a: run_one(*a), todo))


# ------------------------------------------------------------------------------------------------------ scoring
def target_range(cb, fn, file):
    ix = json.load(open(os.path.join(BASE, cb, 'gfy', 'index.json')))
    pre = os.path.relpath(os.path.join(BASE, cb, 'base'), ix['meta']['root'])
    pre = '' if pre == '.' else pre + '/'
    for v in ix['functions'].values():
        if v['name'] == fn and v['file'] == pre + file:
            return v['line'], v['end']
    raise KeyError(fn)


def coverage(repo, file, lo, hi):
    """branch and line coverage of lines lo..hi of file, from the gcda files of the last ./ut_run.sh"""
    ut = os.path.join(repo, '.ut')
    tmp = os.path.join(ut, 'gcov')
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    gcdas = glob.glob(os.path.join(ut, '*.gcda'))
    if not gcdas:
        return None
    sh(['gcov', '--json-format', '--branch-probabilities', '-o', ut] + gcdas, cwd=tmp)
    br_t = br_n = ln_t = ln_n = 0
    import gzip
    for g in glob.glob(os.path.join(tmp, '*.gcov.json.gz')):
        data = json.load(gzip.open(g))
        for f in data['files']:
            if not os.path.normpath(os.path.join(repo, '.ut', f['file'])).endswith(os.sep + file) and not f['file'].endswith(file):
                continue
            for ln in f['lines']:
                if lo <= ln['line_number'] <= hi:
                    ln_n += 1
                    ln_t += ln['count'] > 0
                    for b in ln.get('branches', []):
                        if b.get('throw'):
                            continue
                        br_n += 1
                        br_t += b['count'] > 0
            break
    return {'branches': br_n, 'branches_taken': br_t, 'lines': ln_n, 'lines_run': ln_t}


def parse_stream(path):
    res, tools, denied, text = {}, {}, 0, ''
    for line in open(path, errors='replace'):
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get('type') == 'assistant':
            for b in m['message'].get('content', []):
                if b.get('type') == 'tool_use':
                    name = b['name']
                    if name == 'Bash':
                        c = b['input'].get('command', '').strip()
                        name = 'q ' + c.split()[1] if '/bin-' in c.split()[0] and len(c.split()) > 1 else ('ut_run' if 'ut_run' in c else 'Bash other')
                    tools[name] = tools.get(name, 0) + 1
                elif b.get('type') == 'text':
                    text = b['text']
        elif m.get('type') == 'user':
            for b in m['message'].get('content', []) if isinstance(m['message'].get('content'), list) else []:
                if b.get('type') == 'tool_result' and b.get('is_error') and 'permission' in json.dumps(b.get('content', '')).lower():
                    denied += 1
        elif m.get('type') == 'result':
            res = m
    r = re.findall(r'RESULT:\s*(DONE|PARTIAL)', (res.get('result') or '') + '\n' + text)
    u = res.get('usage', {})
    return {'result': r[-1] if r else 'none', 'cost_usd': res.get('total_cost_usd'), 'turns': res.get('num_turns'),
            'duration_s': round((res.get('duration_ms') or 0) / 1000, 1), 'input_tokens': u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
            + u.get('cache_creation_input_tokens', 0), 'output_tokens': u.get('output_tokens'), 'tools': tools, 'denied': denied,
            'is_error': res.get('is_error'), 'subtype': res.get('subtype')}


def score():
    rows = []
    for cb, c in CODEBASES.items():
        for fn, file in c['tasks']:
            lo, hi = target_range(cb, fn, file)
            tag = re.sub(r'\W+', '_', fn)
            for arm in ('graphify', 'clangd'):
                for d in sorted(glob.glob(os.path.join(BASE, 'runs', cb, arm, tag, '*'))):
                    if not os.path.exists(os.path.join(d, 'done')):
                        continue
                    repo = os.path.join(d, 'repo')
                    row = {'codebase': cb, 'arm': arm, 'task': fn, 'run': int(os.path.basename(d)), **json.load(open(os.path.join(d, 'done')))}
                    row.update(parse_stream(os.path.join(d, 'stream.jsonl')))
                    has = os.path.exists(os.path.join(repo, c['test_file']))
                    r = sh(['./ut_run.sh'], cwd=repo) if has else None
                    out = (r.stdout if r else '')
                    row['test_file'] = has
                    row['builds'] = bool(r) and 'BUILD FAILED' not in out
                    row['passes'] = bool(r) and r.returncode == 0
                    m = re.search(r'(\d+) Tests? (\d+) Failures?', out) or re.search(r'OK \((\d+) tests', out)
                    nt = re.search(r'OK \((\d+) tests|Errors \((\d+) failures, (\d+) tests|(\d+) Tests (\d+) Failures', out)
                    row['tests'] = int(next(g for g in nt.groups() if g)) if nt and cb == 'cvaccel' else (int(m.group(1)) if m else 0)
                    if cb == 'cvaccel' and nt and nt.group(3):
                        row['tests'] = int(nt.group(3))
                    row['coverage'] = coverage(repo, file, lo, hi) if row['builds'] else None
                    rows.append(row)
                    cv = row['coverage'] or {}
                    print(f"{cb:9s} {arm:8s} {fn:28s} {row['run']} {row['result']:7s} build {row['builds']!s:5s} pass {row['passes']!s:5s} "
                          f"tests {row['tests']:3d} br {cv.get('branches_taken', 0)}/{cv.get('branches', 0)} ${row['cost_usd'] or 0:.2f} "
                          f"{row['turns']} turns denied {row['denied']}", flush=True)
    json.dump(rows, open(os.path.join(BASE, 'results.json'), 'w'), indent=1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd')
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', default='')
    a = ap.parse_args()
    {'prepare': prepare, 'run': lambda: run(a.runs, a.jobs, a.only), 'score': score}[a.cmd]()
