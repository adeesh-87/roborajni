#!/usr/bin/env python3
"""makercheck.py KB_DIR REPO : checks what an agent following SKILL-MAKER.md produced. Every FAIL says what to fix.
makercheck.py --skeleton learnings : the table for KB_DIR/learnings.md, one row per learning of resources/learnings.md.
Run it at the end of SKILL-MAKER.md and fix until it prints `ALL PASS`. (The checks come from the mistakes a small
model made in a trial run: invented defaults, an atypical exemplar, an empty mock exemplar, dropped hazards, a
wrong stub mode, a shallow index spot-check, a run command that was never run.)"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.realpath(os.path.join(HERE, '..', '..'))
LEARN = os.path.join(SKILL_DIR, 'resources', 'learnings.md')
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


def learnings():
    """[(ID, first sentence)] from resources/learnings.md"""
    out = []
    for l in open(LEARN, errors='replace'):
        m = re.match(r'^\| (L\d+) \| (.+?) \|', l)
        if m:
            t = re.split(r'(?<=[.:;])\s', m.group(2))[0]
            out.append((m.group(1), t if len(t) <= 110 else t[:110].rsplit(' ', 1)[0] + ' …'))
    return out


def table_rows(text):
    return [[c.strip() for c in l.strip().strip('|').split('|')] for l in text.splitlines()
            if l.startswith('|') and not re.match(r'^\|\s*-', l)]


def main(a):
    if a[:2] == ['--skeleton', 'learnings']:
        print('# Learnings: verdicts for this codebase\n\nOne row per learning of `resources/learnings.md` (read it for the full '
              'text and the check). Applies: yes / no / partly / unknown. Evidence: file:line, a command and its result, or a '
              'count. The project rule is what agents do here; it wins over the generic docs.\n')
        print('| ID | Learning | Applies | Evidence | Project rule |\n|---|---|---|---|---|')
        for i, t in learnings():
            print(f'| {i} | {t} | | | |')
        return 0
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
          'write REPORT per steps 10 and 14')
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

    # 10. workarounds: every category found by workarounds.py has a row with where, and a rule
    wpath = os.path.join(kb, 'workarounds.md')
    wtext = open(wpath).read() if os.path.exists(wpath) else ''
    check('workarounds.md exists (step 8b)', bool(wtext), 'run workarounds.py and write KB_DIR/workarounds.md from resources/templates/workarounds.md')
    if wtext:
        wo = subprocess.run([sys.executable, os.path.join(HERE, 'workarounds.py'), repo, '--code'] + prof.get('code_paths', []) + prof.get('header_paths', [])
                            + ['--tests'] + tdirs, capture_output=True, text=True).stdout
        cats = re.findall(r'^- \*\*(.+?)\*\*', wo, re.M)
        miss = [c for c in cats if c.lower() not in wtext.lower()]
        check(f'workarounds.md has a row for every workarounds.py category ({len(cats)})', not miss, f'add rows for: {", ".join(miss)}')
        rows = [r for r in table_rows(wtext) if len(r) >= 6 and r[0] != '#']
        bad = [r[0] for r in rows if not re.search(r'[\w/.-]+:\d+|[\w/.-]+\.(?:txt|cmake|mk|yml|c|cpp|h|hpp)\b|[0-9a-f]{7}', r[2]) or not r[4] or r[4].startswith('<')]
        check('every workarounds.md row has a Where (file:line or commit) and a Rule for new tests', rows and not bad,
              f'rows {", ".join(bad[:6])}: fill Where and Rule (copy / never / ask / not a workaround: <reason>)')

    # 11. learnings: a verdict with evidence for every ID
    lpath = os.path.join(kb, 'learnings.md')
    ltext = open(lpath).read() if os.path.exists(lpath) else ''
    check('learnings.md exists (step 8c)', bool(ltext), f'python3 {HERE}/makercheck.py --skeleton learnings > {lpath}, then fill it')
    if ltext:
        rows = {r[0]: r for r in table_rows(ltext) if r and re.match(r'L\d+$', r[0])}
        ids = [i for i, _ in learnings()]
        miss = [i for i in ids if i not in rows]
        bad = [i for i in ids if i in rows and (len(rows[i]) < 5 or rows[i][2].lower().split(' ')[0] not in ('yes', 'no', 'partly', 'unknown')
                                                or not rows[i][3])]
        norule = [i for i in ids if i in rows and len(rows[i]) >= 5 and rows[i][2].lower().startswith(('yes', 'partly')) and len(rows[i][4]) < 8]
        pend = [i for i in ids if i in rows and 'pending' in ' '.join(rows[i]).lower()]
        check(f'learnings.md has all {len(ids)} learnings, each with a verdict and evidence', not miss and not bad,
              f'missing {", ".join(miss[:8])}; no verdict or evidence: {", ".join(bad[:8])}')
        check('every "yes"/"partly" learning has a project rule', not norule, f'write the rule agents follow here: {", ".join(norule[:8])}')
        check('no learning is left "pending study"', not pend, f'fill {", ".join(pend)} from the study findings (step 11)')

    # 12. codebase map
    cpath = os.path.join(kb, 'codebase.md')
    ctext = open(cpath).read() if os.path.exists(cpath) else ''
    check('codebase.md made by codemap.py (step 9)', 'Generated by codemap.py' in ctext, f'python3 {HERE}/codemap.py {kb} > {cpath}')
    if ctext:
        check('codebase.md <= 250 lines', len(ctext.splitlines()) <= 250, 'it is a map: shorten the agent sections, link to modules/')
        comps = re.findall(r'^\| `([^`]+)` \|', section(ctext, 'Components') or '', re.M)
        purp = section(ctext, 'Purpose of each component') or ''
        nop = [c for c in comps if not re.search(r'^- `?' + re.escape(c) + r'`?\b.*\(source:', purp, re.M)]
        check('codebase.md: every component has a purpose line with (source: ...)', comps and not nop, f'add: {", ".join(nop[:6])}')
        for t in ('Domain words', 'Rules the code relies on', 'How the tests map to the code'):
            sec = section(ctext, t) or ''
            check(f'codebase.md "{t}" is filled', len(re.findall(r'^- ', sec, re.M)) >= 1, f'write the section (step 9); "- none: <why>" if empty')

    # 13. the change-impact study on this codebase
    sj = os.path.join(kb, 'study', 'study.json')
    check('study/study.json exists (step 11)', os.path.exists(sj), 'follow resources/impact-study.md')
    if os.path.exists(sj):
        try:
            st = json.load(open(sj))
        except ValueError as e:
            st = None
            check('study.json is valid JSON', False, str(e))
        if st:
            sys.path.insert(0, HERE)
            import impactstudy
            cat = impactstudy.catalog()
            sc = st.get('scenarios', [])
            ids = {x.get('id') for x in sc}
            miss = [i for i in cat if i not in ids]
            check(f'study covers every reference ID ({len(cat)}), as a scenario or "na"', not miss, f'missing: {", ".join(miss)}')
            live = [x for x in sc if not x.get('na')]
            resd = os.path.join(kb, 'study', 'results')
            got = {x['id']: json.load(open(os.path.join(resd, x['id'] + '.json'))) for x in live if os.path.exists(os.path.join(resd, x['id'] + '.json'))}
            check(f'every scenario has a result ({len(got)}/{len(live)})', len(got) == len(live),
                  f'impactstudy.py run: {", ".join(x["id"] for x in live if x["id"] not in got)[:120]}')
            inc = [i for i, r in got.items() if r.get('prod_errors')]
            check('no scenario with an incomplete edit (production code must compile)', not inc, f'add edits, run --force: {", ".join(inc)}')
            nol = [x['id'] for x in live if len(x.get('lesson', '')) < 20]
            check('every scenario has a lesson', not nol, f'write "lesson" for {", ".join(nol[:10])}')
            nona = [x['id'] for x in sc if x.get('na') is not None and len(str(x.get('na'))) < 10]
            check('every "na" says why', not nona, f'{", ".join(nona)}')
            nexp = [x['id'] for x in live if x.get('expect') not in impactstudy.OUTCOMES or not x.get('why')]
            check('every scenario has "why" and a prediction ("expect")', not nexp, f'{", ".join(nexp[:10])}')
            ps = [x for x in live if x['id'] not in cat]
            check('3+ scenarios from the project history (P*), or "history": <why none>', len(ps) >= 3 or len(str(st.get('history', ''))) > 10,
                  'resources/impact-study.md step 3')
            check('3+ findings', len(st.get('findings') or []) >= 3, 'write "findings" in study.json')
            for f in ('STUDY.md', 'change-impact.md'):
                fp = os.path.join(kb, f)
                txt = open(fp).read() if os.path.exists(fp) else ''
                newest = max([os.path.getmtime(os.path.join(resd, i + '.json')) for i in got] + [os.path.getmtime(sj)]) if got else 0
                fresh = txt and os.path.getmtime(fp) >= newest and all(f'| {i} |' in txt for i in got)
                check(f'{f} generated from the current results', bool(fresh),
                      f'python3 {HERE}/impactstudy.py report {sj}{" --short" if f != "STUDY.md" else ""} > {fp}')

    # 14. the project skill and the project playbooks
    kid = os.path.basename(os.path.normpath(kb))
    cands = []
    for d in sorted(os.listdir(os.path.dirname(SKILL_DIR))):
        sp_ = os.path.join(os.path.dirname(SKILL_DIR), d, 'SKILL.md')
        if os.path.realpath(os.path.dirname(sp_)) != SKILL_DIR and os.path.exists(sp_) and kid in open(sp_, errors='replace').read():
            cands.append(sp_)
    check(f'a project skill next to ut names this KB ({kid})', bool(cands), f'step 12: create {os.path.dirname(SKILL_DIR)}/ut-<project>/SKILL.md')
    if cands:
        t = open(cands[0], errors='replace').read()
        check('project skill has frontmatter name and description', bool(re.search(r'^---\s*\nname:\s*\S+.*\ndescription:\s*\S.{40,}', t, re.S)),
              'start with --- / name: ut-<project> / description: <trigger words> / ---')
        check('project skill <= 80 lines', len(t.splitlines()) <= 80, 'point to KB files instead of copying them')
        rules = re.findall(r'^\d+\.\s.*$', section(t, 'Always') or '', re.M)
        nosrc = [r[:40] for r in rules if not re.search(r'\([^)]*(?:KB|\.md|notes|study|seams|Commands)[^)]*\)\s*\.?\s*$', r)]
        check('project skill "Always" has 1-12 rules, each ending with its KB source', 1 <= len(rules) <= 12 and not nosrc,
              f'{len(rules)} rules; without a source: {"; ".join(nosrc[:3])}')
        refs = set(re.findall(r'`((?:modules/)?[\w-]+\.md)`', section(t, 'Load when') or ''))
        gone = [r for r in refs if not os.path.exists(os.path.join(kb, r)) and not os.path.exists(os.path.join(SKILL_DIR, r))
                and not r.startswith(('resources/', 'SKILL'))]
        check('every KB file the project skill loads exists', not gone, f'missing in {kb}: {", ".join(gone)}')
    gen = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(SKILL_DIR, 'resources', 'playbooks')) if f.endswith('.md'))
    pb = section(report, 'Playbooks') or ''
    missp = [g for g in gen if not re.search(r'\b' + re.escape(g) + r'\b', pb)]
    check(f'REPORT "## Playbooks" has a line for each generic playbook ({len(gen)})', not missp, f'add "<name>: same" or "<name>: KB override (<why>)" for {", ".join(missp)}')
    kpb = os.path.join(kb, 'playbooks')
    over = sorted(os.path.splitext(f)[0] for f in os.listdir(kpb) if f.endswith('.md')) if os.path.isdir(kpb) else []
    said = re.findall(r'([\w-]+):\s*KB override', pb)
    check('KB playbooks match the overrides named in REPORT', sorted(set(said)) == over and all(o in gen for o in over),
          f'files: {over or "none"}; REPORT says: {said or "none"}; an override has the name of a generic playbook')

    # 15. repository untouched
    gs = subprocess.run(['git', '-C', repo, 'status', '--porcelain'], capture_output=True, text=True).stdout
    dirty = [l for l in gs.splitlines() if not re.search(r'\s(build[\w-]*|\.ut)/?$', l.strip())]
    check('repository unchanged (git status: only build folders)', not dirty, 'restore: ' + ', '.join(dirty[:4]))

    n_fail = sum(1 for _, ok in res if not ok)
    print(f'\n{"ALL PASS" if not n_fail else f"{n_fail} FAIL"} ({len(res)} checks)')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
