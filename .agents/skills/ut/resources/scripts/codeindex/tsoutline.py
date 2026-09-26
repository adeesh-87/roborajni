"""Tree-sitter facts for one function: signature, params, returns, globals and the ordered outline
(control flow + calls). Used by the Graphify and GCC backends and by impact (old/new file versions)."""
import os, re
import graphify_ut as G

_parsers = {}


def parsers():
    if not _parsers:
        _parsers['c'], _parsers['cpp'] = G.parsers()
    return _parsers['c'], _parsers['cpp']


def one_line(t, n=90):
    t = ' '.join(t.split())
    return t if len(t) <= n else t[:n - 3] + '...'


def strip_parens(t):
    t = t.strip()
    while t.startswith('(') and t.endswith(')'):
        depth, ok = 0, True
        for i, ch in enumerate(t):
            depth += ch == '('
            depth -= ch == ')'
            if depth == 0 and i < len(t) - 1:
                ok = False; break
        if not ok:
            break
        t = t[1:-1].strip()
    return t


def subconds(text):
    return len(re.findall(r'&&|\|\||\band\b|\bor\b', text)) + 1 if re.search(r'&&|\|\|', text) else 1


class Ctx:
    def __init__(self, src, is_c, line_of, read_orig=None):
        self.src, self.is_c, self.line_of, self.read_orig = src, is_c, line_of, read_orig

    def t(self, n):
        return G.txt(n, self.src)

    def L(self, n):
        return self.line_of(n.start_point[0] + 1)


def call_name(fn, cx):
    """callee as written: name, Class::name, obj.m, p->m (whitespace removed)"""
    if fn.type == 'template_function':
        fn = fn.child_by_field_name('name') or fn
    if fn.type in ('identifier', 'qualified_identifier'):
        return cx.t(fn)
    if fn.type == 'field_expression':
        return re.sub(r'\s+', '', cx.t(fn))
    if fn.type == 'parenthesized_expression':
        return re.sub(r'\s+', '', cx.t(fn))
    return None


def calls_in(node, cx):
    """calls inside an expression in evaluation order (inner first); lambdas skipped (run later); ?: become decisions"""
    found = []
    stack = [node]
    while stack:
        x = stack.pop()
        if x.type == 'lambda_expression':
            continue
        if x.type == 'call_expression':
            fn = x.child_by_field_name('function')
            nm = call_name(fn, cx) if fn is not None else None
            if nm and nm.split('::')[-1] not in G.NOT_CALLS and not nm.startswith('std::'):
                found.append((x.end_byte, {'t': 'call', 'l': cx.L(x), 'f': nm, 'x': one_line(cx.t(x), 60)}))
        elif x.type == 'conditional_expression':
            c = x.child_by_field_name('condition')
            ct = strip_parens(cx.t(c)) if c is not None else ''
            found.append((x.start_byte, {'t': '?:', 'l': cx.L(x), 'c': one_line(ct), 'n': subconds(ct)}))
        stack.extend(x.children)
    return [s for _, s in sorted(found, key=lambda p: p[0])]


def seq(node, cx):
    if node is None:
        return []
    if node.type == 'compound_statement':
        out = []
        for s in node.named_children:
            out += stmt(s, cx)
        return out
    return stmt(node, cx)


def first_line(node, cx):
    """line of the first statement of a branch (for coverage line counts)"""
    if node is None:
        return None
    if node.type == 'compound_statement':
        kids = [k for k in node.named_children if k.type != 'comment']
        return cx.L(kids[0]) if kids else None
    return cx.L(node)


def cond_text(node, cx):
    if node is None:
        return ''
    if node.type == 'condition_clause':
        v = node.child_by_field_name('value')
        return strip_parens(cx.t(v) if v is not None else cx.t(node))
    return strip_parens(cx.t(node))


def src_tag(d, node, cx):
    """condition produced by a macro (preprocessed mirror): keep the original source line for the reader"""
    if cx.read_orig:
        line = cx.read_orig(node.start_point[0] + 1)      # original source text of that line
        inner = d.get('c', '')
        if line and inner and inner not in line and re.search(r'\b[A-Z][A-Z0-9_]{2,}\s*\(', line):
            d['src'] = one_line(line.strip(), 60)
    return d


def stmt(s, cx):
    t = s.type
    if t == 'compound_statement':
        return seq(s, cx)
    if t == 'if_statement':
        cond = s.child_by_field_name('condition')
        ct = cond_text(cond, cx)
        pre = calls_in(cond, cx) if cond is not None else []
        alt = s.child_by_field_name('alternative')
        if alt is not None and alt.type == 'else_clause':
            alt = alt.named_children[0] if alt.named_children else None
        cons = s.child_by_field_name('consequence')
        d = {'t': 'if', 'l': cx.L(s), 'c': one_line(ct), 'n': subconds(ct),
             'then': seq(cons, cx), 'else': seq(alt, cx) if alt is not None else None,
             'tl': first_line(cons, cx), 'el': first_line(alt, cx) if alt is not None else None, 'end': cx.line_of(s.end_point[0] + 1)}
        return [x for x in pre if x['t'] == 'call'] + [src_tag(d, s, cx)]
    if t == 'switch_statement':
        cond = s.child_by_field_name('condition')
        body = s.child_by_field_name('body')
        cases, pending, has_default = [], [], False
        for c in (body.named_children if body is not None else []):
            if c.type != 'case_statement':
                continue
            v = c.child_by_field_name('value')
            if v is None:
                has_default = True
            pending.append(one_line(cx.t(v), 30) if v is not None else 'default')
            items = []
            for x in c.named_children:
                if v is not None and x.start_byte == v.start_byte and x.end_byte == v.end_byte:
                    continue
                items += stmt(x, cx)
            if items or c.end_byte == body.named_children[-1].end_byte:
                ft = not items or items[-1]['t'] not in ('brk', 'ret', 'throw', 'cont', 'goto')
                stl = [x for x in c.named_children if not (v is not None and x.start_byte == v.start_byte) and x.type != 'comment']
                cases.append({'v': ', '.join(pending), 'l': cx.L(c), 'b': items, 'ft': ft, 'fl': cx.L(stl[0]) if stl else None})
                pending = []
        if pending:
            cases.append({'v': ', '.join(pending), 'l': cx.L(s), 'b': [], 'ft': True})
        ct = cond_text(cond, cx)
        return calls_in(cond, cx) + [{'t': 'switch', 'l': cx.L(s), 'c': one_line(ct), 'cases': cases, 'default': has_default}]
    if t in ('for_statement', 'while_statement', 'do_statement', 'for_range_loop'):
        body = s.child_by_field_name('body')
        if t == 'do_statement':
            cond = s.child_by_field_name('condition')
            ct = cond_text(cond, cx)
            if ct.strip() in ('0', 'false'):
                return seq(body, cx)              # do { } while (0) from a macro: plain block
            b = seq(body, cx) + (calls_in(cond, cx) if cond is not None else [])
            return [{'t': 'loop', 'k': 'do', 'l': cx.L(s), 'c': one_line(ct), 'b': b, 'bl': first_line(body, cx)}]
        if t == 'for_statement':
            head = cx.t(s)
            head = head[:head.find(cx.t(body))] if body is not None else head
            ct = strip_parens(head.strip()[3:].strip())
            cond = s.child_by_field_name('condition')
            pre = []
            init = s.child_by_field_name('initializer')
            if init is not None:
                pre = calls_in(init, cx)
            b = (calls_in(cond, cx) if cond is not None else []) + seq(body, cx)
            upd = s.child_by_field_name('update')
            if upd is not None:
                b += calls_in(upd, cx)
            return pre + [{'t': 'loop', 'k': 'for', 'l': cx.L(s), 'c': one_line(ct), 'b': b, 'bl': first_line(body, cx)}]
        if t == 'for_range_loop':
            head = cx.t(s)
            head = head[:head.find(cx.t(body))] if body is not None else head
            ct = strip_parens(head.strip()[3:].strip())
            right = s.child_by_field_name('right')
            pre = calls_in(right, cx) if right is not None else []
            return pre + [{'t': 'loop', 'k': 'range', 'l': cx.L(s), 'c': one_line(ct), 'b': seq(body, cx), 'bl': first_line(body, cx)}]
        cond = s.child_by_field_name('condition')
        ct = cond_text(cond, cx)
        b = (calls_in(cond, cx) if cond is not None else []) + seq(body, cx)
        return [{'t': 'loop', 'k': 'while', 'l': cx.L(s), 'c': one_line(ct), 'b': b, 'bl': first_line(body, cx)}]
    if t == 'return_statement':
        v = one_line(cx.t(s)[6:].strip().rstrip(';'), 50)
        return calls_in(s, cx) + [{'t': 'ret', 'l': cx.L(s), 'v': v}]
    if t == 'throw_statement':
        return calls_in(s, cx) + [{'t': 'throw', 'l': cx.L(s), 'v': one_line(cx.t(s)[5:].strip().rstrip(';'), 50)}]
    if t == 'break_statement':
        return [{'t': 'brk', 'l': cx.L(s)}]
    if t == 'continue_statement':
        return [{'t': 'cont', 'l': cx.L(s)}]
    if t == 'goto_statement':
        return [{'t': 'goto', 'l': cx.L(s), 'v': one_line(cx.t(s)[4:].strip().rstrip(';'), 30)}]
    if t == 'labeled_statement':
        return [y for x in s.named_children[1:] for y in stmt(x, cx)]
    if t == 'try_statement':
        h = []
        for c in s.named_children:
            if c.type == 'catch_clause':
                p = c.child_by_field_name('parameters')
                h.append({'v': one_line(cx.t(p), 40) if p is not None else '(...)', 'b': seq(c.child_by_field_name('body'), cx)})
        return [{'t': 'try', 'l': cx.L(s), 'b': seq(s.child_by_field_name('body'), cx), 'h': h}]
    if t in ('expression_statement', 'declaration', 'return_statement'):
        out = calls_in(s, cx)
        if t == 'expression_statement' and s.named_children and s.named_children[0].type == 'throw_expression':
            out.append({'t': 'throw', 'l': cx.L(s), 'v': one_line(cx.t(s)[5:].strip().rstrip(';'), 50)})
        return out
    if t in ('comment', 'type_definition', 'struct_specifier', 'enum_specifier', 'class_specifier'):
        return []
    return calls_in(s, cx)


def describe(defn, src, tree_root, is_c, line_of, read_orig=None):
    """facts of one function_definition node"""
    G._IS_C[id(src)] = is_c
    cx = Ctx(src, is_c, line_of, read_orig)
    body = defn.child_by_field_name('body')
    head = src[defn.start_byte:body.start_byte].decode('utf-8', 'replace') if body is not None else cx.t(defn)
    d = {'sig': one_line(head, 140), 'static': bool(re.search(r'\b(static|STATIC|PRIVATE)\b', head))}
    _, decl = G.func_name(defn, src)
    params = []
    plist = decl.child_by_field_name('parameters') if decl is not None else None
    for pd in (plist.named_children if plist is not None else []):
        if pd.type in ('parameter_declaration', 'optional_parameter_declaration'):
            nm = G.innermost_name(pd.child_by_field_name('declarator'), src)
            if nm is None and cx.t(pd).strip() == 'void':
                continue
            params.append([cx.t(nm) if nm is not None else '?', one_line(cx.t(pd), 40)])
    d['params'] = params
    if body is None:
        d.update({'outline': [], 'returns': [], 'globals': {'read': [], 'written': []}})
        return d
    d['outline'] = seq(body, cx)
    rets = []
    for s in G.walk(body):
        if s.type == 'return_statement':
            rt = one_line(cx.t(s)[6:].strip().rstrip(';'), 50) or '(void)'
            if rt not in rets:
                rets.append(rt)
    d['returns'] = rets[:8]
    gvars = G.file_scope_vars(tree_root, src)
    local = G.variables(defn, src) | {p for p, _ in params}
    reads, writes = set(), set()
    for x in G.walk(body):
        if x.type in ('assignment_expression', 'update_expression'):
            lhs = x.child_by_field_name('left') or x.child_by_field_name('argument')
            k = G.ptr_key(lhs, src) if lhs is not None else None
            if k and k[0] == 'var' and k[1] in gvars and k[1] not in local:
                writes.add(k[1])
        if x.type == 'identifier':
            tt = cx.t(x)
            if tt in gvars and tt not in local:
                reads.add(tt)
    d['globals'] = {'read': sorted(reads - writes), 'written': sorted(writes)}
    return d


def functions_of(text, is_c, line_of=lambda l: l, read_orig=None, with_facts=True):
    """[(qualified name, start, end, facts, node)] for every function definition in a file's text"""
    pc, pcpp = parsers()
    src = text if isinstance(text, bytes) else text.encode('utf-8', 'replace')
    tree = (pc if is_c else pcpp).parse(src)
    G._IS_C[id(src)] = is_c
    out = []
    for n in G.walk(tree.root_node):
        if n.type != 'function_definition':
            continue
        nm, _ = G.func_name(n, src)
        if not nm:
            continue
        cls = G.enclosing_class(n, src)
        if cls and '::' not in nm:
            nm = f'{cls}::{nm}'
        facts = describe(n, src, tree.root_node, is_c, line_of, read_orig) if with_facts else {}
        out.append((nm, line_of(n.start_point[0] + 1), line_of(n.end_point[0] + 1), facts, n))
    return out


SYM_TYPES = {'class_specifier': 'class', 'struct_specifier': 'struct', 'union_specifier': 'union', 'enum_specifier': 'enum'}


def symbols_of_file(root, rel):
    """types, enums, enumerators, typedefs, macros and file-scope variables of one ORIGINAL file (tree-sitter)"""
    from .model import test_label
    pc, pcpp = parsers()
    try:
        src = open(os.path.join(root, rel), 'rb').read()
    except OSError:
        return {}
    tree = (pc if rel.endswith('.c') else pcpp).parse(src)
    lines = src.decode('utf-8', 'replace').splitlines()
    out = {}

    def add(name, kind, node, at=None, parent=None):
        if not name or test_label(lines[node.start_point[0]] if node.start_point[0] < len(lines) else '')[0]:
            return
        l = (at or node).start_point[0] + 1
        d = {'name': name, 'kind': kind, 'file': rel, 'line': node.start_point[0] + 1, 'end': node.end_point[0] + 1}
        if parent:
            d.update({'at': l, 'parent': parent})
        out.setdefault(f'{name}@{rel}:{l}', d)

    def scope_name(n):
        parts, p = [], n.parent
        while p is not None:
            if p.type in ('class_specifier', 'struct_specifier') and p.child_by_field_name('name') is not None:
                parts.insert(0, G.txt(p.child_by_field_name('name'), src))
            p = p.parent
        return parts
    for n in G.walk(tree.root_node):
        t = n.type
        if t in SYM_TYPES and n.child_by_field_name('body') is not None:
            nm = n.child_by_field_name('name')
            name = G.txt(nm, src) if nm is not None else None
            if name is None and n.parent is not None and n.parent.type == 'type_definition':
                d = G.innermost_name(n.parent.child_by_field_name('declarator'), src)
                name = G.txt(d, src) if d is not None else None
            if not name:
                continue
            q = '::'.join(scope_name(n) + [name])
            add(q, SYM_TYPES[t], n)
            if t == 'enum_specifier':
                for e in n.child_by_field_name('body').named_children:
                    if e.type == 'enumerator' and e.child_by_field_name('name') is not None:
                        add(f"{q}::{G.txt(e.child_by_field_name('name'), src)}", 'enumerator', n, at=e, parent=q)
        elif t == 'type_definition':
            d = G.innermost_name(n.child_by_field_name('declarator'), src)
            if d is not None:
                add(G.txt(d, src), 'typedef', n)
        elif t == 'alias_declaration' and n.child_by_field_name('name') is not None:
            add(G.txt(n.child_by_field_name('name'), src), 'typedef', n)
        elif t in ('preproc_def', 'preproc_function_def') and n.child_by_field_name('name') is not None:
            add(G.txt(n.child_by_field_name('name'), src), 'macro', n)
        elif t == 'declaration' and n.parent is not None and n.parent.type in ('translation_unit', 'declaration_list'):
            if any(c.type == 'function_declarator' for c in G.walk(n)):
                continue
            const = bool(re.search(r'\b(const|constexpr)\b', G.txt(n, src).split('=')[0]))
            for c in n.named_children:
                if c.type in ('identifier', 'init_declarator', 'pointer_declarator', 'array_declarator'):
                    nm = G.innermost_name(c, src)
                    if nm is not None and nm.type == 'identifier':
                        add(G.txt(nm, src), 'const' if const else 'var', n)
    return out


def access_of_file(root, rel):
    """Class::method -> 'private' | 'protected' for methods declared or defined inside class bodies of one file"""
    if rel.endswith('.c'):
        return {}
    _, pcpp = parsers()
    try:
        src = open(os.path.join(root, rel), 'rb').read()
    except OSError:
        return {}
    out = {}
    for n in G.walk(pcpp.parse(src).root_node):
        if n.type not in ('class_specifier', 'struct_specifier') or n.child_by_field_name('body') is None \
                or n.child_by_field_name('name') is None:
            continue
        cls = G.txt(n.child_by_field_name('name'), src)
        acc = 'private' if n.type == 'class_specifier' else 'public'
        for c in n.child_by_field_name('body').named_children:
            if c.type == 'access_specifier':
                acc = G.txt(c, src).strip().rstrip(':').strip()
                continue
            if c.type in ('field_declaration', 'function_definition', 'declaration', 'template_declaration'):
                d = c.child_by_field_name('declarator')
                while d is not None and d.type != 'function_declarator':
                    d = d.child_by_field_name('declarator') or next((x for x in d.named_children if x.type.endswith('declarator')), None)
                if d is None:
                    continue
                nm = G.innermost_name(d, src)
                if nm is not None and acc in ('private', 'protected'):
                    out[f'{cls}::{G.txt(nm, src)}'] = acc
    return out


def symbols_for(root, rel_files):
    out = {}
    for f in rel_files:
        try:
            out.update(symbols_of_file(root, f))
        except Exception:  # noqa: BLE001 - a file tree-sitter cannot parse contributes nothing
            pass
    return out


def attach_targets(outline, edges, index):
    """fill outline call 'to' from the index call edges of the same function (matched by line + name)"""
    by_line = {}
    for c in edges:
        by_line.setdefault(c.get('line'), []).append(c)
    for s in outline_iter(outline):
        if s['t'] != 'call':
            continue
        cands = by_line.get(s['l'], [])
        short = re.split(r'::|\.|->', s['f'])[-1]
        hit = [c for c in cands if index.node(c['to']) and re.split(r'::|\.|->', index.node(c['to'])['name'])[-1] == short]
        if not hit and len([c for c in cands if c.get('kind') not in ('pointer-target', 'virtual-target')]) == 1 and len(
                [x for x in outline_iter(outline) if x['t'] == 'call' and x['l'] == s['l']]) == 1:
            hit = cands
        s['to'] = hit[0]['to'] if hit else None


def outline_iter(outline):
    from .model import flatten
    return flatten(outline)
