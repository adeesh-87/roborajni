"""Test seams (resources/test-seams.md): detect what the project already uses, record ONE decision per need in the KB,
and give the executor exactly that decision. A decision changes only when the user sets it explicitly."""
import os, re
from .util import sh, read, norm
from .state import now

NEEDS = ('access', 'replace', 'per-test', 'hardware', 'state')
CATALOG = {   # id: (need, name, production change, how - one line for the prompt)
    'A1': ('access', 'test-through-public', False, 'reach static/private code only through its public callers (card Callers, index.sh refs)'),
    'A2': ('access', 'include-source', False, 'the test file #includes the file under test FIRST (before CppUTest headers); that source is not linked into the same binary; C sources go through a C shim file'),
    'A3': ('access', 'static-macro', True, 'production writes STATIC/PRIVATE; tests build with -DUNIT_TEST so they are not static; declare the function in the test'),
    'A4': ('access', 'private-public-define', False, '#define private public / #define protected public after all system headers, before the class header; #undef after'),
    'A5': ('access', 'friend-test', True, 'the class declares friend class <Class>Test; the test group uses that access'),
    'A6': ('access', 'access-template', False, 'explicit-instantiation access helper (Rob<Tag, &Class::member>) per private member, see resources/test-seams.md A6'),
    'A7': ('access', 'test-subclass', False, 'class TestableX : public X { public: using X::method; } for protected members'),
    'B1': ('replace', 'link-seam', False, 'the test binary links a fake .c/.cpp with the same functions instead of the real file'),
    'B2': ('replace', 'interface-injection', False, 'pass a CppUMock/gMock fake of the interface to the code under test'),
    'B3': ('replace', 'function-pointer-seam', False, 'swap the function pointer / ops table with UT_PTR_SET(ptr, fake) (restored after each test)'),
    'B4': ('replace', 'weak-symbol', True, 'the real function is weak; a strong definition in the test binary replaces it'),
    'B5': ('replace', 'macro-rename', False, 'with include-source: #define fn fake_fn before #include of the file under test'),
    'B6': ('replace', 'header-seam', False, 'a fake header with the same name earlier on the test include path'),
    'C1': ('per-test', 'ut-ptr-set', False, 'UT_PTR_SET(ptr, fake) only in the tests that mock; others see the real function'),
    'C2': ('per-test', 'linker-wrap', False, 'link with -Wl,--wrap=fn; __wrap_fn forwards to __real_fn unless the test set its mock flag (reset in teardown); same-object calls and statics are not wrapped'),
    'C3': ('per-test', 'mock-with-passthrough', False, 'the fake forwards to the real function (__real_fn or real_fn) unless the test expects calls'),
    'C4': ('per-test', 'rename-copy', False, 'a renamed copy of the real object (objcopy --redefine-sym fn=real_fn); the fake forwards to real_fn when not mocked'),
    'C5': ('per-test', 'separate-binaries', False, 'tests needing the fake and tests needing the real function are in different executables'),
    'C6': ('per-test', 'gmock-delegate', False, 'ON_CALL(mock, f).WillByDefault(delegate to a real object)'),
    'C7': ('per-test', 'ld-preload', False, 'define the libc function in the test binary, reach the real one with dlsym(RTLD_NEXT, name)'),
    'D1': ('hardware', 'register-header-seam', False, 'a fake header maps register macros to variables the test sets and checks'),
    'D2': ('hardware', 'overridable-base-address', True, 'register base addresses under #ifndef; tests define them to point at RAM'),
    'D3': ('hardware', 'hal-link-seam', False, 'vendor HAL functions replaced at link time by fakes'),
    'E1': ('state', 'reset-via-include', False, 'with include-source, setup() resets the file-static variables directly'),
    'E2': ('state', 'test-reset-function', True, 'production has <module>_reset_for_test() under UNIT_TEST; setup() calls it'),
    'E3': ('state', 'fork-per-test', False, 'run the tests with CppUTest -p (each test in its own process)'),
    'E4': ('state', 're-init', False, 'setup() calls the module public init function'),
}
DEFAULTS = {'access': 'A1', 'replace': 'B1', 'per-test': 'C5', 'hardware': 'D1', 'state': 'E4'}
# id: (where: tests|code|build|run, regex) - evidence that the project already uses it
EVIDENCE = [
    ('A2', 'tests', r'^\s*#\s*include\s*["<][^">]*\.(c|cc|cpp|cxx)[">]'),
    ('A4', 'tests', r'#\s*define\s+(private|protected)\s+public'),
    ('A4', 'build', r'-D(private|protected)=public'),
    ('A3', 'code', r'#\s*define\s+(STATIC|PRIVATE)\b'),
    ('A5', 'code', r'friend\s+class\s+\w*Test\b|FRIEND_TEST\s*\('),
    ('A6', 'tests', r'template\s+struct\s+\w+\s*<\s*\w+\s*,\s*&'),
    ('C2', 'build', r'--wrap[=,]'),
    ('C2', 'tests', r'\b__wrap_\w+\s*\(|\b__real_\w+\s*\('),
    ('C4', 'build', r'--redefine-sym|--prefix-symbols'),
    ('C1', 'tests', r'\bUT_PTR_SET\s*\('),
    ('B4', 'code', r'__attribute__\s*\(\(\s*weak|\bWEAK\s+\w+\s*\('),
]
SRC_INC = ['--include=*.c', '--include=*.cc', '--include=*.cpp', '--include=*.cxx', '--include=*.h', '--include=*.hpp']
BUILD_INC = ['--include=CMakeLists.txt', '--include=*.cmake', '--include=*akefile*', '--include=*.mk', '--include=project.yml']


def detect(root, prof):
    """{id: 'file:line'} for every technique the project already uses (first evidence)"""
    where = {'tests': [os.path.join(root, p) for p in prof.get('test_paths', []) + prof.get('mock_paths', [])],
             'code': [os.path.join(root, p) for p in prof.get('code_paths', []) + prof.get('header_paths', [])],
             'build': [root]}
    found = {}
    for sid, kind, rx in EVIDENCE:
        if sid in found or not where[kind]:
            continue
        inc = BUILD_INC if kind == 'build' else SRC_INC
        rc, out = sh(['grep', '-rnE', '-m', '1', '-e', rx] + inc + ['--exclude-dir=build*', '--exclude-dir=.git', '--exclude-dir=_deps']
                     + [p for p in where[kind] if os.path.exists(p)])
        m = next((re.match(r'^(.+?):(\d+):', l) for l in out.splitlines() if re.match(r'^(.+?):(\d+):', l)), None)
        if m and os.path.exists(m.group(1)):
            found[sid] = f'{norm(os.path.relpath(m.group(1), root))}:{m.group(2)}'
    if re.search(r'(^|\s)-p(\s|$)', prof.get('run_cmd', '')):
        found['E3'] = 'run command uses -p'
    return found


def merge_detected(kb, found):
    """detected techniques become the decision for their need, unless a need is already decided"""
    seams = kb.setdefault('seams', {})
    for sid, ev in found.items():
        need = CATALOG[sid][0]
        if need not in seams:
            seams[need] = {'choice': sid, 'by': 'detected in the existing tests', 'date': now(), 'evidence': ev}
        elif seams[need]['choice'] != sid and sid not in seams[need].get('also_seen', ''):
            # the project already mixes techniques: new tests keep the recorded one; the user may change it
            seams[need]['also_seen'] = (seams[need].get('also_seen', '') + f' {sid} ({ev})').strip()
    return seams


def set_choice(kb, need, sid, by='user'):
    if need not in NEEDS or sid not in CATALOG or CATALOG[sid][0] != need:
        raise ValueError(f'{sid} is not a technique for need {need} (see resources/test-seams.md)')
    old = kb.setdefault('seams', {}).get(need)
    kb['seams'][need] = {'choice': sid, 'by': by, 'date': now(), 'evidence': '',
                         'previous': f"{old['choice']} ({old['date']})" if old and old['choice'] != sid else (old or {}).get('previous', '')}
    return kb['seams'][need]


def options(need, production_ok):
    return [sid for sid, (n, _, prod, _) in CATALOG.items() if n == need and (production_ok or not prod)]


def render(seams):
    """lines for kb.md and for the executor prompt"""
    out = []
    for need in NEEDS:
        d = seams.get(need)
        if d:
            sid = d['choice']
            out.append(f"- {need}: {sid} {CATALOG[sid][1]} - {CATALOG[sid][3]} (decided by {d['by']}, {d['date']}"
                       f"{', evidence ' + d['evidence'] if d.get('evidence') else ''})"
                       + (f"; also in old tests: {d['also_seen']} - do NOT use those for new tests" if d.get('also_seen') else ''))
        else:
            out.append(f'- {need}: not decided')
    return out


def needs_access(cards_md, funcs, lines=None):
    """True when a task's function is static / private / protected (its card header says so)"""
    from .plan import card_block
    for f in funcs:
        m = card_block(cards_md, f, (lines or {}).get(f))
        if m and re.search(r'\bstatic\b|\bprivate\b|\bprotected\b', m.group(0).splitlines()[0]):
            return True
    return False
