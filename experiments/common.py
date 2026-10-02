"""Shared helpers for the libclang based tools (dead_code.py, mcdc.py).

Needs the libclang Python bindings:  pip install libclang
(or point --libclang / $LIBCLANG_PATH at an installed libclang.so / .dll).
"""
import ctypes
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

ci = None  # clang.cindex, loaded by setup_libclang()


class _Extras:
    """libclang C functions the Python bindings don't wrap (all optional)."""


X = _Extras()


class _RangeList(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint), ("ranges", ctypes.c_void_p)]


# clang's CXBinaryOperatorKind / CXUnaryOperatorKind
BINOPS = {1: ".*", 2: "->*", 3: "*", 4: "/", 5: "%", 6: "+", 7: "-", 8: "<<", 9: ">>",
          10: "<=>", 11: "<", 12: ">", 13: "<=", 14: ">=", 15: "==", 16: "!=", 17: "&",
          18: "^", 19: "|", 20: "&&", 21: "||", 22: "=", 23: "*=", 24: "/=", 25: "%=",
          26: "+=", 27: "-=", 28: "<<=", 29: ">>=", 30: "&=", 31: "^=", 32: "|=", 33: ","}
UNOPS = {1: "++", 2: "--", 3: "++", 4: "--", 5: "&", 6: "*", 7: "+", 8: "-", 9: "~",
         10: "!", 11: "__real", 12: "__imag", 13: "__extension__", 14: "co_await"}


def setup_libclang(path=None):
    """Import clang.cindex, optionally from an explicit libclang location."""
    global ci
    if ci is not None:
        return ci
    try:
        import clang.cindex as cindex
    except ImportError:
        sys.exit("error: libclang Python bindings not found - run: pip install libclang")
    path = path or os.environ.get("LIBCLANG_PATH")
    if path and not cindex.Config.loaded:
        if os.path.isdir(path):
            cindex.Config.set_library_path(path)
        else:
            cindex.Config.set_library_file(path)
    ci = cindex
    _register_extras()
    return ci


def _register_extras():
    lib = ci.conf.lib

    def reg(name, argtypes, restype, errcheck=None):
        try:
            fn = getattr(lib, name)
        except AttributeError:
            return None
        fn.argtypes, fn.restype = argtypes, restype
        if errcheck:
            fn.errcheck = errcheck
        return fn

    cur, tu, vp = ci.Cursor, ci.TranslationUnit, ctypes.c_void_p
    X.binop = reg("clang_getCursorBinaryOperatorKind", [cur], ctypes.c_int)
    X.unop = reg("clang_getCursorUnaryOperatorKind", [cur], ctypes.c_int)
    X.spec_template = reg("clang_getSpecializedCursorTemplate", [cur], cur,
                          ci.Cursor.from_result)
    X.overridden = reg("clang_getOverriddenCursors",
                       [cur, ctypes.POINTER(ctypes.POINTER(cur)), ctypes.POINTER(ctypes.c_uint)],
                       None)
    X.dispose_overridden = reg("clang_disposeOverriddenCursors", [ctypes.POINTER(cur)], None)
    X.skipped = reg("clang_getAllSkippedRanges", [tu], ctypes.POINTER(_RangeList))
    X.dispose_ranges = reg("clang_disposeSourceRangeList", [ctypes.POINTER(_RangeList)], None)
    X.evaluate = reg("clang_Cursor_Evaluate", [cur], vp)
    X.eval_kind = reg("clang_EvalResult_getKind", [vp], ctypes.c_int)
    X.eval_int = reg("clang_EvalResult_getAsLongLong", [vp], ctypes.c_longlong)
    X.eval_float = reg("clang_EvalResult_getAsDouble", [vp], ctypes.c_double)
    X.eval_dispose = reg("clang_EvalResult_dispose", [vp], None)


# ---------------------------------------------------------------- cursor helpers

def binop(c):
    """Operator spelling of a BINARY_OPERATOR / COMPOUND_ASSIGNMENT cursor."""
    if X.binop:
        return BINOPS.get(X.binop(c), "?")
    kids = list(c.get_children())
    if len(kids) == 2:
        end = kids[0].extent.end.offset
        for t in c.get_tokens():
            if t.extent.start.offset >= end:
                return t.spelling
    return "?"


def unop(c):
    """Operator spelling of a UNARY_OPERATOR cursor."""
    if X.unop:
        return UNOPS.get(X.unop(c), "?")
    toks = list(c.get_tokens())
    return toks[0].spelling if toks else "?"


def overridden(c):
    """Methods that method cursor c overrides."""
    if not X.overridden:
        return []
    arr, n = ctypes.POINTER(ci.Cursor)(), ctypes.c_uint()
    X.overridden(c, ctypes.byref(arr), ctypes.byref(n))
    out = [ci.Cursor.from_buffer_copy(arr[i]) for i in range(n.value)]  # copy before dispose
    for o in out:
        o._tu = c._tu
    if n.value:
        X.dispose_overridden(arr)
    return out


def specialized_template(c):
    """Template a specialization / instantiated member comes from, or None."""
    return X.spec_template(c) if X.spec_template else None


def skipped_ranges(tu):
    """[(file name, first line, last line)] of preprocessor-skipped blocks."""
    if not X.skipped:
        return []
    lst = X.skipped(tu)
    if not lst:
        return []
    out = []
    arr = ctypes.cast(lst.contents.ranges, ctypes.POINTER(ci.SourceRange))
    for i in range(lst.contents.count):
        r = arr[i]
        if r.start.file:
            out.append((r.start.file.name, r.start.line, r.end.line))
    X.dispose_ranges(lst)
    return out


def evaluate(c):
    """Constant value of an expression cursor as text, or None."""
    if not X.evaluate:
        return None
    res = X.evaluate(c)
    if not res:
        return None
    try:
        kind = X.eval_kind(res)
        if kind == 1:
            return str(X.eval_int(res))
        if kind == 2:
            return repr(X.eval_float(res))
        return None
    finally:
        X.eval_dispose(res)


def qualified_name(c):
    K = ci.CursorKind
    parts, p = [c.spelling], c.semantic_parent
    while p is not None and p.kind != K.TRANSLATION_UNIT:
        if p.kind in (K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL,
                      K.CLASS_TEMPLATE, K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION) and p.spelling:
            parts.append(p.spelling)
        p = p.semantic_parent
    return "::".join(reversed(parts))


# ---------------------------------------------------------------- paths

def match_path(rel, pattern):
    """rel: project-relative path with '/'. pattern: a folder/file prefix
    ('driver/', 'shared/src/proto.c') or an fnmatch glob where '*' also
    matches '/' ('client/**/include/*.h')."""
    pattern = pattern.replace("\\", "/")
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if not any(ch in pattern for ch in "*?["):
        p = pattern.rstrip("/")
        return rel == p or rel.startswith(p + "/")
    return fnmatch.fnmatchcase(rel, pattern)


class PathFilter:
    """Decides which files are 'project' files and gives their relative path."""

    def __init__(self, root, include=(), exclude=()):
        self.root = os.path.realpath(root)
        self.include, self.exclude = list(include), list(exclude)
        self._cache = {}

    def rel(self, path):
        """Project-relative path ('/' separated) or None if not a project file."""
        if path in self._cache:
            return self._cache[path]
        full = os.path.realpath(path)
        r = None
        if full == self.root or full.startswith(self.root + os.sep):
            cand = os.path.relpath(full, self.root).replace(os.sep, "/")
            if (not self.include or any(match_path(cand, p) for p in self.include)) and \
                    not any(match_path(cand, p) for p in self.exclude):
                r = cand
        self._cache[path] = r
        return r


# ---------------------------------------------------------------- compile db

WRAPPERS = {"ccache", "sccache", "distcc", "icecc"}
DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "-MJ", "--serialize-diagnostics", "-Xclang"}
DROP = {"-c", "-M", "-MM", "-MD", "-MMD", "-MP", "-MG", "-S", "-E", "-pipe", "-w",
        "-fpch-preprocess", "-save-temps"}
SAFE_WITH_VALUE = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros", "-D", "-U",
                   "-x", "--sysroot", "-isysroot", "-target", "--target"}
SAFE_PREFIX = ("-I", "-isystem", "-iquote", "-idirafter", "-D", "-U", "-std=", "--sysroot=",
               "--target=", "-m32", "-m64", "-ffreestanding", "-nostdinc", "-fshort-wchar",
               "-funsigned-char", "-fsigned-char", "-x")


class Entry:
    """One compile_commands.json entry."""

    def __init__(self, file, directory, args, command):
        self.file, self.directory, self.args, self.command = file, directory, args, command

    def key(self):
        return (self.file, tuple(self.args))


def load_compile_db(path):
    if os.path.isdir(path):
        path = os.path.join(path, "compile_commands.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    entries = []
    for e in data:
        directory = os.path.normpath(os.path.join(base, e.get("directory", ".")))
        if "arguments" in e:
            argv = list(e["arguments"])
            command = " ".join(argv)
        else:
            command = e["command"]
            argv = shlex.split(command, posix=(os.name != "nt"))
        file = os.path.normpath(os.path.join(directory, e["file"]))
        entries.append(Entry(file, directory, clean_args(argv, file, directory), command))
    return entries


def clean_args(argv, file, directory):
    """Compiler argv -> arguments for libclang (no compiler, -c, -o, -M*, -W*, input)."""
    argv = list(argv)
    while argv and os.path.basename(argv[0]) in WRAPPERS:
        argv.pop(0)
    out, i = [], 1  # argv[0] is the compiler
    while i < len(argv):
        a = argv[i]
        if a in DROP_WITH_VALUE:
            i += 2
            continue
        if a in DROP or a.startswith(("-W", "-pedantic", "-fdiagnostics-color", "-fcolor-diag",
                                      "-MF", "-MT", "-MQ")):
            i += 1
            continue
        if not a.startswith("-") and os.path.normpath(os.path.join(directory, a)) == file:
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def safe_args(args):
    """Only include paths / defines / language flags - fallback for gcc-only flags."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in SAFE_WITH_VALUE and i + 1 < len(args):
            out += [a, args[i + 1]]
            i += 2
            continue
        if a.startswith(SAFE_PREFIX):
            out.append(a)
        i += 1
    return out


_builtin_cache = {}


def builtin_include_args(compiler, resource_dir=None):
    """libclang from pip has no clang builtin headers (stddef.h, stdbool.h...).
    Use --resource-dir, else an installed clang's, else the compiler's own."""
    if resource_dir:
        return ["-resource-dir", resource_dir]
    if compiler in _builtin_cache:
        return _builtin_cache[compiler]
    result = []
    if _libclang_has_builtins():
        result = []
    else:
        for cmd in ([compiler, "-print-file-name=include"], ["clang", "-print-resource-dir"],
                    ["gcc", "-print-file-name=include"]):
            if not cmd[0] or not shutil.which(cmd[0]):
                continue
            try:
                outp = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                continue
            if cmd[1] == "-print-resource-dir":
                if os.path.isfile(os.path.join(outp, "include", "stddef.h")):
                    result = ["-resource-dir", outp]
                    break
            elif os.path.isfile(os.path.join(outp, "stddef.h")):
                result = ["-isystem", outp]
                break
    _builtin_cache[compiler] = result
    return result


_has_builtins = None


def _libclang_has_builtins():
    global _has_builtins
    if _has_builtins is None:
        tu = ci.Index.create().parse("probe.c", unsaved_files=[("probe.c", "#include <stddef.h>\n")])
        _has_builtins = not any(d.severity >= ci.Diagnostic.Error for d in tu.diagnostics)
    return _has_builtins


# ---------------------------------------------------------------- products / config

class Product:
    def __init__(self, name, entries, sources=(), public_headers=(), entry_points=(),
                 extra_roots=(), tests=False):
        self.name, self.entries = name, entries
        self.sources, self.public_headers = list(sources), list(public_headers)
        self.entry_points, self.extra_roots = list(entry_points), list(extra_roots)
        self.tests = tests  # only adds uses; never the reason code is reported

    def owns(self, rel):
        return not self.sources or any(match_path(rel, p) for p in self.sources)


def add_common_args(ap):
    g = ap.add_argument_group("input")
    g.add_argument("-p", "--compile-db", metavar="PATH",
                   help="compile_commands.json (or its folder)")
    g.add_argument("--config", metavar="JSON",
                   help="multi-product config file (see example_config.json)")
    g.add_argument("--root", metavar="DIR",
                   help="project root; only files below it are reported "
                        "(default: config folder, or current folder)")
    g.add_argument("--include", action="append", default=[], metavar="PATTERN",
                   help="only analyse/report files matching (folder prefix or glob, repeatable)")
    g.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                   help="skip files matching (e.g. tests/ or '*/third_party/*', repeatable)")
    g = ap.add_argument_group("clang")
    g.add_argument("--extra-arg", action="append", default=[], metavar="ARG",
                   help="extra compiler argument, e.g. --extra-arg=--target=aarch64-linux-gnu")
    g.add_argument("--resource-dir", help="clang resource dir with builtin headers")
    g.add_argument("--libclang", help="path to libclang.so/.dll or its folder")
    g.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1,
                   help="parallel parses (default: CPU count)")
    g.add_argument("--show-errors", action="store_true",
                   help="list the first compile errors of each file that had any")
    g.add_argument("-q", "--quiet", action="store_true", help="no progress output")


def load_products(args):
    """-> (root, PathFilter, [Product]) from --config or plain --compile-db."""
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg_dir = os.path.dirname(os.path.abspath(args.config))
        root = args.root or os.path.join(cfg_dir, cfg.get("project_root", "."))
        pf = PathFilter(root, cfg.get("include", []) + args.include,
                        cfg.get("exclude", []) + args.exclude)
        dbs = {}

        def db(path):
            path = os.path.join(cfg_dir, path)
            if path not in dbs:
                dbs[path] = load_compile_db(path)
            return dbs[path]

        products = []
        for p in cfg["products"]:
            spec = p.get("compile_commands") or cfg["compile_commands"]
            entries = [e for path in (spec if isinstance(spec, list) else [spec])
                       for e in db(path)]
            rx = re.compile(p["command_regex"]) if p.get("command_regex") else None
            sel = [e for e in entries if (rel := pf.rel(e.file)) is not None
                   and (not p.get("sources") or any(match_path(rel, s) for s in p["sources"]))
                   and (rx is None or rx.search(e.command))]
            products.append(Product(p["name"], sel, p.get("sources", []),
                                    p.get("public_headers", []), p.get("entry_points", []),
                                    cfg.get("extra_roots", []) + p.get("extra_roots", []),
                                    p.get("tests", False)))
        return pf.root, pf, products
    if not args.compile_db:
        sys.exit("error: give -p <compile_commands.json> or --config <file>")
    root = args.root or os.getcwd()
    pf = PathFilter(root, args.include, args.exclude)
    entries = [e for e in load_compile_db(args.compile_db) if pf.rel(e.file) is not None]
    return pf.root, pf, [Product("all", entries)]


# ---------------------------------------------------------------- parsing

def parse(entry, extra_args=(), resource_dir=None, detailed=False):
    """-> (TranslationUnit or None, info dict with errors / fallback notes)."""
    os.chdir(entry.directory)
    compiler = ""
    m = re.match(r"\s*(\S+)", entry.command)
    if m and os.path.basename(m.group(1)) not in WRAPPERS:
        compiler = m.group(1)
    builtins = builtin_include_args(compiler, resource_dir)
    opts = ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD if detailed else 0
    idx = ci.Index.create()
    info = {"file": entry.file, "fallback": False, "errors": []}
    tu = None
    for attempt, args in enumerate((entry.args, safe_args(entry.args))):
        try:
            tu = idx.parse(entry.file, args=list(args) + builtins + list(extra_args), options=opts)
        except ci.TranslationUnitLoadError:
            tu = None
        bad_arg = tu is not None and any("unknown argument" in d.spelling for d in tu.diagnostics)
        if tu is not None and not bad_arg:
            info["fallback"] = attempt == 1
            break
    if tu is None:
        info["errors"] = ["libclang could not parse this file"]
        return None, info
    info["errors"] = [f"{d.location.file.name if d.location.file else '?'}:{d.location.line}: "
                      f"{d.spelling}" for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    return tu, info


def _init_worker(libclang):
    setup_libclang(libclang)


def run_all(entries, worker, worker_arg, args):
    """Run worker(entry, worker_arg) for every entry, in parallel. Returns the
    results in the same order as entries."""
    n = len(entries)
    results = [None] * n
    if args.jobs <= 1 or n <= 1:
        for i, e in enumerate(entries):
            _progress(args, i + 1, n, e.file)
            results[i] = worker(e, worker_arg)
        return results
    with ProcessPoolExecutor(max_workers=args.jobs, initializer=_init_worker,
                             initargs=(args.libclang,)) as ex:
        futs = {ex.submit(worker, e, worker_arg): i for i, e in enumerate(entries)}
        for done, fut in enumerate(as_completed(futs), 1):
            _progress(args, done, n, entries[futs[fut]].file)
            results[futs[fut]] = fut.result()
    return results


def _progress(args, i, n, file):
    if not args.quiet:
        sys.stderr.write(f"\r[{i}/{n}] {os.path.basename(file)[:60]:<60}")
        if i == n:
            sys.stderr.write("\n")
        sys.stderr.flush()


def report_parse_problems(infos, pf, show):
    bad = [i for i in infos if i["errors"]]
    fb = [i for i in infos if i["fallback"]]
    if fb:
        print(f"note: {len(fb)} file(s) needed the reduced argument set "
              f"(compiler flags libclang doesn't know)", file=sys.stderr)
    if bad:
        print(f"warning: {len(bad)} of {len(infos)} file(s) had compile errors - results for "
              f"those may be incomplete (use --show-errors, --extra-arg, --resource-dir)",
              file=sys.stderr)
        if show:
            for i in bad:
                print(f"  {pf.rel(i['file']) or i['file']}:", file=sys.stderr)
                for e in i["errors"][:5]:
                    print(f"      {e}", file=sys.stderr)


# ---------------------------------------------------------------- output

def print_table(headers, rows, out=sys.stdout):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in [headers] + rows) for i in range(len(headers))]
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    fmt = "| " + " | ".join(f"{{:<{w}}}" for w in widths) + " |"
    print(line, file=out)
    print(fmt.format(*headers), file=out)
    print(line, file=out)
    for r in rows:
        print(fmt.format(*r), file=out)
    print(line, file=out)


def short(text, width):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."
