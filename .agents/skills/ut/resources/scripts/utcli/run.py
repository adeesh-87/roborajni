"""Executor loop, pilot and closeout: the agent writes code; the tool does everything else."""
import os, re, shlex, subprocess, time
from .util import sh, script, read, write, RES, SKILL_DIR, words, norm, say
from .frameworks import FRAMEWORKS, parse_summary, failures, first_errors
from .state import now

# The agent may run ONLY index.sh for code questions; grep/find/Glob are denied so it queries the index instead.
DEFAULT_AGENT = ("claude -p --permission-mode acceptEdits "
                 f"--allowedTools 'Read,Edit,Write,MultiEdit,Bash({script('index.sh')}:*)' "
                 "--disallowedTools 'Grep,Glob,Bash(grep:*),Bash(rg:*),Bash(find:*),Bash(cat:*){deny_code}'")
# {deny_code}: Read(./<code path>/**) for every code and header path of the profile: the code under test is read
# through `index.sh source` (test files, mocks and build files stay readable).


def prompt_for(st, kb_dir, t, error=None, review=None):
    prof = st['profile']; fw = prof.get('framework') or 'cpputest'
    P = []
    P.append('You are writing C/C++ unit tests for a task prepared by a tool. Rules:')
    P.append(f"- Write or edit ONLY these files (create them if missing): {', '.join(t['touches'])}. Never touch other files; never change production code.")
    P.append('- Do not run the build or the tests; the tool does that after you finish and will come back with the first error if any.')
    P.append('- Copy the exemplar\'s shape exactly (includes, group/fixture, setup/teardown, naming, asserts, mock style).')
    P.append('- Expected values are literals derived from reading the code and its comments; never derived by running the code. '
             'If the code seems wrong, keep the assertion that the specification implies and say so in RESULT.')
    P.append('- One test per line of the Cases table. Finish with a line: RESULT: DONE  or  RESULT: PARTIAL <what is missing>.')
    ix, gd = script('index.sh'), os.path.join(kb_dir, 'index')
    P.append(f"- Everything you need about the code is below. For anything else ask the code index, never grep or open source files:\n"
             f"  `{ix} source {gd} <function|type|macro|constant>` (its code or definition; `\"TEST(Group, Name)\"` for a test; `name@LINE` for one overload),\n"
             f"  `{ix} refs {gd} <function>` (callers, tests, mocks, pointers), `{ix} defs {gd} <name>` (every definition, mocks included),\n"
             f"  `{ix} find {gd} <regex>` (names), `{ix} card|deps {gd} <function>`. Reading the code folders and grep are blocked;\n"
             f"  Read only the test, mock and build files you write. If the index cannot answer a question, say which one in RESULT.")
    from .seams import render as render_seams
    from .kb import load_kb
    seams = load_kb(kb_dir).get('seams', {})
    P.append('- Test seams below are DECIDED for this project: use only these techniques, never another one. If the task needs '
             'a seam whose need is "not decided" (e.g. calling a static/private function, mocking in one test but not another), '
             'do not improvise: finish with RESULT: PARTIAL needs seam <need>.')
    P.append('\n## Test seams (decided)\n' + '\n'.join(render_seams(seams)))
    P.append(f"\nRepository root: {st['repo']}\n")
    P.append('## Task\n' + read(os.path.join(st.dir, 'tasks', f"{t['id']}.md")))
    P.append('\n## Test exemplar (copy this shape)\n' + read(os.path.join(kb_dir, 'exemplars', 'test.md')))
    if t['type'] in ('fix-mocks', 'add-tests') or 'mock' in ' '.join(c[2] for c in t.get('cases', [])):
        P.append('\n## Mock exemplar\n' + read(os.path.join(kb_dir, 'exemplars', 'mock.md')))
    P.append('\n## Registration\n' + read(os.path.join(kb_dir, 'exemplars', 'register.md')))
    from .plan import card_block
    cards = read(os.path.join(kb_dir, 'modules', f"{os.path.basename(t['file'])}.cards.md"))
    lines = t.get('lines') or {}
    for f in t['functions']:
        m = card_block(cards, f, lines.get(f))
        if m:
            P.append(f'\n## Card: {f}\n' + m.group(0).strip())
    src = read(os.path.join(st['repo'], t['file']))
    for f in t['functions']:   # the function's source itself, cut from the card's line range
        m = card_block(cards, f, lines.get(f))
        if m and m.group(1) and src:
            a, b = int(m.group(1)), int(m.group(2))
            P.append(f"\n## Source: {t['file']}:{a}-{b}\n```c\n" + '\n'.join(src.splitlines()[a - 1:b]) + '\n```')
    P += diagrams_for(st, kb_dir, t, cards)
    if t['test_file'] and os.path.exists(os.path.join(st['repo'], t['test_file'])):
        body = read(os.path.join(st['repo'], t['test_file']))
        P.append(f"\n## Current test file {t['test_file']} ({len(body.splitlines())} lines; add to it)\n```cpp\n{body[:6000]}\n```")
    P.append('\n## Playbook\n' + read(os.path.join(RES, 'playbooks', f"{t['type']}.md")))
    tool_md = read(os.path.join(RES, FRAMEWORKS[fw]['tool_md']))
    P.append('\n## Framework syntax\n' + tool_md)
    if error:
        P.append('\n## The tool built and ran your tests. It FAILED. First errors:\n```\n' + error + '\n```')
        errs = read(os.path.join(RES, FRAMEWORKS[fw]['errors_md']))
        rows = [l for l in errs.splitlines() if l.startswith('| ') and any(k in l for k in error_keys(error))]
        if rows:
            P.append('Known causes for these messages:\n' + '\n'.join(rows[:6]))
        P.append('Fix the cause in the files you may write. Do not weaken or delete an assertion to make a test pass.')
    if review:
        P.append('\n## The user reviewed your test file and asks for these changes:\n' + review + '\nApply them to the same file.')
    return '\n'.join(P)


DIAG_LEGEND = ('Mermaid TEXT for you to read (never render it). Flow: Lnn = source line; T/F = the condition true/false; '
               '"NOT HIT" = no test takes that edge yet; "Nx" = times taken. Sequence: the calls in order with the branch or loop '
               'around them; participant notes name existing test doubles to reuse.')
DIAG_BUDGET = 900      # words of diagrams per prompt


def diagrams_for(st, kb_dir, t, cards):
    from .plan import card_block
    """flowchart when branches matter (coverage task, >= 4 decisions); sequence when collaborators matter (mock task,
    >= 2 interface/external/pointer calls). Always generated fresh from the index (includes the last coverage run)."""
    # default off: in the A/B run on cvaccel the diagrams did not improve results (resources/diagrams.md)
    mode = st.get('diagrams') or st['profile'].get('prompt_diagrams', 'off')
    gd = os.path.join(kb_dir, 'index')
    if mode == 'off' or not os.path.exists(os.path.join(gd, 'index.json')):
        return []
    out, budget = [], DIAG_BUDGET
    for f in t['functions']:
        m = card_block(cards, f, (t.get('lines') or {}).get(f))
        block = m.group(3) if m else ''
        ndec = len(re.findall(r'^\s+L\d+\s', block, re.M))
        calls = (re.search(r'^Calls: (.*)$', block, re.M) or re.search('()', '')).group(1)
        nmock = len(re.findall(r'\[(?:interface|function|pointer)|pure virtual', calls))
        want = [('flow', mode == 'on' or t['type'] == 'raise-coverage' or ndec >= 4),
                ('seq', mode == 'on' or t['type'] == 'fix-mocks' or nmock >= 2)]
        for kind, ok in want:
            if not ok:
                continue
            ln = (t.get('lines') or {}).get(f)
            rc, txt = sh([script('index.sh'), kind, gd, f'{f}@{ln}' if ln else f], cwd=st['repo'])
            if rc != 0 or not txt.strip().startswith('%%'):
                continue
            w = words(txt)
            if w > budget:
                out.append(f'\n(The {kind} diagram of {f} is {w} words, over the budget: `index.sh {kind} {gd} {f}` prints it.)')
                continue
            budget -= w
            out.append(f"\n## {'Flow' if kind == 'flow' else 'Sequence'}: {f}\n```mermaid\n{txt.strip()}\n```")
    if out:
        out.insert(0, '\n## Diagrams\n' + DIAG_LEGEND)
    return out


def error_keys(error):
    keys = set()
    for w in ('undefined reference', 'multiple definition', 'No such file', 'extern', 'Unexpected call', 'WAS NOT fulfilled',
              'expected', 'Memory leak', 'too few', 'too many', 'conflicting', 'was not declared', 'Called more', 'Called fewer', 'Argument'):
        if w.lower() in error.lower():
            keys.add(w)
    return keys or {'error'}


def call_agent(st, prompt_path, agent_cmd):
    prof = st['profile']
    code = [p.strip('./') for p in prof.get('code_paths', []) + prof.get('header_paths', []) if p.strip('./')]
    agent_cmd = agent_cmd.replace('{deny_code}', ''.join(f',Read(./{p}/**)' for p in code))
    cmd = agent_cmd.replace('{prompt}', shlex.quote(prompt_path))
    if '{prompt}' in agent_cmd:
        rc, out = sh(cmd, cwd=st['repo'], timeout=3600)
    else:
        rc, out = sh(cmd, cwd=st['repo'], timeout=3600, input_text=read(prompt_path))
    return rc, out


def registered(st, test_file):
    base = os.path.basename(test_file)
    if st['profile'].get('build_system') == 'ceedling':
        return True                     # Ceedling picks test_*.c up by itself
    rc, out = sh(['grep', '-rlF', base, '--include=CMakeLists.txt', '--include=*.cmake', '--include=Makefile*', '--include=*.mk', st['repo']])
    return bool(out.strip())


def build_and_test(st, t=None):
    cmds = st['commands']; env = cmds.get('env_setup', '')
    pre = (env + ' && ') if env and env != 'none' else ''
    rc, bout = sh(pre + cmds['build'], cwd=st['repo'])
    if rc != 0:
        return 'BUILD_FAILED', '\n'.join(first_errors(bout)) or bout[-2000:], bout
    run_cmd = single_test_cmd(st, t) if t else cmds['run']
    rc2, rout = sh(pre + run_cmd, cwd=st['repo'])
    fw = framework_of(st, t['test_file']) if t and t.get('test_file') else (st['profile'].get('framework') or 'cpputest')
    summ = parse_summary(fw, rout)
    if rc2 != 0 or (summ and summ.get('failed')):
        return 'TESTS_FAILED', '\n'.join(failures(fw, rout) + [l for l in rout.splitlines() if 'expected' in l.lower() or 'but was' in l.lower()][:10]) or rout[-2000:], rout
    return 'OK', summ or {'exit': rc2}, rout


def framework_of(st, test_file):
    src = read(os.path.join(st['repo'], test_file))
    for k, f in FRAMEWORKS.items():
        if re.search(f['detect'], src, re.M):
            return k
    return st['profile'].get('framework') or 'cpputest'


def binary_for(st, test_file):
    """the test executable whose build target lists this test file (CMake/Make), else the first one"""
    bins = st['baseline'].get('test_binaries', [])
    base = os.path.basename(test_file)
    for bf in ('CMakeLists.txt', os.path.join('tests', 'CMakeLists.txt'), 'Makefile'):
        txt = read(os.path.join(st['repo'], bf))
        m = re.search(r'add_executable\s*\(\s*(\w+)[^)]*\b' + re.escape(base), txt)
        if m:
            hit = [b for b in bins if os.path.basename(b) == m.group(1)]
            if hit:
                return hit[0]
    return bins[0] if bins else ''


def single_test_cmd(st, t):
    if not t or not t.get('test_file'):
        return st['commands']['run']
    fw = framework_of(st, t['test_file'])          # the test file decides the framework (mixed repos)
    test_src = read(os.path.join(st['repo'], t['test_file']))
    groups = re.findall(FRAMEWORKS[fw]['test_regex'], test_src, re.M)
    group = groups[0][0] if groups and isinstance(groups[0], tuple) else (groups[0] if groups else '')
    binary = binary_for(st, t['test_file'])
    if not binary or not group:
        return st['commands']['run']
    if st['profile'].get('build_system') == 'ceedling':
        return f"ceedling test:{os.path.basename(t['test_file']).rsplit('.', 1)[0]}"
    return FRAMEWORKS[fw]['filter'](binary, group, '')


def run_tasks(st, kb_dir, agent_cmd, executor='E1', dry=False, max_attempts=3, only=None):
    tasks = st['plan']['tasks']
    while True:
        ready = [t for t in tasks if t['status'] == 'TODO' and all(d['status'] in ('DONE', 'PARTIAL', 'DROPPED') for d in tasks if d['id'] in t['depends'])
                 and all(st['plan']['checkpoints'].get(str(w), '') == 'PASSED' for w in range(1, t['wave']) if any(x['wave'] == w for x in tasks))
                 and (not only or t['id'] in only)]
        if not ready:
            break
        t = ready[0]
        t['status'], t['owner'] = 'IN_PROGRESS', executor; st.log(executor, f"start {t['id']} {t['title']}"); st.save()
        error = None
        new_files = [f for f in t['touches'] if f.endswith(('.c', '.cc', '.cpp', '.cxx')) and not os.path.exists(os.path.join(st['repo'], f))]
        before = {f: read(os.path.join(st['repo'], f), None) for f in t['touches']}     # to restore if the task ends BLOCKED
        for attempt in range(1, max_attempts + 1):
            t['attempts'] = attempt
            ppath = os.path.join(st.dir, 'prompts', f"{t['id']}-{attempt}.md")
            write(ppath, prompt_for(st, kb_dir, t, error))
            say(f"[{executor}] {t['id']} attempt {attempt}: prompt {words(read(ppath))} words -> {ppath}")
            if dry:
                t['status'] = 'TODO'; st.save(); return
            rc, out = call_agent(st, ppath, agent_cmd)
            write(os.path.join(st.dir, 'logs', f"{t['id']}-{attempt}-agent.log"), out)
            result = re.search(r'RESULT:\s*(DONE|PARTIAL.*)', out)
            unregistered = [f for f in new_files if os.path.exists(os.path.join(st['repo'], f)) and not registered(st, f)]
            if unregistered:
                status, detail, log = 'NOT_REGISTERED', f"new test file(s) not registered in the build: {', '.join(unregistered)}. Add them exactly as exemplars/register.md shows.", ''
            else:
                status, detail, log = build_and_test(st, t)
            write(os.path.join(st.dir, 'logs', f"{t['id']}-{attempt}-build.log"), log)
            if status == 'OK':
                t['status'] = 'PARTIAL' if result and result.group(1).startswith('PARTIAL') else 'DONE'
                t['notes'] = (result.group(1) if result else '') + f' | tests: {detail}'
                st.log(executor, f"{t['id']} {t['status']} after {attempt} attempt(s): {detail}"); break
            error = detail if isinstance(detail, str) else str(detail)
            say(f"[{executor}] {t['id']} {status}: {error.splitlines()[0][:120] if error else ''}")
        else:
            t['status'] = 'BLOCKED'; t['notes'] = f'after {max_attempts} attempts: {error[:300] if error else ""}'
            st['open_issues'].append(f"{t['id']} BLOCKED: {error.splitlines()[0][:160] if error else ''}")
            st.log(executor, f"{t['id']} BLOCKED; its files restored, the broken attempt kept in blocked/{t['id']}/")
            for f, old in before.items():           # keep the broken attempt for a human, restore the tree for the next task
                p = os.path.join(st['repo'], f)
                if os.path.exists(p):
                    write(os.path.join(st.dir, 'blocked', t['id'], f), read(p))
                if old is None:
                    if os.path.exists(p): os.remove(p)
                else:
                    write(p, old)
        from .plan import write_task_file
        write_task_file(st, t, kb_dir); st.save()
        checkpoint(st, t['wave'], executor, kb_dir)


def checkpoint(st, wave, executor, kb_dir):
    tasks = st['plan']['tasks']
    if any(t['wave'] == wave and t['status'] in ('TODO', 'IN_PROGRESS') for t in tasks) or str(wave) in st['plan']['checkpoints']:
        return
    status, detail, log = build_and_test(st)
    write(os.path.join(st.dir, 'logs', f'checkpoint-wave-{wave}.log'), log)
    st['plan']['checkpoints'][str(wave)] = 'PASSED' if status == 'OK' else f'FAILED ({status})'
    st.log(executor, f"checkpoint wave {wave}: {st['plan']['checkpoints'][str(wave)]} {detail if status == 'OK' else ''}")
    if status == 'OK':
        sh([script('index.sh'), 'refresh', os.path.join(kb_dir, 'index')], cwd=st['repo'])
    else:
        st['open_issues'].append(f'checkpoint wave {wave} failed: {str(detail).splitlines()[0][:160]}')
    st.save()


def closeout(st, kb_dir):
    status, detail, log = build_and_test(st)
    write(os.path.join(st.dir, 'logs', 'final.log'), log)
    tasks = st['plan']['tasks']
    counts = {s: sum(1 for t in tasks if t['status'] == s) for s in ('DONE', 'PARTIAL', 'BLOCKED', 'DROPPED', 'TODO')}
    summary = (f"Date: {now()} | Tasks: {counts['DONE']}/{len(tasks)} done, {counts['PARTIAL']} partial, {counts['BLOCKED']} blocked | "
               f"Build+tests: {status} {detail if status == 'OK' else ''} | Baseline: {st['baseline'].get('tests', '')} | Open issues: {len(st['open_issues'])}")
    st['final_summary'] = summary
    st['next_steps'] = [f"{t['id']} {t['status']}: {t.get('notes', '')[:100]}" for t in tasks if t['status'] != 'DONE'] or ['nothing open']
    st.log('tool', 'closeout: ' + summary); st.done('closeout'); st.save()
    sh([script('index.sh'), 'refresh', os.path.join(kb_dir, 'index')], cwd=st['repo'])
    return summary
