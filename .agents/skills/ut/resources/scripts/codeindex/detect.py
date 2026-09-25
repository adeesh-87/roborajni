"""detect ROOT [--cdb compile_commands.json] [--json]: which index backends work on THIS machine for THIS code, and
which one to use. Checks are real (load libclang and parse one unit; compile a probe with the build's compiler)."""
import json, os, re, shlex, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

BACKENDS = {
    'clang': 'compiler AST (libclang) with the build flags: exact overloads/templates/virtual calls/macros, lambdas, callbacks',
    'gcc': "the build's own GCC (also cross gcc >= 10) writes the call graph; branches from tree-sitter",
    'graphify': 'tree-sitter graph (bundled Graphify) + fixes: works without a compile DB and on code that does not compile',
    'codemap': 'bash + grep: no Python; names only, rough decisions (last resort)',
}


def first_tu(cdb):
    try:
        ents = json.load(open(cdb, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    for e in ents:
        if os.path.splitext(e['file'])[1].lower() in ('.c', '.cc', '.cpp', '.cxx'):
            return e
    return None


def check_clang(cdb):
    try:
        from .clangload import load
        ci = load()
    except ImportError as e:
        return False, str(e)[:160]
    if not cdb:
        return False, 'needs compile_commands.json'
    e = first_tu(cdb)
    if not e:
        return False, 'compile DB has no C/C++ source'
    from .be_clang import args_of
    src = os.path.realpath(os.path.join(e['directory'], e['file']))
    try:
        cwd = os.getcwd()
        os.chdir(e['directory'])
        tu = ci.Index.create().parse(src, args=args_of(e, src))
        os.chdir(cwd)
    except Exception as ex:  # noqa: BLE001
        return False, f'libclang could not parse {os.path.basename(src)}: {ex}'
    errs = [d for d in tu.diagnostics if d.severity >= 3]
    if errs:
        return False, f'{len(errs)} parse errors in {os.path.basename(src)} (e.g. {errs[0].spelling[:80]}): vendor compiler extensions? set UT_CLANG_EXTRA'
    return True, f'libclang parsed {os.path.basename(src)} cleanly'


def check_gcc(cdb):
    if not cdb:
        return False, 'needs compile_commands.json'
    e = first_tu(cdb)
    if not e:
        return False, 'compile DB has no C/C++ source'
    args = e.get('arguments') or shlex.split(e['command'])
    while args and os.path.basename(args[0]) in ('ccache', 'sccache'):
        args = args[1:]
    comp = args[0]
    exe = comp if os.path.isabs(comp) else shutil.which(comp)
    if not exe:
        return False, f'compiler {comp} not found'
    with tempfile.TemporaryDirectory() as t:
        src = os.path.join(t, 'p.c')
        open(src, 'w').write('int g(int);\nint f(int x) { return g(x); }\n')
        r = subprocess.run([exe, '-x', 'c', '-O0', '-fcallgraph-info', '-c', src, '-o', os.path.join(t, 'p.o')],
                           capture_output=True, text=True, cwd=t)
        if r.returncode != 0 or not os.path.exists(os.path.join(t, 'p.ci')):
            return False, f"{os.path.basename(comp)} does not support -fcallgraph-info (GCC >= 10 needed): {(r.stderr.strip().splitlines() or [''])[-1][:80]}"
    return True, f'{os.path.basename(comp)} writes call graphs'


def check_graphify():
    vpy = os.path.join(HERE, '..', '..', 'vendor', 'graphify', '.venv', 'bin', 'python')
    if os.path.exists(vpy):
        r = subprocess.run([vpy, '-c', 'import graphify, tree_sitter_cpp'], capture_output=True)
        return (r.returncode == 0), ('skill venv ready' if r.returncode == 0 else 'venv broken: run index.sh setup')
    for py in ('python3', 'python'):
        if shutil.which(py):
            r = subprocess.run([py, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'])
            if r.returncode == 0:
                return True, 'Python 3.10+ found; index.sh setup creates the venv'
    return False, 'no Python 3.10+'


def detect(root, cdb=None):
    res = {}
    res['clang'] = check_clang(cdb)
    res['gcc'] = check_gcc(cdb)
    res['graphify'] = check_graphify()
    res['codemap'] = (True, 'always available')
    from .lsp import find_clangd
    cd = find_clangd()
    rec = next(b for b in ('clang', 'gcc', 'graphify', 'codemap') if res[b][0])
    why = {'clang': 'most accurate and it parses your code cleanly',
           'gcc': 'libclang is not usable here, but your own compiler gives exact call edges',
           'graphify': 'no compile DB (or neither compiler route works); tolerant parser',
           'codemap': 'no Python available'}[rec]
    return {'backends': {k: {'ok': v[0], 'note': v[1], 'what': BACKENDS[k]} for k, v in res.items()},
            'recommended': rec, 'why': why, 'clangd': cd or '', 'viable': [b for b in BACKENDS if res[b][0]]}


def main(a):
    root = a[0] if a else '.'
    cdb = a[a.index('--cdb') + 1] if '--cdb' in a else None
    d = detect(os.path.realpath(root), cdb)
    if '--json' in a:
        print(json.dumps(d, indent=1)); return
    print('| Backend | Works here | Note | What it is |\n|---|---|---|---|')
    for k, v in d['backends'].items():
        print(f"| {k} | {'yes' if v['ok'] else 'no'} | {v['note']} | {v['what']} |")
    print(f"\nRecommended: {d['recommended']} ({d['why']}).")
    print(f"clangd for interactive queries (index.sh lsp): {d['clangd'] or 'not found (index.sh setup clangd)'}")
