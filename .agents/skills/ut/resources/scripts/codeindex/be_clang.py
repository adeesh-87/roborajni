"""Clang backend: the compiler's own AST (libclang) with the build's real flags from compile_commands.json.
Exact overloads, templates, virtual calls, calls from macro expansions, constructors, lambdas and function-pointer /
std::function bindings; the outline comes from the same AST. One process per translation unit batch."""
import json, os, re, shlex, sys
from .model import Index, fid, norm, is_testside, test_label, FRAMEWORK, TEST_LINE

FUNC_KINDS = ('FUNCTION_DECL', 'CXX_METHOD', 'CONSTRUCTOR', 'DESTRUCTOR', 'FUNCTION_TEMPLATE', 'CONVERSION_FUNCTION')
CLASS_KINDS = ('STRUCT_DECL', 'CLASS_DECL', 'CLASS_TEMPLATE', 'UNION_DECL', 'CLASS_TEMPLATE_PARTIAL_SPECIALIZATION')
SCOPE_KINDS = ('NAMESPACE', 'LINKAGE_SPEC', 'UNEXPOSED_DECL') + CLASS_KINDS
WRAP = ('UNEXPOSED_EXPR', 'PAREN_EXPR', 'CSTYLE_CAST_EXPR', 'CXX_STATIC_CAST_EXPR', 'CXX_REINTERPRET_CAST_EXPR',
        'CXX_FUNCTIONAL_CAST_EXPR', 'CXX_CONST_CAST_EXPR', 'UNARY_OPERATOR')
SKIP_ARGS = ('-c', '-MD', '-MMD', '-MP', '-M', '-MM', '-fcallgraph-info', '-fstack-usage', '-flto', '-fno-fat-lto-objects')


def one_line(t, n=90):
    t = ' '.join((t or '').split())
    return t if len(t) <= n else t[:n - 3] + '...'


# ---------------------------------------------------------------------------------------------- compile DB
def entries_of(cdb_path):
    out = {}
    for e in json.load(open(cdb_path, encoding='utf-8')):
        f = os.path.realpath(os.path.join(e['directory'], e['file']))
        out.setdefault(f, e)                     # first entry wins (a file built by two targets)
    return out


def args_of(e, src):
    args = e.get('arguments') or shlex.split(e['command'], posix=(os.name != 'nt'))
    while args and os.path.basename(args[0]).lower() in ('ccache', 'sccache', 'distcc', 'icecc'):
        args = args[1:]
    out, skip = [], False
    for a in args[1:]:
        if skip:
            skip = False; continue
        if a in ('-o', '-MF', '-MT', '-MQ'):
            skip = True; continue
        if a in SKIP_ARGS or a.startswith(('-Wp,-M', '-o', '-fcallgraph-info', '-fdump-', '-fprofile-', '--coverage', '-ftest-coverage')):
            continue
        if os.path.realpath(os.path.join(e['directory'], a)) == src:
            continue
        out.append(a)
    # relative include paths are relative to the entry's directory
    fixed = []
    for a in out:
        m = re.match(r'^(-I|-isystem|-iquote|-include)(.+)$', a)
        if m and not os.path.isabs(m.group(2)):
            a = m.group(1) + os.path.normpath(os.path.join(e['directory'], m.group(2)))
        fixed.append(a)
    return fixed + ['-Wno-unknown-warning-option', '-ferror-limit=0'] + shlex.split(os.environ.get('UT_CLANG_EXTRA', ''))


# ---------------------------------------------------------------------------------------------- one TU
class TU:
    def __init__(self, ci, root, scope, path):
        self.ci, self.root, self.scope, self.path = ci, root, scope, path
        self.K = ci.CursorKind
        self.files = {}
        self.defs, self.decls, self.ext = {}, {}, {}
        self.binds, self.stores, self.args, self.inherits, self.fixtures = [], [], [], [], []
        self.symbols = {}
        self.lambdas = 0

    # ---- source helpers
    def fbytes(self, name):
        if name not in self.files:
            try:
                self.files[name] = open(name, 'rb').read()
            except OSError:
                self.files[name] = b''
        return self.files[name]

    def text(self, c):
        s, e = c.extent.start, c.extent.end
        if not s.file or not e.file or s.file.name != e.file.name:
            return ''
        return self.fbytes(s.file.name)[s.offset:e.offset].decode('utf-8', 'replace')

    def between(self, a, b):
        ea, sb = a.extent.end, b.extent.start
        if not ea.file or not sb.file or ea.file.name != sb.file.name:
            return ''
        return self.fbytes(ea.file.name)[ea.offset:sb.offset].decode('utf-8', 'replace').strip()

    def rel(self, fname):
        return norm(os.path.relpath(os.path.realpath(fname), self.root))

    def in_scope(self, fname):
        f = os.path.realpath(fname)
        return any(f == s or f.startswith(s + os.sep) for s in self.scope)

    def in_repo(self, fname):
        return os.path.realpath(fname).startswith(self.root + os.sep)

    def line(self, c):
        return c.extent.start.line

    def src_line(self, fname, line):
        ls = self.fbytes(fname).split(b'\n')
        return ls[line - 1].decode('utf-8', 'replace') if 0 < line <= len(ls) else ''

    # ---- names
    def qual(self, c):
        parts, p = [c.spelling], c.semantic_parent
        while p is not None and p.kind.name in CLASS_KINDS:
            parts.insert(0, p.spelling); p = p.semantic_parent
        return '::'.join(x for x in parts if x)

    def cls_of(self, c):
        p = c.semantic_parent
        return self.qual(p) if p is not None and p.kind.name in CLASS_KINDS else None

    def usr(self, r):
        """USR of a referenced function; a template specialization maps to its template"""
        try:
            t = self.ci.conf.lib.clang_getSpecializedCursorTemplate(r)
        except Exception:  # noqa: BLE001
            t = None
        if t is not None and t.kind.name in FUNC_KINDS:
            r = t
        return r.canonical.get_usr()

    def unwrap(self, c):
        while c is not None and c.kind.name in WRAP:
            kids = list(c.get_children())
            if c.kind.name == 'UNARY_OPERATOR' and not self.text(c).lstrip().startswith(('&', '*')):
                return c
            if not kids:
                return c
            c = kids[-1]
        return c

    # ---- entry
    def run(self, args):
        ci = self.ci
        tu = ci.Index.create().parse(self.path, args=args, options=ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        errs = [d for d in tu.diagnostics if d.severity >= 3]
        self.errors = [f'{self.rel(d.location.file.name) if d.location.file else "?"}:{d.location.line}: {d.spelling}' for d in errs[:3]]
        self.n_errors = len(errs)
        self.visit_scope(tu.cursor)
        return self

    def visit_scope(self, c):
        for ch in c.get_children():
            f = ch.location.file
            if f is None or not self.in_scope(f.name):
                if ch.kind.name in ('NAMESPACE', 'LINKAGE_SPEC') :
                    self.visit_scope(ch)          # namespaces are reopened in scope files too
                continue
            k = ch.kind.name
            if k in FUNC_KINDS:
                if ch.is_definition():
                    self.function(ch)
                elif k == 'CXX_METHOD' and ch.is_pure_virtual_method():
                    self.pure_decl(ch)
            elif k in CLASS_KINDS:
                if ch.is_definition():
                    self.klass(ch)
                    self.symbol(ch, {'CLASS_DECL': 'class', 'UNION_DECL': 'union'}.get(k, 'struct' if k == 'STRUCT_DECL' else 'class'))
                self.visit_scope(ch)
            elif k == 'ENUM_DECL' and ch.is_definition():
                self.symbol(ch, 'enum')
                for e in ch.get_children():
                    if e.kind.name == 'ENUM_CONSTANT_DECL':
                        self.symbol(e, 'enumerator', parent=ch)
            elif k in ('TYPEDEF_DECL', 'TYPE_ALIAS_DECL'):
                self.symbol(ch, 'typedef')
            elif k == 'MACRO_DEFINITION':
                self.symbol(ch, 'macro')
            elif k in SCOPE_KINDS:
                self.visit_scope(ch)
            elif k == 'VAR_DECL':
                self.symbol(ch, 'const' if ch.type.is_const_qualified() else 'var')
                self.var_decl(ch, None)
                self.expr_walk(ch, None, [])

    def symbol(self, c, kind, parent=None):
        """a named type / enum / macro / global, so agents look it up in the index instead of reading headers"""
        if not c.spelling or c.spelling.startswith('(') or not c.location.file:
            return
        name = self.qual(c) if kind in ('class', 'struct', 'union', 'enum', 'typedef') else c.spelling
        if parent is not None and parent.spelling:
            name = f'{self.qual(parent)}::{c.spelling}'
        lab, _ = test_label(self.src_line(c.location.file.name, c.location.line))
        if lab:
            return
        rng = parent if parent is not None else c
        f = self.rel(c.location.file.name)
        self.symbols.setdefault(f'{name}@{f}:{c.location.line}', {
            'name': name, 'kind': kind, 'file': f, 'line': rng.extent.start.line, 'end': rng.extent.end.line,
            **({'at': c.location.line, 'parent': self.qual(parent)} if parent is not None else {})})

    def klass(self, c):
        name = self.qual(c)
        lab, kind = test_label(self.src_line(c.location.file.name, c.location.line))
        if lab:                                     # classes generated by TEST(...) / TEST_GROUP(...) macros
            if kind == 'fixture':
                self.fixtures.append([self.rel(c.location.file.name), c.location.line, lab])
            return
        for ch in c.get_children():
            if ch.kind.name == 'CXX_BASE_SPECIFIER':
                base = (ch.referenced.spelling if ch.referenced is not None else ch.type.spelling).split('::')[-1]
                base = re.sub(r'<.*', '', base)
                self.inherits.append([name, base, self.rel(c.location.file.name)])

    def pure_decl(self, c):
        u = c.canonical.get_usr()
        if u in self.decls:
            return
        f = c.location.file.name
        self.decls[u] = {'name': self.qual(c), 'file': self.rel(f), 'line': self.line(c), 'end': c.extent.end.line,
                         'cls': self.cls_of(c), 'pure': True, 'virtual': True, 'sig': self.sig(c), 'params': self.params(c),
                         'outline': [], 'returns': [], 'globals': {'read': [], 'written': []}, 'calls': [], 'decl_only': True}

    def sig(self, c):
        res = c.result_type.spelling if c.kind.name not in ('CONSTRUCTOR', 'DESTRUCTOR') else ''
        ps = ', '.join(f'{a.type.spelling} {a.spelling}'.strip() for a in c.get_children() if a.kind.name == 'PARM_DECL')
        const = ' const' if c.kind.name == 'CXX_METHOD' and c.is_const_method() else ''
        st = 'static ' if c.linkage == self.ci.LinkageKind.INTERNAL else ''
        return one_line(f'{st}{res} {self.qual(c)}({ps}){const}'.strip(), 140)

    def params(self, c):
        ps = [ch for ch in c.get_children() if ch.kind.name == 'PARM_DECL']      # also works for templates
        return [[a.spelling or '?', one_line(f'{a.type.spelling} {a.spelling}', 40)] for a in ps]

    # ---- function definitions
    def function(self, c, name=None, cls=None, lam=None):
        u = lam or c.canonical.get_usr()
        if u in self.defs:
            return u
        f = c.extent.start.file.name if c.extent.start.file else c.location.file.name
        d = {'name': name or self.qual(c), 'file': self.rel(f), 'line': self.line(c), 'end': c.extent.end.line,
             'cls': cls if lam else self.cls_of(c),
             'static': (not lam) and c.linkage == self.ci.LinkageKind.INTERNAL,
             'virtual': (not lam) and c.kind.name == 'CXX_METHOD' and c.is_virtual_method(),
             'pure': (not lam) and c.kind.name == 'CXX_METHOD' and c.is_pure_virtual_method(),
             'sig': self.sig(c) if not lam else one_line(self.text(c).split('{')[0], 100),
             'params': self.params(c) if not lam else [], 'calls': [], 'returns': [], 'globals': {'read': set(), 'written': set()}}
        if not lam and c.kind.name in ('CXX_METHOD', 'CONSTRUCTOR', 'DESTRUCTOR', 'FUNCTION_TEMPLATE', 'CONVERSION_FUNCTION'):
            acc = c.canonical.access_specifier.name.lower()       # private/protected: tests must go through a public caller
            if acc in ('private', 'protected'):
                d['access'] = acc
        if not lam and c.semantic_parent is not None and c.semantic_parent.kind.name in CLASS_KINDS:
            p = c.semantic_parent
            d['owner_line'] = (self.rel(p.location.file.name), p.location.line) if p.location.file else None
        self.defs[u] = d
        body = next((ch for ch in c.get_children() if ch.kind.name == 'COMPOUND_STMT'), None)
        self.cur = u
        ctx = {'fn': u, 'params': [ch.spelling for ch in c.get_children() if ch.kind.name == 'PARM_DECL']}
        if c.kind.name == 'CONSTRUCTOR':            # member initializers: calls happen before the body
            pre = []
            for ch in c.get_children():
                if ch.kind.name not in ('COMPOUND_STMT', 'PARM_DECL', 'MEMBER_REF', 'TYPE_REF', 'NAMESPACE_REF', 'TEMPLATE_REF'):
                    self.expr_walk(ch, ctx, pre)
            d['outline'] = [x for x in pre if x['t'] == 'call']
        else:
            d['outline'] = []
        d['outline'] += self.seq(body, ctx) if body is not None else []
        d['globals'] = {'read': sorted(d['globals']['read'] - d['globals']['written']), 'written': sorted(d['globals']['written'])}
        d['returns'] = d['returns'][:8]
        return u

    # ---- statements -> outline
    def seq(self, c, ctx):
        if c is None:
            return []
        if c.kind.name == 'COMPOUND_STMT':
            out = []
            for ch in c.get_children():
                out += self.stmt(ch, ctx)
            return out
        return self.stmt(c, ctx)

    def first_line(self, c):
        if c is None:
            return None
        if c.kind.name == 'COMPOUND_STMT':
            kids = list(c.get_children())
            return self.line(kids[0]) if kids else None
        return self.line(c)

    def cond_items(self, kids, ctx):
        """leading init-statement / condition variable, then the condition"""
        pre, i = [], 0
        while i < len(kids) - 1 and kids[i].kind.name in ('VAR_DECL', 'DECL_STMT'):
            self.expr_walk(kids[i], ctx, pre); i += 1
        return pre, i

    def stmt(self, c, ctx):
        k = c.kind.name
        L = self.line(c)
        kids = list(c.get_children())
        if k == 'COMPOUND_STMT':
            return self.seq(c, ctx)
        if k == 'IF_STMT':
            pre, i = self.cond_items(kids, ctx)
            cond = kids[i] if i < len(kids) else None
            items = list(pre)
            if cond is not None:
                self.expr_walk(cond, ctx, items)
            ct = one_line(self.text(cond)) if cond is not None else ''
            then = self.seq(kids[i + 1], ctx) if i + 1 < len(kids) else []
            els = self.seq(kids[i + 2], ctx) if i + 2 < len(kids) else None
            d = {'t': 'if', 'l': L, 'c': ct, 'n': subconds(ct), 'then': then, 'else': els,
                 'tl': self.first_line(kids[i + 1]) if i + 1 < len(kids) else None,
                 'el': self.first_line(kids[i + 2]) if i + 2 < len(kids) else None, 'end': c.extent.end.line}
            return [x for x in items if x['t'] == 'call'] + [d]
        if k == 'SWITCH_STMT':
            pre, i = self.cond_items(kids, ctx)
            cond, body = (kids[i], kids[i + 1]) if i + 1 < len(kids) else (kids[i] if i < len(kids) else None, None)
            items = list(pre)
            if cond is not None:
                self.expr_walk(cond, ctx, items)
            cases, cur, has_default = [], None, False
            for ch in (body.get_children() if body is not None else []):
                if ch.kind.name in ('CASE_STMT', 'DEFAULT_STMT'):
                    labels, x = [], ch
                    while x is not None and x.kind.name in ('CASE_STMT', 'DEFAULT_STMT'):
                        xk = list(x.get_children())
                        if x.kind.name == 'CASE_STMT':
                            labels.append(one_line(self.text(xk[0]), 30) if xk else '?')
                            x = xk[-1] if len(xk) > 1 else None
                        else:
                            labels.append('default'); has_default = True
                            x = xk[0] if xk else None
                    cur = {'v': ', '.join(labels), 'l': self.line(ch), 'b': self.stmt(x, ctx) if x is not None else [],
                           'fl': self.line(x) if x is not None else None}
                    cases.append(cur)
                elif cur is not None:
                    cur['b'] += self.stmt(ch, ctx)
            for cs in cases:
                cs['ft'] = not cs['b'] or cs['b'][-1]['t'] not in ('brk', 'ret', 'throw', 'cont', 'goto')
            ct = one_line(self.text(cond)) if cond is not None else ''
            return [x for x in items if x['t'] == 'call'] + [{'t': 'switch', 'l': L, 'c': ct, 'cases': cases, 'default': has_default}]
        if k in ('WHILE_STMT', 'DO_STMT', 'FOR_STMT', 'CXX_FOR_RANGE_STMT'):
            if not kids:
                return []
            if k == 'DO_STMT':
                body, cond = kids[0], kids[-1]
                ct = one_line(self.text(cond))
                lit = self.unwrap(cond)
                if ct.strip('() ') in ('0', 'false') or (lit is not None and lit.kind.name in ('INTEGER_LITERAL', 'CXX_BOOL_LITERAL_EXPR')
                                                        and ct.strip('() ') not in ('1', 'true')):
                    return self.seq(body, ctx)
                b = self.seq(body, ctx)
                self.expr_walk(cond, ctx, b)
                return [{'t': 'loop', 'k': 'do', 'l': L, 'c': ct, 'b': b, 'bl': self.first_line(body)}]
            body = kids[-1]
            head = self.text(c)
            bt = self.text(body)
            head = head[:head.find(bt)] if bt and bt in head else head.split('{')[0]
            head = re.sub(r'^\s*(for|while)\s*', '', head).strip()
            ct = one_line(strip_parens(head))
            pre, b = [], []
            if k == 'WHILE_STMT':
                p0, i = self.cond_items(kids, ctx)
                b = p0
                for x in kids[i:-1]:
                    self.expr_walk(x, ctx, b)
            elif k == 'FOR_STMT':
                rest = kids[:-1]
                if rest and rest[0].kind.name == 'DECL_STMT':
                    self.expr_walk(rest[0], ctx, pre); rest = rest[1:]
                for x in rest:
                    self.expr_walk(x, ctx, b)
            else:
                for x in kids[:-1]:
                    if x.kind.name != 'VAR_DECL':
                        self.expr_walk(x, ctx, pre)
            b = [x for x in b if x['t'] == 'call'] + self.seq(body, ctx)
            kind = {'WHILE_STMT': 'while', 'FOR_STMT': 'for', 'CXX_FOR_RANGE_STMT': 'range'}[k]
            return [x for x in pre if x['t'] == 'call'] + [{'t': 'loop', 'k': kind, 'l': L, 'c': ct, 'b': b, 'bl': self.first_line(body)}]
        if k == 'RETURN_STMT':
            items = []
            for x in kids:
                self.expr_walk(x, ctx, items)
            rt = self.text(c)
            v = one_line(rt[6:].strip().rstrip(';'), 50) if rt.lstrip().startswith('return') else ''
            d = self.defs[ctx['fn']]
            if (v or '(void)') not in d['returns']:
                d['returns'].append(v or '(void)')
            return items + [{'t': 'ret', 'l': L, 'v': v}]
        if k == 'BREAK_STMT':
            return [{'t': 'brk', 'l': L}]
        if k == 'CONTINUE_STMT':
            return [{'t': 'cont', 'l': L}]
        if k in ('GOTO_STMT', 'INDIRECT_GOTO_STMT'):
            return [{'t': 'goto', 'l': L, 'v': one_line(self.text(c)[4:].strip().rstrip(';'), 30)}]
        if k == 'LABEL_STMT':
            return [y for x in kids for y in self.stmt(x, ctx)]
        if k == 'CXX_TRY_STMT':
            h = []
            for ch in kids[1:]:
                if ch.kind.name == 'CXX_CATCH_STMT':
                    ck = list(ch.get_children())
                    v = next((one_line(self.text(x), 40) for x in ck if x.kind.name == 'VAR_DECL'), '(...)')
                    h.append({'v': v, 'b': self.seq(ck[-1], ctx) if ck else []})
            return [{'t': 'try', 'l': L, 'b': self.seq(kids[0], ctx) if kids else [], 'h': h}]
        if k in ('NULL_STMT', 'ASM_STMT', 'MS_ASM_STMT'):
            return []
        items = []
        self.expr_walk(c, ctx, items)
        if k == 'CXX_THROW_EXPR' or (kids and k == 'UNEXPOSED_EXPR' and self.text(c).lstrip().startswith('throw')):
            items.append({'t': 'throw', 'l': L, 'v': one_line(self.text(c)[5:].strip(), 50)})
        return items

    # ---- expressions: calls in evaluation order, ?:, globals, function-pointer facts
    def expr_walk(self, c, ctx, out, callee_ref=None):
        k = c.kind.name
        if k == 'LAMBDA_EXPR':
            if ctx is not None:
                self.lambda_node(c, ctx)
            return
        if k == 'CONDITIONAL_OPERATOR':
            kids = list(c.get_children())
            ct = one_line(self.text(kids[0])) if kids else ''
            out.append({'t': '?:', 'l': self.line(c), 'c': ct, 'n': subconds(ct)})
        kids = list(c.get_children())
        if k == 'CALL_EXPR':
            callee = self.unwrap(kids[0]) if kids else None
            for i, ch in enumerate(kids):
                self.expr_walk(ch, ctx, out, callee_ref=callee if i == 0 else None)
            self.call(c, kids, callee, ctx, out)
            return
        for ch in kids:
            self.expr_walk(ch, ctx, out)
        if ctx is None:
            if k == 'VAR_DECL':
                self.var_decl(c, None)
            return
        d = self.defs[ctx['fn']]
        if k == 'DECL_REF_EXPR':
            r = c.referenced
            if r is not None and r.kind.name == 'VAR_DECL' and self.is_global(r):
                d['globals']['read'].add(r.spelling)
        elif k == 'BINARY_OPERATOR' and len(kids) == 2:
            op = self.between(kids[0], kids[1])
            if op == '=':
                self.assign(kids[0], kids[1], ctx)
                self.mark_written(kids[0], d)
        elif k == 'COMPOUND_ASSIGNMENT_OPERATOR' and kids:
            self.mark_written(kids[0], d)
        elif k == 'UNARY_OPERATOR' and kids:
            t = self.text(c)
            if '++' in t or '--' in t:
                self.mark_written(kids[0], d)
        elif k == 'VAR_DECL':
            self.var_decl(c, ctx)

    def is_global(self, r):
        p = r.semantic_parent
        if p is None or not r.location.file or not self.in_scope(r.location.file.name) or r.type.is_const_qualified():
            return False                                # constants are not state
        return p.kind.name in ('TRANSLATION_UNIT', 'NAMESPACE') or (p.kind.name in CLASS_KINDS and r.storage_class == self.ci.StorageClass.STATIC)

    def mark_written(self, lhs, d):
        x = self.unwrap(lhs)
        if x is not None and x.kind.name == 'DECL_REF_EXPR' and x.referenced is not None and x.referenced.kind.name == 'VAR_DECL' \
                and self.is_global(x.referenced):
            d['globals']['written'].add(x.referenced.spelling)

    def key_of(self, e):
        """where a function pointer lives: ('field', name) | ('var', name)"""
        x = self.unwrap(e)
        if x is None:
            return None
        if x.kind.name in ('MEMBER_REF_EXPR', 'MEMBER_REF'):
            return ('field', x.spelling)
        if x.kind.name == 'DECL_REF_EXPR' and x.referenced is not None:
            r = x.referenced
            return ('field', r.spelling) if r.kind.name == 'FIELD_DECL' else ('var', r.spelling)
        if x.kind.name == 'ARRAY_SUBSCRIPT_EXPR':
            kids = list(x.get_children())
            return self.key_of(kids[0]) if kids else None
        return None

    def value_of(self, e, ctx):
        """a function (usr), a lambda (id) or a parameter index stored somewhere"""
        x = self.unwrap(e)
        for _ in range(4):                          # std::function(f) / implicit conversions wrap the value
            if x is not None and x.kind.name == 'CALL_EXPR' and x.referenced is not None and x.referenced.kind.name == 'CONSTRUCTOR':
                kids = [k for k in x.get_children()]
                if len(kids) == 1:
                    x = self.unwrap(kids[0]); continue
            break
        if x is None:
            return None
        if x.kind.name == 'LAMBDA_EXPR' and ctx is not None:
            return ('fn', self.lambda_node(x, ctx))
        if x.kind.name in ('DECL_REF_EXPR', 'MEMBER_REF_EXPR') and x.referenced is not None:
            r = x.referenced
            if r.kind.name in FUNC_KINDS:
                return ('fn', self.usr(r))
            if r.kind.name == 'PARM_DECL' and ctx is not None and r.spelling in ctx['params']:
                return ('param', ctx['params'].index(r.spelling))
        return None

    def assign(self, lhs, rhs, ctx):
        key, val = self.key_of(lhs), self.value_of(rhs, ctx)
        if not key or not val:
            return
        site = f"{self.rel(lhs.extent.start.file.name)}:{self.line(lhs)}" if lhs.extent.start.file else ''
        if val[0] == 'fn':
            self.binds.append([list(key), val[1], site])
        elif ctx is not None:
            self.stores.append([ctx['fn'], list(key), val[1]])

    def var_decl(self, c, ctx):
        kids = [k for k in c.get_children() if k.kind.name not in ('TYPE_REF', 'NAMESPACE_REF', 'TEMPLATE_REF')]
        if not kids:
            return
        init = kids[-1]
        if init.kind.name == 'INIT_LIST_EXPR':
            self.init_list(init, c.type, ctx, c.spelling)
            return
        val = self.value_of(init, ctx)
        if val and val[0] == 'fn':
            self.binds.append([['var', c.spelling], val[1], f"{self.rel(c.location.file.name)}:{c.location.line}"])

    def init_list(self, lst, typ, ctx, varname):
        decl = typ.get_canonical().get_declaration()
        fields = [f.spelling for f in decl.get_children() if f.kind.name == 'FIELD_DECL'] if decl is not None else []
        is_array = typ.get_canonical().kind.name in ('CONSTANTARRAY', 'INCOMPLETEARRAY')
        for i, el in enumerate(lst.get_children()):
            x = el
            field = None
            if x.kind.name == 'UNEXPOSED_EXPR':            # designated: .field = value
                ks = list(x.get_children())
                if len(ks) == 2 and ks[0].kind.name == 'MEMBER_REF':
                    field, x = ks[0].spelling, ks[1]
            if x.kind.name == 'INIT_LIST_EXPR':
                self.init_list(x, x.type, ctx, varname); continue
            val = self.value_of(x, ctx)
            if not val or val[0] != 'fn':
                continue
            if field is None and not is_array and i < len(fields):
                field = fields[i]
            key = ['var', varname] if is_array or field is None else ['field', field]
            self.binds.append([key, val[1], f"{self.rel(el.location.file.name)}:{el.location.line}" if el.location.file else ''])

    def lambda_node(self, c, ctx):
        outer = self.defs[ctx['fn']]
        lid = f"lambda:{outer['file']}:{c.extent.start.line}:{c.extent.start.column}"
        if lid not in self.defs:
            base = outer['cls'] or outer['name'].split('::')[0]
            name = f"{outer['name'].rsplit('::', 1)[-1]}.lambda@{c.extent.start.line}"
            saved = self.cur
            self.function(c, name=(f'{outer["cls"]}::{name}' if outer.get('cls') else name), cls=outer.get('cls'), lam=lid)
            self.defs[lid]['lambda_of'] = ctx['fn']
            self.cur = saved
        return lid

    def call(self, c, kids, callee, ctx, out):
        r = c.referenced
        L = self.line(c)
        text = self.text(c)
        head = re.sub(r'\s+', '', text.split('(')[0] if '(' in text else text)
        ctext = one_line(text, 60)
        if not text and c.location.file:                     # inside a macro argument: use the source line
            text = self.src_line(c.location.file.name, L).strip()
            ctext = (r.spelling if r is not None else '?') + '(...)'
        if ctx is None:
            return
        target, kind, show = None, 'direct', head
        if r is not None and r.kind.name in FUNC_KINDS:
            if r.spelling == 'operator()' and r.semantic_parent is not None and 'function' in (r.semantic_parent.spelling or '') \
                    and (not r.location.file or not self.in_repo(r.location.file.name)):
                obj = self.unwrap(kids[0]) if kids else None       # std::function object called: a pointer call
                key = self.param_key(obj, ctx) or (self.key_of(obj) if obj is not None else None)
                show = re.sub(r'\s+', '', self.text(obj)) if obj is not None and self.text(obj) else head
                target, kind = ('ptr', key, show or head), 'pointer'
            elif r.kind.name in ('CONSTRUCTOR', 'DESTRUCTOR') and not (r.location.file and self.in_scope(r.location.file.name)):
                return
            elif not r.spelling or (r.spelling.startswith('operator') and not (r.location.file and self.in_scope(r.location.file.name))):
                return
            else:
                target = self.usr(r)
                if r.kind.name == 'CXX_METHOD' and r.is_virtual_method() and callee is not None and callee.kind.name == 'MEMBER_REF_EXPR' \
                        and '::' not in head:
                    kind = 'virtual'
                short = r.spelling
                where = text or (self.src_line(c.location.file.name, L) if c.location.file else '')
                if r.kind.name != 'CONSTRUCTOR' and short not in where:
                    kind, show = 'macro', r.spelling          # the call is produced by a macro expansion
                else:
                    show = head if head else r.spelling
                self.note_ext(r)
        else:
            key = self.param_key(callee, ctx) or (self.key_of(callee) if callee is not None else None)
            if key is None and r is None:
                return
            target, kind = ('ptr', key, head or (key[-1] if key and isinstance(key[-1], str) else '?')), 'pointer'
        # function-pointer arguments: register(cb) stores cb somewhere
        if r is not None and r.kind.name in FUNC_KINDS:
            for i, a in enumerate(kids[1:]):
                val = self.value_of(a, ctx)
                if val and val[0] == 'fn':
                    self.args.append([self.usr(r), r.spelling, i, val[1], f"{self.rel(c.location.file.name)}:{L}" if c.location.file else ''])
        d = self.defs[ctx['fn']]
        d['calls'].append([target, L, kind])
        out.append({'t': 'call', 'l': L, 'f': show, 'x': ctext, 'to': target if isinstance(target, str) else ['ptr'] + list(target[1:]) if target else None})

    def param_key(self, x, ctx):
        """a call through a parameter of this function: ('param', fn, index) - bound to what callers pass"""
        x = self.unwrap(x) if x is not None else None
        if x is not None and x.kind.name == 'DECL_REF_EXPR' and x.referenced is not None and x.referenced.kind.name == 'PARM_DECL' \
                and x.referenced.spelling in ctx['params']:
            return ('param', ctx['fn'], ctx['params'].index(x.referenced.spelling))
        return None

    def note_ext(self, r):
        u = self.usr(r)
        if u in self.ext or not r.location.file:
            return
        top, p = None, r.semantic_parent
        while p is not None and p.kind.name != 'TRANSLATION_UNIT':
            if p.kind.name == 'NAMESPACE':
                top = p.spelling
            p = p.semantic_parent
        self.ext[u] = {'name': self.qual(r), 'file': os.path.realpath(r.location.file.name), 'line': r.location.line,
                       'std': top in ('std', '__gnu_cxx', '__cxxabiv1', 'boost'),
                       'pure': r.kind.name == 'CXX_METHOD' and r.is_pure_virtual_method(),
                       'virtual': r.kind.name == 'CXX_METHOD' and r.is_virtual_method(), 'cls': self.cls_of(r),
                       'method': r.kind.name in ('CXX_METHOD', 'CONSTRUCTOR', 'DESTRUCTOR'),
                       'ctor': r.kind.name in ('CONSTRUCTOR', 'DESTRUCTOR')}

    def result(self):
        for d in self.defs.values():
            d['globals'] = {k: sorted(v) for k, v in d['globals'].items()} if isinstance(d['globals'].get('read'), set) else d['globals']
        return {'defs': self.defs, 'decls': self.decls, 'ext': self.ext, 'binds': self.binds, 'stores': self.stores,
                'args': self.args, 'inherits': self.inherits, 'fixtures': self.fixtures, 'symbols': self.symbols, 'errors': self.errors, 'n_errors': self.n_errors, 'file': self.rel(self.path)}


def strip_parens(t):
    t = t.strip()
    if t.startswith('(') and t.endswith(')'):
        depth = 0
        for i, ch in enumerate(t):
            depth += ch == '('
            depth -= ch == ')'
            if depth == 0 and i < len(t) - 1:
                return t
        return t[1:-1].strip()
    return t


def subconds(text):
    return len(re.findall(r'&&|\|\|', text)) + 1 if re.search(r'&&|\|\|', text) else 1


def parse_one(job):
    root, scope, path, args, cwd = job
    try:
        from .clangload import load
        ci = load()
        os.chdir(cwd)
        return TU(ci, root, scope, path).run(args).result()
    except Exception as e:  # noqa: BLE001 - report and continue with the other units
        import traceback
        return {'fatal': f'{path}: {e}', 'trace': traceback.format_exc()[-800:], 'file': path}


# ---------------------------------------------------------------------------------------------- build
def build(out_path, cdb_path, paths):
    import graphify_ut as G
    root = G.repo_root(paths)
    scope = [os.path.realpath(p) for p in paths]
    ents = entries_of(cdb_path)
    files = [f for f in G.collect(paths) if os.path.splitext(f)[1].lower() in G.SRC_EXTS]
    jobs, borrowed = [], []
    for f in files:
        e = ents.get(f)
        if e is None:                                  # no compile command: borrow flags from a neighbour
            same = [x for p, x in ents.items() if os.path.dirname(p) == os.path.dirname(f)]
            lang = [x for p, x in ents.items() if os.path.splitext(p)[1] == os.path.splitext(f)[1]]
            e = (same or lang or list(ents.values()) or [None])[0]
            if e is None:
                continue
            borrowed.append(norm(os.path.relpath(f, root)))
            args = args_of(e, os.path.realpath(os.path.join(e['directory'], e['file'])))
            for x in ents.values():                    # plus every include path / define the build uses anywhere
                for a in args_of(x, os.path.realpath(os.path.join(x['directory'], x['file']))):
                    if a.startswith(('-I', '-isystem', '-D')) and a not in args:
                        args.insert(0, a)
            jobs.append((root, scope, f, args, e['directory']))
            continue
        jobs.append((root, scope, f, args_of(e, os.path.realpath(os.path.join(e['directory'], e['file']))), e['directory']))
    workers = max(1, int(os.environ.get('UT_JOBS') or os.cpu_count() or 4))
    if workers > 1 and len(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
            results = list(pool.map(parse_one, jobs))
    else:
        results = [parse_one(j) for j in jobs]
    ix = Index.empty('clang', root, [norm(os.path.relpath(s, root)) for s in scope], cdb_path)
    fatal = [r for r in results if 'fatal' in r]
    results = [r for r in results if 'fatal' not in r]
    merge(ix, results, root)
    notes = []
    errs = [(r['file'], r['n_errors'], r['errors']) for r in results if r['n_errors']]
    if errs:
        notes.append(f"{len(errs)} translation units parsed WITH errors (their facts may be incomplete): " +
                     '; '.join(f"{f} ({n}: {e[0] if e else ''})" for f, n, e in errs[:5]))
    if borrowed:
        notes.append(f"no compile command, flags borrowed from a neighbour: {', '.join(borrowed[:8])}")
    for x in fatal:
        notes.append('FAILED: ' + x['fatal'])
    ix.meta['notes'] = notes
    ix.meta['units'] = len(jobs)
    ix.save(out_path)
    for n in notes:
        print('  ' + n)
    return ix


def merge(ix, results, root):
    for r in results:
        for k, v in r.get('symbols', {}).items():
            ix.symbols.setdefault(k, v)
    usr2id, defs = {}, {}
    for r in results:
        for u, d in r['defs'].items():
            defs.setdefault(u, d)
        for u, d in r['decls'].items():
            defs.setdefault(u, d)
    # test blocks: every definition written on a TEST(...) line (and fixture methods of a TEST_GROUP class) is one node
    line_cache = {}

    def src_line(f, l):
        if f not in line_cache:
            try:
                line_cache[f] = open(os.path.join(root, f), encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                line_cache[f] = []
        ls = line_cache[f]
        return ls[l - 1] if 0 < l <= len(ls) else ''

    groups = {}
    for u, d in defs.items():
        key = None
        lab, kind = test_label(src_line(d['file'], d['line']))
        if lab:
            key = (d['file'], d['line'], lab, kind)
        elif d.get('owner_line'):
            of, ol = d['owner_line']
            lab, kind = test_label(src_line(of, ol))
            if lab and kind == 'fixture':
                key = (of, ol, lab, kind)
        if key:
            groups.setdefault(key, []).append(u)
    for r in results:                                # TEST_GROUP blocks without methods still get their node
        for f, l, lab in r.get('fixtures', []):
            if not any(k[0] == f and k[1] == l for k in groups):
                groups[(f, l, lab, 'fixture')] = []
    grouped = {}
    for (f, l, lab, kind), us in groups.items():
        i = fid(lab, f, l)
        body = max((defs[u] for u in us), key=lambda d: d['end'] - d['line']) if us else {}
        ix.functions[i] = {'name': lab, 'label': lab, 'file': f, 'line': l, 'end': max([defs[u]['end'] for u in us] or [l]), 'kind': kind,
                           'sig': lab, 'outline': [s for u in us for s in defs[u].get('outline', [])] if kind == 'fixture' else body.get('outline', []),
                           'returns': [], 'params': [], 'globals': {'read': [], 'written': []}}
        for u in us:
            usr2id[u] = i; grouped[u] = i
    for u, d in defs.items():
        if u in grouped:
            continue
        i = fid(d['name'], d['file'], d['line'])
        usr2id[u] = i
        ix.functions[i] = {k: v for k, v in d.items() if k not in ('calls', 'owner_line', 'decl_only')}
        ix.functions[i]['kind'] = 'function'
    # externals
    ext_meta = {}
    for r in results:
        for u, e in r['ext'].items():
            ext_meta.setdefault(u, e)

    def ext_for(u):
        e = ext_meta.get(u)
        if e is None:
            return None
        f = e['file']
        in_repo = f.startswith(root + os.sep)
        rel = norm(os.path.relpath(f, root)) if in_repo else None
        name = e['name']
        if e.get('ctor') or 'operator' in name or e.get('std'):
            return None                                     # implicit / out-of-scope constructors: not a dependency
        if not in_repo and ('::' in name or name.startswith(('operator', '__builtin', '~'))):
            return None                                     # std:: internals, operators, constructors of library types
        if (rel and FRAMEWORK.search(rel) or (not in_repo and FRAMEWORK.search(f))) and '::' in name:
            return None                                     # test-framework methods (assert/mock plumbing)
        kind = 'test-framework' if FRAMEWORK.search(rel or f) else 'interface' if e.get('pure') else 'function' if in_repo else 'library'
        i = 'ext:' + name
        if i not in ix.externals:
            ix.externals[i] = {'name': name, 'kind': kind, 'declared_in': rel or '(not in repo: system/library)'}
        return i
    ptr_ext = {}
    for u, d in defs.items():
        src = usr2id[u]
        for target, line, kind in d.get('calls', []):
            if isinstance(target, str):
                to = usr2id.get(target) or ext_for(target)
                if to is None or to == src:
                    continue
                if kind == 'macro' and to in ix.externals and ix.externals[to]['kind'] == 'test-framework':
                    continue
                ix.add_call(src, to, line, d['file'], kind)
            elif target:
                _, key, show = target
                name = show or (key[1] if key else '?')
                i = ptr_id(key, name, defs)
                if i not in ix.externals:
                    where = (f"parameter {name} of {defs.get(key[1], {}).get('name', '?')}" if key and key[0] == 'param'
                             else f"{'field' if key and key[0] == 'field' else 'variable or parameter'} {key[1] if key else name}")
                    ix.externals[i] = {'name': name, 'kind': 'pointer', 'declared_in': f"{where} in {d['file']}"}
                ptr_ext.setdefault(tuple(key) if key else ('expr', name), set()).add(i)
                ix.add_call(src, i, line, d['file'], 'pointer')
    # outline targets; calls that resolve to nothing kept in the index (implicit constructors, std internals) are dropped
    def fix(items):
        out = []
        for s in items:
            if s['t'] == 'call':
                t = s.get('to')
                if isinstance(t, str):
                    s['to'] = usr2id.get(t) or ('ext:' + ext_meta[t]['name'] if t in ext_meta and 'ext:' + ext_meta[t]['name'] in ix.externals else None)
                    if s['to'] is None:
                        continue
                elif isinstance(t, list) and t and t[0] == 'ptr':
                    s['to'] = ptr_id(tuple(t[1]) if t[1] else None, t[2] or (t[1][1] if t[1] else '?'), defs)
            for k in ('then', 'else', 'b'):
                if s.get(k):
                    s[k] = fix(s[k])
            for c in s.get('cases', []) + s.get('h', []):
                c['b'] = fix(c.get('b') or [])
            out.append(s)
        return out
    for i in set(usr2id.values()):
        if ix.functions[i].get('outline'):
            ix.functions[i]['outline'] = fix(ix.functions[i]['outline'])
    # function-pointer targets: direct bindings, and functions passed to a registration call that stores its parameter
    binds = {}
    for r in results:
        for key, val, site in r['binds']:
            binds.setdefault(tuple(key), set()).add((val, site))
    stores = {}
    for r in results:
        for fn, key, pidx in r['stores']:
            stores.setdefault(fn, []).append((tuple(key), pidx))
    store_by_short = {}
    for fn, lst in stores.items():
        short = defs.get(fn, {}).get('name', '').split('::')[-1]
        for key, pidx in lst:
            store_by_short.setdefault((short, pidx), []).append(key)
    for r in results:
        for callee, short, idx, val, site in r['args']:
            keys = [k for k, p in stores.get(callee, []) if p == idx] or store_by_short.get((short, idx), [])
            for key in keys:
                binds.setdefault(key, set()).add((val, site))
            binds.setdefault(('param', callee, idx), set()).add((val, site))     # called through the parameter itself
    for key, exts in ptr_ext.items():
        for e in exts:
            tg = []
            for val, site in sorted(binds.get(key, ())):
                t = usr2id.get(val)
                if t is None:
                    continue
                tg.append([t, site])
                ix.add_call(e, t, ix.functions[t]['line'], ix.functions[t]['file'], 'pointer-target', 'INFERRED')
            if tg:
                ix.externals[e]['targets'] = tg
    seen = set()
    for r in results:
        for d, b, f in r['inherits']:
            if (d, b) not in seen:
                seen.add((d, b)); ix.inherits.append([d, b, f])
    ix.reindex()
    ix.bind_virtual_targets()


def ptr_id(key, name, defs):
    if key and key[0] == 'param':
        return f"ext:{defs.get(key[1], {}).get('name', '?')}/{name}"
    return 'ext:' + name


def _flat(outline):
    from .model import flatten
    return flatten(outline)
