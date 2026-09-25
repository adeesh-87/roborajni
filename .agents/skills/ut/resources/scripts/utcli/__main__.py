"""ut - the tool around the agent. Setup, research, knowledge base, plan and the executor loop are scripted;
the agent is called only to write test code.  Run:  python3 -m utcli <command> [options]"""
import argparse, json, os, re, sys, subprocess
from .state import State, PHASES
from .util import ask, say, read, write, sh, script, RES, SKILL_DIR, norm, words
from . import detect, kb as KB, baseline, plan as PLAN, run as RUN, harness as HARNESS
from .frameworks import FRAMEWORKS, COVERAGE_TOOLS


def load(args):
    st = State(args.task)
    if 'repo' not in st.d:
        sys.exit(f'{args.task}/state.json has no repo: run init first')
    return st


def opt(p):
    p.add_argument('--task', required=True, help='task folder')
    p.add_argument('--yes', action='store_true', help='take every default, ask nothing')
    p.add_argument('--answers', help='JSON file with answers (non-interactive)')


def answers_of(args):
    return json.load(open(args.answers)) if getattr(args, 'answers', None) else {}


# ------------------------------------------------------------------ init (phase 1)
def cmd_init(args):
    A = answers_of(args)
    st = State(args.task)
    root = detect.repo_root(args.repo or '.')
    st['repo'] = root; st['skill_dir'] = SKILL_DIR
    ident = detect.kb_id(root)
    st['kb_dir'] = KB.kb_dir_for(SKILL_DIR, ident.get('id', 'unknown'))
    os.makedirs(os.path.join(st.dir, 'tasks'), exist_ok=True); os.makedirs(os.path.join(st.dir, 'logs'), exist_ok=True)
    kb = KB.load_kb(st['kb_dir'])
    prof = kb.get('profile') or detect.profile(root)
    for k, v in A.get('profile', {}).items():
        prof[k] = v
    say(f"Repository: {root}  (codebase id {ident.get('id')}; KB {'found' if kb else 'new'})")
    say('Detected profile (correct anything wrong as key=value, empty line to accept):')
    for k, v in prof.items():
        if k != 'ci_hints':
            say(f'  {k} = {v}')
    if prof.get('ci_hints'):
        say('  CI hints: ' + ' || '.join(prof['ci_hints'][:4]))
    if not args.yes and not A:
        while True:
            try:
                line = input('  > ').strip()
            except EOFError:
                line = ''
            if not line:
                break
            if '=' in line:
                k, v = line.split('=', 1); k = k.strip(); v = v.strip()
                prof[k] = [x.strip() for x in v.split(',')] if k.endswith('_paths') else v
    for k, v in A.get('profile', {}).items():
        prof[k] = v
    st['profile'] = prof
    st['request'] = ask('What should I work on? (diff | uncommitted | names of files/functions | continue)', A.get('request', 'diff'), args.yes, A, 'request')
    st['mode'] = 'resume' if st['request'].startswith('continue') else 'diff' if st['request'] in ('diff', 'uncommitted') or st['request'].startswith('range') else 'ask'
    st['permissions'] = {'production_code': ask('May the agent change production code?', 'no', args.yes, A, 'production_code'),
                         'delete_tests': ask('May it delete obsolete tests/mocks?', 'ask', args.yes, A, 'delete_tests'),
                         'commit': ask('Commit?', 'no', args.yes, A, 'commit')}
    st['safe_run'] = ask('Safe to run the build and tests on this machine now?', 'yes', args.yes, A, 'safe_run')
    docs = ask('Docs or decomposition to read (paths, comma separated)', 'none', args.yes, A, 'inputs')
    st['inputs'] = [] if docs == 'none' else [d.strip() for d in docs.split(',')]
    cov = ask('Coverage in this task? (no | tool metric target)', 'no', args.yes, A, 'coverage')
    st['coverage'] = {'wanted': 'no'} if cov == 'no' else {'wanted': 'yes', 'spec': cov}
    res = []
    fw = prof.get('framework')
    if fw: res.append(FRAMEWORKS[fw]['tool_md'])
    if prof.get('build_system'): res.append('tools/build-systems.md')
    for k, (name, md, pat) in COVERAGE_TOOLS.items():
        if name == prof.get('coverage_tool'): res.append(md)
    st['resources'] = res
    for q, a in (('request', st['request']), ('permissions', str(st['permissions'])), ('safe_run', st['safe_run']), ('coverage', cov)):
        st.decide(q, a)
    st.done('setup'); st.log('tool', 'setup done'); st.save()
    say(f"state: {st.path}")


# ------------------------------------------------------------------ baseline (phase 2)
def cmd_baseline(args):
    st = load(args)
    if st['safe_run'] != 'yes':
        sys.exit('safe_run is not yes; refusing to build')
    kb = KB.load_kb(st['kb_dir'])
    res = baseline.run_baseline(st, st['repo'], kb)
    say(f"build: {res['build']}  tests: {res.get('tests', '-')}  single-test: {st['baseline'].get('single_test_cmd')}  compile DB: {st['profile'].get('compile_db')}")
    for p in res.get('problems', [])[:8]:
        say('  problem: ' + p)
    if res.get('tests', '').startswith('none') or not st['profile'].get('test_paths'):
        st['pilot'] = 'yes (greenfield)'
    kb.update({'id': os.path.basename(st['kb_dir']), 'profile': st['profile'], 'updated': res['date']})
    KB.save_kb(st['kb_dir'], kb)
    st.done('baseline', res['build']); st.log('tool', f"baseline {res}"); st.save()


# ------------------------------------------------------------------ knowledge (phase 3)
def cmd_kb(args):
    st = load(args); root = st['repo']; prof = st['profile']; kb = KB.load_kb(st['kb_dir'])
    ident = detect.kb_id(root)
    kb.update({'id': ident.get('id'), 'remote': ident.get('remote'), 'roots': root, 'profile': prof})
    backend = choose_backend(args, st, prof, root)
    rc, out, gd = KB.build_graph(st['kb_dir'], root, prof, prof.get('compile_db'), backend)
    say('\n'.join(l for l in out.splitlines() if re.search(r'index:|backend|preprocessed|augmented|MODE|WARNING|FAILED|translation units|flags borrowed', l)))
    if rc != 0 and backend != 'graphify':
        say(f'index build with {backend} FAILED; falling back to graphify')
        backend = 'graphify'
        rc, out, gd = KB.build_graph(st['kb_dir'], root, prof, prof.get('compile_db'), backend)
    prof['index_backend'] = backend
    kb['last_graph_build'] = f"{baseline.now()} (backend {backend}; {'compile DB' if prof.get('compile_db', 'none') != 'none' else 'no compile DB'})"
    scan = KB.testscan(st['kb_dir'], root, prof)
    ex = KB.make_exemplars(st['kb_dir'], root, prof, scan)
    conv = kb.get('conventions', {})
    if conv.get('approved', 'no') == 'no':
        kb['conventions'] = {'approved': 'no', 'lines': KB.conventions_from_scan(scan, prof) if scan else ['greenfield: no tests yet']}
    files = KB.scope_files(root, prof)
    if args.files:
        files = [f for f in files if any(f.startswith(x) or f == x for x in args.files)]
    kb['modules'] = KB.module_cards(st['kb_dir'], root, prof, gd, files)
    st['kb_modules'] = kb['modules']
    if prof.get('diagrams', 'auto') != 'off' and backend != 'codemap':
        say(KB.make_diagrams(st['kb_dir'], root))
    kb['updated'] = baseline.now()
    KB.save_kb(st['kb_dir'], kb)
    idx = os.path.join(SKILL_DIR, 'resources', 'kb', 'INDEX.md')
    if kb['id'] and not kb['id'].startswith('local-') and kb['id'] not in read(idx):     # local KBs are machine-specific, not listed
        with open(idx, 'a', encoding='utf-8') as fh:
            fh.write(f"| {kb['id']} | {kb.get('remote', '')} | {root} | | {kb['updated']} | {kb['updated']} |\n")
    say(f"KB: {st['kb_dir']}  exemplar: {ex or 'none (greenfield)'}  modules: {len(kb['modules'])}  conventions: {len(kb['conventions']['lines'])} lines")
    st.done('knowledge'); st.log('tool', f"knowledge: {len(kb['modules'])} module cards"); st.save()


def choose_backend(args, st, prof, root):
    """the index backend: the profile's choice, else detection; ONE question only when the choice is a real trade-off"""
    want = prof.get('index_backend') or 'auto'
    if want != 'auto':
        return want
    d = KB.detect_backends(root, prof.get('compile_db'))
    rec, viable = d.get('recommended', 'graphify'), d.get('viable', [])
    say('Index backends on this machine: ' + ', '.join(f"{b} {'OK' if v.get('ok') else 'no (' + v.get('note', '')[:60] + ')'}"
                                                      for b, v in d.get('backends', {}).items()))
    choice = rec
    if rec != 'clang' and 'gcc' in viable and 'graphify' in viable:      # a real trade-off: ask once
        choice = ask('Index backend? gcc = exact calls from your own compiler (compiles every unit once); '
                     'graphify = tolerant tree-sitter parse (no compile needed)', rec, args.yes, answers_of(args), 'index_backend')
    say(f"index backend: {choice} ({d.get('why', '') if choice == rec else 'your choice'})")
    st.decide('index backend', choice)
    return choice


# ------------------------------------------------------------------ index (switch backend / compare)
def cmd_index(args):
    st = load(args); prof = st['profile']; root = st['repo']
    if args.compare:
        other = os.path.join(st['kb_dir'], f'index-{args.compare}')
        rc, out = sh([script('index.sh'), 'build', '--backend', args.compare] + (['--cdb', os.path.join(root, prof['compile_db'])]
                     if prof.get('compile_db', 'none') != 'none' else []) + [other] + KB.scan_paths(prof), cwd=root)
        rc, out = sh([script('index.sh'), 'compare', KB.index_dir(st['kb_dir']), other], cwd=root)
        write(os.path.join(st.dir, f'compare-{args.compare}.md'), out)
        say(out[:3000]); return
    prof['index_backend'] = args.backend
    rc, out, gd = KB.build_graph(st['kb_dir'], root, prof, prof.get('compile_db'), args.backend)
    say(out.strip().splitlines()[-1] if out.strip() else out)
    kb = KB.load_kb(st['kb_dir']); kb['profile'] = prof
    kb['modules'] = KB.module_cards(st['kb_dir'], root, prof, gd, [m['file'] for m in kb.get('modules', [])])
    if prof.get('diagrams', 'auto') != 'off':
        say(KB.make_diagrams(st['kb_dir'], root))
    KB.save_kb(st['kb_dir'], kb)
    st.decide('index backend', args.backend); st.save()


# ------------------------------------------------------------------ coverage (phase 7, scripted)
def cmd_coverage(args):
    """run the coverage build+tests, import the report into the index, annotate the flowcharts, add G work items"""
    st = load(args); root = st['repo']; kb = KB.load_kb(st['kb_dir'])
    cmds = kb.setdefault('commands', {})
    cmd = args.cov_cmd or cmds.get('coverage', {}).get('cmd')
    imp = [x for x in (['--lcov', args.lcov] if args.lcov else ['--gcov-dir', args.gcov_dir] if args.gcov_dir else
                       ['--ctc', args.ctc] if args.ctc else ['--json', args.json] if args.json else [])]
    imp = imp or (cmds.get('coverage_import', {}).get('cmd', '').split(' ', 1) if cmds.get('coverage_import') else [])
    if not imp:
        sys.exit('give the report to import: --lcov FILE | --gcov-dir BUILD_DIR | --ctc profile.txt | --json FILE '
                 '(and --cmd "coverage build+run command" to produce it)')
    if cmd:
        say(f'running: {cmd}')
        rc, out = sh(cmd, cwd=root)
        write(os.path.join(st.dir, 'logs', 'coverage-run.log'), out)
        if rc != 0:
            sys.exit(f'coverage command FAILED (rc {rc}); see logs/coverage-run.log')
        cmds['coverage'] = {'cmd': cmd, 'verified': baseline.now()}
    gd = KB.index_dir(st['kb_dir'])
    rc, out = sh([script('index.sh'), 'cov-import', gd, imp[0], os.path.join(root, imp[1]) if not os.path.isabs(imp[1]) else imp[1]], cwd=root)
    say(out.strip())
    if rc != 0:
        sys.exit('import FAILED')
    cmds['coverage_import'] = {'cmd': f'{imp[0]} {imp[1]}', 'verified': baseline.now()}
    KB.save_kb(st['kb_dir'], kb)
    say(KB.make_diagrams(st['kb_dir'], root))
    rc, gaps = sh([script('index.sh'), 'uncovered', gd], cwd=root)
    write(os.path.join(st.dir, 'coverage-gaps.md'), gaps)
    ir = KB.index_root(gd)
    code = tuple(norm(os.path.relpath(os.path.join(root, p), ir)) for p in st['profile']['code_paths'])
    items, n = [], len(st['work_items'])
    for m in re.finditer(r'^- (\S+) \((\S+):(\d+)\)(?:: (.*))?$', gaps, re.M):
        name, file, line, g = m.groups()
        if not file.startswith(code) or '.lambda@' in name:
            continue
        n += 1
        f_repo = norm(os.path.relpath(os.path.join(ir, file), root))
        items.append({'id': f'W{n}', 'item': f'{f_repo}:{name} (L{line})', 'kind': 'coverage gap' if g else 'never executed',
                      'tests': 'see card', 'mocks': '', 'work': ('G drive: ' + g) if g else 'D no test runs it', 'cat': 'G' if g else 'D',
                      'gaps': [x.strip() for x in (g or '').split(';') if x.strip()], 'in_scope': '', 'priority': ''})
    known = {w['item'].split(' (')[0] for w in st['work_items']}
    new = [w for w in items if w['item'].split(' (')[0] not in known]
    st['work_items'] += new
    st['coverage']['last'] = out.strip().splitlines()[-1] if out.strip() else ''
    st['coverage_gaps'] = [l[2:] for l in gaps.splitlines() if l.startswith('- ')][:60]
    st.done('coverage', st['coverage']['last'][:80])
    say(f"{len(new)} coverage work items added (G = missing outcomes, D = never executed); full list: {os.path.join(st.dir, 'coverage-gaps.md')}")
    for w in new[:20]:
        say(f"  {w['id']:<4} {w['cat']}  {w['item'][:70]}  {w['work'][:90]}")
    st.log('tool', f'coverage imported: {len(new)} work items'); st.save()


# ------------------------------------------------------------------ trace (runtime sequences)
def cmd_trace(args):
    st = load(args); root = st['repo']; prof = st['profile']
    gd = KB.index_dir(st['kb_dir'])
    run = args.run or (st['baseline'].get('test_binaries') or [''])[0]
    if not run:
        sys.exit('give --run "test command" (the test binary built with the trace flags)')
    cmd = [script('index.sh'), 'trace', gd, '--run', run]
    if prof.get('build_system') == 'cmake' and not args.no_build:
        defs = ' '.join(re.findall(r'-D\w+=\S+', prof.get('build_cmd', '')))
        cmd += ['--cmake', root, '--build-dir', os.path.join(gd, 'trace', 'build'), '--cmake-args', defs]
        if not args.run:                                # the baseline binary, but from the instrumented build tree
            m = re.search(r'-B\s*(\S+)', prof.get('build_cmd', ''))
            bdir = os.path.join(root, m.group(1) if m else 'build')
            rel = os.path.relpath(run if os.path.isabs(run) else os.path.join(root, run), bdir)
            if not rel.startswith('..'):
                cmd[cmd.index('--run') + 1] = '{build}/' + rel
    rc, out = sh(cmd, cwd=root)
    say(out.strip()[-1500:])
    if rc == 0:
        kb = KB.load_kb(st['kb_dir'])
        KB.module_cards(st['kb_dir'], root, prof, gd, [m['file'] for m in kb.get('modules', [])])   # cards gain runtime reach
        st.log('tool', 'trace: runtime sequences + reach'); st.save()


# ------------------------------------------------------------------ discovery (phase 4)
def cmd_discover(args):
    st = load(args); gd = KB.index_dir(st['kb_dir'])
    if args.base or args.uncommitted or args.range:
        items, summary = PLAN.discover_diff(st, st['repo'], gd, args.base, args.uncommitted, args.range)
        say(summary.strip()[:600])
    elif args.names:
        items = PLAN.discover_ask(st, st['repo'], gd, args.names)
    else:
        items = st['work_items']
    st['work_items'] = items
    for w in items:
        say(f"  {w['id']:<4} {w['cat']}  {w['item'][:60]:<60} {w['kind']:<16} tests: {w.get('tests', '')[:40]}")
    st.done('discovery', f'{len(items)} items'); st.log('tool', f'discovery: {len(items)} work items'); st.save()


# ------------------------------------------------------------------ scope (phase 5)
def cmd_scope(args):
    st = load(args); A = answers_of(args)
    sel = ask('Work items in scope (all | W1,W3,... | none)', A.get('scope', 'all'), args.yes, A, 'scope')
    keep = None if sel == 'all' else {x.strip() for x in sel.split(',')}
    for w in st['work_items']:
        w['in_scope'] = 'yes' if (keep is None or w['id'] in keep) and w['cat'] != 'I' else 'no'
        w['priority'] = str(PLAN.ORDER.index(w['cat']) + 1 if w['cat'] in PLAN.ORDER else 9)
    st['acceptance'] = ask('Done when?', A.get('acceptance', 'build OK, all tests pass'), args.yes, A, 'acceptance')
    kb = KB.load_kb(st['kb_dir'])
    approved = kb.get('conventions', {}).get('approved', 'no') != 'no'
    no_tests = [w for w in st['work_items'] if w['in_scope'] == 'yes' and w.get('tests', '').startswith('0')]
    st['pilot'] = 'yes (greenfield)' if st['pilot'].startswith('yes (green') else 'yes (conventions not approved)' if not approved else \
        'yes (in-scope code has no tests)' if no_tests and not approved else 'no'
    st.decide('scope', sel); st.decide('acceptance', st['acceptance'])
    say(f"in scope: {sum(1 for w in st['work_items'] if w['in_scope'] == 'yes')} items; pilot: {st['pilot']}")
    st.done('scope'); st.save()


# ------------------------------------------------------------------ plan (phase 8)
def cmd_plan(args):
    st = load(args)
    tasks = PLAN.make_plan(st, st['kb_dir'], st['profile'])
    reasons = PLAN.complexity(st)
    for t in tasks:
        say(f"  {t['id']} w{t['wave']} {t['type']:<14} {t['file']:<28} {len(t['cases'])} cases  touches {', '.join(t['touches'])}")
    if reasons:
        say('COMPLEX: ' + '; '.join(reasons) + f" -> consider a stronger model for the plan (template: {os.path.join(RES, 'templates', 'decompose-request.md')})")
    if not args.yes:
        ok = ask('Approve the plan?', 'yes', False, answers_of(args), 'approve')
        if ok != 'yes':
            say('edit tasks/*.md or state.json and run plan again'); return
    st.done('plan', f'{len(tasks)} tasks'); st.log('tool', f'plan: {len(tasks)} tasks'); st.save()


# ------------------------------------------------------------------ run (phase 9)
def cmd_run(args):
    st = load(args)
    if not st['plan']['tasks']:
        sys.exit('no plan: run plan first')
    if args.diagrams:
        st['diagrams'] = args.diagrams
    RUN.run_tasks(st, st['kb_dir'], args.agent, executor=args.executor, dry=args.dry_run, max_attempts=args.attempts, only=args.only)
    if all(t['status'] != 'TODO' for t in st['plan']['tasks']):
        st.done('execute')
    st.save()
    for t in st['plan']['tasks']:
        say(f"  {t['id']} {t['status']:<12} attempts {t['attempts']}  {t.get('outcome', '')} {(t.get('notes', '') if t['status'] != 'TODO' else '')[:100]}")


# ------------------------------------------------------------------ pilot (phase 6)
def cmd_pilot(args):
    st = load(args); kb = KB.load_kb(st['kb_dir']); prof = st['profile']
    if not prof.get('framework') or not prof.get('test_paths'):
        sys.exit("No tests exist yet: run `ut harness --framework cpputest|gtest` first (creates tests/ and the CMake target), then baseline, kb, pilot")
    # pick two functions: fewest decisions without external calls, and one with a mockable dependency
    cands = []
    for m in kb.get('modules', []):
        cards = read(os.path.join(st['kb_dir'], 'modules', f"{m['name']}.cards.md"))
        for h in re.finditer(r'^## (\S+)\s+\((\S+):(\d+)-(\d+)\)(.*?)$(.*?)(?=^## |\Z)', cards, re.M | re.S):
            name, file, a, b, flags, body = h.groups()
            nd = len(re.findall(r'^\s+L\d+', body, re.M)); ext = '[function' in body or '[pointer' in body
            if 'static' in flags or 'Existing tests calling it directly: none' not in body:
                continue
            cands.append((name, file, nd, ext))
    simple = sorted([c for c in cands if not c[3]], key=lambda c: c[2])[:1]
    withdep = sorted([c for c in cands if c[3]], key=lambda c: c[2])[:1]
    picks = simple + withdep
    if not picks:
        sys.exit('no untested public functions found for a pilot')
    file = picks[0][1]; fw = prof['framework']
    base = os.path.basename(file).rsplit('.', 1)[0]
    test_file = os.path.join(prof['test_paths'][0] if prof['test_paths'] else 'tests', FRAMEWORKS[fw]['file_pattern'].format(module=base))
    t = {'id': 'PILOT', 'title': f"pilot tests for {', '.join(p[0] for p in picks)}", 'type': 'add-tests', 'file': file,
         'functions': [p[0] for p in picks], 'work_items': [], 'wave': 0, 'depends': [], 'status': 'TODO', 'owner': '', 'attempts': 0,
         'touches': [test_file] + [r.split(':')[0] for r in re.findall(r'^- (\S+:\d+)', read(os.path.join(st['kb_dir'], 'exemplars', 'register.md')), re.M)][:1],
         'test_file': test_file, 'cases': []}
    cards = read(os.path.join(st['kb_dir'], 'modules', f"{os.path.basename(file)}.cards.md"))
    for p in picks:
        t['cases'] += [(p[0],) + c for c in PLAN.cases_for(cards, p[0])[:2]]
    PLAN.write_task_file(st, t, st['kb_dir'])
    review = None
    for rnd in range(1, 4):
        ppath = os.path.join(st.dir, 'prompts', f'PILOT-{rnd}.md'); write(ppath, RUN.prompt_for(st, st['kb_dir'], t, review=review))
        say(f"pilot round {rnd}: prompt {words(read(ppath))} words")
        if args.dry_run:
            return
        rc, out = RUN.call_agent(st, ppath, args.agent)
        status, detail, log = RUN.build_and_test(st, t)
        for fix in range(2):
            if status == 'OK': break
            write(ppath, RUN.prompt_for(st, st['kb_dir'], t, error=str(detail))); RUN.call_agent(st, ppath, args.agent)
            status, detail, log = RUN.build_and_test(st, t)
        say(f"pilot build/run: {status} {detail if status == 'OK' else str(detail)[:300]}")
        say('----- ' + test_file + ' -----'); say(read(os.path.join(st['repo'], test_file))); say('-----')
        review = ask('Approve as is, or describe changes', 'approve', args.yes, answers_of(args), f'review{rnd}')
        if review == 'approve':
            break
    # save the approved style
    body = read(os.path.join(st['repo'], test_file))
    write(os.path.join(st['kb_dir'], 'exemplars', 'test.md'), f'# Test exemplar: {test_file}  (approved on {baseline.now()} by the user, pilot)\n'
          'Copy this shape for every new test.\n\n```cpp\n' + KB.annotate(body, fw) + '\n```\n')
    kb.setdefault('conventions', {})['approved'] = f'{baseline.now()} (pilot: {test_file})'
    KB.save_kb(st['kb_dir'], kb)
    st['pilot'] = 'done'; st.done('pilot'); st.log('tool', f'pilot approved: {test_file}'); st.save()


def cmd_harness(args):
    st = load(args)
    rc, out, files = HARNESS.create(st, args.framework, args.dir)
    say(('harness OK: ' if rc == 0 else 'harness FAILED: ') + ', '.join(files) + '\n' + ('' if rc == 0 else out[-1500:]))
    st.log('tool', f"harness {args.framework}: {'OK' if rc == 0 else 'FAILED'}"); st.save()
    if rc == 0:
        say('now run: baseline, then kb, then pilot')


def cmd_close(args):
    st = load(args); say(RUN.closeout(st, st['kb_dir']))


def cmd_status(args):
    st = load(args)
    say(f"phases: {', '.join(p + ('✔' if p in st['phases'] else '·') for p in PHASES)}")
    say(f"work items: {len(st['work_items'])}  tasks: {[(t['id'], t['status']) for t in st['plan']['tasks']]}")
    say(f"next: {st['next_steps']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog='ut', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('init', help='phase 1: detect, ask, create the task folder'); opt(s); s.add_argument('--repo')
    s = sub.add_parser('baseline', help='phase 2: verified commands, compile DB, build + run'); opt(s)
    s = sub.add_parser('kb', help='phase 3: graph, testscan, exemplars, conventions, cards'); opt(s); s.add_argument('--files', nargs='*', help='limit cards to these files/dirs')
    s = sub.add_parser('discover', help='phase 4: work items'); opt(s); s.add_argument('--base'); s.add_argument('--uncommitted', action='store_true'); s.add_argument('--range'); s.add_argument('--names', nargs='*')
    s = sub.add_parser('scope', help='phase 5: choose work items, acceptance, pilot decision'); opt(s)
    s = sub.add_parser('pilot', help='phase 6: two tests reviewed by the user become the exemplar'); opt(s); s.add_argument('--agent', default=RUN.DEFAULT_AGENT); s.add_argument('--dry-run', action='store_true')
    s = sub.add_parser('plan', help='phase 8: tasks with Cases from the cards'); opt(s)
    s = sub.add_parser('run', help='phase 9: executor loop'); opt(s); s.add_argument('--agent', default=RUN.DEFAULT_AGENT, help='command; reads the prompt on stdin, or use {prompt} for the file')
    s.add_argument('--executor', default='E1'); s.add_argument('--dry-run', action='store_true'); s.add_argument('--attempts', type=int, default=3); s.add_argument('--only', nargs='*')
    s.add_argument('--diagrams', choices=['auto', 'on', 'off'], help='Mermaid diagrams in the prompts (default: the profile, auto)')
    s = sub.add_parser('harness', help='greenfield: create tests/CMakeLists.txt + runner + smoke test, hook into the root CMake, build it'); opt(s); s.add_argument('--framework', default='cpputest', choices=['cpputest', 'gtest']); s.add_argument('--dir', default='tests')
    s = sub.add_parser('close', help='phase 10'); opt(s)
    s = sub.add_parser('index', help='rebuild the code index with another backend, or compare two backends'); opt(s)
    s.add_argument('--backend', default='clang', choices=['clang', 'gcc', 'graphify', 'codemap']); s.add_argument('--compare', choices=['clang', 'gcc', 'graphify'])
    s = sub.add_parser('coverage', help='phase 7: run coverage, import it, annotate flowcharts, add work items'); opt(s)
    s.add_argument('--cmd', dest='cov_cmd', help='coverage build+run command'); s.add_argument('--lcov'); s.add_argument('--gcov-dir'); s.add_argument('--ctc'); s.add_argument('--json')
    s = sub.add_parser('trace', help='runtime sequence per TEST (-finstrument-functions); cards gain runtime reach'); opt(s)
    s.add_argument('--run', help='test command; {build} = the trace build dir'); s.add_argument('--no-build', action='store_true')
    s = sub.add_parser('status'); opt(s)
    a = p.parse_args(argv)
    {'init': cmd_init, 'baseline': cmd_baseline, 'kb': cmd_kb, 'discover': cmd_discover, 'scope': cmd_scope, 'pilot': cmd_pilot,
     'plan': cmd_plan, 'run': cmd_run, 'close': cmd_close, 'status': cmd_status, 'harness': cmd_harness,
     'index': cmd_index, 'coverage': cmd_coverage, 'trace': cmd_trace}[a.cmd](a)


if __name__ == '__main__':
    main()
