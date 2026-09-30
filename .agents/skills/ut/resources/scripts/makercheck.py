#!/usr/bin/env python3
"""makercheck.py KB_DIR REPO : checks what an agent following SKILL-MAKER.md produced. Every FAIL says what to fix.
Run it at the end of SKILL-MAKER.md and fix until it prints `ALL PASS`. (The checks come from the mistakes a small
model made in a trial run: invented defaults, an atypical exemplar, an empty mock exemplar, dropped hazards, a
wrong stub mode, a shallow index spot-check, a run command that was never run.)"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEAM_DEFAULTS = {'access': 'A1', 'replace': 'B1', 'per-test': 'C5', 'hardware': 'D1', 'state': 'E4'}
res = []


def check(name, ok, fix=''):
    res.append((name, ok))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'\n     fix: {fix}'))


def section(text, title):
    m = re.search(r'^##\s+' + re.escape(title) + r'.*?$(.*?)(?=^##\s|\Z)', text, re.M | re.S)
    return m.group(1) if m else None


def code_block(text):
    m = re.search(r'```[\w+]*\n(.*?)```', text, re.S)
    return m.group(1) if m else ''


def exists_verbatim(repo, dirs, block):
    lines = [l.split('//')[0].rstrip() for l in block.splitlines() if l.strip() and not l.strip().startswith('//')]
    probe = [l for l in lines if len(l.strip()) > 12][:3]
    if not probe:
        return False, None
    for d in dirs:
        for dp, dn, fn in os.walk(os.path.join(repo, d)):
            dn[:] = [x for x in dn if not x.startswith(('build', '.'))]
            for f in fn:
                t = open(os.path.join(dp, f), errors='replace').read()
                if all(p.strip() in t for p in probe):
                    return True, os.path.relpath(os.path.join(dp, f), repo)
    return False, None


def main(a):
    if len(a) < 2:
        print(__doc__); sys.exit(2)
    kb, repo = os.path.abspath(a[0]), os.path.abspath(a[1])
    kj = json.load(open(os.path.join(kb, 'kb.json')))
    prof = kj.get('profile', {})
    tdirs = prof.get('test_paths', []) + prof.get('mock_paths', [])
    notes = open(os.path.join(kb, 'notes.md')).read() if os.path.exists(os.path.join(kb, 'notes.md')) else ''
    report = open(os.path.join(kb, 'SETUP-REPORT.md')).read() if os.path.exists(os.path.join(kb, 'SETUP-REPORT.md')) else ''

    # 1. files and sections
    for t in ('Toolchain', 'Build notes', 'Stubs', 'Coverage', 'Change hazards', 'Index spot-check'):
        check(f'notes.md has "## {t}"', section(notes, t) is not None, f'add the section to {kb}/notes.md (SKILL-MAKER.md)')
    check('SETUP-REPORT.md has Questions and Checklist', bool(re.search(r'Question', report)) and bool(re.search(r'Checklist', report)),
          'write REPORT per steps 11-12')
    kbmd = os.path.join(kb, 'kb.md')
    check('kb.md <= 120 lines', os.path.exists(kbmd) and sum(1 for _ in open(kbmd)) <= 120, 'move details to notes.md / modules/')

    # 2. commands really verified
    cmds = kj.get('commands', {})
    bad = [k for k, v in cmds.items() if not isinstance(v, dict)]
    check('kb.json commands keep the {cmd, verified} format', not bad,
          f'{", ".join(bad)} edited by hand: never edit kb.json; set a command with `ut baseline --task T --{bad[0] if bad else "run"} "<cmd>"`')
    cmds = {k: (v if isinstance(v, dict) else {'cmd': v, 'verified': ''}) for k, v in cmds.items()}
    for k in ('build', 'run'):
        v = (cmds.get(k) or {}).get('verified', '')
        check(f'command "{k}" verified', bool(v) and not v.startswith(('FAILED', 'not run')), f'make `{(cmds.get(k) or {}).get("cmd")}` work, rerun `ut baseline`')
    bdir = (prof.get('compile_db') or 'build-ut/x').split('/')[0]
    built = os.path.isdir(os.path.join(repo, bdir))
    check(f'build folder {bdir} kept', built, f'rebuild it with the build command; never delete build-ut* or build-mcdc '
          '(later tasks and this checker use them)')
    run = (cmds.get('run') or {}).get('cmd', '')
    tok = next((t for t in run.split() if '/' in t and not t.startswith('-')), '')
    if tok and not tok.startswith(('$', '<')) and built:
        check(f'run command binary exists ({tok})', os.path.exists(os.path.join(repo, tok)), 'correct the path of the test binary in the run command')
    st = (cmds.get('single_test') or {}).get('cmd', '')
    tok = next((t for t in st.split() if '/' in t), '')
    if tok and run and 'ctest' not in run:
        check('single-test command uses the run command\'s binary', os.path.basename(tok) in run,
              f'single_test uses {tok}; the main binary is in the run command: `{run}`')

    # 3. exemplar: real, verbatim, typical (in the build target that holds most test files)
    ex = open(os.path.join(kb, 'exemplars', 'test.md')).read() if os.path.exists(os.path.join(kb, 'exemplars', 'test.md')) else ''
    ok, src = exists_verbatim(repo, tdirs, code_block(ex))
    check('exemplars/test.md is verbatim from a test file', ok, 'copy a real test file verbatim (cut to <= 80 lines)')
    if src:
        targets = {}
        for bf in [os.path.join(dp, f) for d in tdirs + ['.'] for dp, _, fs in os.walk(os.path.join(repo, d)) for f in fs
                   if f in ('CMakeLists.txt', 'Makefile') and '/build' not in dp][:20]:
            t = open(bf, errors='replace').read()
            for m in re.finditer(r'add_executable\s*\(\s*(\w+)([^)]*)\)', t):
                body = m.group(2)
                for v in re.findall(r'\$\{(\w+)\}', body):
                    mv = re.search(r'set\s*\(\s*' + v + r'\b([^)]*)\)', t)
                    body += mv.group(1) if mv else ''
                files = re.findall(r'([\w/.-]+(?:_test|Test\w*)\.(?:cpp|cxx|cc|c)\b|[\w/.-]*test_\w+\.(?:cpp|cxx|cc|c)\b)', body)
                targets[m.group(1)] = files
        if targets:
            big = max(targets, key=lambda k: len(targets[k]))
            inbig = any(os.path.basename(src) == os.path.basename(f) for f in targets[big])
            check(f'exemplar ({src}) belongs to the main test target ({big}: {len(targets[big])} test files)', inbig,
                  f'pick the exemplar from the files of `{big}` (the style most tests use); special-purpose test files are not exemplars')

    # 4. mock exemplar when the tests use doubles
    doubles = subprocess.run(['grep', '-rlE', r'__wrap_|mock\(|MOCK_METHOD|_Expect|:\s*public\s+I[A-Z]\w*'] +
                             [os.path.join(repo, d) for d in tdirs if os.path.exists(os.path.join(repo, d))], capture_output=True, text=True).stdout.split()
    mk = open(os.path.join(kb, 'exemplars', 'mock.md')).read() if os.path.exists(os.path.join(kb, 'exemplars', 'mock.md')) else ''
    if doubles:
        ok, _ = exists_verbatim(repo, tdirs, code_block(mk))
        check(f'exemplars/mock.md holds a real test double ({len(doubles)} files use doubles)', ok,
              f'copy one real stub/mock/fake verbatim, plus the test lines that drive it (e.g. from {os.path.relpath(doubles[0], repo)})')

    # 5. stub mode matches the code
    wrapdefs = subprocess.run(['grep', '-rlE', r'__wrap_\w+\s*\('] + [os.path.join(repo, d) for d in tdirs if os.path.exists(os.path.join(repo, d))],
                              capture_output=True, text=True).stdout.split()
    wrapdefs = sorted({os.path.realpath(f) for f in wrapdefs})
    if wrapdefs:
        lenient = any('expectedCallsLeft' in open(f, errors='replace').read() for f in wrapdefs)
        stubs = (section(notes, 'Stubs') or '').lower()
        said = 'lenient' if 'lenient' in stubs and 'strict' not in stubs else 'strict' if 'strict' in stubs and 'lenient' not in stubs else None
        want = 'lenient' if lenient else 'strict'
        check(f'notes Stubs states the stub mode ({want}: {"expectedCallsLeft found" if lenient else "no expectedCallsLeft in the stubs"})',
              said == want, f'write "mode: {want}" in notes.md ## Stubs, with the evidence (grep expectedCallsLeft in {", ".join(os.path.relpath(f, repo) for f in wrapdefs[:2])})')
    if wrapdefs and built:
        wc = subprocess.run([sys.executable, os.path.join(HERE, 'wrapcheck.py'), repo, os.path.join(repo, bdir)]
                            + [x for d in tdirs for x in ('--stubs', d)], capture_output=True, text=True).stdout
        first = [l for l in wc.splitlines() if l.startswith(('OK:', 'FLAG', 'STUB', 'STALE', 'INLINE', 'UNGUARDED'))]
        check('notes Stubs has the wrapcheck result', all(l[:40] in (section(notes, 'Stubs') or '') for l in first[:3]),
              'paste the output of wrapcheck.py into notes.md ## Stubs')

    # 6. hazards: every scanner line kept or dismissed with a reason
    hz = subprocess.run([sys.executable, os.path.join(HERE, 'hazards.py'), repo, '--code'] + prof.get('code_paths', []) + prof.get('header_paths', [])
                        + ['--tests'] + tdirs, capture_output=True, text=True).stdout
    sec = section(notes, 'Change hazards') or ''
    missing = []
    for l in hz.splitlines():
        m = re.search(r'([\w./-]+\.(?:cpp|cxx|cc|c|hpp|hh|h|txt)(?::\d+)?)\b', l)
        if l.startswith('- ') and 'none found' not in l and m and m.group(1) not in sec:
            missing.append(m.group(1))
    check(f'every hazards.py finding is in notes Change hazards (kept, or "false alarm: <reason>")', not missing,
          f'missing: {", ".join(missing[:6])}{" ..." if len(missing) > 6 else ""}')

    # 7. seams: decided, or asked with the real default
    seams = kj.get('seams', {})
    for need, dflt in SEAM_DEFAULTS.items():
        if need in seams:
            d = seams[need]
            if d.get('by') == 'user' and not d.get('evidence') and re.search(r'not confirmed|not available|defaults? (?:used|accepted)', report, re.I):
                check(f'seam "{need}" is not recorded as the user\'s decision when the user did not answer', False,
                      f'record it as a default: `ut seams --task T --set {need}={d.get("choice")} --by "default, not confirmed by the user"`')
            continue
        m = re.search(need + r'[^\n]*\b([A-E][1-7])\b', report)
        check(f'undecided seam "{need}" is asked with a technique ID default (test-seams.md: {dflt})', bool(m),
              f'in REPORT questions: "{need}: which technique? [{dflt}]" (test-seams.md table "Default"); never invent "not needed"')

    # 8. index spot-check done with spotcheck.py
    sp = section(notes, 'Index spot-check') or ''
    check('index spot-check has >= 3 spotcheck.py lines', len(re.findall(r'index callers \d+', sp)) >= 3,
          'run spotcheck.py for >= 3 functions (one C++ method called on objects, if C++) and paste its lines')

    # 9. MC/DC recorded when clang >= 18 exists
    cl = subprocess.run(['sh', '-c', 'clang --version 2>/dev/null | head -1'], capture_output=True, text=True).stdout
    mv = re.search(r'version (\d+)', cl)
    if mv and int(mv.group(1)) >= 18:
        cov = section(notes, 'Coverage') or ''
        check('notes Coverage has the clang MC/DC line (MC/DC: x/y conditions)', bool(re.search(r'MC/DC:?\s*\d+/\d+', cov)), 'step 7.2')
        check('notes Coverage states the "exceeds max (6)" warning count', bool(re.search(r'exceeds max[^\n]*\d|\d+[^\n]*exceeds max', cov)),
              'count the warnings of the clang MC/DC build: grep -c "exceeds max" <build log>, and write it (0 is an answer)')
        check('notes Coverage lists >= 3 decisions (file:line) for the CTC++ cross-check', len(re.findall(r'[\w/.-]+\.(?:cpp|cxx|cc|c):\d+', cov)) >= 3,
              'list 3-5 decisions with 2+ conditions (file:line) under "cross-check pending"')

    # 10. repository untouched
    gs = subprocess.run(['git', '-C', repo, 'status', '--porcelain'], capture_output=True, text=True).stdout
    dirty = [l for l in gs.splitlines() if not re.search(r'\s(build[\w-]*|\.ut)/?$', l.strip())]
    check('repository unchanged (git status: only build folders)', not dirty, 'restore: ' + ', '.join(dirty[:4]))

    n_fail = sum(1 for _, ok in res if not ok)
    print(f'\n{"ALL PASS" if not n_fail else f"{n_fail} FAIL"} ({len(res)} checks)')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
