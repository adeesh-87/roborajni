"""MC/DC from clang source-based coverage (clang 18+: -fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc).

  llvm-cov export -format=lcov   lines and branches (the same as every other import)
  llvm-cov export -format=text   per decision: which conditions have an independence pair
  llvm-cov show -show-mcdc       per decision: the condition vectors the tests executed

For every condition without an independence pair this module computes the test that would complete one: it rebuilds
the decision from its source text (conditions -> C1..Cn, && || ! -> and or not), enumerates every vector the
short-circuit evaluation can produce, and pairs them the way llvm-cov does (the condition and the outcome differ; every
other condition is equal or not evaluated in one of the two). The answer is condition values plus the expected outcome,
written with the conditions' own source text, so a test writer needs no MC/DC theory.
"""
import itertools, json, os, re, subprocess, tempfile

MAX_CONDITIONS_CLANG18 = 6       # clang 18 does not instrument decisions with more conditions (a compile warning says so)


def _llvm_cov():
    for c in ('llvm-cov', 'llvm-cov-18', 'llvm-cov-19', 'llvm-cov-20'):
        if subprocess.run(['sh', '-c', f'command -v {c}'], capture_output=True).returncode == 0:
            return c
    raise SystemExit('llvm-cov not found (install llvm, same major version as the clang that built the tests)')


def _objects_args(objects):
    return [objects[0]] + [x for o in objects[1:] for x in ('-object', o)]


def export(profdata, objects):
    """(lcov text, export json) for the given test binaries"""
    cov = _llvm_cov()
    base = [cov, 'export', '-instr-profile', profdata] + _objects_args(objects)
    lcov = subprocess.run(base + ['-format=lcov'], capture_output=True, text=True)
    js = subprocess.run(base + ['-format=text'], capture_output=True, text=True)
    if lcov.returncode or js.returncode:
        raise SystemExit('llvm-cov export failed: ' + (lcov.stderr or js.stderr)[-400:])
    return lcov.stdout, json.loads(js.stdout)


VEC = re.compile(r'^[\s|]*(\d+)\s*\{\s*([TF\-,\s]+?)\s*=\s*([TF])\s*\}')     # nested '|  |' for template instantiations


def show_vectors(profdata, objects, source):
    """{(line, col): {'conds': [(line, col)], 'vectors': [(tuple of 'T'/'F'/None, 'T'/'F')], 'pairs': {i: bool}}}"""
    cov = _llvm_cov()
    r = subprocess.run([cov, 'show', '-instr-profile', profdata] + _objects_args(objects) + ['-show-mcdc', source],
                       capture_output=True, text=True)
    out, cur = {}, None
    for line in r.stdout.splitlines():
        m = re.search(r'MC/DC Decision Region \((\d+):(\d+)\) to \((\d+):(\d+)\)', line)
        if m:
            # a template gives one region per instantiation at the same place: merge them (source-level view)
            cur = out.setdefault((int(m.group(1)), int(m.group(2))), {'end': (int(m.group(3)), int(m.group(4))),
                                                                       'conds': [], 'vectors': [], 'pairs': {},
                                                                       'constant': set(), 'instances': 0})
            cur['instances'] += 1
            cur['conds_seen'] = []
            continue
        if cur is None:
            continue
        m = re.search(r'Condition C(\d+) --> \((\d+):(\d+)\)', line)
        if m:
            if cur['instances'] == 1:
                cur['conds'].append((int(m.group(2)), int(m.group(3))))
            continue
        m = VEC.match(line)
        if m:
            vals = [v.strip() for v in m.group(2).split(',')]
            v = (tuple(None if v == '-' else v for v in vals), m.group(3))
            if v not in cur['vectors']:
                cur['vectors'].append(v)
            continue
        m = re.search(r'C(\d+)-Pair: (covered|not covered|constant folded)', line)
        if m:
            i = int(m.group(1))
            if m.group(2) == 'constant folded':
                cur['constant'].add(i)
            cur['pairs'][i] = cur['pairs'].get(i, False) or m.group(2) == 'covered'
        if 'MC/DC Coverage for Decision' in line:
            cur = None
    return out


def _slice(lines, a, b):
    """source text from (line, col) a to (line, col) b, 1-based, end exclusive (llvm-cov region convention)"""
    (l1, c1), (l2, c2) = a, b
    if l1 == l2:
        return lines[l1 - 1][c1 - 1:c2 - 1]
    parts = [lines[l1 - 1][c1 - 1:]] + lines[l1:l2 - 1] + [lines[l2 - 1][:c2 - 1]]
    return '\n'.join(parts)


def expression(src_lines, region, conds, cond_ends):
    """Python boolean expression over C1..Cn, or None when the decision text holds anything but conditions,
    && || ! and parentheses (then no suggestion is computed)"""
    start, end = region
    text = _slice(src_lines, start, end)
    # replace conditions from the last to the first so earlier offsets stay valid (all on the decision's lines)
    def off(pos):
        l, c = pos
        if l == start[0]:
            return c - start[1]
        return sum(len(x) + 1 for x in src_lines[start[0] - 1:l - 1]) - (start[1] - 1) + (c - 1)
    spans = sorted(((off(s), off(cond_ends[s]), i) for i, s in enumerate(conds, 1) if s in cond_ends), reverse=True)
    if len(spans) != len(conds):
        return None, text
    expr = text
    for a, b, i in spans:
        expr = expr[:a] + f' C{i} ' + expr[b:]
    py = expr.replace('&&', ' and ').replace('||', ' or ')
    py = re.sub(r'!(?!=)', ' not ', py)
    if re.sub(r'\bC\d+\b|\band\b|\bor\b|\bnot\b|[()\s]', '', py):
        return None, text
    return py, text


def all_vectors(py, n):
    """every (vector, outcome) the short-circuit evaluation can produce; vector entries 'T'/'F'/None (not evaluated)"""
    res = set()
    for bits in itertools.product((False, True), repeat=n):
        seen = set()

        def c(i, bits=bits, seen=seen):
            seen.add(i)
            return bits[i - 1]
        out = eval(re.sub(r'\bC(\d+)\b', r'_c(\1)', py), {'_c': c})
        res.add((tuple(('T' if bits[i - 1] else 'F') if i in seen else None for i in range(1, n + 1)), 'T' if out else 'F'))
    return sorted(res, key=lambda v: [x or '' for x in v[0]])


def pairs_for(i, u, v):
    """u and v form an independence pair for condition i (1-based), llvm-cov rules"""
    (a, ra), (b, rb) = u, v
    if a[i - 1] is None or b[i - 1] is None or a[i - 1] == b[i - 1] or ra == rb:
        return False
    return all(a[j] == b[j] or a[j] is None or b[j] is None for j in range(len(a)) if j != i - 1)


def suggest(py, n, executed, missing):
    """for each condition without a pair: one new vector that pairs with an executed one, else two new vectors"""
    everything = all_vectors(py, n)
    execd = [v for v in executed]
    plan = {}
    for i in missing:
        best = None
        for u in execd:
            for v in everything:
                if v not in execd and pairs_for(i, u, v):
                    best = {'add': [v], 'with': u}
                    break
            if best:
                break
        if not best:
            for u, v in itertools.combinations(everything, 2):
                if pairs_for(i, u, v):
                    best = {'add': [u, v], 'with': None}
                    break
        if best:
            plan[i] = best
    return plan


def from_llvm(profdata, objects, root, rel_to, from_lcov_text):
    """the normalized coverage files (lines, branches) plus 'mcdc' per file: {decision line: [decision, ...]}"""
    lcov, js = export(profdata, objects)
    tmp = tempfile.NamedTemporaryFile('w', suffix='.info', delete=False)
    tmp.write(lcov)
    tmp.close()
    files = from_lcov_text(tmp.name, root)
    os.unlink(tmp.name)
    for f in js['data'][0]['files']:
        rel = rel_to(root, f['filename'])
        if not rel or not f.get('mcdc_records'):
            continue
        fc = files.setdefault(rel, {'lines': {}, 'branches': {}, 'decisions': {}})
        cond_ends = {(b[0], b[1]): (b[2], b[3]) for b in f.get('branches', [])}
        # decisions written inside a macro: their conditions sit in the expansion records, at the macro definition;
        # key them at the line that uses the macro (unambiguous only when one expansion holds that macro region)
        macro_site = {}
        for e in f.get('expansions', []):
            for b in e.get('branches', []):
                cond_ends.setdefault((b[0], b[1]), (b[2], b[3]))
                macro_site.setdefault((b[0], b[1]), []).append(e['source_region'][0])
        vec = show_vectors(profdata, objects, f['filename'])
        src = open(f['filename'], encoding='utf-8', errors='replace').read().splitlines()
        out = fc.setdefault('mcdc', {})
        merged = {}
        for rec in f['mcdc_records']:                      # one record per template instantiation: merge by place
            start = (rec[0], rec[1])
            if start in merged:
                merged[start] = merged[start][:-1] + [[a or b for a, b in zip(merged[start][-1], rec[-1])]]
            else:
                merged[start] = list(rec)
        for rec in merged.values():
            start, end, covered = (rec[0], rec[1]), (rec[2], rec[3]), list(rec[-1])
            shown = vec.get(start, {})
            execd = [(tuple(v), r) for v, r in shown.get('vectors', [])]
            for i in range(1, len(covered) + 1):          # merged instantiations: a pair may span two of them
                if not covered[i - 1] and any(pairs_for(i, u, v) for u, v in itertools.combinations(execd, 2)):
                    covered[i - 1] = True
            conds = shown.get('conds') or []
            py, text = expression(src, (start, end), conds, cond_ends) if conds else (None, _slice(src, start, end))
            n = len(covered)
            const = shown.get('constant', set())
            dec = {'line': start[0], 'col': start[1], 'end': list(end), 'text': ' '.join(text.split()),
                   'conditions': [{'text': ' '.join(_slice(src, s, cond_ends[s]).split()) if s in cond_ends else f'C{i}',
                                   'covered': bool(covered[i - 1]), **({'constant': True} if i in const else {})}
                                  for i, s in enumerate(conds or [None] * n, 1)],
                   'executed': [[list(v), r] for v, r in shown.get('vectors', [])]}
            if shown.get('instances', 1) > 1:
                dec['text'] += '  (template: instantiations merged)'
            missing = [i for i in range(1, n + 1) if not covered[i - 1] and i not in const]
            if missing and py and not const:
                dec['suggest'] = {str(i): {'add': [[list(v), r] for v, r in s['add']], 'with': [list(s['with'][0]), s['with'][1]] if s['with'] else None}
                                  for i, s in suggest(py, n, [(tuple(v), r) for v, r in shown.get('vectors', [])], missing).items()}
            sites = macro_site.get(conds[0] if conds else start) or []
            if len(set(sites)) == 1 and sites[0] != start[0]:
                dec['macro_at'] = start[0]                  # conditions below use the macro's parameter names
                dec['text'] += f'  (macro, used at line {sites[0]})'
                out.setdefault(str(sites[0]), []).append(dec)
            else:
                if sites:
                    dec['text'] += f"  (macro used at lines {', '.join(map(str, sorted(set(sites))))}; not separable per use)"
                out.setdefault(str(start[0]), []).append(dec)
    return files


def describe_vector(conds, vec, res):
    parts = []
    for c, v in zip(conds, vec):
        parts.append(f"`{c['text']}` {'TRUE' if v == 'T' else 'FALSE'}" if v else f"`{c['text']}` not evaluated")
    return ', '.join(parts) + f" -> decision {'TRUE' if res == 'T' else 'FALSE'}"


def gaps(dec):
    """lines like 'L16 MC/DC 1/2: `bytes == 0` not shown independent: add a test with ...'"""
    conds = dec['conditions']
    n = len(conds)
    done = sum(1 for c in conds if c['covered'])
    out = []
    for i, c in enumerate(conds, 1):
        if c['covered']:
            continue
        if c.get('constant'):
            out.append((dec['line'], f"MC/DC {done}/{n} in ({dec['text']}): `{c['text']}` is a compile-time constant: "
                                     f"no test can show it independent (justify it in the review; not a test task)"))
            continue
        s = (dec.get('suggest') or {}).get(str(i))
        consts = [x['text'] for x in conds if x.get('constant')]
        if consts:
            out.append((dec['line'], f"MC/DC {done}/{n} in ({dec['text']}): `{c['text']}` not shown independent, and "
                                     f"{', '.join(f'`{x}`' for x in consts)} is a compile-time constant: check by reading "
                                     f"whether `{c['text']}` can decide the outcome at all (often it cannot)"))
            continue
        if s and s['with']:
            how = 'add a test with ' + describe_vector(conds, *s['add'][0]) + ' (pairs with an existing run: ' + describe_vector(conds, *s['with']) + ')'
        elif s:
            how = 'add two tests: ' + ' and '.join(describe_vector(conds, *v) for v in s['add'])
        else:
            how = 'find two tests that differ only in this condition and flip the outcome'
        out.append((dec['line'], f"MC/DC {done}/{n} in ({dec['text']}): `{c['text']}` not shown independent: {how}"))
    return out
