#!/usr/bin/env python3
"""impactstudy.py: the change-impact study (resources/change-impact.md) re-run on YOUR codebase.

Each scenario makes ONE change to a scratch clone of the repository, the way a developer would (production callers
updated so production code compiles, tests untouched). Then it builds, runs the tests, and records what noticed the
change: the compiler, the linker, failing tests, a crash, or nothing. The real repository is never edited.

  impactstudy.py setup   STUDY.json          clone `source` into `work` (if missing), configure, build, run: the baseline
  impactstudy.py check   STUDY.json          validate the file: every edit applies, every catalog ID is a scenario or n/a
  impactstudy.py run     STUDY.json [ID...]  run scenarios (skips ones with a result; --force reruns)
  impactstudy.py status  STUDY.json          which scenarios have results, and their outcome
  impactstudy.py report  STUDY.json [--short] > FILE   STUDY.md (full), or the short form for KB change-impact.md

STUDY.json (paths in edits are relative to the repository root):
{
  "project": "one line: what codebase, language, test framework, test binaries",
  "source": "/abs/repo",                     read only; `setup` clones it (git clone --shared) when `work` is missing
  "work": "/abs/task/study/src",             the scratch copy; the only place edits happen
  "build_dir": "build-study",                inside work; kept across scenarios (incremental builds)
  "configure": "cmake -S . -B build-study -G Ninja -DBUILD_UNIT_TESTS=ON -DCMAKE_CXX_FLAGS='--coverage -O0' ...",
  "build": "cmake --build build-study -- -k 0",   keep going after errors (ninja -k 0, make -k), so all errors count
  "tests": [{"name": "unit_tests", "cmd": "build-study/tests/unit_tests -v", "binary": "build-study/tests/unit_tests"}],
  "framework": "cpputest" | "gtest" | "unity" | "generic",
  "coverage": "gcov" | null,                 gcov: did any test execute the changed lines (needs --coverage builds)
  "code_paths": ["src"], "test_paths": ["tests"],
  "index": "/abs/KB_DIR/index",              optional: the ut code index, to predict impacted TESTs before the change
  "scenarios": [
    {"id": "B2", "cat": "Function body", "title": "Off-by-one in a tested boundary",
     "change": "`Queue::push`: `n >= kMax` becomes `>`", "why": "why this target (evidence file:line)",
     "symbol": "Queue::push", "expect": "tests",           your prediction: compiler|linker|tests|crash|nothing
     "edits": [{"file": "src/queue.c", "old": "exact text", "new": "text", "count": 1}],
               {"glob": "src/**/*.c", "regex": "push\\(([^()]*)\\)", "new": "push(\\1, 0)", "min": 1}
               {"patch": "p1.diff"}                        (git apply; relative to STUDY.json's folder)
     "new_files": {"src/new.c": "text"}, "delete_files": ["src/old.c"],
     "lesson": "after the run: what a diff task must do for this kind of change here"},
    {"id": "X1", "na": "why this change cannot happen in this codebase"}
  ],
  "findings": ["after the run: 3-6 numbered conclusions for this codebase, with IDs"]
}
"""
import fnmatch, glob, gzip, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, '..', 'change-impact.md')
OUTCOMES = ['compiler', 'linker', 'tests', 'crash', 'nothing']
ICON = {'compiler': '🟥 compiler', 'linker': '🟧 linker', 'tests': '🟨 tests', 'crash': '🟪 crash', 'nothing': '⬜ nothing'}
RECONF = ('CMakeLists.txt', '.cmake', 'Makefile', '.mk', 'meson.build', 'project.yml')


def sh(cmd, cwd, timeout=3600):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, errors='replace')
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b'').decode(errors='replace') if isinstance(e.stdout, bytes) else (e.stdout or '')
        return 'TIMEOUT', out


def load(path):
    st = json.load(open(path))
    st['_dir'] = os.path.dirname(os.path.abspath(path))
    st['_res'] = os.path.join(st['_dir'], 'results')
    os.makedirs(st['_res'], exist_ok=True)
    st.setdefault('build_dir', 'build-study')
    st.setdefault('framework', 'generic')
    st.setdefault('test_paths', ['tests'])
    st.setdefault('code_paths', ['src'])
    for k in ('source', 'work', 'build', 'tests', 'scenarios'):
        if k not in st:
            sys.exit(f'STUDY.json: "{k}" missing')
    if os.path.realpath(st['work']) == os.path.realpath(st['source']):
        sys.exit('"work" must be a scratch copy, never the repository itself')
    return st


def catalog():
    """the reference study's scenario IDs and titles (resources/change-impact.md)"""
    out = {}
    for l in open(REF, errors='replace'):
        m = re.match(r'^\| ([A-Z]\d+) \| \*\*(.+?)\*\*', l)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def is_test(st, f):
    return any(f == t.rstrip('/') or f.startswith(t.rstrip('/') + '/') for t in st['test_paths'])


# ------------------------------------------------------------------------------------------------ work copy
def reset(st):
    w = st['work']
    sh('git checkout -q -- . && git clean -qfd -e "%s"' % st['build_dir'], w)


def setup(st):
    w, src = st['work'], st['source']
    if not os.path.exists(w):
        os.makedirs(os.path.dirname(w), exist_ok=True)
        rc, out = sh(f'git clone -q --shared "{src}" "{w}" && git -C "{w}" submodule update -q --init --recursive', os.path.dirname(w))
        if rc != 0:
            sys.exit(f'clone failed:\n{out[-800:]}\nCopy the repository yourself (rsync -a --exclude "build*" SRC/ WORK/) and run setup again.')
    if not os.path.isdir(os.path.join(w, '.git')):
        sh('git init -q && git add -A && git -c user.email=study@local -c user.name=study commit -qm baseline', w)
    with open(os.path.join(w, '.git', 'info', 'exclude'), 'a') as f:
        f.write(f"\n/{st['build_dir']}/\n")
    dirty = sh('git status --porcelain --untracked-files=no', src)[1].strip()
    if st.get('configure'):
        rc, out = sh(st['configure'], w)
        if rc != 0:
            sys.exit(f'configure failed ({rc}):\n{out[-1500:]}')
    rc, log = sh(st['build'], w)
    if rc != 0:
        sys.exit(f'baseline build failed ({rc}): fix "build"/"configure" first.\n{log[-2000:]}')
    tests = run_tests(st)
    base = {'build_ok': True, 'warnings': warnings(log), 'tests': tests,
            'source_uncommitted_changes': dirty.splitlines()[:20],
            'head': sh('git rev-parse --short HEAD', w)[1].strip()}
    json.dump(base, open(os.path.join(st['_res'], '_baseline.json'), 'w'), indent=1)
    for n, t in tests.items():
        print(f"{n}: {t['summary']}" + (f"  (failing at baseline: {len(t['failed'])}; they are subtracted)" if t['failed'] else ''))
    if dirty:
        print('NOTE: the source repository has uncommitted changes; the clone has only committed code (HEAD).')
    print(f"baseline written: {os.path.join(st['_res'], '_baseline.json')}")


# ------------------------------------------------------------------------------------------------ edits
def expand(st, pattern):
    w = st['work']
    return sorted(os.path.relpath(p, w) for p in glob.glob(os.path.join(w, pattern), recursive=True)
                  if os.path.isfile(p) and not os.path.relpath(p, w).startswith(st['build_dir'] + '/'))


def apply(st, s, dry=False):
    """apply the scenario's edits to the (reset) work copy; returns problems (empty = all applied)"""
    w, probs = st['work'], []
    for e in s.get('edits', []):
        if 'patch' in e:
            p = e['patch'] if os.path.isabs(e['patch']) else os.path.join(st['_dir'], e['patch'])
            rc, out = sh(f'git apply {"--check " if dry else ""}"{p}"', w)
            if rc != 0:
                probs.append(f"patch {e['patch']} does not apply: {out.strip()[:200]}")
        elif 'regex' in e:
            files = expand(st, e.get('glob', '**/*'))
            n = 0
            for f in files:
                p = os.path.join(w, f)
                t = open(p, errors='replace').read()
                t2, k = re.subn(e['regex'], e['new'], t, flags=re.M)
                if k:
                    n += k
                    if not dry:
                        open(p, 'w').write(t2)
            if n < e.get('min', 1):
                probs.append(f"regex {e['regex']!r} in {e.get('glob', '**/*')}: {n} matches, want >= {e.get('min', 1)}")
        else:
            p = os.path.join(w, e['file'])
            if not os.path.exists(p):
                probs.append(f"{e['file']}: no such file")
                continue
            t = open(p, errors='replace').read()
            n = t.count(e['old'])
            want = e.get('count', 1)
            if n == 0 or (want != 'all' and n != want):
                probs.append(f"{e['file']}: text found {n} time(s), want {want}: {e['old'][:70]!r}")
                continue
            if not dry:
                open(p, 'w').write(t.replace(e['old'], e['new']) if want == 'all' or n > 1 else t.replace(e['old'], e['new'], 1))
    for f, text in s.get('new_files', {}).items():
        if not dry:
            os.makedirs(os.path.dirname(os.path.join(w, f)) or w, exist_ok=True)
            open(os.path.join(w, f), 'w').write(text)
    for f in s.get('delete_files', []):
        if not os.path.exists(os.path.join(w, f)):
            probs.append(f'{f}: cannot delete, no such file')
        elif not dry:
            os.remove(os.path.join(w, f))
    return probs


# ------------------------------------------------------------------------------------------------ build and run
ERR = re.compile(r'^(?:In file included from .*?)?([^\s:][^:]*\.(?:cpp|cxx|cc|c|hpp|hxx|hh|h|inl|ipp)):(\d+):(?:(\d+):)? (?:fatal )?error: (.*)$')
LINK = re.compile(r'undefined reference|undefined symbol|multiple definition|ld returned|ld: error|ld\.lld: error|collect2: error|unresolved external')


def norm(st, f):
    w, b = os.path.realpath(st['work']), os.path.join(os.path.realpath(st['work']), st['build_dir'])
    for base in ([] if os.path.isabs(f) else [b, w] + [os.path.join(b, d) for d in ('tests', 'src')]):
        p = os.path.normpath(os.path.join(base, f))
        if os.path.exists(p):
            f = p
            break
    f = os.path.normpath(f)
    return os.path.relpath(f, w) if f.startswith(w + '/') else f


def parse_build(st, log):
    errs, files, link = [], {}, []
    for l in log.splitlines():
        l = l.strip()
        m = ERR.match(l)
        if m:
            f = norm(st, m.group(1))
            files[f] = files.get(f, 0) + 1
            errs.append(f'{f}:{m.group(2)}: {m.group(4)[:160]}')
        elif LINK.search(l):
            link.append(re.sub(r'^\S*?:(\(\.text\S*\))?\s*', '', l)[:220])
    return errs, files, link


def warnings(log):
    return sorted({re.sub(r'^(\.\./)*', '', l.strip())[:220] for l in log.splitlines() if ': warning:' in l})


def parse_tests(fw, out):
    """(summary line or None, failing test names normalised to Group.Name)"""
    if fw == 'cpputest':
        summ = re.findall(r'^(?:OK|Errors) \(.*\)$', out, re.M)
        fails = [f'{a}.{b}' for a, b in re.findall(r'Failure in TEST\((\w+), (\w+)\)', out)]
    elif fw == 'gtest':
        summ = re.findall(r'^\[==========\] \d+ tests? from .* ran\..*$', out, re.M)
        fails = re.findall(r'^\[  FAILED  \] (\w+\.\w+)', out, re.M)
    elif fw == 'unity':
        summ = re.findall(r'^\d+ Tests \d+ Failures \d+ Ignored.*$', out, re.M)
        fails = [f'{os.path.basename(a)}.{b}' for a, b in re.findall(r'^(\S+?):\d+:(\w+):FAIL', out, re.M)]
    else:
        summ, fails = [], []
    return (summ[-1] if summ else None), sorted(set(fails))


def run_tests(st):
    res = {}
    for t in st['tests']:
        if t.get('binary') and not os.path.exists(os.path.join(st['work'], t['binary'])):
            res[t['name']] = {'ran': False, 'summary': 'NOT BUILT', 'failed': [], 'crash': False}
            continue
        rc, out = sh(t['cmd'], st['work'], timeout=t.get('timeout', 900))
        summ, fails = parse_tests(st['framework'], out)
        crash = rc == 'TIMEOUT' or (isinstance(rc, int) and (rc < 0 or rc >= 128)) or \
            (st['framework'] != 'generic' and summ is None and rc != 0)
        if st['framework'] == 'generic' and rc not in (0, 'TIMEOUT') and not crash:
            fails = [f"{t['name']} (exit {rc})"]
        res[t['name']] = {'ran': True, 'rc': rc, 'crash': crash, 'failed': fails,
                          'summary': summ or (f'CRASHED or HUNG (exit {rc})' if crash else f'exit {rc}'),
                          'tail': out[-1500:]}
    return res


def changed_lines(st):
    rc, d = sh('git diff -U0 --no-color', st['work'])
    res, cur = {}, None
    for l in d.splitlines():
        if l.startswith('+++ '):
            cur = l[6:] if l.startswith('+++ b/') else None
        m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', l)
        if m and cur and not is_test(st, cur):
            a, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if n:
                res.setdefault(cur, set()).update(range(a, a + n))
    return res


def reach(st, chg):
    """changed production lines that are executable, and how many some test executed (gcov over all .gcda)"""
    if st.get('coverage') != 'gcov' or not chg:
        return None
    b = os.path.join(st['work'], st['build_dir'])
    lines = branches = 0
    hit_l = hit_b = 0
    tmp = tempfile.mkdtemp()
    for f, want in chg.items():
        base = os.path.basename(f)
        hits, brs = {}, {}
        for gcda in glob.glob(os.path.join(b, '**', os.path.splitext(base)[0] + '*.gcda'), recursive=True):
            sh(f'{st.get("gcov", "gcov")} --json-format --branch-probabilities -o "{os.path.dirname(gcda)}" "{gcda}"', tmp)
            for g in glob.glob(os.path.join(tmp, '*.gcov.json.gz')):
                for jf in json.load(gzip.open(g))['files']:
                    if os.path.normpath(jf['file']).endswith(f):
                        for ln in jf['lines']:
                            if ln['line_number'] in want:
                                hits[ln['line_number']] = hits.get(ln['line_number'], 0) + ln['count']
                                for k, br in enumerate(ln.get('branches', [])):
                                    if not br.get('throw'):
                                        brs[(ln['line_number'], k)] = brs.get((ln['line_number'], k), 0) + br['count']
                os.remove(g)
        lines += len(hits)
        hit_l += sum(1 for v in hits.values() if v)
        branches += len(brs)
        hit_b += sum(1 for v in brs.values() if v)
    shutil.rmtree(tmp, ignore_errors=True)
    return {'lines': lines, 'lines_hit': hit_l, 'branches': branches, 'branches_hit': hit_b}


# ------------------------------------------------------------------------------------------------ prediction (index)
def tname(n):
    m = re.match(r'^\w+\((\w+),\s*(\w+)\)', n)
    return f'{m.group(1)}.{m.group(2)}' if m else n


def predict(st, s):
    """TESTs the ut code index links to the changed symbol, before the change: direct, and through up to 2 levels
    of production callers"""
    if not st.get('index') or not s.get('symbol'):
        return None
    ix = json.load(open(os.path.join(st['index'], 'index.json')))
    sym = s['symbol']
    ids = {i for i, f in ix['functions'].items() if f['kind'] != 'test' and
           (f['name'] == sym or ('::' not in sym and f['name'].split('::')[-1] == sym))}
    if not ids:
        return {'found': False}
    callers = {}
    for c in ix['calls']:
        callers.setdefault(c['to'], set()).add(c['from'])
    kind = lambda i: ix['functions'].get(i, {}).get('kind')
    direct, trans, frontier, seen = set(), set(), set(ids), set(ids)
    for hop in range(3):
        nxt = set()
        for i in frontier:
            for c in callers.get(i, ()):
                if kind(c) == 'test':
                    (direct if hop == 0 else trans).add(tname(ix['functions'][c]['name']))
                elif c not in seen and c in ix['functions']:
                    seen.add(c)
                    nxt.add(c)
        frontier = nxt
    files = sorted({ix['functions'][c]['file'] for i in ids for c in callers.get(i, ()) if kind(c) == 'test'})
    return {'found': True, 'direct': sorted(direct), 'transitive': sorted(trans - direct), 'test_files': files,
            'tests_total': sum(1 for f in ix['functions'].values() if f['kind'] == 'test')}


# ------------------------------------------------------------------------------------------------ one scenario
def outcome(r):
    if r.get('errors') or (not r['build_ok'] and not r.get('link')):
        return 'compiler'
    if r.get('link') or any(not t['ran'] for t in r['tests'].values()):
        return 'linker'
    if any(t.get('crash') for t in r['tests'].values()):
        return 'crash'
    if r.get('failed'):
        return 'tests'
    return 'nothing'


def run_one(st, s, base):
    w = st['work']
    reset(st)
    probs = apply(st, s)
    if probs:
        reset(st)
        return {'id': s['id'], 'error': 'edits did not apply: ' + '; '.join(probs)}
    diff = sh('git diff --no-color', w)[1] + ''.join(f'\n+++ new file {f}\n' for f in s.get('new_files', {}))
    touched = [l[6:] for l in diff.splitlines() if l.startswith('+++ b/')] + list(s.get('new_files', {})) + s.get('delete_files', [])
    reconf = st.get('configure') and (s.get('new_files') or s.get('delete_files') or any(f.endswith(RECONF) for f in touched))
    for t in st['tests']:
        if t.get('binary') and os.path.exists(os.path.join(w, t['binary'])):
            os.remove(os.path.join(w, t['binary']))
    for g in glob.glob(os.path.join(w, st['build_dir'], '**', '*.gcda'), recursive=True):
        os.remove(g)
    if reconf:
        sh(st['configure'], w)
    rc, log = sh(st['build'], w)
    errs, files, link = parse_build(st, log)
    tests = run_tests(st)
    base_fail = {n: set(t['failed']) for n, t in base['tests'].items()}
    failed = sorted({f for n, t in tests.items() for f in t['failed'] if f not in base_fail.get(n, set())})
    r = {'id': s['id'], 'build_ok': rc == 0, 'build_rc': rc, 'errors': errs[:15], 'error_count': len(errs), 'error_files': files,
         'link': link[:8], 'warnings_new': [x for x in warnings(log) if x not in set(base['warnings'])][:8],
         'tests': {n: {k: v for k, v in t.items() if k != 'tail' or t.get('crash')} for n, t in tests.items()},
         'failed': failed, 'reach': reach(st, changed_lines(st)), 'predict': predict(st, s), 'diff': diff[:6000],
         'log_tail': log[-2500:] if rc != 0 and not errs and not link else ''}
    r['outcome'] = outcome(r)
    r['prod_errors'] = sorted(f for f in files if not is_test(st, f))   # a developer would have fixed these: edit incomplete
    reset(st)
    if reconf:
        sh(st['configure'], w)
    return r


def run(st, ids, force):
    bp = os.path.join(st['_res'], '_baseline.json')
    if not os.path.exists(bp):
        sys.exit('no baseline: run `impactstudy.py setup STUDY.json` first')
    base = json.load(open(bp))
    todo = [s for s in st['scenarios'] if not s.get('na') and (not ids or s['id'] in ids)]
    for s in todo:
        out = os.path.join(st['_res'], s['id'] + '.json')
        if os.path.exists(out) and not force:
            continue
        print(f"{s['id']}: {s.get('title', '')} ...", flush=True)
        r = run_one(st, s, base)
        json.dump(r, open(out, 'w'), indent=1)
        if r.get('error'):
            print(f"  ERROR {r['error']}")
            os.remove(out)
            continue
        exp = s.get('expect')
        print(f"  {r['outcome']}" + (f"  (you expected {exp})" if exp and exp != r['outcome'] else '') +
              f"  errors {r['error_count']} in {len(r['error_files'])} file(s), link {len(r['link'])}, failing TESTs {len(r['failed'])}")
        if r['prod_errors']:
            print(f"  EDIT INCOMPLETE: production files do not compile: {', '.join(r['prod_errors'][:5])}. A developer would have "
                  'fixed them: add edits for them (or narrow "build" to the test targets), then run this ID with --force')


# ------------------------------------------------------------------------------------------------ check / status
def check(st):
    probs, ids = [], set()
    cat = catalog()
    for s in st['scenarios']:
        i = s.get('id')
        if not i or i in ids:
            probs.append(f'scenario id missing or duplicated: {i}')
        ids.add(i)
        if s.get('na'):
            continue
        for k in ('cat', 'title', 'change', 'why', 'expect', 'edits'):
            if not s.get(k) and not (k == 'edits' and (s.get('new_files') or s.get('delete_files'))):
                probs.append(f'{i}: "{k}" missing')
        if s.get('expect') and s['expect'] not in OUTCOMES:
            probs.append(f'{i}: expect must be one of {OUTCOMES}')
        if i in cat and s.get('title') and s['title'] != cat[i]:
            print(f'note {i}: title differs from the reference ("{cat[i]}"): fine if it is the same kind of change')
        reset(st)
        for p in apply(st, s):                       # applied for real (edits may build on each other), then reset
            probs.append(f'{i}: {p}')
    reset(st)
    missing = [i for i in cat if i not in ids]
    if missing:
        probs.append('reference scenarios neither run nor marked "na": ' + ', '.join(missing))
    extra = [s['id'] for s in st['scenarios'] if s['id'] not in cat and not s.get('na')]
    print(f"{len(ids)} scenarios ({len(cat) - len(missing)} of {len(cat)} reference IDs covered, {len(extra)} project ones: {', '.join(extra) or 'none'})")
    for p in probs:
        print('FAIL', p)
    print('OK' if not probs else f'{len(probs)} problem(s)')
    return 1 if probs else 0


def results(st):
    out = {}
    for s in st['scenarios']:
        p = os.path.join(st['_res'], s['id'] + '.json')
        if os.path.exists(p):
            out[s['id']] = json.load(open(p))
    return out


def status(st):
    res = results(st)
    for s in st['scenarios']:
        r = res.get(s['id'])
        state = f"n/a: {s['na']}" if s.get('na') else (r['outcome'] if r else 'not run')
        miss = '' if s.get('na') or not r or s.get('lesson') else '  (lesson missing)'
        if r and r.get('prod_errors'):
            miss += '  EDIT INCOMPLETE: ' + ', '.join(r['prod_errors'][:3])
        print(f"{s['id']:5} {state}{miss}")


# ------------------------------------------------------------------------------------------------ report
def cell(t):
    return str(t).replace('|', '\\|').replace('\n', ' ')


def happened(r, st):
    if r['outcome'] == 'compiler':
        f = ', '.join(f'`{k}` ({v})' for k, v in sorted(r['error_files'].items(), key=lambda kv: -kv[1])[:4])
        return f"{r['error_count']} compile error(s) in {len(r['error_files'])} file(s): {f}" + ('' if r['error_files'] else ' (unparsed; see details)')
    if r['outcome'] == 'linker':
        return 'link error<br>`' + cell((r['link'] or ['test binary not built'])[0])[:160] + '`'
    fails = r['failed']
    s = ''
    if fails:
        s = f'{len(fails)} failing TEST(s)<br>' + '<br>'.join(f'`{cell(f)}`' for f in fails[:4]) + (f'<br>… +{len(fails) - 4}' if len(fails) > 4 else '')
    if r['outcome'] == 'crash':
        s = (s + '<br>then ' if s else '') + 'crash or hang: ' + '; '.join(cell(t['summary']) for t in r['tests'].values() if t.get('crash'))
    return s or 'builds, all tests pass' + (f"<br>new warning: `{cell(r['warnings_new'][0])[:120]}`" if r.get('warnings_new') else '')


def reached(r):
    x = r.get('reach')
    if not x or not x['lines']:
        return '-'
    return f"{x['lines_hit']}/{x['lines']} lines" + (f", {x['branches_hit']}/{x['branches']} branches" if x['branches'] else '')


def predicted(r):
    p = r.get('predict')
    if not p:
        return '-'
    if not p['found']:
        return 'symbol not in the index'
    if r['outcome'] == 'compiler':
        broke = {f for f in r['error_files']}
        hit = broke & set(p['test_files'])
        return f"files: {len(hit)}/{len([f for f in broke])} predicted"
    if r['failed']:
        d = len(set(r['failed']) & set(p['direct']))
        t = len(set(r['failed']) & (set(p['direct']) | set(p['transitive'])))
        return f"TESTs: {d}/{len(r['failed'])} direct, {t}/{len(r['failed'])} incl. callers (flagged {len(p['direct'])} + {len(p['transitive'])})"
    return f"nothing failed; {len(p['direct']) + len(p['transitive'])} TESTs would have been flagged"


def report(st, short):
    res = results(st)
    run_s = [s for s in st['scenarios'] if not s.get('na') and s['id'] in res]
    base = json.load(open(os.path.join(st['_res'], '_baseline.json')))
    by = {o: [s['id'] for s in run_s if res[s['id']]['outcome'] == o] for o in OUTCOMES}
    L = [f"# Change impact on this codebase{' (short)' if short else ''}", '',
         st.get('project', '(project: describe it in STUDY.json "project")'), '',
         f"Each row made ONE change to a scratch clone (HEAD {base.get('head', '?')}) the way a developer would: production code "
         "and its callers updated until they compiled, tests untouched. Then the tests were built and run "
         f"({', '.join(n + ': ' + t['summary'] for n, t in base['tests'].items())} at baseline). "
         "Every row was run by `impactstudy.py`; none is a guess. IDs match the reference study "
         "(resources/change-impact.md); P-IDs are changes specific to this codebase.", '',
         '## Summary', '', '| Caught by | Scenarios |', '|---|---|']
    L += [f"| {ICON[o]} | {len(by[o])}: {', '.join(by[o])} |" for o in OUTCOMES]
    exp = [s for s in run_s if s.get('expect')]
    wrong = [f"{s['id']} (expected {s['expect']}, was {res[s['id']]['outcome']})" for s in exp if s['expect'] != res[s['id']]['outcome']]
    L += ['', f"Predictions made before running: {len(exp) - len(wrong)} of {len(exp)} right." + (' Wrong: ' + '; '.join(wrong) + '.' if wrong else '')]
    na = [s for s in st['scenarios'] if s.get('na')]
    if na:
        L += ['', 'Not applicable here: ' + '; '.join(f"{s['id']} ({s['na']})" for s in na) + '.']
    L += ['', '## Findings for this codebase', '']
    L += [f'{k}. {f}' for k, f in enumerate(st.get('findings') or ['(write "findings" in STUDY.json after the run)'], 1)]
    cats = []
    for s in run_s:
        if s['cat'] not in cats:
            cats.append(s['cat'])
    for c in cats:
        L += ['', f'## {c}', '']
        if short:
            L += ['| # | Change | Caught by | What to do |', '|---|---|---|---|']
        else:
            L += ['| # | Change | Caught by | What happened | Change reached by tests | Index before the change | What a diff task must do |',
                  '|---|---|---|---|---|---|---|']
        for s in run_s:
            if s['cat'] != c:
                continue
            r = res[s['id']]
            ch = f"**{cell(s['title'])}**: {cell(s['change'])}"
            lesson = cell(s.get('lesson') or '(lesson missing)')
            if short:
                L.append(f"| {s['id']} | {ch} | {ICON[r['outcome']]} | {lesson} |")
            else:
                L.append(f"| {s['id']} | {ch.replace(': ', '<br>', 1) if ': ' in ch else ch} | {ICON[r['outcome']]} | {happened(r, st)} | {reached(r)} | {predicted(r)} | {lesson} |")
    if short:
        ref = open(REF, errors='replace').read()
        k = ref.find('## What a diff task must do, per change kind')
        if k >= 0:
            L += ['', ref[k:].replace('## What a diff task must do, per change kind', '## What a diff task must do, per change kind (reference study)', 1).rstrip()]
    else:
        L += ['', '## Details per scenario']
        for s in run_s:
            r = res[s['id']]
            L += ['', f"### {s['id']}: {s['title']}", '', f"{s['change']}", '', f"Why this target: {s.get('why', '-')}", '',
                  f"Outcome: {ICON[r['outcome']]}" + (f" (predicted: {s['expect']})" if s.get('expect') else '')]
            if r.get('prod_errors'):
                L += ['', f"Production files that did not compile (edit incomplete): {', '.join(r['prod_errors'])}"]
            if r['errors']:
                L += ['', 'First compile errors:', '```'] + r['errors'][:8] + ['```']
            if r['link']:
                L += ['', 'Link:', '```'] + r['link'][:5] + ['```']
            if r['failed']:
                L += ['', f"Failing TESTs ({len(r['failed'])}): " + ', '.join(f'`{f}`' for f in r['failed'][:20])]
            for n, t in r['tests'].items():
                if t.get('crash'):
                    L += ['', f'{n} crashed or hung:', '```', t.get('tail', '')[-600:], '```']
            if r.get('log_tail'):
                L += ['', 'Build failed with no parsed error:', '```', r['log_tail'][-800:], '```']
            d = r['diff'].splitlines()
            L += ['', '```diff'] + d[:40] + ([f'... ({len(d) - 40} more lines)'] if len(d) > 40 else []) + ['```']
    print('\n'.join(L))


def main(a):
    if len(a) < 2 or a[0] not in ('setup', 'check', 'run', 'status', 'report'):
        print(__doc__)
        sys.exit(2)
    st = load(a[1])
    if a[0] == 'setup':
        setup(st)
    elif a[0] == 'check':
        sys.exit(check(st))
    elif a[0] == 'run':
        run(st, [x for x in a[2:] if not x.startswith('--')], '--force' in a)
    elif a[0] == 'status':
        status(st)
    else:
        report(st, '--short' in a)


if __name__ == '__main__':
    main(sys.argv[1:])
