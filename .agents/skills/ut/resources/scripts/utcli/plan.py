"""Discovery → work items; scope; plan with Cases from the cards."""
import os, re
from .util import sh, script, read, write, md_table_rows, norm
from .frameworks import FRAMEWORKS, CAT_TO_TYPE

ORDER = ['E', 'F', 'C', 'B', 'A', 'D', 'G', 'H']
WAVE = {'fix-build': 1, 'fix-mocks': 2, 'remove-tests': 2, 'update-tests': 2, 'add-tests': 3, 'fix-run': 3, 'raise-coverage': 4}


def discover_diff(st, root, gd, base=None, uncommitted=False, rng=None):
    args = ['--base', base] if base else ['--uncommitted'] if uncommitted else ['--range', rng]
    out_md = os.path.join(st.dir, 'impact.md')
    rc, out = sh([script('index.sh'), 'refresh', gd], cwd=root)
    rc, out = sh([script('index.sh'), 'impact', gd] + args + ['--out', out_md], cwd=root)
    if rc != 0:
        return [], out
    items = []
    for cells in md_table_rows(read(out_md), 'W'):
        if len(cells) < 7 or cells[0] == 'W#':
            continue
        items.append({'id': cells[0], 'item': cells[1], 'kind': cells[2], 'tests': cells[3], 'mocks': cells[4],
                      'work': cells[5], 'cat': cells[6][:1], 'in_scope': '', 'priority': '',
                      'includers': re.findall(r'(\S+\.(?:cpp|cxx|cc|c)\b)', cells[3]) if cells[2].startswith('type/macro') else []})
    st['range'] = ' '.join(args)
    items += baseline_items(st, len(items))
    return items, read(out_md).split('\n## Work items')[0]


def baseline_items(st, n):
    """a failing baseline build or failing tests become E / F work items on the files named in the errors"""
    out = []
    probs = st['baseline'].get('problems', [])
    files = {}
    for p in probs:
        m = re.search(r'([\w./-]+\.(?:cpp|cc|cxx|c|hpp|h)):(\d+)', p)
        if not m or 'CMakeFiles/' in m.group(1):
            continue                                        # make/cmake summary lines carry no source file
        f = norm(os.path.relpath(m.group(1), st['repo'])) if os.path.isabs(m.group(1)) else m.group(1)
        files.setdefault(f, []).append(p[:160])
    for f, ps in files.items():
        n += 1
        cat = 'E' if any(p.startswith('build') for p in ps) else 'F'
        out.append({'id': f'W{n}', 'item': f'{f}: baseline {"build" if cat == "E" else "tests"} failing', 'kind': 'baseline failure',
                    'tests': '; '.join(ps[:2]), 'mocks': '', 'work': 'fix so the baseline builds/passes' , 'cat': cat, 'in_scope': '', 'priority': ''})
    return out


def discover_ask(st, root, gd, names):
    items, n = [], 0
    expanded = []
    for name in names:                                    # a file path expands to every function of its card
        if os.path.exists(os.path.join(root, name)):
            rc, card = sh([script('index.sh'), 'card', gd, name], cwd=root)
            funcs = [m.group(1) for m in re.finditer(r'^## (\S+)\s+\([^)]*\)(.*)$', card, re.M)
                     if 'static' not in m.group(2) and not m.group(1).endswith(('::' + m.group(1).split('::')[0], '::~' + m.group(1).split('::')[0]))]
            expanded += [(f, name) for f in funcs] or [(name, name)]
        else:
            expanded.append((name, ''))
    for name, file_hint in expanded:
        rc, out = sh(['grep', '-rnwE', name, '--include=*.c', '--include=*.cc', '--include=*.cpp', '--include=*.h', '--include=*.hpp']
                     + [os.path.join(root, p) for p in st['profile']['code_paths']])
        files = sorted({norm(os.path.relpath(l.split(':', 1)[0], root)) for l in out.splitlines() if ':' in l})
        rc2, tests = sh([script('index.sh'), 'tests', gd, name], cwd=root)
        rc3, deps = sh([script('index.sh'), 'deps', gd, name], cwd=root)
        n += 1
        thits = [l for l in tests.splitlines() if re.match(r'\d+ hop', l)]
        items.append({'id': f'W{n}', 'item': f"{file_hint or (files[0] if files else '?')}:{name}", 'kind': 'targeted',
                      'tests': f'{len(thits)}: ' + '; '.join(h.split(': ', 1)[1].split('  ')[0] for h in thits[:2]) if thits else '0: none',
                      'mocks': '; '.join(l[2:].split('  [')[0] for l in deps.splitlines() if l.startswith('- '))[:120],
                      'work': 'D new tests (targeted)', 'cat': 'D', 'in_scope': '', 'priority': ''})
    return items


def card_block(cards_md, func, line=None):
    """the card of FUNC; with LINE, the overload whose range contains it"""
    ms = list(re.finditer(r'^## ' + re.escape(func) + r'\s+\(\S+:(\d+)-(\d+)\).*?$(.*?)(?=^## |\Z)', cards_md, re.M | re.S)) or \
        list(re.finditer(r'^## ' + re.escape(func) + r'\s.*?$()()(.*?)(?=^## |\Z)', cards_md, re.M | re.S))
    if not ms:
        return None
    if line:
        for m in ms:
            if m.group(1) and int(m.group(1)) <= int(line) <= int(m.group(2)):
                return m
    return ms[0]


def card_decisions(cards_md, func, line=None):
    """decision lines of one function from a cards file"""
    m = card_block(cards_md, func, line)
    if not m:
        return None
    block = m.group(3)
    dec = re.findall(r'^\s+(L\d+)\s+(\S+)\s+(.*)$', block, re.M)
    returns = re.search(r'^Returns: (.*)$', block, re.M)
    params = re.search(r'^Params: (.*)$', block, re.M)
    calls = re.search(r'^Calls: (.*)$', block, re.M)
    return {'decisions': dec, 'returns': returns.group(1) if returns else '', 'params': params.group(1) if params else '',
            'calls': calls.group(1) if calls else '', 'block': block.strip()}


def cases_for(cards_md, func, line=None):
    d = card_decisions(cards_md, func, line)
    cases = []
    if not d:
        return [('happy path', '', '')]
    if not d['decisions']:
        cases.append(('straight-line: typical inputs', '', d['returns'] or 'return value'))
    for line, kind, cond in d['decisions']:
        cond = cond.split('   src:')[0]
        if kind in ('if', '?:'):
            cases.append((f'{line} {cond} is TRUE', '', '')); cases.append((f'{line} {cond} is FALSE', '', ''))
        elif kind == 'switch':
            cs = re.findall(r'cases: (.*?)(?: \+ default| \(NO default\)|$)', cond)
            for c in (cs[0].split(', ') if cs else ['each case']):
                cases.append((f'{line} case {c}', '', ''))
            if 'default' in cond:
                cases.append((f'{line} unknown value (default)', '', ''))
        elif kind in ('for', 'while', 'do-while'):
            cases.append((f'{line} loop 0 iterations', '', '')); cases.append((f'{line} loop 1 iteration', '', '')); cases.append((f'{line} loop many iterations', '', ''))
    for dep in re.findall(r'(\w[\w:>.-]*)\(\) \[(?:function|pointer)', d['calls']):
        cases.append((f'dependency {dep} returns an error', f'{dep} -> error', ''))
    return cases[:14]


def make_plan(st, kb_dir, prof):
    tasks, tid = [], 0
    fw = prof.get('framework', 'cpputest') or 'cpputest'
    groups = {}
    from .kb import test_name_pattern
    pattern = test_name_pattern(kb_dir, prof, fw)
    kb_mods = {m['file']: m for m in (st.get('kb_modules') or [])}
    notes = []
    for w in st['work_items']:
        if w.get('in_scope', 'yes') != 'yes':
            continue
        if w['cat'] == 'H':
            notes.append(f"{w['item']} was already changed on this range: read it first"); continue
        if w['kind'].startswith('deleted') and w['tests'].startswith('0') and w['mocks'] in ('none', ''):
            w['in_scope'] = 'no (nothing references it)'; continue
        if w['kind'] == 'baseline failure':
            groups.setdefault((w['item'].split(':')[0], 'fix-build' if w['cat'] == 'E' else 'fix-run'), []).append(dict(w, header=True)); continue
        if w['kind'].startswith('type/macro'):
            for inc in w.get('includers', []):        # a header change is checked in every test file that includes it
                ttype = 'fix-mocks' if re.search(r'mock|stub|fake', inc, re.I) else 'update-tests'
                groups.setdefault((inc, ttype), []).append(dict(w, item=f"{inc}: re-check {'mocks' if ttype == 'fix-mocks' else 'tests'} using {w['item']}", header=True))
            if not w.get('includers'):
                w['in_scope'] = 'no (no test includes it)'
            continue
        file = w['item'].split(':')[0]
        ttype = CAT_TO_TYPE.get(w['cat'], 'add-tests')
        groups.setdefault((file, ttype), []).append(w)
    for (file, ttype), ws in sorted(groups.items(), key=lambda kv: (WAVE.get(kv[0][1], 3), kv[0][0])):
        cards_all = read(os.path.join(kb_dir, 'modules', f'{os.path.basename(file)}.cards.md'))
        chunks, cur, cur_cases = [], [], 0
        for w in ws:                                    # a task holds <= 12 cases or <= 4 functions
            fn = w['item'].split(':', 1)[1].split(' (')[0] if ':' in w['item'] else ''
            ln = (re.search(r'\(L(\d+)\)', w['item']) or re.search('()', '')).group(1) or None
            n = (len(w['gaps']) if ttype == 'raise-coverage' and w.get('gaps') else
                 len(cases_for(cards_all, fn, ln)) if fn and ttype in ('add-tests', 'raise-coverage', 'update-tests') else 1)
            if cur and (cur_cases + n > 12 or len(cur) >= 4):
                chunks.append(cur); cur, cur_cases = [], 0
            cur.append(w); cur_cases += n
        if cur:
            chunks.append(cur)
        prev_same_file = None
        for chunk in chunks:
            tid += 1
            is_header_task = any(w.get('header') for w in chunk)
            funcs = [] if is_header_task else [w['item'].split(':', 1)[1].split(' (')[0] for w in chunk if ':' in w['item']]
            base = os.path.basename(file).rsplit('.', 1)[0]
            cards = read(os.path.join(kb_dir, 'modules', f'{os.path.basename(file)}.cards.md'))
            mod_tests = kb_mods.get(file, {}).get('test_files', [])
            mod_tests = [x for x in mod_tests if base in os.path.basename(x)] + [x for x in mod_tests if base not in os.path.basename(x)]
            test_file = file if is_header_task else existing_test_file(chunk) or (mod_tests[0] if mod_tests else '') or \
                os.path.join(prof['test_paths'][0] if prof['test_paths'] else 'tests', pattern.format(module=base))
            cases = []
            gaps_of = {w['item'].split(':', 1)[1].split(' (')[0]: w.get('gaps') for w in chunk if ':' in w['item']}
            lines_of = {w['item'].split(':', 1)[1].split(' (')[0]: (re.search(r'\(L(\d+)\)', w['item']) or re.search('()', '')).group(1) or None
                        for w in chunk if ':' in w['item']}
            for f in funcs:
                if ttype == 'raise-coverage' and gaps_of.get(f):      # only the outcomes the coverage run never took
                    cases += [(f, gap_case(g), '', 'the outcome the code gives for it') for g in gaps_of[f]]
                    continue
                cases += [(f,) + c for c in cases_for(cards, f, lines_of.get(f))] if ttype in ('add-tests', 'raise-coverage', 'update-tests') else []
            if is_header_task:
                cases = [(w['item'].split(': re-check')[0], f"re-check boundary values / types after {w['item'].split('using ')[-1]}", '', 'unchanged or updated')
                         if 'baseline' not in w['kind'] else (w['item'].split(':')[0], w['tests'][:120], '', 'builds and passes') for w in chunk]
            touches = [test_file] + ([m for w in chunk for m in re.findall(r'(\S+\.(?:c|cc|cpp|h|hpp)):', w.get('mocks', ''))] if ttype == 'fix-mocks' else [])
            reg = read(os.path.join(kb_dir, 'exemplars', 'register.md'))
            touches += list({r.split(':')[0] for r in re.findall(r'^- (\S+:\d+)', reg, re.M)})[:1]
            t = {'id': f'T{tid:02d}', 'title': f'{ttype} {file}: {", ".join(funcs)[:60] or "header change"}', 'type': ttype, 'file': file, 'functions': funcs,
                 'notes': '; '.join(notes),
                 'work_items': [w['id'] for w in chunk], 'wave': WAVE.get(ttype, 3), 'depends': [], 'status': 'TODO', 'owner': '',
                 'attempts': 0, 'touches': sorted(set(touches)), 'test_file': test_file, 'cases': cases,
                 'lines': {f: l for f, l in lines_of.items() if l and f in funcs}}
            if prev_same_file:                          # same test file: one task after the other
                t['depends'] = [prev_same_file]
            prev_same_file = t['id']
            tasks.append(t)
    waves = sorted({t['wave'] for t in tasks})          # renumber waves consecutively so checkpoints line up
    for t in tasks:
        t['wave'] = waves.index(t['wave']) + 1
    for t in tasks:   # earlier-wave tasks touching the same file are dependencies
        t['depends'] = sorted(set(t.get('depends', [])) | {o['id'] for o in tasks if o['wave'] < t['wave'] and set(o['touches']) & set(t['touches'])})
    st['plan'] = {'tasks': tasks, 'checkpoints': {}}
    for t in tasks:
        write_task_file(st, t, kb_dir)
    return tasks


def gap_case(g):
    """'L47 if (st == BUSY) never TRUE' -> 'L47 make (st == BUSY) TRUE - never taken by any test yet'"""
    m = re.match(r'L(\d+) (if|\?:) \((.*)\) never (TRUE|FALSE)$', g)
    if m:
        return f'L{m.group(1)} make ({m.group(3)}) {m.group(4)} - never taken by any test yet'
    m = re.match(r'L(\d+) (?:if|\?:) \((.*)\): (?:only )?(\d+/\d+) (?:branch|condition) outcomes hit', g)
    if m:
        return f'L{m.group(1)} ({m.group(2)}): each sub-condition must decide the outcome alone ({m.group(3)} outcomes hit so far)'
    m = re.match(r'L(\d+) loop \((.*)\) body never runs', g)
    if m:
        return f'L{m.group(1)} loop ({m.group(2)}) runs at least once'
    m = re.match(r'L(\d+) loop \((.*)\) never exits normally', g)
    if m:
        return f'L{m.group(1)} loop ({m.group(2)}) ends because its condition becomes false'
    m = re.match(r'L(\d+) switch \((.*)\) case (.*) never taken', g)
    if m:
        return f'L{m.group(1)} switch ({m.group(2)}) takes case {m.group(3)}'
    return g


def existing_test_file(ws):
    for w in ws:
        m = re.search(r'\((\S+\.(?:cpp|cxx|cc|c)\b):L\d+\)', w.get('tests', ''))
        if m:
            return m.group(1)
    return ''


def write_task_file(st, t, kb_dir):
    L = [f"# {t['id']} — {t['title']}", f"Type: {t['type']} | Wave: {t['wave']} | Work items: {', '.join(t['work_items'])} | Depends on: {', '.join(t['depends']) or '-'} | Status: {t['status']}",
         '', '## Goal', f"{t['type']} for {', '.join(t['functions']) or t['file']} in {t['file']}; tests live in {t['test_file']}.",
         '', '## Touches (only these files may be written)'] + [f'- {x}' for x in t['touches']]
    L += ['', '## Cases (one test per line; fill Expected from the code, never by running it)', '| # | Function | Inputs / state | Mock setup | Expected |', '|---|---|---|---|---|']
    for i, c in enumerate(t['cases'], 1):
        L.append(f'| {i} | {c[0]} | {c[1]} | {c[2]} | {c[3]} |')
    L += ['', '## Done when', f"- `{st['baseline'].get('single_test_cmd', '<single-test command>')}` for {t['test_file']} passes",
          '', '## Result', f"Outcome: {t.get('outcome', '')} | Attempts: {t.get('attempts', 0)} | Notes: {t.get('notes', '')}"]
    write(os.path.join(st.dir, 'tasks', f"{t['id']}.md"), '\n'.join(L) + '\n')


def complexity(st):
    tasks = st['plan']['tasks']
    reasons = []
    if len(tasks) > 10: reasons.append(f'{len(tasks)} tasks (> 10)')
    if len({t['wave'] for t in tasks}) > 3: reasons.append('> 3 waves')
    if len(st['work_items']) > 40: reasons.append('> 40 work items')
    if st['baseline'].get('build') == 'FAILED' and not any(w['cat'] == 'E' for w in st['work_items']): reasons.append('baseline build broken, cause unclear')
    return reasons
