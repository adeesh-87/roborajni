"""What the tool must know per test framework: how to detect it, read its summary, run one test."""
import re

FRAMEWORKS = {
    'cpputest': {
        'name': 'CppUTest', 'tool_md': 'tools/cpputest.md', 'errors_md': 'tools/errors/cpputest.md',
        'detect': r'CppUTest/TestHarness\.h|^\s*TEST_GROUP\s*\(',
        'summary': re.compile(r'^(OK|Errors) \((?:(\d+) failures?, )?(\d+) tests?, (\d+) ran', re.M),
        'summary_fields': lambda m: {'passed': int(m.group(4)) - int(m.group(2) or 0), 'failed': int(m.group(2) or 0), 'total': int(m.group(3))},
        'failure_line': r'^\S+:\d+: error: Failure in TEST\(',
        'filter': lambda binary, group, test: f'{binary} -sg {group}' + (f' -sn {test}' if test else ''),
        'test_regex': r'^\s*TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', 'group_regex': r'^\s*TEST_GROUP\s*\(\s*(\w+)',
        'file_pattern': '{module}_test.cpp', 'lang': 'cpp',
    },
    'gtest': {
        'name': 'GoogleTest', 'tool_md': 'tools/gtest-gmock.md', 'errors_md': 'tools/errors/gtest-gmock.md',
        'detect': r'gtest/gtest\.h',
        'summary': re.compile(r'^\[  PASSED  \] (\d+) tests?\.(?:.*?^\[  FAILED  \] (\d+) tests?, listed below)?', re.M | re.S),
        'summary_fields': lambda m: {'passed': int(m.group(1)), 'failed': int(m.group(2) or 0), 'total': int(m.group(1)) + int(m.group(2) or 0)},
        'failure_line': r'^\[  FAILED  \] \w+\.\w+',
        'filter': lambda binary, group, test: f"{binary} --gtest_filter='{group}.{test or '*'}'",
        'test_regex': r'^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)', 'group_regex': r'class\s+(\w+)\s*:\s*public\s+(?:::)?testing::Test',
        'file_pattern': '{module}_test.cpp', 'lang': 'cpp',
    },
    'unity': {
        'name': 'Unity', 'tool_md': 'tools/unity-cmock.md', 'errors_md': 'tools/errors/unity-cmock.md',
        'detect': r'[<"]unity\.h[>"]|RUN_TEST\s*\(',
        'summary': re.compile(r'^(\d+) Tests (\d+) Failures (\d+) Ignored', re.M),
        'summary_fields': lambda m: {'passed': int(m.group(1)) - int(m.group(2)) - int(m.group(3)), 'failed': int(m.group(2)), 'total': int(m.group(1))},
        'failure_line': r':\d+:\w+:FAIL',
        'filter': lambda binary, group, test: (f'ceedling test:{group}' if binary.startswith('ceedling') else binary),
        'test_regex': r'^\s*(?:static\s+)?void\s+(test_\w+|\w+_should_\w+)\s*\(', 'group_regex': r'$^',
        'file_pattern': 'test_{module}.c', 'lang': 'c',
    },
    'parasoft': {
        'name': 'Parasoft C/C++test', 'tool_md': 'tools/parasoft-cpptest.md', 'errors_md': 'tools/errors/parasoft-cpptest.md',
        'detect': r'CPPTEST_TEST|cpptest\.h',
        'summary': re.compile(r'$^'), 'summary_fields': lambda m: {}, 'failure_line': r'$^',
        'filter': lambda binary, group, test: binary,
        'test_regex': r'CPPTEST_TEST\s*\(\s*(\w+)\s*\)', 'group_regex': r'CPPTEST_TEST_SUITE\s*\(\s*(\w+)',
        'file_pattern': 'TestSuite_{module}.cpp', 'lang': 'cpp',
    },
}
CAT_TO_TYPE = {'A': 'remove-tests', 'B': 'update-tests', 'C': 'fix-mocks', 'D': 'add-tests', 'E': 'fix-build',
               'F': 'fix-run', 'G': 'raise-coverage', 'H': 'update-tests'}
COVERAGE_TOOLS = {'ctc': ('Testwell CTC++', 'tools/ctc.md', r'ctcwrap|ctc -i|ctcpost'),
                  'gcov': ('gcov/lcov/gcovr', 'tools/gcov-lcov.md', r'--coverage|-fprofile-arcs|gcovr|lcov'),
                  'parasoft': ('Parasoft coverage', 'tools/parasoft-cpptest.md', r'cpptestcc|cpptestcov')}


CTEST = re.compile(r'(\d+)% tests passed, (\d+) tests failed out of (\d+)')


def parse_summary(fw, text):
    m = CTEST.search(text)                       # ctest wraps any framework
    if m:
        return {'passed': int(m.group(3)) - int(m.group(2)), 'failed': int(m.group(2)), 'total': int(m.group(3))}
    f = FRAMEWORKS.get(fw)
    if not f:
        return None
    m = f['summary'].search(text)
    if not m:
        return None
    return f['summary_fields'](m)


def failures(fw, text, limit=10):
    return re.findall(FRAMEWORKS[fw]['failure_line'] + r'.*', text, re.M)[:limit]


def first_errors(text, limit=5):
    pat = re.compile(r'(error|Error)[: ]|undefined reference|multiple definition|No such file|cannot find -l|fatal error')
    return [l.strip()[:220] for l in text.splitlines() if pat.search(l)][:limit]
