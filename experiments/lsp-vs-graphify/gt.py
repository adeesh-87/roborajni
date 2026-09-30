#!/usr/bin/env python3
"""gt.py ROOT COMPILE_DB OUT.json : ground truth call graph from GCC itself (-fcallgraph-info, -O0: no inlining).
Independent of both contenders (Graphify uses tree-sitter, clangd uses clang). Every function defined in the repo
becomes a node keyed by (file, line of its name); every direct call becomes an edge with its call-site line.
Indirect calls (virtual, function pointers) are listed with their call-site source line for manual adjudication."""
import json, os, re, shlex, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

NODE = re.compile(r'^node:\s*\{\s*title:\s*"((?:[^"\\]|\\.)*)"\s*label:\s*"((?:[^"\\]|\\.)*)"(.*)\}\s*$')
EDGE = re.compile(r'^edge:\s*\{\s*sourcename:\s*"((?:[^"\\]|\\.)*)"\s*targetname:\s*"((?:[^"\\]|\\.)*)"(?:\s*label:\s*"((?:[^"\\]|\\.)*)")?')


def short_name(sig):
    if '<lambda' in sig:
        return ['<lambda>']
    s = re.sub(r'\s*\[with .*\]$', '', sig.strip())
    depth, cut = 0, None
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ')':
            depth += 1
        elif s[i] == '(':
            depth -= 1
            if depth == 0:
                cut = i
                break
    head = s[:cut] if cut is not None else s
    flat, depth = '', 0
    for ch in head:
        if ch == '<':
            depth += 1; continue
        if ch == '>' and depth:
            depth -= 1; continue
        if depth == 0:
            flat += ch
    q = flat.split(' ')[-1].lstrip('*&')
    parts = [p for p in q.split('::') if p and p != '{anonymous}']
    return parts


def clean_sig(sig):
    """signature without namespaces-in-parameters noise: used to map a header declaration to its definition"""
    return re.sub(r'\s+', ' ', sig.replace('{anonymous}::', '')).strip()


def build(root, cdb, out):
    root = os.path.realpath(root)
    ents, seen = [], set()
    for e in json.load(open(cdb)):
        f = os.path.realpath(os.path.join(e['directory'], e['file']))
        if f not in seen:
            seen.add(f); ents.append(e)
    tmp = tempfile.mkdtemp()

    def run(k_e):
        k, e = k_e
        args = e.get('arguments') or shlex.split(e['command'])
        cmd, skip = [args[0]], False
        src = os.path.realpath(os.path.join(e['directory'], e['file']))
        for a in args[1:]:
            if skip:
                skip = False; continue
            if a in ('-o', '-MF', '-MT'):
                skip = True; continue
            if a in ('-c',) or re.match(r'^-O', a) or a.startswith(('-o', '--coverage', '-fprofile')) or os.path.realpath(os.path.join(e['directory'], a)) == src:
                continue
            cmd.append(a)
        obj = os.path.join(tmp, f'u{k}.o')
        cmd += ['-O0', '-fcallgraph-info', '-c', src, '-o', obj]
        r = subprocess.run(cmd, cwd=e['directory'], capture_output=True, text=True)
        return e['directory'], os.path.join(tmp, f'u{k}.ci'), r.returncode, r.stderr[-300:]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(run, enumerate(ents)))
    nodes, edges = {}, set()
    lines = {}

    def src_line(f, l):
        if f not in lines:
            try:
                lines[f] = open(os.path.join(root, f), encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                lines[f] = []
        return lines[f][l - 1].strip() if 0 < l <= len(lines[f]) else ''
    indirect = []
    for cwd, ci, rc, err in results:
        if rc != 0 or not os.path.exists(ci):
            print('compile failed:', err); continue
        title2 = {}
        raw_edges = []
        for line in open(ci, encoding='utf-8', errors='replace'):
            m = NODE.match(line.strip())
            if m:
                lab = m.group(2).replace('\\n', '\n').split('\n')
                loc = re.match(r'^(.*):(\d+):(\d+)$', lab[1]) if len(lab) > 1 else None
                if not loc:
                    continue
                f = os.path.realpath(os.path.join(cwd, loc.group(1)))
                if not f.startswith(root + os.sep) or '/lib/unity/' in f:
                    continue
                rel = os.path.relpath(f, root)
                parts = short_name(lab[0])
                title2[m.group(1)] = (rel, int(loc.group(2)), int(loc.group(3)), '::'.join(parts[-2:]) if len(parts) > 1 else (parts[-1] if parts else '?'),
                                      'ellipse' not in m.group(3), clean_sig(lab[0]))
                continue
            m = EDGE.match(line.strip())
            if m:
                raw_edges.append((m.group(1), m.group(2), m.group(3)))
        for t, (rel, l, col, name, defined, sig) in title2.items():
            if defined:
                nodes.setdefault(f'{rel}:{l}', {'file': rel, 'line': l, 'col': col, 'name': name, 'sig': sig})
        for s, t, lab in raw_edges:
            a = title2.get(s)
            if not a or not a[4]:
                continue
            site = re.match(r'^(.*):(\d+):(\d+)$', lab or '')
            sl = int(site.group(2)) if site else 0
            src_key = f'{a[0]}:{a[1]}'
            if t == '__indirect_call':
                indirect.append({'from': src_key, 'from_name': a[3], 'line': sl, 'text': src_line(a[0], sl)})
                continue
            b = title2.get(t)
            if not b:
                continue                       # outside the repo (libc, libstdc++, unity)
            edges.add((src_key, f'{b[0]}:{b[1]}', b[3], sl, b[5]))
    # declarations never defined in the repo but called (pure virtual interfaces) are added by adjudication
    json.dump({'nodes': nodes, 'edges': sorted(edges), 'indirect': indirect}, open(out, 'w'), indent=1)
    print(f'{len(nodes)} functions, {len(edges)} direct call edges, {len(indirect)} indirect call sites -> {out}')


if __name__ == '__main__':
    build(*sys.argv[1:4])
