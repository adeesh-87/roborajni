"""cov-import INDEX_JSON (--lcov FILE | --gcov-dir DIR | --ctc PROFILE_TXT | --json FILE) [--out FILE]
Normalizes a coverage report into coverage.json next to the index:
  {source, generated, files: {repo-relative path: {lines: {L: hits}, branches: {L: [taken, ...]}, decisions: {L: [true, false]}}}}
Decision outcomes are then read per outline decision by outcome() (used by the flowcharts and `uncovered`).

Sources:
  lcov     .info from lcov/geninfo (DA and BRDA records)
  gcov-dir a build tree with .gcda files: runs `gcov --json-format --stdout` (gcc 9+)
  ctc      Testwell CTC++ execution profile listing (ctcpost -p profile.txt): per line hits, and true/false counts of
           decisions. Parsed from the documented column layout; check the first import against ctc2html once.
  json     the normalized format above (convert any other tool to it)
"""
import datetime, gzip, json, os, re, subprocess, sys, tempfile
from .model import Index, norm, decisions, flatten, is_testside


def rel_to(root, p, base=None):
    if not p:
        return None
    if not os.path.isabs(p):
        cand = [os.path.join(base, p)] if base else []
        cand.append(os.path.join(root, p))
        p = next((c for c in cand if os.path.exists(c)), cand[-1])
    p = os.path.realpath(p)
    return norm(os.path.relpath(p, root)) if p.startswith(root + os.sep) else None


def empty():
    return {'lines': {}, 'branches': {}, 'decisions': {}}


def from_lcov(path, root):
    files, cur = {}, None
    base = os.path.dirname(os.path.abspath(path))
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('SF:'):
            r = rel_to(root, line[3:], base)
            cur = files.setdefault(r, empty()) if r else None
        elif cur is None:
            continue
        elif line.startswith('DA:'):
            l, c = line[3:].split(',')[:2]
            cur['lines'][l] = cur['lines'].get(l, 0) + int(float(c))
        elif line.startswith('BRDA:'):
            l, blk, br, taken = line[5:].split(',')[:4]
            cur['branches'].setdefault(l, []).append(0 if taken == '-' else int(taken))
    return files


def from_gcov_dir(d, root):
    files = {}
    d = os.path.abspath(d)                       # gcov runs in a temporary directory
    gcdas = [os.path.join(a, f) for a, _, fs in os.walk(d) for f in fs if f.endswith('.gcda')]
    with tempfile.TemporaryDirectory() as tmp:
        for g in gcdas:
            r = subprocess.run(['gcov', '--json-format', '--stdout', '--branch-probabilities', '-o', os.path.dirname(g), g], cwd=tmp,
                               capture_output=True, text=True, errors='replace')
            for chunk in r.stdout.splitlines():
                chunk = chunk.strip()
                if not chunk.startswith('{'):
                    continue
                try:
                    data = json.loads(chunk)
                except ValueError:
                    continue
                cwd = data.get('current_working_directory') or os.path.dirname(g)
                for f in data.get('files', []):
                    rp = rel_to(root, f['file'], cwd)
                    if not rp:
                        continue
                    fc = files.setdefault(rp, empty())
                    for ln in f.get('lines', []):
                        k = str(ln['line_number'])
                        fc['lines'][k] = fc['lines'].get(k, 0) + ln.get('count', 0)
                        brs = []
                        for b in ln.get('branches', []):       # a call that may throw = (return, throw) arc pair: not a decision
                            if b.get('throw'):
                                if brs:
                                    brs.pop()
                                continue
                            brs.append(b.get('count', 0))
                        if brs:
                            old = fc['branches'].get(k)
                            fc['branches'][k] = [a + b for a, b in zip(old, brs)] if old and len(old) == len(brs) else brs
    return files


TWO = re.compile(r'^\s*(\d+)\s+(\d+|-)\s+(\d+)\s+(\S.*)$')
ONE = re.compile(r'^\s*(\d+|-)\s+(\d+)\s+(\S.*)$')


def from_ctc(path, root):
    files, cur = {}, None
    base = os.path.dirname(os.path.abspath(path))
    for line in open(path, encoding='utf-8', errors='replace'):
        m = re.match(r'^\s*MONITORED SOURCE FILE\s*:\s*(.+?)\s*$', line)
        if m:
            r = rel_to(root, m.group(1), base)
            cur = files.setdefault(r, empty()) if r else None
            continue
        if cur is None or '***TER' in line or not line.strip():
            continue
        m = TWO.match(line)
        if m:
            t, f, l = int(m.group(1)), (0 if m.group(2) == '-' else int(m.group(2))), m.group(3)
            cur['decisions'][l] = [t, f]
            cur['lines'].setdefault(l, t + f)
            continue
        m = ONE.match(line)
        if m and m.group(1) != '-':
            cur['lines'][m.group(2)] = int(m.group(1))
    return files


def load(index_path):
    p = os.path.join(os.path.dirname(os.path.abspath(index_path)), 'coverage.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def main(a):
    if len(a) < 3:
        print(__doc__); sys.exit(2)
    ix = Index.load(a[0])
    root = ix.meta['root']
    kind, src = a[1], a[2]
    out = a[a.index('--out') + 1] if '--out' in a else os.path.join(os.path.dirname(os.path.abspath(a[0])), 'coverage.json')
    files = {'--lcov': from_lcov, '--gcov-dir': from_gcov_dir, '--ctc': from_ctc}.get(kind, lambda p, r: json.load(open(p))['files'])(src, root)
    files = {k: v for k, v in files.items() if k}
    cov = {'source': kind.lstrip('-'), 'from': os.path.abspath(src), 'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
           'files': files}
    json.dump(cov, open(out, 'w', encoding='utf-8'))
    s = summary(ix, cov)
    print(f"coverage: {out}  ({len(files)} files; source {cov['source']})")
    print(f"decision outcomes: {s['hit']}/{s['total']} hit in {s['functions']} functions with decisions; "
          f"{len(s['never'])} functions never executed; {len(s['gaps'])} functions with missing outcomes")
    return cov


# ---------------------------------------------------------------------------------------------- per decision
def cnt(fc, line):
    if line is None:
        return None
    v = fc['lines'].get(str(line))
    return v


def outcome(fc, d):
    """{'T': n, 'F': n} for if/?:, {'body': n, 'skip': n} for loops, {'cases': {v: n}} for switch; None if unknown.
    Missing values stay None (not measurable from this report)."""
    if fc is None:
        return None
    L = d['l']
    dec = fc['decisions'].get(str(L))
    br = fc['branches'].get(str(L))
    if d['t'] in ('if', '?:'):
        if dec:
            return {'T': dec[0], 'F': dec[1], 'how': 'ctc'}
        tl = d.get('tl')
        if d['t'] == 'if' and tl and tl != L and cnt(fc, tl) is not None:
            T = cnt(fc, tl)
            el = d.get('el')
            if el and el != L and cnt(fc, el) is not None:
                F = cnt(fc, el)
            elif cnt(fc, L) is not None:
                F = max(0, cnt(fc, L) - T)
            else:
                F = None
            if F is not None and br and len(br) >= 2 and d.get('n', 1) > 1:
                return {'T': T, 'F': F, 'how': 'lines', 'conds': f"{sum(1 for b in br if b)}/{len(br)} condition outcomes hit"}
            return {'T': T, 'F': F, 'how': 'lines'}
        if br and len(br) == 2 and d.get('n', 1) == 1:
            return {'T': br[0], 'F': br[1], 'how': 'branches'}
        if br:
            hit = sum(1 for b in br if b)
            if hit == len(br):
                return {'T': None, 'F': None, 'all': f'all {len(br)} branch outcomes hit', 'how': 'branches'}
            return {'partial': f"{hit}/{len(br)} branch outcomes hit", 'T': None, 'F': None,
                    'all0': not any(br), 'how': 'branches'}
        c = cnt(fc, L)
        return {'T': None, 'F': None, 'never': c == 0, 'how': 'lines'} if c is not None else None
    if d['t'] == 'loop':
        body = cnt(fc, d.get('bl')) if d.get('bl') not in (None, L) else None
        if dec:
            return {'body': dec[0], 'exit': dec[1], 'how': 'ctc'}
        if br and len(br) == 2:
            return {'body': body if body is not None else br[0], 'exit': br[1], 'how': 'branches'}
        return {'body': body, 'exit': None, 'how': 'lines'} if body is not None else None
    if d['t'] == 'switch':
        res = {}
        for c in d['cases']:
            n = cnt(fc, c.get('fl')) if c.get('fl') not in (None, L) else None
            if n is None:
                n = cnt(fc, c['l']) if c['l'] != L else None
            res[c['v']] = n
        return {'cases': res, 'how': 'lines'}
    return None


def gaps_of(fn, fc):
    """missing outcomes of one function: [(line, text)]"""
    out = []
    for d in decisions(fn.get('outline') or []):
        o = outcome(fc, d)
        if not o:
            continue
        cond = d.get('c', '')
        if d['t'] in ('if', '?:'):
            if o.get('T') == 0:
                out.append((d['l'], f"{d['t']} ({cond}) never TRUE"))
            if o.get('F') == 0:
                out.append((d['l'], f"{d['t']} ({cond}) never FALSE"))
            if o.get('partial') and not o.get('all0'):
                out.append((d['l'], f"{d['t']} ({cond}): only {o['partial']}"))
            m = re.match(r'(\d+)/(\d+)', o.get('conds') or '')
            if m and int(m.group(1)) < int(m.group(2)):
                out.append((d['l'], f"{d['t']} ({cond}): {o['conds']} (each sub-condition must flip the outcome)"))
        elif d['t'] == 'loop':
            if o.get('body') == 0:
                out.append((d['l'], f"loop ({cond}) body never runs"))
            if o.get('exit') == 0:
                out.append((d['l'], f"loop ({cond}) never exits normally"))
        elif d['t'] == 'switch':
            for v, n in o['cases'].items():
                if n == 0:
                    out.append((d['l'], f"switch ({cond}) case {v} never taken"))
    return out


def summary(ix, cov):
    total = hit = funcs = 0
    never, gaps = [], {}
    for i, n in ix.functions.items():
        if n.get('kind') != 'function' or not n.get('outline'):
            continue
        fc = cov['files'].get(n['file'])
        if fc is None:
            continue
        if cnt(fc, n['line']) == 0 and all(v == 0 for k, v in fc['lines'].items() if n['line'] <= int(k) <= n['end']):
            never.append(i); continue
        ds = decisions(n['outline'])
        if ds:
            funcs += 1
        for d in ds:
            o = outcome(fc, d) or {}
            for k in ('T', 'F', 'body'):
                if o.get(k) is not None:
                    total += 1; hit += o[k] > 0
            for v in (o.get('cases') or {}).values():
                if v is not None:
                    total += 1; hit += v > 0
        g = gaps_of(n, fc)
        if g:
            gaps[i] = g
    return {'total': total, 'hit': hit, 'functions': funcs, 'never': never, 'gaps': gaps}


def cmd_uncovered(a):
    """uncovered INDEX [FILE|FUNCTION]: functions never run and decision outcomes never taken (from coverage.json)"""
    ix = Index.load(a[0])
    cov = load(a[0])
    if cov is None:
        sys.exit('no coverage.json next to the index: run cov-import first')
    want = a[1] if len(a) > 1 else None
    s = summary(ix, cov)
    sel = lambda i: want is None or ix.functions[i]['file'] == want or ix.functions[i]['name'] in (want, want.split('::')[-1]) \
        or ix.functions[i]['name'].split('::')[-1] == want
    print(f"# Coverage gaps ({cov['source']}, {cov['generated']}): {s['hit']}/{s['total']} decision outcomes hit")
    never = [i for i in s['never'] if sel(i) and not is_testside(ix.functions[i]['file'])]
    if never:
        print('\n## Functions never executed by the tests')
        for i in never:
            n = ix.functions[i]
            print(f"- {n['name']} ({n['file']}:{n['line']})")
    gaps = [(i, g) for i, g in s['gaps'].items() if sel(i) and not is_testside(ix.functions[i]['file'])]
    if gaps:
        print('\n## Decision outcomes never taken')
        for i, g in gaps:
            n = ix.functions[i]
            print(f"- {n['name']} ({n['file']}:{n['line']}): " + '; '.join(f'L{l} {t}' for l, t in g))
    if not never and not gaps:
        print('no gaps')
