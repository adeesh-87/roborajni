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

  card  GRAPH_JSON SCAN_DIR FUNCTION|FILE  test-planning card: signature, params, every decision with its
                                        line, returns, globals touched, calls, callers, existing tests
  impact GRAPH_JSON SCAN_DIR --base REF|--uncommitted|--range A..B [--out FILE] [--context FILE]
                                        every changed function/type in the code under test, with the tests, callers
                                        and mocks it touches and the work category (fixed table): the pick-list
  deps  GRAPH_JSON FILE|FUNCTION        what it calls outside itself (mock/stub candidates first)
  tests GRAPH_JSON FUNCTION [HOPS=4]    test blocks that reach FUNCTION through calls (incl. via function pointers)
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


def preprocess(entry, src, root, scope):
    """-> ((segments, seen), error). segments = [[file_rel, first_orig_line, [lines]], ...] for in-scope text;
    seen = every in-scope file the preprocessor entered (also macro-only headers that leave no text)"""
    cmd = pp_command(entry, src)
    if cmd is None:
        return None, 'unsupported compiler ' + entry.get('command', '')[:40]
    try:
        r = subprocess.run(cmd, cwd=entry['directory'], capture_output=True, text=True, errors='replace', timeout=300)
    except Exception as e:
        return None, str(e)
    if r.returncode != 0:
        return None, (r.stderr.strip().splitlines() or ['failed'])[-1][:200]
    segs, cur, line, cache, seen = [], None, 0, {}, set()
    seg = None
    for raw in r.stdout.split('\n'):
        if raw[:1] == '#':
            m = MARK.match(raw)
            if m:
                line = int(m.group(1))
                key = m.group(2)
                if key not in cache:          # resolving paths is the slow part: once per distinct marker
                    f = key.encode().decode('unicode_escape')
                    f = os.path.realpath(os.path.join(entry['directory'], f)) if not f.startswith('<') else f
                    cache[key] = norm(os.path.relpath(f, root)) if in_scope(f, scope) else None
                cur, seg = cache[key], None
                if cur:
                    seen.add(cur)
                continue
        if cur is not None:
            if seg is None or seg[0] != cur or seg[1] + len(seg[2]) != line:
                seg = [cur, line, []]
                segs.append(seg)
            seg[2].append(raw)
        line += 1
    return (segs, seen), None


def owners(tu_segs):
    """each in-scope file's text is kept in ONE translation unit: itself if it is a TU, else the TU with the
    same stem (x.h -> x.c), else the first non-test TU that includes it, else the first TU"""
    tus = sorted(tu_segs)
    stem = lambda f: os.path.splitext(os.path.basename(f))[0].lower()
    is_test = lambda f: bool(re.search(r'(^|/)(test|tests|unittest|ut)/|test', f, re.I))
    inc = {}
    for tu in tus:
        for f, _, _ in tu_segs[tu]:
            inc.setdefault(f, [])
            if tu not in inc[f]:
                inc[f].append(tu)
    own = {}
    for f, users in inc.items():
        if f in tu_segs:
            own[f] = f
            continue
        same = [t for t in users if stem(t) == stem(f)]
        prod = [t for t in users if not is_test(t)]
        own[f] = (same or prod or users)[0]
    return own


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
    linemap, covered, plain, failed, jobs = {}, set(), [], [], []
    for f in files:
        rel = norm(os.path.relpath(f, root))
        if rel.startswith('..'):
            die(f'{f} is outside the repository root {root}')
        if f in entries and os.path.splitext(f)[1].lower() in SRC_EXTS:
            jobs.append((f, rel))
        else:
            plain.append((f, rel))
    from concurrent.futures import ThreadPoolExecutor
    workers = int(os.environ.get('UT_JOBS') or os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda j: preprocess(entries[j[0]], j[0], root, scope), jobs))
    tu_segs = {}
    for (f, rel), (res, err) in zip(jobs, results):
        if res is not None:
            tu_segs[rel] = res[0]
            covered |= res[1]
        else:
            failed.append(f'{rel}: {err}')
            plain.append((f, rel))
    own = owners(tu_segs)
    for tu, segs in tu_segs.items():
        out_lines, runs = [], []
        for f, start, lines in segs:
            if own.get(f) != tu:
                continue   # this header's text lives in another translation unit
            runs.append([len(out_lines) + 1, len(lines), f, start])
            out_lines.extend(lines)
            covered.add(f)
        dst = os.path.join(scan, tu)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(out_lines) + '\n')
        linemap[tu] = runs
    n_plain = 0
    for f, rel in plain:
        if rel in covered:
            continue   # already preprocessed inside a translation unit (headers, or .c/.cc files #included by another unit)
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
NOT_CALLS = {'static_cast', 'reinterpret_cast', 'const_cast', 'dynamic_cast', 'sizeof', 'alignof', 'decltype',
             'typeid', 'noexcept', 'static_assert', '_Static_assert', 'defined', '__builtin_expect',
             '__builtin_offsetof', 'offsetof', 'va_start', 'va_end', 'va_arg'}


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
            name = txt(fn, src)
            if name not in NOT_CALLS and not name.startswith('std::'):
                yield name, n.start_point[0] + 1
        elif fn.type == 'field_expression':
            if body_is_c(src):
                # C: calls through struct members (hooks, driver tables) are function pointers
                yield txt(fn, src).replace(' ', ''), n.start_point[0] + 1
            else:
                # C++: obj.method() / ptr->method(): resolved later by the receiver's declared type
                f = fn.child_by_field_name('field')
                if f is not None:
                    rec = fn.child_by_field_name('argument')
                    r = ''
                    if rec is not None and rec.type == 'identifier':
                        r = txt(rec, src)
                    elif rec is not None and rec.type == 'field_expression' and \
                            rec.child_by_field_name('argument') is not None and \
                            txt(rec.child_by_field_name('argument'), src) == 'this':
                        r = txt(rec.child_by_field_name('field'), src)
                    elif rec is not None and rec.type == 'this':
                        r = 'this'
                    yield f'member:{txt(f, src)}|{r}', n.start_point[0] + 1


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


def innermost_name(d, src):
    """identifier inside a (pointer/function/array/parenthesized/init) declarator"""
    while d is not None and d.type not in ('identifier', 'field_identifier', 'qualified_identifier',
                                           'destructor_name', 'operator_name', 'type_identifier'):
        nxt = d.child_by_field_name('declarator')
        if nxt is None:
            nxt = next((c for c in d.named_children if c.type not in ('parameter_list', 'type_qualifier')), None)
        d = nxt
    return d


def enclosing_class(n, src):
    p = n.parent
    while p is not None:
        if p.type in ('class_specifier', 'struct_specifier'):
            nm = p.child_by_field_name('name')
            return txt(nm, src) if nm is not None else None
        if p.type == 'function_definition':
            return None
        p = p.parent
    return None


TYPE_WORDS = {'const', 'volatile', 'struct', 'class', 'union', 'enum', 'unsigned', 'signed', 'typename', 'mutable', 'static', 'auto'}


def base_type(ty, src):
    """`const fw::Clock&` -> Clock, `std::unique_ptr<IBus>` -> IBus (pointee of smart pointers), None for auto"""
    if ty is None:
        return None
    t = txt(ty, src)
    m = re.search(r'(?:unique_ptr|shared_ptr|weak_ptr|reference_wrapper)\s*<\s*([\w:]+)', t)
    if m:
        t = m.group(1)
    t = re.sub(r'<.*>', '', t)
    t = t.split('::')[-1]
    words = [w for w in re.findall(r'[A-Za-z_]\w*', t) if w not in TYPE_WORDS]
    return words[-1] if words else None


def declared_types(node, src):
    """name -> base type for parameters and declarations below node"""
    out = {}
    for d in walk(node):
        if d.type in ('parameter_declaration', 'optional_parameter_declaration', 'declaration'):
            bt = base_type(d.child_by_field_name('type'), src)
            if not bt:
                continue
            if d.type == 'declaration':
                decls = [c for c in d.named_children if c.type in ('identifier', 'init_declarator', 'pointer_declarator',
                                                                    'reference_declarator', 'array_declarator')]
            else:
                decls = [d.child_by_field_name('declarator')]
            for dc in decls:
                nm = innermost_name(dc, src)
                if nm is not None and nm.type == 'identifier':
                    out[txt(nm, src)] = bt
    return out


def ptr_key(expr, src):
    """key under which a function pointer is stored/called: ('field', name) or ('var', name)"""
    e = expr
    while e is not None and e.type in ('parenthesized_expression', 'pointer_expression', 'subscript_expression'):
        e = e.child_by_field_name('argument') or e.named_children[0] if e.named_children else None
    if e is None:
        return None
    if e.type == 'field_expression':
        f = e.child_by_field_name('field')
        return ('field', txt(f, src)) if f is not None else None
    if e.type == 'identifier':
        return ('var', txt(e, src))
    return None


def value_ident(v, src):
    """function name used as a value: f, &f, (cast)f"""
    while v is not None and v.type in ('pointer_expression', 'cast_expression', 'parenthesized_expression'):
        v = v.child_by_field_name('argument') or v.child_by_field_name('value') or \
            (v.named_children[-1] if v.named_children else None)
    if v is not None and v.type in ('identifier', 'qualified_identifier'):
        return txt(v, src)
    return None


def analyse(path, parser, is_c=None):
    """functions (+calls), variables, and facts for C++ methods and function pointers"""
    src = open(path, 'rb').read()
    _IS_C[id(src)] = path.endswith('.c') if is_c is None else is_c
    tree = parser.parse(src)
    funcs = []
    x = {'methods': {}, 'bindings': [], 'structs': {}, 'params': {}, 'stores': {}, 'args': [], 'fnptr_fields': set(), 'positional': [], 'class_fields': {}}
    for n in walk(tree.root_node):
        t = n.type
        if t == 'function_definition':
            name, decl = func_name(n, src)
            if not name:
                continue
            cls = enclosing_class(n, src)
            if cls and '::' not in name:
                name = f'{cls}::{name}'
            head = src[n.start_byte:decl.start_byte if decl is not None else n.start_byte].decode('utf-8', 'replace')
            body = n.child_by_field_name('body')
            funcs.append({'name': name, 'line': n.start_point[0] + 1, 'end': n.end_point[0] + 1,
                          'static': bool(re.search(r'\b(static|STATIC|PRIVATE)\b', head)),
                          'calls': list(callees(body, src)) if body is not None else [],
                          'locals': declared_types(n, src) if not _IS_C.get(id(src), True) else {}})
            params = []
            plist = decl.child_by_field_name('parameters') if decl is not None else None
            for pd in (plist.named_children if plist is not None else []):
                nm = innermost_name(pd.child_by_field_name('declarator'), src) if pd.type == 'parameter_declaration' else None
                params.append(txt(nm, src) if nm is not None else None)
            x['params'][name] = params
            if body is not None:
                for a in walk(body):
                    if a.type == 'assignment_expression':
                        k = ptr_key(a.child_by_field_name('left'), src)
                        v = value_ident(a.child_by_field_name('right'), src)
                        if k and v in params:
                            x['stores'].setdefault(name, []).append((k, params.index(v), a.start_point[0] + 1))
                    elif a.type == 'call_expression':
                        fn = a.child_by_field_name('function'); args = a.child_by_field_name('arguments')
                        if fn is not None and fn.type == 'identifier' and args is not None:
                            for i, arg in enumerate(args.named_children):
                                v = value_ident(arg, src)
                                if v:
                                    x['args'].append((txt(fn, src), i, v, a.start_point[0] + 1))
        elif t == 'field_declaration':
            cls = enclosing_class(n, src)
            d = n.child_by_field_name('declarator')
            if cls and d is not None and d.type != 'function_declarator':
                nm = innermost_name(d, src)
                bt = base_type(n.child_by_field_name('type'), src)
                if nm is not None and bt:
                    x['class_fields'].setdefault(cls, {})[txt(nm, src)] = bt
            if cls and d is not None and d.type == 'function_declarator':
                nm = innermost_name(d, src)
                text = txt(n, src)
                if nm is not None:
                    x['methods'][f'{cls}::{txt(nm, src)}'] = {
                        'virtual': bool(re.search(r'\bvirtual\b', text)) or bool(re.search(r'\boverride\b', text)),
                        'pure': bool(re.search(r'=\s*0\s*;?\s*$', text))}
        elif t == 'struct_specifier' and n.child_by_field_name('body') is not None:
            fields = []
            for fd in n.child_by_field_name('body').named_children:
                if fd.type == 'field_declaration':
                    fdecl = fd.child_by_field_name('declarator')
                    nm = innermost_name(fdecl, src)
                    fields.append(txt(nm, src) if nm is not None else None)
                    if nm is not None and fdecl is not None and any(c.type == 'function_declarator' for c in walk(fdecl)):
                        x['fnptr_fields'].add(txt(nm, src))
            names = []
            if n.child_by_field_name('name') is not None:
                names.append(txt(n.child_by_field_name('name'), src))
            if n.parent is not None and n.parent.type == 'type_definition':
                td = innermost_name(n.parent.child_by_field_name('declarator'), src)
                if td is not None:
                    names.append(txt(td, src))
            for nm in names:
                x['structs'][nm] = fields
        elif t == 'assignment_expression':
            k = ptr_key(n.child_by_field_name('left'), src)
            v = value_ident(n.child_by_field_name('right'), src)
            if k and v:
                x['bindings'].append((k, v, n.start_point[0] + 1))
        elif t == 'init_declarator':
            decl, val = n.child_by_field_name('declarator'), n.child_by_field_name('value')
            nm = innermost_name(decl, src)
            if nm is None or val is None:
                continue
            ty = n.parent.child_by_field_name('type') if n.parent is not None else None
            tyname = None
            if ty is not None:
                tn = ty.child_by_field_name('name') if ty.type == 'struct_specifier' else ty
                tyname = txt(tn, src) if tn is not None else None
            if val.type == 'initializer_list':
                is_array = any(c.type == 'array_declarator' for c in walk(decl))
                elems = val.named_children if is_array else [val]
                for el in elems:
                    if el.type == 'initializer_list':
                        init_bindings(el, tyname, x, src)
                    elif is_array:
                        v = value_ident(el, src)
                        if v:
                            x['bindings'].append((('var', txt(nm, src)), v, el.start_point[0] + 1))
            else:
                v = value_ident(val, src)
                if v:
                    x['bindings'].append((('var', txt(nm, src)), v, n.start_point[0] + 1))
    return funcs, variables(tree.root_node, src), x


def init_bindings(lst, tyname, x, src):
    """{ .open = f, ... } or positional { f, g } for a struct whose field order is known"""
    pos = 0
    for el in lst.named_children:
        if el.type == 'initializer_pair':
            des = el.child_by_field_name('designator')
            des = des if des is not None else el.named_children[0]
            field = txt(des, src).lstrip('.').strip() if des is not None else None
            v = value_ident(el.child_by_field_name('value'), src)
            if field and v:
                x['bindings'].append((('field', field), v, el.start_point[0] + 1))
            continue
        v = value_ident(el, src)
        if v and tyname:
            x['positional'].append((tyname, pos, v, el.start_point[0] + 1))   # field order resolved later
        pos += 1


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

    # 1. parse the mirror (active code) -> static flags + calls
    scan_funcs, pointer_vars, facts = {}, {}, {}
    for d, _, files in os.walk(scan):
        for fn in files:
            p = os.path.join(d, fn)
            rel = norm(os.path.relpath(p, scan))
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            funcs, vars_, facts[rel] = analyse(p, pc if ext == '.c' else pcpp)
            scan_funcs[rel], pointer_vars[rel] = funcs, vars_

    declared_methods = set()
    for fx in facts.values():
        declared_methods |= set(fx['methods'])
    for funcs in scan_funcs.values():
        declared_methods |= {f['name'] for f in funcs if '::' in f['name']}

    # C++: Graphify names methods by their bare name (`emit`, `.write()`); qualify them as Class::name()
    byid = {n['id']: n for n in nodes}
    called = {e['target'] for e in links if e.get('relation') == 'calls'} | \
             {n['id'] for n in nodes if re.search(r'\(\)$', n['label'])}
    for e in links:
        if e.get('relation') in ('defines', 'method'):
            c, m = byid.get(e['source']), byid.get(e['target'])
            bare = m['label'].lstrip('.') if m else ''
            bare = bare[:-2] if bare.endswith('()') else bare
            if c and m and '::' not in m['label'] and '.' not in c['label'] and not c['label'].endswith('()') \
                    and (m.get('_callable') or m['id'] in called or f"{c['label']}::{bare}" in declared_methods):
                m['short_label'] = bare
                m['label'] = f"{c['label']}::{bare}()"
                m['norm_label'] = m['label'].lower()
                m['_callable'] = True

    by_fileline, by_label = {}, {}
    for n in nodes:
        if n.get('_callable'):
            by_fileline.setdefault((n.get('source_file'), loc(n)), n)
            key = n['label'][:-2] if n['label'].endswith('()') else n['label']
            by_label.setdefault(key, []).append(n)
            if '::' in key:
                by_label.setdefault(key.split('::')[-1], []).append(n)
    tmpl = next((n for n in nodes if n.get('_callable')), {'community': 0, 'community_name': ''})
    community_of = {}
    for n in nodes:
        community_of.setdefault(n.get('source_file'), (n.get('community', 0), n.get('community_name', '')))

    class_fields = {}
    for fx in facts.values():
        for c, flds in fx['class_fields'].items():
            class_fields.setdefault(c, {}).update(flds)
    bases = {}
    for e in links:
        if e.get('relation') == 'inherits' and e['source'] in byid and e['target'] in byid:
            bases.setdefault(byid[e['source']]['label'], []).append(byid[e['target']]['label'].split('::')[-1])
    new_nodes, new_edges, ext_calls = [], [], []
    existing = {(e['source'], e['target'], e['relation']) for e in links}

    def resolve(name, prefer_file):
        short = name.split('::')[-1]
        cands = by_label.get(name) or by_label.get(short) or []
        same = [c for c in cands if c.get('source_file') == prefer_file]
        return (same or cands or [None])[0]

    def member_targets(callee, f):
        """obj.m() -> [Class::m node] using the receiver's declared type (local, parameter or class field),
        walking base classes; without a known type only a method name that exists in ONE class is linked"""
        m, _, rec = callee[7:].partition('|')
        cls = f['name'].rsplit('::', 1)[0] if f and '::' in f['name'] else None
        ty = None
        if rec == 'this':
            ty = cls
        elif rec and f:
            ty = f.get('locals', {}).get(rec) or class_fields.get(cls, {}).get(rec)
        if ty:
            todo, seen_t = [ty], set()
            while todo:
                t = todo.pop(0)
                if t in seen_t:
                    continue
                seen_t.add(t)
                hit = by_label.get(f'{t}::{m}')
                if hit:
                    return hit[:1], 'EXTRACTED'
                todo += bases.get(t, [])
            return [], None
        cands = [c for c in by_label.get(m, []) if '::' in c['label']]
        return (cands[:1], 'INFERRED') if len({c['label'] for c in cands}) == 1 else ([], None)

    def add_call(src_node, callee, rel, line, vars_, f=None):
        if callee.startswith('member:'):
            cands, conf = member_targets(callee, f)
            for c in cands:
                key = (src_node['id'], c['id'], 'calls')
                if key not in existing:
                    existing.add(key)
                    e = edge(src_node['id'], c['id'], rel, line); e['confidence'] = conf
                    new_edges.append(e)
            return
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

    n_static, def_site = 0, {}
    for rel, funcs in scan_funcs.items():
        for f in funcs:
            node = by_fileline.get((rel, f['line']))
            if node is None:
                cands = [c for c in by_label.get(f['name'], []) if c.get('source_file') == rel
                         and (c['label'][:-2] == f['name'] or '::' not in f['name'])]
                if not cands and '::' in f['name']:   # method defined here, declared in its class header
                    cands = [c for c in by_label.get(f['name'], []) if c['label'][:-2] == f['name']]
                node = cands[0] if len(cands) == 1 else None
            if node is None:
                continue
            if '::' in f['name'] and loc(node) != f['line']:
                def_site[node['id']] = (rel, f['line'])
            node['static'] = f['static']; n_static += f['static']
            for callee, line in f['calls']:
                add_call(node, callee, rel, line, pointer_vars[rel], f)

    for rel, fx in facts.items():
        for qual, info in fx['methods'].items():
            for c in by_label.get(qual, []):
                c['virtual'] = c.get('virtual') or info['virtual']
                c['pure_virtual'] = c.get('pure_virtual') or info['pure']

    # 2. remap to original files/lines (preprocessed mode)
    for x in nodes + links + new_edges:
        f, l = x.get('source_file'), loc(x)
        if f and x.get('label') == os.path.basename(f):
            continue   # the file node itself stays on its own file
        if f in lm.m and l:
            of, ol = lm.to_orig(f, l)
            x['source_file'], x['source_location'] = of, f'L{ol}'
    ext_calls = [(s, c, *lm.to_orig(r, l), p) for (s, c, r, l, p) in ext_calls]
    # methods defined outside their class: node moves to the definition, declaration kept
    for nid, (rel, line) in def_site.items():
        n = byid[nid]
        n['declared_at'] = f"{n.get('source_file')}:{n.get('source_location')}"
        of, ol = lm.to_orig(rel, line)
        n['source_file'], n['source_location'] = of, f'L{ol}'


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
        funcs, vars_, _ = analyse(path, pcpp)
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
                if callee.startswith('member:'):
                    cands, conf = member_targets(callee, f)
                    for c in [c for c in cands if c['id'] not in drop]:
                        e = edge(node['id'], c['id'], rel, line); e['confidence'] = conf
                        new_edges.append(e)
                    continue
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
    all_vars = set().union(*pointer_vars.values()) if pointer_vars else set()
    for src_node, callee, rel, line, is_ptr in ext_calls:
        if src_node['id'] in drop:
            continue
        is_ptr = is_ptr or callee in all_vars
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

    # 4b. function pointers: bind each pointer call to the functions stored in that pointer
    known = {k for k, v in by_label.items() if v}
    fnptr_fields = set().union(*(fx['fnptr_fields'] for fx in facts.values())) if facts else set()
    structs = {}
    for fx in facts.values():
        for k, v in fx['structs'].items():
            structs.setdefault(k, v)
    for fx in facts.values():   # positional { f, g } initializers: struct may be defined in another unit
        for tyname, pos, fn, line in fx['positional']:
            fl = structs.get(tyname)
            if fl and pos < len(fl) and fl[pos]:
                fx['bindings'].append((('field', fl[pos]), fn, line))
    binds = {}
    for rel, fx in facts.items():
        for key, fn, line in fx['bindings']:
            # a known function, or anything stored in a function-pointer field (e.g. malloc into .allocate)
            if fn in known or (key[0] == 'field' and key[1] in fnptr_fields):
                binds.setdefault(key, set()).add((fn, *lm.to_orig(rel, line)))
        for callee, idx, fn, line in fx['args']:          # register_cb(my_handler) -> stored param
            if fn not in known:
                continue
            for rel2, fx2 in facts.items():
                for key, pidx, _ in fx2['stores'].get(callee, []):
                    if pidx == idx:
                        binds.setdefault(key, set()).add((fn, *lm.to_orig(rel, line)))
    n_bound = 0
    for n in ext_nodes.values():
        if n['kind'] != 'pointer':
            continue
        expr = n['label'][:-2]
        key = ('field', re.split(r'\.|->', expr)[-1]) if ('.' in expr or '->' in expr) else ('var', expr)
        targets = sorted(binds.get(key, ()))
        if not targets:
            continue
        grouped = {}
        for fn, f, l in targets:
            grouped.setdefault(fn, []).append(f'{f}:L{l}')
        n['targets'] = [f"{fn} (bound at {', '.join(sites[:3])}{' ...' if len(sites) > 3 else ''})"
                        for fn, sites in grouped.items()]
        for fn, f, l in targets:
            tgt = resolve(fn, f)
            if tgt is not None and (n['id'], tgt['id'], 'calls') not in existing:
                existing.add((n['id'], tgt['id'], 'calls'))
                e = edge(n['id'], tgt['id'], f, l); e['confidence'] = 'INFERRED'; e['context'] = 'pointer-target'
                keep_links.append(e); n_bound += 1

    # 5. merge duplicates (same function reached from several translation units)
    canon, merged = {}, {}
    nodes.sort(key=lambda n: 0 if n.get('declared_at') else 1)
    for n in nodes:
        k = (n['label'], n.get('declared_at') or f"{n.get('source_file')}:{n.get('source_location')}")
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
    n_virt = sum(1 for n in nodes if n.get('pure_virtual'))
    print(f"augmented: {n_static} static functions marked, {n_virt} pure virtual methods, "
          f"{n_bound} function-pointer targets bound, {len(new_nodes)} test blocks, "
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
            if tg.get('targets'):
                where += '; may call: ' + ', '.join(tg['targets'][:4])
            kind = (tg.get('kind', 'function') if tg.get('type') == 'external'
                    else 'interface' if tg.get('pure_virtual') else 'in-scope code')
            if kind == 'interface':
                iface = tg['label'].rsplit('::', 1)[0]
                impl = sorted({f"{ids[e['source']]['label']} ({ids[e['source']].get('source_file')})" for e in g['links']
                               if e.get('relation') == 'inherits' and e['target'] in ids and e['source'] in ids
                               and ids[e['target']]['label'].split('::')[-1] == iface})
                where = (f"pure virtual, declared in {tg.get('source_file')}:{tg.get('source_location')}: mock the interface"
                         + (f"; implemented by: {', '.join(impl)}" if impl else '; no implementation or mock found'))
            r = rows.setdefault(tg['label'], [kind, where, []])
            r[2].append(f"{n['label']} @ {e.get('source_file')}:{e.get('source_location')}")
    order = ['function', 'interface', 'pointer', 'macro', 'in-scope code', 'library', 'test-framework']
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
        die('usage: tests GRAPH_JSON FUNCTION [MAX_HOPS=4]')
    g, ids, _, inc = load(argv[0])
    hops = int(argv[2]) if len(argv) == 3 else 4
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


# --------------------------------------------------------------------------- function cards
DECISION_TYPES = {'if_statement': 'if', 'switch_statement': 'switch', 'while_statement': 'while',
                  'do_statement': 'do-while', 'for_statement': 'for', 'conditional_expression': '?:'}


def file_scope_vars(root, src):
    out = set()
    for d in root.named_children:
        if d.type == 'declaration':
            for c in d.named_children:
                if c.type in ('identifier', 'init_declarator', 'pointer_declarator', 'array_declarator'):
                    nm = innermost_name(c, src)
                    if nm is not None and nm.type == 'identifier':
                        out.add(txt(nm, src))
    return out


def one_line(t, n=90):
    t = ' '.join(t.split())
    return t if len(t) <= n else t[:n - 3] + '...'


def find_def(scan, name, pc, pcpp, want_rel=None):
    """(rel, node, src, root) of the function definition called name (Class::m or plain)"""
    hits = []
    for d, _, files in os.walk(scan):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXTS:
                continue
            p = os.path.join(d, fn)
            rel = norm(os.path.relpath(p, scan))
            src = open(p, 'rb').read()
            if name.split('::')[-1].encode() not in src:
                continue
            tree = (pc if ext == '.c' else pcpp).parse(src)
            _IS_C[id(src)] = ext == '.c'
            for n in walk(tree.root_node):
                if n.type != 'function_definition':
                    continue
                nm, _ = func_name(n, src)
                if not nm:
                    continue
                cls = enclosing_class(n, src)
                q = f'{cls}::{nm}' if cls and '::' not in nm else nm
                if q == name or q.split('::')[-1] == name.split('::')[-1] and ('::' not in name or q.endswith(name)):
                    hits.append((rel, n, src, tree.root_node))
    if want_rel:
        pref = [h for h in hits if h[0] == want_rel]
        if pref:
            return pref[0]
    return hits[0] if hits else None


def card_for(name, node_info, scan, lm, root, ids, out, inc, pc, pcpp):
    rel_hint = None
    if node_info:
        for r, runs in lm.m.items():   # which mirror file holds this original file?
            if any(rr[2] == node_info.get('source_file') for rr in runs[0]):
                rel_hint = r; break
        rel_hint = rel_hint or node_info.get('source_file')
    hit = find_def(scan, name, pc, pcpp, rel_hint)
    lines = []
    if not hit:
        lines.append(f'## {name}: definition not found in the scanned code')
        return '\n'.join(lines)
    rel, n, src, tree_root = hit
    of, ol = lm.to_orig(rel, n.start_point[0] + 1)
    _, el = lm.to_orig(rel, n.end_point[0] + 1)
    body = n.child_by_field_name('body')
    head = src[n.start_byte:body.start_byte].decode('utf-8', 'replace') if body is not None else txt(n, src)
    static = bool(re.search(r'\b(static|STATIC|PRIVATE)\b', head))
    lines.append(f'## {name}  ({of}:{ol}-{el}){"  static" if static else ""}')
    lines.append(f'Signature: {one_line(head, 140)}')
    if body is None:
        return '\n'.join(lines)
    decl = n.child_by_field_name('declarator')
    while decl is not None and decl.type != 'function_declarator':
        decl = decl.child_by_field_name('declarator')
    params = []
    plist = decl.child_by_field_name('parameters') if decl is not None else None
    for pd in (plist.named_children if plist is not None else []):
        if pd.type == 'parameter_declaration':
            nm = innermost_name(pd.child_by_field_name('declarator'), src)
            if nm is None and txt(pd, src).strip() == 'void':
                continue
            params.append((txt(nm, src) if nm is not None else '?', one_line(txt(pd, src), 40)))
    if params:
        lines.append('Params: ' + '; '.join(f'{p} ({t})' for p, t in params))
    # decisions, returns, compound conditions
    decisions, returns, seen_lines = [], [], set()
    for x in walk(body):
        if x.type in DECISION_TYPES:
            cond = x.child_by_field_name('condition')
            ctext = one_line(txt(cond, src)) if cond is not None else ''
            if x.type == 'do_statement' and ctext.strip('()') == '0':
                continue   # do { } while (0) from a macro
            if x.type == 'for_statement':
                ctext = one_line(txt(x, src).split('{')[0].strip()[3:].strip())
            f2, l2 = lm.to_orig(rel, x.start_point[0] + 1)
            srcline = read_line(root, f2, l2)
            kind = DECISION_TYPES[x.type]
            extra = ''
            if x.type == 'if_statement' and x.child_by_field_name('alternative') is not None:
                extra = ' (has else)'
            if cond is not None:
                ops = sum(1 for y in walk(cond) if y.type == 'binary_expression' and
                          txt(y.child_by_field_name('operator') if y.child_by_field_name('operator') else y, src) in ('&&', '||')) \
                    if cond.type != 'identifier' else 0
                ops = len(re.findall(r'&&|\|\|', txt(cond, src)))
                if ops:
                    extra += f' [{ops + 1} sub-conditions: each must flip the outcome alone]'
            if x.type == 'switch_statement':
                cases = [one_line(txt(c.child_by_field_name('value'), src), 30) for c in walk(x)
                         if c.type == 'case_statement' and c.child_by_field_name('value') is not None]
                has_default = any(c.type == 'case_statement' and c.child_by_field_name('value') is None for c in walk(x))
                extra += f" cases: {', '.join(cases)}{' + default' if has_default else ' (NO default)'}"
            tag = ''
            inner = ctext.strip().strip('()').strip()
            if srcline and inner and inner not in srcline and re.search(r'\b[A-Z][A-Z0-9_]{2,}\s*\(', srcline):
                tag = f'   src: {one_line(srcline.strip(), 60)}'   # condition came from a macro: show the source line
            key = (l2, kind, ctext)
            if key in seen_lines:
                continue
            seen_lines.add(key)
            decisions.append(f'  L{l2:<5} {kind:<8} {ctext}{extra}{tag}')
        elif x.type == 'return_statement':
            rt = one_line(txt(x, src)[6:].strip().rstrip(';'), 50) or '(void)'
            if rt not in returns:
                returns.append(rt)
    if decisions:
        lines.append('Decisions (drive each outcome; loops: 0, 1, many):')
        lines += decisions[:40]
        if len(decisions) > 40:
            lines.append(f'  ... {len(decisions) - 40} more')
    else:
        lines.append('Decisions: none (straight-line code)')
    if returns:
        lines.append('Returns: ' + ' | '.join(returns[:8]))
    # globals
    gvars = file_scope_vars(tree_root, src)
    local = variables(n, src) | {p for p, _ in params}
    reads, writes = set(), set()
    for x in walk(body):
        if x.type == 'assignment_expression' or x.type == 'update_expression':
            lhs = x.child_by_field_name('left') or x.child_by_field_name('argument')
            k = ptr_key(lhs, src) if lhs is not None else None
            if k and k[0] == 'var' and k[1] in gvars and k[1] not in local:
                writes.add(k[1])
        if x.type == 'identifier':
            t = txt(x, src)
            if t in gvars and t not in local:
                reads.add(t)
    reads -= writes
    if reads or writes:
        lines.append('Globals/statics: ' + ', '.join(sorted(f'{w} (written)' for w in writes) + sorted(f'{r} (read)' for r in reads)))
    # calls (from the graph), callers, tests
    nid = node_info['id'] if node_info else None
    if nid:
        calls = []
        for e in out.get(nid, []):
            tg = ids[e['target']]
            if tg.get('type') == 'external':
                where = tg.get('declared_in') or ''
                if tg.get('targets'):
                    where = 'may call ' + ', '.join(t.split(' (')[0] for t in tg['targets'][:3])
                calls.append(f"{tg['label']} [{tg.get('kind')}: {where}]")
            else:
                st = ' static' if tg.get('static') else ''
                calls.append(f"{tg['label']} ({tg.get('source_file')}:{tg.get('source_location')}{st})")
        if calls:
            lines.append('Calls: ' + '; '.join(sorted(set(calls))))
        callers = sorted({(f"via pointer {ids[e['source']]['label']}" if ids[e['source']].get('type') == 'external'
                           else f"{ids[e['source']]['label']} ({ids[e['source']].get('source_file')})") for e in inc.get(nid, [])
                          if ids[e['source']].get('kind') not in ('test', 'fixture')})
        if callers:
            lines.append('Callers: ' + '; '.join(callers[:8]))
        tests = sorted({f"{ids[e['source']]['label']} ({ids[e['source']].get('source_file')}:{ids[e['source']].get('source_location')})"
                        for e in inc.get(nid, []) if ids[e['source']].get('kind') in ('test', 'fixture')
                        or re.search(r'(^|/)(test|tests)/', ids[e['source']].get('source_file') or '')})
        lines.append('Existing tests calling it directly: ' + ('; '.join(tests[:8]) if tests else 'none'))
    return '\n'.join(lines)


def cmd_card(argv):
    """card GRAPH_JSON SCAN_DIR NAME|FILE: test-planning card(s) for a function or every function of a file"""
    if len(argv) != 3:
        die('usage: card GRAPH_JSON SCAN_DIR FUNCTION|FILE')
    gpath, scan, target = argv
    base = os.path.dirname(os.path.abspath(scan))
    root = open(os.path.join(base, 'SOURCE_ROOT')).read().strip()
    lm = LineMap(os.path.join(base, 'linemap.json'))
    g, ids, out, inc = load(gpath)
    pc, pcpp = parsers()
    t = norm(target)
    nodes = [n for n in ids.values() if n.get('_callable') and n.get('source_file') == t
             and n.get('kind') not in ('test', 'fixture') and '::' not in n['label'].rstrip('()') or
             (n.get('source_file') == t and n.get('declared_at'))]
    if nodes:
        nodes = [n for n in ids.values() if n.get('_callable') and n.get('source_file') == t and n.get('kind') not in ('test', 'fixture')]
        nodes.sort(key=lambda n: int((LOC.search(n.get('source_location') or 'L0') or LOC.search('L0')).group(1)))
        print(f'# Cards for {t} ({len(nodes)} functions)')
        for n in nodes:
            print(); print(card_for(n['label'].rstrip('()') if n['label'].endswith('()') else n['label'], n, scan, lm, root, ids, out, inc, pc, pcpp))
        return
    cands = find(ids, t)
    print(card_for(t, cands[0] if cands else None, scan, lm, root, ids, out, inc, pc, pcpp))


# --------------------------------------------------------------------------- impact of a code change
def parse_funcs_text(text, is_c, pc, pcpp):
    """functions of a file content: name -> dict(start, end, sig, body, calls, static)"""
    src = text if isinstance(text, bytes) else text.encode('utf-8', 'replace')
    tree = (pc if is_c else pcpp).parse(src)
    _IS_C[id(src)] = is_c
    out, spans = {}, []
    for n in walk(tree.root_node):
        if n.type != 'function_definition':
            continue
        nm, decl = func_name(n, src)
        if not nm:
            continue
        cls = enclosing_class(n, src)
        if cls and '::' not in nm:
            nm = f'{cls}::{nm}'
        body = n.child_by_field_name('body')
        head = src[n.start_byte:(body.start_byte if body is not None else n.end_byte)].decode('utf-8', 'replace')
        head = re.sub(r'\s+', ' ', head).strip()
        btxt = re.sub(r'\s+', ' ', txt(body, src)) if body is not None else ''
        out.setdefault(nm, []).append({'start': n.start_point[0] + 1, 'end': n.end_point[0] + 1, 'sig': head, 'body': btxt,
                   'calls': {c for c, _ in callees(body, src)} if body is not None else set(),
                   'static': bool(re.search(r'\b(static|STATIC|PRIVATE)\b', head))})
        spans.append((n.start_point[0] + 1, n.end_point[0] + 1))
    return out, spans


HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


def changed_lines(diff_text):
    """new-side line numbers touched by a unified diff (-U0), and old-side deleted line numbers"""
    new, old = set(), set()
    for line in diff_text.splitlines():
        m = HUNK.match(line)
        if not m:
            continue
        os_, oc, ns, nc = int(m.group(1)), int(m.group(2) or 1), int(m.group(3)), int(m.group(4) or 1)
        new |= set(range(ns, ns + max(nc, 1)))
        old |= set(range(os_, os_ + oc))
    return new, old


def git(root, *args):
    r = subprocess.run(['git', '-C', root] + list(args), capture_output=True, text=True, errors='replace')
    return r.stdout if r.returncode == 0 else ''


CATEGORY = {   # change kind -> (tests calling it, mocks of it, new work, category letters in priority order)
    'added': ('none yet', 'none', 'D new tests; C a mock if other modules\' tests call it', 'D'),
    'deleted': ('A remove (ask)', 'A remove (ask)', 'check shared mocks first', 'A'),
    'signature': ('B update calls', 'C update every mock/stub (else the test build breaks)', '', 'C B'),
    'modified-logic': ('B re-check expected values', 'C only if the contract changed', 'D tests for new branches', 'B D'),
    'new-dependency': ('B tests now need the new mock', 'C create/extend the mock', 'E link errors until it exists', 'C B'),
    'moved/renamed': ('B includes/names', 'C names', 'E build registration', 'B E'),
    'type/macro': ('B tests using the type/limit (boundary values)', 'C mocks returning it', 'D new enum values/fields', 'B'),
}


def cmd_impact(argv):
    """impact GRAPH_JSON SCAN_DIR (--base REF | --uncommitted | --range A..B) [--out FILE] [--context FILE]"""
    a = list(argv)
    if len(a) < 3:
        die('usage: impact GRAPH_JSON SCAN_DIR (--base REF | --uncommitted | --range A..B) [--out FILE] [--context FILE]')
    gpath, scan = a[0], a[1]; a = a[2:]
    mode, ref, out_file, ctx_file = None, None, None, None
    while a:
        k = a.pop(0)
        if k == '--base': mode, ref = 'base', a.pop(0)
        elif k == '--uncommitted': mode = 'uncommitted'
        elif k == '--range': mode, ref = 'range', a.pop(0)
        elif k == '--out': out_file = a.pop(0)
        elif k == '--context': ctx_file = a.pop(0)
        else: die('unknown option ' + k)
    if not mode:
        die('give --base REF, --uncommitted or --range A..B')
    base_dir = os.path.dirname(os.path.abspath(scan))
    root = open(os.path.join(base_dir, 'SOURCE_ROOT')).read().strip()
    args = open(os.path.join(base_dir, 'BUILD_ARGS')).read().splitlines() if os.path.exists(os.path.join(base_dir, 'BUILD_ARGS')) else []
    paths = [l[5:] for l in args if l.startswith('path=')]
    cwd = next((l[4:] for l in args if l.startswith('cwd=')), root)
    rel_paths = [norm(os.path.relpath(os.path.realpath(os.path.join(cwd, p)), root)) for p in paths]
    is_testside = lambda f: bool(re.search(r'(^|/)(test|tests|unittest|unittests|ut|mocks?|stubs?|fakes?)(/|$)|test_|_test\.|Test\.|[Mm]ock|[Ss]tub|[Ff]ake', f))
    g, ids, out, inc = load(gpath)
    pc, pcpp = parsers()

    if mode == 'base':
        mb = git(root, 'merge-base', ref, 'HEAD').strip() or ref
        old_ref, diff_args, label = mb, [mb], f'branch vs {ref} (merge-base {mb[:10]})'
    elif mode == 'range':
        lo, _, hi = ref.partition('..'); old_ref, diff_args, label = lo, [lo, hi or 'HEAD'], f'{lo[:10]}..{(hi or "HEAD")[:10]}'
    else:
        old_ref, diff_args, label = 'HEAD', ['HEAD'], 'uncommitted changes (staged + unstaged + untracked)'
    status = git(root, 'diff', '--name-status', '-M', *diff_args, '--', *(rel_paths or ['.']))
    files = []
    for line in status.splitlines():
        parts = line.split('\t')
        st = parts[0][0]
        if st == 'R':
            files.append(('R', parts[1], parts[2]))
        else:
            files.append((st, parts[1], parts[1]))
    if mode == 'uncommitted':
        for f in git(root, 'ls-files', '--others', '--exclude-standard', '--', *(rel_paths or ['.'])).splitlines():
            files.append(('A', f, f))
    files = [(st, o, n) for st, o, n in files if os.path.splitext(n)[1].lower() in EXTS or os.path.splitext(o)[1].lower() in EXTS]
    code_files = [x for x in files if not is_testside(x[2])]
    test_files = [x for x in files if is_testside(x[2])]
    # headers changed OUTSIDE the scan paths (config, include/, shared headers) still matter when scope code includes them
    outside_hdrs = []
    if rel_paths:
        for line in git(root, 'diff', '--name-status', '-M', *diff_args, '--', '.').splitlines():
            parts = line.split('\t'); f = parts[-1]
            if os.path.splitext(f)[1].lower() in ('.h', '.hh', '.hpp', '.hxx') and not any(f == p or f.startswith(p + '/') for p in rel_paths) \
                    and not is_testside(f) and parts[0][0] != 'D':
                outside_hdrs.append(('M', f, f))
        code_files += outside_hdrs

    items, header_items = [], []
    for st, old_p, new_p in code_files:
        is_c = os.path.splitext(new_p)[1].lower() == '.c'
        old_txt = git(root, 'show', f'{old_ref}:{old_p}') if st != 'A' else ''
        try:
            new_txt = open(os.path.join(root, new_p), encoding='utf-8', errors='replace').read() if st != 'D' else ''
        except OSError:
            new_txt = ''
        of, _ = parse_funcs_text(old_txt, is_c, pc, pcpp)
        nf, nspans = parse_funcs_text(new_txt, is_c, pc, pcpp)
        dtxt = git(root, 'diff', '-U0', '-M', *diff_args, '--', old_p, new_p) if st != 'A' else ''
        nlines, olines = changed_lines(dtxt) if dtxt else (set(range(1, new_txt.count('\n') + 2)), set())
        all_old_bodies = {d['body'] for ds in of.values() for d in ds}
        for name in sorted(set(of) | set(nf)):
            olds, news = list(of.get(name, [])), list(nf.get(name, []))
            # pair identical definitions first (a function can exist in several #if branches)
            for n in list(news):
                for o in olds:
                    if o['sig'] == n['sig'] and o['body'] == n['body']:
                        olds.remove(o); news.remove(n); break
            pairs = []
            for n in news:                                   # changed or added definitions
                o = next((o for o in olds if o['sig'] == n['sig']), None) or \
                    next((o for o in olds if o['body'] == n['body']), None) or (olds[0] if olds else None)
                if o is not None:
                    olds.remove(o)
                pairs.append((o, n))
            pairs += [(o, None) for o in olds]                # deleted definitions
            for o, n in pairs:
                if o and not n:
                    kind = 'deleted'
                elif n and not o:
                    kind = 'moved/renamed' if st == 'R' and n['body'] in all_old_bodies else 'added'
                elif o['sig'] != n['sig']:
                    kind = 'signature'
                elif o['body'] != n['body']:
                    kind = 'modified-logic'
                else:
                    continue
                newdeps = sorted(n['calls'] - o['calls']) if o and n else sorted(n['calls']) if n and not o else []
                newdeps = [d for d in newdeps if d not in NOT_CALLS and not d.startswith('member:')]
                items.append({'file': new_p if n else old_p, 'name': name, 'kind': kind, 'line': (n or o)['start'],
                              'end': (n or o)['end'], 'static': (n or o)['static'], 'newdeps': newdeps,
                              'old_sig': o['sig'] if o else '', 'new_sig': n['sig'] if n else ''})
        # changes outside any function (types, macros, declarations) — matters most in headers
        outside = sorted(l for l in nlines if not any(s <= l <= e for s, e in nspans))
        if outside and new_txt:
            lines = new_txt.splitlines()
            kinds = set()
            for l in outside:
                t = lines[l - 1].strip() if l - 1 < len(lines) else ''
                if re.match(r'#\s*define', t): kinds.add('macro')
                elif re.search(r'\b(typedef|struct|union|enum)\b', t) or re.match(r'\s*[A-Za-z_]\w*\s*[,;=]', t): kinds.add('type')
                elif re.search(r'\w+\s*\(', t): kinds.add('declaration')
                elif t and not t.startswith(('//', '/*', '*')): kinds.add('other')
            if kinds & {'macro', 'type'} or (kinds == {'declaration'} and new_p.endswith(('.h', '.hpp', '.hh'))):
                if (st, old_p, new_p) in outside_hdrs:
                    kinds.add('outside scan paths')
                header_items.append({'file': new_p, 'lines': outside[:12], 'kinds': sorted(kinds),
                                     'text': [lines[l - 1].strip()[:80] for l in outside[:6] if l - 1 < len(lines)]})

    # graph lookups
    def node_for(name, file):
        cands = [n for n in ids.values() if n.get('_callable') and n.get('source_file') == file and
                 (n['label'] == name + '()' or n['label'] == name)]
        return cands[0] if cands else (find(ids, name) or [None])[0]

    def tests_reaching(nid, hops=4):
        seen, frontier, found = {nid: [ids[nid]['label']]}, [nid], []
        for depth in range(hops):
            nxt = []
            for cur in frontier:
                for e in inc.get(cur, []):
                    c = e['source']
                    if c in seen:
                        continue
                    seen[c] = seen[cur] + [ids[c]['label']]
                    n = ids[c]
                    if n.get('kind') in ('test', 'fixture') or is_testside(n.get('source_file') or ''):
                        found.append((depth + 1, n))
                    nxt.append(c)
            frontier = nxt
        return found

    def mocks_of(name, file):
        short = name.split('::')[-1]
        res = []
        for n in ids.values():
            if n.get('_callable') and n['label'] in (short + '()', name + '()') and is_testside(n.get('source_file') or '') and n.get('source_file') != file:
                res.append(f"{n.get('source_file')}:{n.get('source_location')}")
        # C++ interface: implementers in test paths
        if '::' in name:
            cls = name.rsplit('::', 1)[0]
            for e in g['links']:
                if e.get('relation') == 'inherits' and e['target'] in ids and ids[e['target']]['label'].split('::')[-1] == cls \
                        and e['source'] in ids and is_testside(ids[e['source']].get('source_file') or ''):
                    res.append(f"{ids[e['source']]['label']} ({ids[e['source']].get('source_file')})")
        # generated / macro mocks: CMock mock_<header>.h includes, FFF fakes, Parasoft stubs
        hdr = os.path.splitext(os.path.basename(file))[0]
        hits = subprocess.run(['grep', '-rlE', rf'mock_{re.escape(hdr)}\.h|FAKE_(VALUE|VOID)_FUNC[A-Z_]*\s*\([^;]*\b{re.escape(short)}\b|CppTest_Stub_{re.escape(short)}\b|{re.escape(short)}_(Expect|ExpectAndReturn|Ignore|Stub)',
                               '--include=*.c', '--include=*.cc', '--include=*.cpp', '--include=*.h', '--include=*.hpp']
                              + [os.path.join(root, p) for p in rel_paths if is_testside(p)] , capture_output=True, text=True)
        for h in hits.stdout.split():
            res.append(f"{norm(os.path.relpath(h, root))} (generated/macro mock usage)")
        return sorted(set(res))

    rows, details = [], []
    for it in items:
        nd = node_for(it['name'], it['file']) if it['kind'] != 'deleted' else node_for(it['name'], it['file'])
        tests, callers = [], []
        if nd:
            tests = sorted({f"{n['label']} ({n.get('source_file')}:{n.get('source_location')})" for _, n in tests_reaching(nd['id'])})
            callers = sorted({f"{ids[e['source']]['label']} ({ids[e['source']].get('source_file')})" for e in inc.get(nd['id'], [])
                              if not is_testside(ids[e['source']].get('source_file') or '') and ids[e['source']].get('type') != 'external'})
        mocks = mocks_of(it['name'], it['file'])
        kind = it['kind']
        if kind == 'modified-logic' and it['newdeps']:
            kind = 'new-dependency'
        t_, m_, new_, cat = CATEGORY[kind]
        if kind == 'added' and it['static']:
            new_ = 'D tests through its public callers (static)'
        if kind in ('modified-logic', 'signature', 'new-dependency') and not tests:
            cat = 'D ' + cat; new_ = 'D no test reaches it yet; ' + new_
        cats = ' '.join(dict.fromkeys(cat.split()))
        it.update({'tests': tests, 'callers': callers, 'mocks': mocks, 'kind': kind, 'cat': cats.split()[0], 'cats': cats,
                   'work': '; '.join(x for x in (t_ if tests else '', m_ if mocks else '', new_) if x)})
        rows.append(it)
    for h in header_items:
        includers = subprocess.run(['grep', '-rlE', rf'#\s*include\s*["<]([^">]*/)?{re.escape(os.path.basename(h["file"]))}[">]',
                                    '--include=*.c', '--include=*.cc', '--include=*.cpp', '--include=*.h', '--include=*.hpp',
                                    os.path.join(root, '.')], capture_output=True, text=True).stdout.split()
        includers = sorted(norm(os.path.relpath(x, root)) for x in includers)
        h['includers_test'] = [x for x in includers if is_testside(x)]
        h['includers_code'] = [x for x in includers if not is_testside(x)]

    # ---- output
    L = []
    L.append(f'# Impact of the code change ({label})')
    L.append(f'Scope: {", ".join(rel_paths) or "whole repo"}. Generated {__import__("datetime").date.today()} by graphify.sh impact. '
             'Every row is a fact from git, the syntax tree and the graph; the category comes from a fixed table.')
    n_notest = sum(1 for r in rows if not r['tests'] and r['kind'] != 'deleted')
    L.append(f'\nSummary: {len(code_files)} code files changed ({len([x for x in code_files if x[0]=="A"])} added, '
             f'{len([x for x in code_files if x[0]=="D"])} deleted, {len([x for x in code_files if x[0]=="R"])} renamed); '
             f'{len(rows)} functions changed; {n_notest} of them reached by no test; {len(header_items)} type/macro/declaration '
             f'changes outside functions; {len(test_files)} test/mock files already changed on this range.')
    L.append('\n## Work items (copy into context.md; choose which to do)')
    L.append('| W# | Code item (file:function) | Change kind | Existing tests | Mocks affected | Proposed work | Cat | In scope | Priority | Acceptance |')
    L.append('|----|---------------------------|-------------|----------------|----------------|---------------|-----|----------|----------|------------|')
    w = 0
    for r in rows:
        w += 1
        r['w'] = w
        L.append(f"| W{w} | {r['file']}:{r['name']} (L{r['line']}) | {r['kind']}{' (static)' if r['static'] else ''} | "
                 f"{len(r['tests'])}: {'; '.join(r['tests'][:2]) if r['tests'] else 'none'}{' …' if len(r['tests']) > 2 else ''} | "
                 f"{'; '.join(r['mocks'][:2]) if r['mocks'] else 'none'}{' …' if len(r['mocks']) > 2 else ''} | {r['work']} | {r['cat']} | | | |")
    for h in header_items:
        w += 1
        L.append(f"| W{w} | {h['file']} (L{','.join(map(str, h['lines'][:4]))}{'…' if len(h['lines']) > 4 else ''}) | type/macro ({'/'.join(h['kinds'])}) | "
                 f"{len(h['includers_test'])} test files include it | see includers | {CATEGORY['type/macro'][0]}; {CATEGORY['type/macro'][3]} | B | | | |")
    for st, o, n in test_files:
        w += 1
        L.append(f"| W{w} | {n} | test/mock code already {'added' if st=='A' else 'deleted' if st=='D' else 'changed'} on this range | — | — | read it before redoing this work | H | | | |")
    if rows or header_items:
        L.append('\n## Details')
    for r in rows:
        L.append(f"\n### W{r['w']} {r['file']}:{r['name']}  [{r['kind']}, L{r['line']}-{r['end']}]  categories {r['cats']}")
        if r['kind'] == 'signature':
            L.append(f"- was: `{r['old_sig'][:120]}`"); L.append(f"- now: `{r['new_sig'][:120]}`")
        if r['newdeps']:
            L.append(f"- new calls (need a mock/stub if external): {', '.join(r['newdeps'])}")
        L.append(f"- tests reaching it: {'; '.join(r['tests']) if r['tests'] else 'none'}")
        L.append(f"- production callers (their tests may mock it): {'; '.join(r['callers']) if r['callers'] else 'none'}")
        L.append(f"- mocks/stubs/fakes of it: {'; '.join(r['mocks']) if r['mocks'] else 'none'}")
    for h in header_items:
        L.append(f"\n### {h['file']} lines {', '.join(map(str, h['lines']))}  [{'/'.join(h['kinds'])}]")
        for t in h['text']:
            L.append(f"- `{t}`")
        L.append(f"- test/mock files including it: {', '.join(h['includers_test']) or 'none'}")
        L.append(f"- code files including it: {', '.join(h['includers_code'][:10]) or 'none'}")
    text = '\n'.join(L) + '\n'
    if out_file:
        open(out_file, 'w', encoding='utf-8').write(text)
        print(f'impact written: {out_file} ({len(rows)} functions, {len(header_items)} header changes, {len(test_files)} test files)')
    else:
        print(text)
    if ctx_file and os.path.exists(ctx_file):
        c = open(ctx_file, encoding='utf-8').read()
        table = [l for l in L if l.startswith('| W')]
        marker = '|----|---------------------------|'
        i = c.find(marker)
        if i >= 0:
            j = c.find('\n', i) + 1
            c = c[:j] + '\n'.join(table) + '\n' + c[j:]
            c = c.replace('Discovery mode / range:', f'Discovery mode / range: diff, {label} (full list: impact.md)', 1)
            open(ctx_file, 'w', encoding='utf-8').write(c)
            print(f'{len(table)} work-item rows inserted into {ctx_file}')


# --------------------------------------------------------------------------- self-test
def cmd_mkcdb(argv):
    """mkcdb FIXTURE_DIR: write compile_commands.json for the self-test fixture with local compilers"""
    fx = os.path.realpath(argv[0])
    cc = next((c for c in [os.environ.get('CC'), 'cc', 'gcc', 'clang'] if c and shutil.which(c)), None)
    cxx = next((c for c in [os.environ.get('CXX'), 'c++', 'g++', 'clang++'] if c and shutil.which(c)), None)
    if not cc or not cxx:
        print('no C/C++ compiler found (set CC and CXX): self-test runs WITHOUT a compile DB')
        sys.exit(3)
    inc = ['-Iconfig', '-Ihal', '-Ilib/crc', '-Isrc', '-Itests']
    entries = []
    for d, _, files in os.walk(fx):
        for n in sorted(files):
            ext = os.path.splitext(n)[1]
            if ext in ('.c', '.cpp'):
                f = os.path.relpath(os.path.join(d, n), fx).replace(os.sep, '/')
                comp = cc if ext == '.c' else cxx
                entries.append({'directory': fx, 'file': f,
                                'arguments': [comp] + inc + (['-std=c++17'] if ext == '.cpp' else []) + ['-c', f, '-o', f + '.o']})
    json.dump(entries, open(os.path.join(fx, 'compile_commands.json'), 'w'), indent=1)
    print(f'compile DB for self-test: {cc} / {cxx}')


def cmd_check(argv):
    """check GRAPH_JSON [plain]: verify the self-test fixture's known answers"""
    g, ids, out, inc = load(argv[0])
    plain = len(argv) > 1 and argv[1] == 'plain'
    by = {}
    for n in g['nodes']:
        by.setdefault(n['label'], []).append(n)
    def node(label):
        return (by.get(label) or [{}])[0]
    def calls(a, b):
        return any(ids[e['target']]['label'] == b for e in out.get(node(a).get('id'), []))
    results = []
    def check(name, ok, mode_ok=True):
        if mode_ok:
            results.append((name, bool(ok)))
    check('STATIC helper marked static', node('uart_wait_ready()').get('static') is True)
    check('crc16 is an external function declared in lib/crc/crc.h',
          node('crc16()').get('kind') == 'function' and node('crc16()').get('declared_in') == 'lib/crc/crc.h')
    check('proto_frame_done -> crc16 at original line 11',
          any(ids[e['target']]['label'] == 'crc16()' and e.get('source_location') == 'L11'
              for e in out.get(node('proto_frame_done()').get('id'), [])))
    check('only the active #if variant: uart_flush -> hal_dma_start, not uart_send',
          calls('uart_flush()', 'hal_dma_start()') and not calls('uart_flush()', 'uart_send()'), not plain)
    check('FW_ASSERT expanded to fw_assert_failed', calls('uart_send()', 'fw_assert_failed()'), not plain)
    check('designated initializer: s_ops->write may call uart_write', calls('s_ops->write()', 'uart_write()'))
    check('positional initializer: s_events.on_error may call drv_on_error', calls('s_events.on_error()', 'drv_on_error()'))
    check('registered callback: s_cb may call drv_uart_cb', calls('s_cb()', 'drv_uart_cb()'))
    check('C++ interface method is pure virtual', node('IBus::write()').get('pure_virtual') is True, not plain)
    check('Logger::emit defined in src/logger.cpp and calls IBus::write',
          node('Logger::emit()').get('source_file') == 'src/logger.cpp' and calls('Logger::emit()', 'IBus::write()'), not plain)
    check('TEST block node calls proto_feed', calls('TEST(Proto, Feed_StartByte_ReturnsZero)', 'proto_feed()'))
    check('TEST block reaches Logger::log through a typed local', calls('TEST(Logger, Log_Writes)', 'Logger::log()'))
    check('no node points outside the repository',
          not any((n.get('source_file') or '').startswith(('/', '..')) for n in g['nodes']))
    width = max(len(n) for n, _ in results)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    bad = sum(1 for _, ok in results if not ok)
    print(f"self-test: {len(results) - bad}/{len(results)} passed" + (' (plain mode: no compile DB)' if plain else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    try:   # `... | head` must not print a traceback
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    cmds = {'mirror': cmd_mirror, 'augment': cmd_augment, 'deps': cmd_deps, 'tests': cmd_tests,
            'mkcdb': cmd_mkcdb, 'check': cmd_check, 'card': cmd_card, 'impact': cmd_impact}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__); sys.exit(2)
    cmds[sys.argv[1]](sys.argv[2:])
