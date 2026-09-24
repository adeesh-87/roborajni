#!/usr/bin/env python3
"""graphify_ut.py - C/C++ fixes around the bundled Graphify for the ut skill.

Run with the Graphify venv python (graphify.sh does this). Two steps:

  mirror SCAN_DIR [--cdb compile_commands.json] PATH...
      Copy the in-scope C/C++ files to SCAN_DIR with repo-relative paths.
      With --cdb every source that has a compile command is PREPROCESSED with its real flags
      (macros expanded, only the active #if branch kept); text from files outside the scope
      (system and third-party headers) is dropped; SCAN_DIR/../linemap.json maps every mirror
      line back to the original file and line.

  augment GRAPH_JSON SCAN_DIR
      Fix graph.json after `graphify update`:
      - lines and files remapped to the original sources (preprocessed mode)
      - `static` attribute on functions (also STATIC / PRIVATE macros in plain mode)
      - calls to functions outside the scanned code become `external` nodes with `declared_in`
        and `kind` = function | macro | pointer (called through a variable) | library
      - every TEST / TEST_F / TEST_P / TYPED_TEST / IGNORE_TEST / TEST_GROUP block becomes its own
        node, e.g. `TEST_F(ProtoTest, Feed_StartByte)`, with its own calls
      - duplicate nodes (same function seen from several translation units) merged

  deps  GRAPH_JSON FILE|FUNCTION        what it calls outside itself (mock/stub candidates first)
  tests GRAPH_JSON FUNCTION [HOPS=3]    test blocks that reach FUNCTION through calls
"""
import bisect, json, os, re, shlex, shutil, subprocess, sys

EXTS = {'.c', '.cc', '.cpp', '.cxx', '.c++', '.h', '.hh', '.hpp', '.hxx', '.inl', '.ipp', '.tpp'}
SRC_EXTS = {'.c', '.cc', '.cpp', '.cxx', '.c++'}
SKIP_DIRS = {'.git', 'graphify-out', '.agents', 'node_modules'}
TEST_MACROS = {'TEST', 'TEST_F', 'TEST_P', 'TYPED_TEST', 'TYPED_TEST_P', 'IGNORE_TEST',
               'TEST_GROUP', 'TEST_GROUP_BASE', 'TEST_CASE', 'TEST_CASE_METHOD', 'SCENARIO', 'FIXTURE_TEST_CASE'}
TEST_LINE = re.compile(r'^\s*(' + '|'.join(sorted(TEST_MACROS, key=len, reverse=True)) + r')\s*\(([^()]*)\)')
LOC = re.compile(r'L(\d+)')


def norm(p):
    return p.replace('\\', '/') if p else p


def die(msg):
    sys.exit('graphify_ut: ' + msg)


def repo_root(paths):
    first = os.path.abspath(paths[0])
    start = first if os.path.isdir(first) else os.path.dirname(first)
    try:
        r = subprocess.run(['git', '-C', start, 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        r = os.path.commonpath([os.path.abspath(p) for p in paths]) if len(paths) > 1 else start
    return os.path.realpath(r)


def collect(paths):
    files = []
    for p in paths:
        p = os.path.realpath(p)
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for d, dirs, names in os.walk(p):
                dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
                files += [os.path.join(d, n) for n in names if os.path.splitext(n)[1].lower() in EXTS]
        else:
            die('no such path: ' + p)
    return sorted(set(files))


# --------------------------------------------------------------------------- mirror
def pp_command(entry, src):
    args = entry.get('arguments') or shlex.split(entry['command'], posix=(os.name != 'nt'))
    while args and os.path.basename(args[0]).lower() in ('ccache', 'sccache', 'distcc', 'icecc'):
        args = args[1:]
    comp = os.path.basename(args[0]).lower()
    msvc = comp in ('cl', 'cl.exe', 'clang-cl', 'clang-cl.exe')
    out, skip = [args[0]], False
    for a in args[1:]:
        if skip:
            skip = False; continue
        if a in ('-o', '-MF', '-MT', '-MQ') or (msvc and a in ('/Fo', '-Fo')):
            skip = True; continue
        if a in ('-c', '/c', '-MD', '-MMD', '-MP', '-M', '-MM') or a.startswith(('-Wp,-M', '-o', '/Fo', '-Fo', '/Fd')):
            continue
        if os.path.realpath(os.path.join(entry['directory'], a)) == src:
            continue
        out.append(a)
    if msvc:
        return out + ['/E', src]
    if comp.startswith(('icc', 'iar', 'xcc', 'armcc', 'cx')) and 'gcc' not in comp and 'clang' not in comp:
        return None   # vendor compilers: unknown preprocess flags -> plain copy
    return out + ['-E', src]


MARK = re.compile(r'^#\s*(?:line\s+)?(\d+)\s+"((?:[^"\\]|\\.)*)"')


def preprocess(entry, src, root, scope, dst):
    cmd = pp_command(entry, src)
    if cmd is None:
        return None, 'unsupported compiler ' + entry.get('command', '')[:40]
    try:
        r = subprocess.run(cmd, cwd=entry['directory'], capture_output=True, text=True, errors='replace', timeout=300)
    except Exception as e:
        return None, str(e)
    if r.returncode != 0:
        return None, (r.stderr.strip().splitlines() or ['failed'])[-1][:200]
    runs, out_lines, cur, line, seen = [], [], None, 0, set()
    for raw in r.stdout.splitlines():
        m = MARK.match(raw)
        if m:
            line = int(m.group(1))
            f = m.group(2).encode().decode('unicode_escape')
            f = os.path.realpath(os.path.join(entry['directory'], f)) if not f.startswith('<') else f
            cur = norm(os.path.relpath(f, root)) if in_scope(f, scope) else None
            if cur:
                seen.add(cur)
            continue
        if cur is not None:
            out_lines.append(raw)
            n = len(out_lines)
            if runs and runs[-1][2] == cur and runs[-1][0] + runs[-1][1] == n and runs[-1][3] + runs[-1][1] == line:
                runs[-1][1] += 1
            else:
                runs.append([n, 1, cur, line])
        line += 1
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out_lines) + '\n')
    return (runs, seen), None


def in_scope(f, scope):
    return any(f == s or f.startswith(s + os.sep) for s in scope)


def cmd_mirror(argv):
    cdb = None
    if len(argv) >= 2 and argv[1] == '--cdb':
        cdb = argv[2]; argv = [argv[0]] + argv[3:]
    if len(argv) < 2:
        die('usage: mirror SCAN_DIR [--cdb FILE] PATH...')
    scan, paths = os.path.abspath(argv[0]), argv[1:]
    root = repo_root(paths)
    scope = [os.path.realpath(p) for p in paths]
    files = collect(paths)
    if not files:
        die('no C/C++ files found in: ' + ' '.join(paths))
    if os.path.isdir(scan):
        shutil.rmtree(scan)
    base = os.path.dirname(scan)
    lm_path = os.path.join(base, 'linemap.json')
    if os.path.exists(lm_path):
        os.remove(lm_path)
    entries = {}
    if cdb:
        for e in json.load(open(cdb, encoding='utf-8')):
            p = os.path.realpath(os.path.join(e['directory'], e['file']))
            entries.setdefault(p, e)
    linemap, covered, plain, failed = {}, set(), [], []
    for f in files:
        rel = norm(os.path.relpath(f, root))
        if rel.startswith('..'):
            die(f'{f} is outside the repository root {root}')
        if f in entries and os.path.splitext(f)[1].lower() in SRC_EXTS:
            res, err = preprocess(entries[f], f, root, scope, os.path.join(scan, rel))
            if res:
                linemap[rel], seen = res
                covered |= seen
                continue
            failed.append(f'{rel}: {err}')
        plain.append((f, rel))
    n_plain = 0
    for f, rel in plain:
        if rel in covered and os.path.splitext(f)[1].lower() not in SRC_EXTS:
            continue   # header already seen (preprocessed) inside a translation unit
        dst = os.path.join(scan, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(f, dst); n_plain += 1
    with open(os.path.join(base, 'SOURCE_ROOT'), 'w') as fh:
        fh.write(root + '\n')
    if linemap:
        json.dump(linemap, open(lm_path, 'w'))
    print(f'scope: {len(files)} C/C++ files under {root}')
    if cdb:
        print(f'preprocessed with compile flags: {len(linemap)} translation units '
              f'(covering {len(covered)} in-scope files); plain copies: {n_plain}')
        if not linemap:
            print('WARNING: nothing was preprocessed: is the compile DB from THIS build and are the files in it?')
    for x in failed[:10]:
        print('  not preprocessed (plain copy used): ' + x)


# --------------------------------------------------------------------------- tree-sitter helpers
def parsers():
    from tree_sitter import Language, Parser
    import tree_sitter_c, tree_sitter_cpp
    return Parser(Language(tree_sitter_c.language())), Parser(Language(tree_sitter_cpp.language()))


def txt(n, src):
    return src[n.start_byte:n.end_byte].decode('utf-8', 'replace')


def walk(n):
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(reversed(x.children))


def func_name(defn, src):
    d = defn.child_by_field_name('declarator')
    while d is not None and d.type != 'function_declarator':
        d = d.child_by_field_name('declarator')
    if d is None:
        return None, None
    nm = d.child_by_field_name('declarator')
    if nm is None:
        return None, d
    return txt(nm, src), d


_IS_C = {}


def body_is_c(src):
    return _IS_C.get(id(src), True)


def callees(body, src):
    for n in walk(body):
        if n.type != 'call_expression':
            continue
        fn = n.child_by_field_name('function')
        if fn is None:
            continue
        if fn.type == 'template_function':
            fn = fn.child_by_field_name('name') or fn
        if fn.type in ('identifier', 'qualified_identifier'):
            yield txt(fn, src), n.start_point[0] + 1
        elif fn.type == 'field_expression' and body_is_c(src):
            # C: calls through struct members (hooks, driver tables) are function pointers
            yield txt(fn, src).replace(' ', ''), n.start_point[0] + 1


def variables(root, src):
    """identifiers declared as variables/params/fields (a call through them is a pointer call)"""
    out = set()
    for n in walk(root):
        if n.type in ('init_declarator', 'parameter_declaration', 'field_declaration', 'declaration'):
            d = n.child_by_field_name('declarator')
            while d is not None and d.type in ('init_declarator', 'pointer_declarator', 'array_declarator',
                                               'reference_declarator', 'parenthesized_declarator'):
                d = d.child_by_field_name('declarator') or (d.named_children[0] if d.named_children else None)
            if d is not None and d.type in ('identifier', 'field_identifier'):
                out.add(txt(d, src))
            elif d is not None and d.type == 'function_declarator':
                inner = d.child_by_field_name('declarator')
                if inner is not None and inner.type == 'parenthesized_declarator':
                    for x in walk(inner):
                        if x.type in ('identifier', 'field_identifier'):
                            out.add(txt(x, src)); break
    return out


def analyse(path, parser, is_c=None):
    src = open(path, 'rb').read()
    _IS_C[id(src)] = path.endswith('.c') if is_c is None else is_c
    tree = parser.parse(src)
    funcs = []
    for n in walk(tree.root_node):
        if n.type != 'function_definition':
            continue
        name, decl = func_name(n, src)
        if not name:
            continue
        head = src[n.start_byte:decl.start_byte if decl is not None else n.start_byte].decode('utf-8', 'replace')
        body = n.child_by_field_name('body')
        funcs.append({'name': name, 'line': n.start_point[0] + 1, 'end': n.end_point[0] + 1,
                      'static': bool(re.search(r'\b(static|STATIC|PRIVATE)\b', head)),
                      'calls': list(callees(body, src)) if body is not None else []})
    return funcs, variables(tree.root_node, src)


# --------------------------------------------------------------------------- augment
class LineMap:
    def __init__(self, path):
        self.m = {}
        if os.path.exists(path):
            for f, runs in json.load(open(path)).items():
                self.m[f] = (sorted(runs), [r[0] for r in sorted(runs)])

    def to_orig(self, f, line):
        if f not in self.m:
            return f, line
        runs, starts = self.m[f]
        i = bisect.bisect_right(starts, line) - 1
        if i < 0:
            return f, line
        s, ln, of, ol = runs[i]
        if line < s + ln:
            return of, ol + (line - s)
        return of, ol + ln - 1


FRAMEWORK = re.compile(r'(^|/)(unity|cmock|cpputest|cppumock|gtest|gmock|googletest|googlemock|catch2?|doctest|fff|ceedling)(/|[._-]|$)', re.I)


def declared_names(path, parser, cache={}):
    """function names DECLARED or DEFINED in a header (tree-sitter), not merely called there"""
    if path not in cache:
        names = set()
        try:
            src = open(path, 'rb').read()
            for n in walk(parser.parse(src).root_node):
                if n.type in ('declaration', 'field_declaration', 'function_definition'):
                    d = n.child_by_field_name('declarator')
                    while d is not None and d.type in ('pointer_declarator', 'reference_declarator', 'init_declarator'):
                        d = d.child_by_field_name('declarator')
                    if d is not None and d.type == 'function_declarator':
                        nm = d.child_by_field_name('declarator')
                        if nm is not None and nm.type in ('identifier', 'field_identifier', 'qualified_identifier'):
                            names.add(txt(nm, src))
        except OSError:
            pass
        cache[path] = names
    return cache[path]


def header_index(root, names, parser):
    """name -> first repo header that declares it; set of names defined as function-like macros"""
    want = {n.split('::')[-1] for n in names if '.' not in n and '->' not in n}
    decl, macro = {}, set()
    if not want:
        return decl, macro
    pat = re.compile(r'#\s*define\s+(\w+)\s*\(|\b(\w+)\s*\(')
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(('build', 'cmake-build'))]
        for n in files:
            if os.path.splitext(n)[1].lower() not in ('.h', '.hh', '.hpp', '.hxx', '.inl'):
                continue
            p = os.path.join(d, n)
            try:
                t = open(p, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            hits = set()
            for m in pat.finditer(t):
                nm = m.group(1) or m.group(2)
                if nm in want:
                    if m.group(1):
                        macro.add(nm)
                        hits.add(nm)
                    else:
                        hits.add(nm)
            if not hits:
                continue
            real = declared_names(p, parser)
            rel = os.path.relpath(p, root).replace(os.sep, '/')
            for nm in hits:
                if (nm in real or nm in macro) and (nm not in decl or len(rel) < len(decl[nm])):
                    decl[nm] = rel
    return decl, macro


def cmd_augment(argv):
    if len(argv) != 2:
        die('usage: augment GRAPH_JSON SCAN_DIR')
    gpath, scan = argv
    base = os.path.dirname(os.path.abspath(scan))
    root = open(os.path.join(base, 'SOURCE_ROOT')).read().strip()
    lm = LineMap(os.path.join(base, 'linemap.json'))
    g = json.load(open(gpath, encoding='utf-8'))
    nodes, links = g['nodes'], g['links']
    for x in nodes + links:
        if x.get('source_file'):
            x['source_file'] = norm(x['source_file'])
    pc, pcpp = parsers()

    def loc(x):
        m = LOC.search(x.get('source_location') or '')
        return int(m.group(1)) if m else None

    by_fileline, by_label = {}, {}
    for n in nodes:
        if n.get('_callable'):
            by_fileline.setdefault((n.get('source_file'), loc(n)), n)
            by_label.setdefault(n['label'][:-2] if n['label'].endswith('()') else n['label'], []).append(n)
    tmpl = next((n for n in nodes if n.get('_callable')), {'community': 0, 'community_name': ''})
    community_of = {}
    for n in nodes:
        community_of.setdefault(n.get('source_file'), (n.get('community', 0), n.get('community_name', '')))

    # 1. parse the mirror (active code) -> static flags + calls
    scan_funcs, pointer_vars = {}, {}
    for d, _, files in os.walk(scan):
        for fn in files:
            p = os.path.join(d, fn)
            rel = norm(os.path.relpath(p, scan))
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            funcs, vars_ = analyse(p, pc if ext == '.c' else pcpp)
            scan_funcs[rel], pointer_vars[rel] = funcs, vars_

    new_nodes, new_edges, ext_calls = [], [], []
    existing = {(e['source'], e['target'], e['relation']) for e in links}

    def resolve(name, prefer_file):
        short = name.split('::')[-1]
        cands = by_label.get(name) or by_label.get(short) or []
        same = [c for c in cands if c.get('source_file') == prefer_file]
        return (same or cands or [None])[0]

    def add_call(src_node, callee, rel, line, vars_):
        tgt = resolve(callee, rel)
        if tgt is not None:
            key = (src_node['id'], tgt['id'], 'calls')
            if key not in existing:
                existing.add(key)
                new_edges.append(edge(src_node['id'], tgt['id'], rel, line))
            return
        ext_calls.append((src_node, callee, rel, line, callee in vars_))

    def edge(s, t, rel, line):
        return {'source': s, 'target': t, 'relation': 'calls', '_origin': 'ut', 'confidence': 'EXTRACTED',
                'confidence_score': 1.0, 'context': 'call', 'source_file': rel,
                'source_location': f'L{line}', 'weight': 1.0}

    n_static = 0
    for rel, funcs in scan_funcs.items():
        for f in funcs:
            node = by_fileline.get((rel, f['line']))
            if node is None:
                cands = [c for c in by_label.get(f['name'], []) if c.get('source_file') == rel]
                node = cands[0] if len(cands) == 1 else None
            if node is None:
                continue
            node['static'] = f['static']; n_static += f['static']
            for callee, line in f['calls']:
                add_call(node, callee, rel, line, pointer_vars[rel])

    # 2. remap to original files/lines (preprocessed mode)
    for x in nodes + links + new_edges:
        f, l = x.get('source_file'), loc(x)
        if f and x.get('label') == os.path.basename(f):
            continue   # the file node itself stays on its own file
        if f in lm.m and l:
            of, ol = lm.to_orig(f, l)
            x['source_file'], x['source_location'] = of, f'L{ol}'
    ext_calls = [(s, c, *lm.to_orig(r, l), p) for (s, c, r, l, p) in ext_calls]

    # 3. test blocks: one node per TEST(...) block, parsed from the ORIGINAL test file
    drop = set()
    test_files = {n.get('source_file') for n in nodes if n.get('source_file')}
    for rel in sorted(f for f in test_files if f and os.path.splitext(f)[1].lower() in SRC_EXTS):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
        macro_lines = {i + 1 for i, t in enumerate(lines) if TEST_LINE.match(t)}
        if not macro_lines:
            continue
        for n in nodes:
            if n.get('source_file') == rel and loc(n) in macro_lines:
                drop.add(n['id'])
            if n.get('source_file') == rel and n.get('_callable') and re.fullmatch(r'[A-Z][A-Z0-9_]*\(\)', n['label']) \
                    and n['label'][:-2] in TEST_MACROS:
                drop.add(n['id'])
        funcs, vars_ = analyse(path, pcpp)
        made = {n['id'] for n in new_nodes}
        for f in funcs:
            if f['name'] not in TEST_MACROS:
                continue   # e.g. setup() written inside TEST_GROUP(...) on the same line
            m = TEST_LINE.match(lines[f['line'] - 1]) if f['line'] - 1 < len(lines) else None
            if not m:
                continue
            label = f"{m.group(1)}({', '.join(a.strip() for a in m.group(2).split(','))})"
            com = community_of.get(rel, (0, ''))
            node = {'id': re.sub(r'\W+', '_', f'{rel}_{label}').strip('_').lower(), 'label': label,
                    '_callable': True, '_origin': 'ut', 'community': com[0], 'community_name': com[1],
                    'file_type': 'code', 'norm_label': label.lower(), 'source_file': rel,
                    'source_location': f"L{f['line']}", 'type': 'code', 'kind': 'test' if m.group(1) != 'TEST_GROUP' else 'fixture'}
            if node['id'] in made:
                continue
            made.add(node['id'])
            new_nodes.append(node)
            for callee, line in f['calls']:
                if callee in TEST_MACROS or (re.fullmatch(r'[A-Z][A-Z0-9_]*', callee) and not resolve(callee, rel)):
                    continue   # assertion / framework macros
                tgt = resolve(callee, rel)
                if tgt is not None and tgt['id'] not in drop:
                    new_edges.append(edge(node['id'], tgt['id'], rel, line))
                elif tgt is None:
                    ext_calls.append((node, callee, rel, line, callee in vars_))
    # drop collapsed/expanded test nodes and nodes that only hung off them
    keep_links = [e for e in links + new_edges if e['source'] not in drop and e['target'] not in drop]
    linked = {e['source'] for e in keep_links} | {e['target'] for e in keep_links}
    orphan = {n['id'] for n in nodes if not n.get('source_file') and n['id'] not in linked}
    nodes = [n for n in nodes if n['id'] not in drop and n['id'] not in orphan] + new_nodes

    # 4. external nodes
    decl, macros = header_index(root, {c for _, c, _, _, _ in ext_calls}, pcpp)
    ext_nodes = {}
    for src_node, callee, rel, line, is_ptr in ext_calls:
        if src_node['id'] in drop:
            continue
        member = '.' in callee or '->' in callee
        declared = None if member else (decl.get(callee) or decl.get(callee.split('::')[-1]))
        from_expansion = callee.split('.')[-1].split('->')[-1] not in (read_line(root, rel, line) or callee)
        if from_expansion and not declared:
            continue   # call created by a framework macro expansion (e.g. test registration)
        kind = ('pointer' if (is_ptr or member) else 'macro' if callee in macros
                else 'test-framework' if declared and FRAMEWORK.search(declared)
                else 'function' if declared else 'library')
        nid = 'ext_' + re.sub(r'\W+', '_', callee).lower()
        if nid not in ext_nodes:
            ext_nodes[nid] = {'id': nid, 'label': callee + '()', '_callable': True, '_origin': 'ut',
                              'community': src_node.get('community', 0), 'community_name': src_node.get('community_name', ''),
                              'file_type': 'external', 'external': True, 'kind': kind, 'norm_label': callee.lower() + '()',
                              'source_file': '', 'source_location': '', 'type': 'external',
                              'declared_in': (f'variable or parameter in {rel}' if kind == 'pointer'
                                              else declared or '(not in repo: system/library)')}
        key = (src_node['id'], nid, 'calls')
        if key not in existing:
            existing.add(key)
            keep_links.append(edge(src_node['id'], nid, rel, line))
    nodes += ext_nodes.values()

    # 5. merge duplicates (same function reached from several translation units)
    canon, merged = {}, {}
    for n in nodes:
        k = (n.get('source_file'), n['label'], n.get('source_location'))
        if n.get('source_file') and k in canon:
            merged[n['id']] = canon[k]
        else:
            canon[k] = n['id']
    nodes = [n for n in nodes if n['id'] not in merged]
    seen, final_links = set(), []
    for e in keep_links:
        e['source'] = merged.get(e['source'], e['source']); e['target'] = merged.get(e['target'], e['target'])
        k = (e['source'], e['target'], e['relation'], e.get('source_location'))
        if k not in seen:
            seen.add(k); final_links.append(e)
    g['nodes'], g['links'] = nodes, final_links
    g.setdefault('graph', {})['ut_augmented'] = {'preprocessed': bool(lm.m), 'external_nodes': len(ext_nodes),
                                                 'test_blocks': len(new_nodes)}
    json.dump(g, open(gpath, 'w', encoding='utf-8'))
    kinds = {}
    for n in ext_nodes.values():
        kinds[n['kind']] = kinds.get(n['kind'], 0) + 1
    n_static = sum(1 for n in nodes if n.get('static'))
    print(f"augmented: {n_static} static functions marked, {len(new_nodes)} test blocks, "
          f"{len(ext_nodes)} external callees {kinds}, {len(merged)} duplicate nodes merged, "
          f"{'lines mapped to original sources' if lm.m else 'plain mode (no compile DB)'}")


_line_cache = {}


def read_line(root, rel, line):
    if rel not in _line_cache:
        try:
            _line_cache[rel] = open(os.path.join(root, rel), encoding='utf-8', errors='replace').read().splitlines()
        except OSError:
            _line_cache[rel] = []
    ls = _line_cache[rel]
    return ls[line - 1] if 0 < line <= len(ls) else None


# --------------------------------------------------------------------------- queries for the ut skill
def load(gpath):
    g = json.load(open(gpath, encoding='utf-8'))
    ids = {n['id']: n for n in g['nodes']}
    out, inc = {}, {}
    for e in g['links']:
        if e.get('relation') == 'calls' and e['source'] in ids and e['target'] in ids:
            out.setdefault(e['source'], []).append(e)
            inc.setdefault(e['target'], []).append(e)
    return g, ids, out, inc


def find(ids, target):
    t = target[:-2] if target.endswith('()') else target
    return [n for n in ids.values() if n.get('_callable') and
            (n['label'] in (t, t + '()') or n['label'].split('::')[-1] in (t, t + '()'))]


def cmd_deps(argv):
    """deps GRAPH FILE|FUNCTION : what the code under test calls outside itself = mock/stub candidates"""
    if len(argv) != 2:
        die('usage: deps GRAPH_JSON FILE_OR_FUNCTION')
    g, ids, out, _ = load(argv[0])
    t = norm(argv[1])
    srcs = [n for n in ids.values() if n.get('_callable') and n.get('source_file') == t] or find(ids, t)
    if not srcs:
        die(f'nothing found for {t} (use a repo-relative file path or a function name)')
    files = {n.get('source_file') for n in srcs}
    rows = {}
    for n in srcs:
        for e in out.get(n['id'], []):
            tg = ids[e['target']]
            if tg.get('source_file') in files and tg.get('type') != 'external':
                continue   # call inside the same file: not a dependency
            where = tg.get('declared_in') if tg.get('type') == 'external' else f"defined in {tg.get('source_file')}:{tg.get('source_location')}"
            kind = tg.get('kind', 'function') if tg.get('type') == 'external' else 'in-scope code'
            r = rows.setdefault(tg['label'], [kind, where, []])
            r[2].append(f"{n['label']} @ {e.get('source_file')}:{e.get('source_location')}")
    order = ['function', 'pointer', 'macro', 'in-scope code', 'library', 'test-framework']
    print(f"# dependencies of {t}  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)")
    for kind in order:
        items = sorted((k, v) for k, v in rows.items() if v[0] == kind)
        if not items:
            continue
        print(f"\n## {kind}")
        for label, (_, where, sites) in items:
            print(f"- {label}  [{where}]  called by: {'; '.join(sorted(set(sites))[:4])}{' ...' if len(set(sites)) > 4 else ''}")


def cmd_tests(argv):
    """tests GRAPH FUNCTION [MAX_HOPS] : test blocks that reach FUNCTION through calls"""
    if len(argv) not in (2, 3):
        die('usage: tests GRAPH_JSON FUNCTION [MAX_HOPS=3]')
    g, ids, _, inc = load(argv[0])
    hops = int(argv[2]) if len(argv) == 3 else 3
    starts = find(ids, argv[1])
    if not starts:
        die(f'function not found: {argv[1]}')
    def in_test_file(n):
        return bool(re.search(r'(^|/)(test|tests|unittest|unittests|ut|utest)/|(^|/)test_[^/]*$|_test\.[^/]*$|Test[^/]*\.[^/]*$',
                              n.get('source_file') or ''))
    seen, frontier, found = {s['id']: [s['label']] for s in starts}, [s['id'] for s in starts], []
    for depth in range(hops):
        nxt = []
        for nid in frontier:
            for e in inc.get(nid, []):
                c = e['source']
                if c in seen:
                    continue
                seen[c] = seen[nid] + [ids[c]['label']]
                n = ids[c]
                if n.get('kind') in ('test', 'fixture'):
                    found.append((depth + 1, n, seen[c], 'TEST block'))
                    continue
                if in_test_file(n) and n['label'] != 'main()':
                    found.append((depth + 1, n, seen[c], 'test-file function'))
                nxt.append(c)          # keep walking: helpers are called by the real tests
        frontier = nxt
    if not found:
        print(f"no test reaches {argv[1]} within {hops} call hops")
    for d, n, chain, what in sorted(found, key=lambda x: (x[0], x[1].get('source_file', ''), x[1]['label'])):
        print(f"{d} hop(s) [{what}]: {n['label']}  {n.get('source_file')}:{n.get('source_location')}   via {' <- '.join(chain)}")


if __name__ == '__main__':
    cmds = {'mirror': cmd_mirror, 'augment': cmd_augment, 'deps': cmd_deps, 'tests': cmd_tests}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__); sys.exit(2)
    cmds[sys.argv[1]](sys.argv[2:])
