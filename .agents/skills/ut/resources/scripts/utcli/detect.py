"""Phase 1 detection: everything a file can tell us, no questions."""
import os, re
from .util import sh, script, read, norm
from .frameworks import FRAMEWORKS, COVERAGE_TOOLS

TEST_DIR = re.compile(r'(^|/)(test|tests|unittest|unittests|ut|utest|mocks?|stubs?|fakes?)$', re.I)
VENDOR = re.compile(r'(^|/)(unity|cmock|cpputest|googletest|gtest|gmock|fff|catch2|doctest|ceedling|vendor|third[_-]?party|external|build[^/]*)(/|$)', re.I)


def repo_root(path):
    rc, out = sh(['git', '-C', path, 'rev-parse', '--show-toplevel'])
    return out.strip() if rc == 0 else os.path.abspath(path)


def kb_id(root):
    rc, out = sh([script('kb-id.sh'), root])
    return dict(l.split('=', 1) for l in out.splitlines() if '=' in l)


HEADER_DIR = re.compile(r'(^|/)(include|inc|api|public|interface|interfaces)$', re.I)


def find_dirs(root):
    tests, code, headers = [], [], []
    for d, dirs, files in os.walk(root):
        rel = norm(os.path.relpath(d, root))
        dirs[:] = [x for x in dirs if not x.startswith('.') and not VENDOR.search(norm(os.path.join(rel, x)))]
        if rel == '.':
            continue
        if TEST_DIR.search(rel):
            tests.append(rel); dirs[:] = []; continue
        if any(f.endswith(('.c', '.cpp', '.cc', '.cxx')) for f in files) and rel.count('/') < 3:
            code.append(rel)
        if HEADER_DIR.search(rel) and rel.count('/') < 3:
            headers.append(rel); dirs[:] = []           # public headers: interfaces the code under test calls
    # keep only top-most code dirs
    code = [c for c in code if not any(c.startswith(o + '/') for o in code if o != c)]
    headers = [h for h in headers if not any(h.startswith(c + '/') or h == c for c in code)]
    find_dirs.headers = headers
    return tests, code


def detect_framework(root, test_dirs):
    counts = {}
    for k, f in FRAMEWORKS.items():
        rc, out = sh(['grep', '-rlE', f['detect'], '--include=*.c', '--include=*.cc', '--include=*.cpp', '--include=*.h', '--include=*.hpp']
                     + [os.path.join(root, t) for t in test_dirs] if test_dirs else ['true'])
        counts[k] = len([l for l in out.split() if not VENDOR.search(norm(l))]) if test_dirs else 0
    best = max(counts, key=counts.get) if counts and max(counts.values()) > 0 else ''
    mock = ''
    if test_dirs:
        for pat, name in (('mock\\(\\)\\.', 'CppUMock'), ('EXPECT_CALL|MOCK_METHOD', 'gMock'), ('FAKE_(VALUE|VOID)_FUNC', 'FFF'),
                          ('_ExpectAndReturn|_Expect\\(', 'CMock'), ('CppTest_Stub_', 'Parasoft stubs')):
            rc, out = sh(['grep', '-rlE', pat, '--include=*.c', '--include=*.cc', '--include=*.cpp'] + [os.path.join(root, t) for t in test_dirs])
            n = len([l for l in out.split() if not VENDOR.search(norm(l))])
            if n:
                mock = mock or name
    return best, counts, mock


def detect_build(root):
    found = [f for f in ('CMakeLists.txt', 'Makefile', 'makefile', 'GNUmakefile', 'project.yml', 'meson.build', 'SConstruct') if os.path.exists(os.path.join(root, f))]
    system = 'ceedling' if 'project.yml' in found else 'cmake' if 'CMakeLists.txt' in found else 'make' if any('akefile' in f for f in found) else ''
    ci = []
    for f in ('.gitlab-ci.yml', 'Jenkinsfile', 'azure-pipelines.yml', 'Makefile', 'CMakePresets.json'):
        p = os.path.join(root, f)
        if os.path.exists(p):
            for l in read(p).splitlines():
                if re.search(r'ctest|make .*test|ceedling|cpptestcli|RunAllTests|gtest|cmake --build|\bbuild\.sh|run_tests', l):
                    ci.append(f'{f}: {l.strip()[:120]}')
    wf = os.path.join(root, '.github', 'workflows')
    if os.path.isdir(wf):
        for f in os.listdir(wf):
            for l in read(os.path.join(wf, f)).splitlines():
                if re.search(r'ctest|make .*test|ceedling|cmake --build|run:.*test', l):
                    ci.append(f'.github/workflows/{f}: {l.strip()[:120]}')
    rc, out = sh(['find', root, '-name', 'compile_commands.json', '-not', '-path', '*/.git/*'])
    cdb = [norm(os.path.relpath(x, root)) for x in out.split()][:3]
    cov = ''
    for k, (name, md, pat) in COVERAGE_TOOLS.items():
        rc, out = sh(['grep', '-rlE', pat, '--include=*akefile*', '--include=CMakeLists.txt', '--include=*.cmake', '--include=*.yml', '--include=*.sh', root])
        if out.strip():
            cov = name; break
    return system, ci[:8], cdb, cov


def guess_commands(system, cdb):
    if system == 'cmake':
        b = 'build' if not cdb else os.path.dirname(cdb[0]) or 'build'
        return {'build': f'cmake -S . -B {b} -DCMAKE_EXPORT_COMPILE_COMMANDS=ON && cmake --build {b} -j',
                'run': f'ctest --test-dir {b} --output-on-failure', 'clean': f'cmake --build {b} --target clean'}
    if system == 'ceedling':
        return {'build': 'ceedling test:all', 'run': 'ceedling test:all', 'clean': 'ceedling clobber'}
    if system == 'make':
        return {'build': 'make', 'run': 'make test', 'clean': 'make clean'}
    return {'build': '?', 'run': '?', 'clean': ''}


def profile(root):
    tests, code = find_dirs(root)
    fw, counts, mock = detect_framework(root, tests)
    system, ci, cdb, cov = detect_build(root)
    mock_dirs = [t for t in tests if re.search(r'mock|stub|fake', t, re.I)]
    test_dirs = [t for t in tests if t not in mock_dirs]
    cmds = guess_commands(system, cdb)
    return {'code_paths': code, 'header_paths': getattr(find_dirs, 'headers', []), 'test_paths': test_dirs, 'mock_paths': mock_dirs,
            'framework': fw, 'diagrams': 'auto', 'prompt_diagrams': 'off',
            'framework_counts': {k: v for k, v in counts.items() if v}, 'mock_style': mock, 'build_system': system,
            'build_cmd': cmds['build'], 'run_cmd': cmds['run'], 'clean_cmd': cmds['clean'], 'ci_hints': ci,
            'compile_db': cdb[0] if cdb else 'none', 'coverage_tool': cov or 'none', 'env_setup': 'none'}
