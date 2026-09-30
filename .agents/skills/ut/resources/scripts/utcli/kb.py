"""Knowledge base: graph, testscan, exemplars, conventions, cards. Generated parts are re-creatable."""
import json, os, re
from .util import sh, script, read, write, norm, RES, words
from .frameworks import FRAMEWORKS

LABELS = [  # regex -> annotation for the exemplar (first match wins)
    (r'extern\s*"C"', 'C header inside extern "C"'), (r'#include\s*[<"](CppUTest|gtest|gmock|unity|cpptest)', 'framework header'),
    (r'#include\s*"mock_', 'CMock generated mock'), (r'#include', 'header of the code under test / helper'),
    (r'TEST_GROUP\s*\(', 'test group: one per source file'), (r'class \w+\s*:\s*public\s+(::)?testing::Test', 'fixture class'),
    (r'\b(setup|SetUp|setUp)\s*\(', 'runs before each test: reset state'), (r'\b(teardown|TearDown|tearDown)\s*\(', 'runs after each test: verify mocks, clean up'),
    (r'mock\(\)\.checkExpectations', 'mock verification'), (r'mock\(\)\.clear', 'mock reset'),
    (r'^\s*(TEST|TEST_F|TEST_P)\s*\(', 'one test = one behaviour: <Function>_<Condition>_<Expected>'), (r'^\s*(static\s+)?void\s+test_', 'one test = one behaviour'),
    (r'mock\(\)\.expect|EXPECT_CALL|_ExpectAndReturn|_Expect\(|_IgnoreAndReturn|\.return_val\s*=', 'arrange: what the dependency must return / receive'),
    (r'\b(LONGS_EQUAL|CHECK|EXPECT_|ASSERT_|TEST_ASSERT|STRCMP_EQUAL|POINTERS_EQUAL|BYTES_EQUAL|DOUBLES_EQUAL|MEMCMP_EQUAL)', 'assert: expected value first'),
    (r'RUN_TEST\s*\(', 'test registration (Unity runner)'), (r'\bmain\s*\(', 'runner'),
]


def kb_dir_for(skill_dir, cid):
    return os.path.join(skill_dir, 'resources', 'kb', cid)


def load_kb(kb_dir):
    p = os.path.join(kb_dir, 'kb.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


def save_kb(kb_dir, kb):
    os.makedirs(kb_dir, exist_ok=True)
    json.dump(kb, open(os.path.join(kb_dir, 'kb.json'), 'w', encoding='utf-8'), indent=1)
    render_kb(kb_dir, kb)


def render_kb(kb_dir, kb):
    L = [f"# Knowledge base: {kb.get('id', '')}", '> Generated sections from kb.json (the ut tool). Hand-written notes: notes.md, modules/<name>.md.',
         f"> Last updated: {kb.get('updated', '')}", '', '## Identity', '| Key | Value |', '|---|---|']
    for k in ('id', 'remote', 'roots', 'last_graph_build'):
        L.append(f"| {k} | {kb.get(k, '')} |")
    L += ['', '## Profile', '| Key | Value |', '|---|---|'] + [f'| {k} | {v} |' for k, v in kb.get('profile', {}).items() if k != 'ci_hints']
    L += ['', '## Commands (verified by running them)', '| Purpose | Command | Verified on |', '|---|---|---|']
    for k, v in kb.get('commands', {}).items():
        L.append(f"| {k} | `{v.get('cmd', '')}` | {v.get('verified', '')} |")
    L += [f"Paths written by build: {', '.join(kb.get('build_paths', []))}", f"Summary line: {kb.get('summary_example', '')}"]
    conv = kb.get('conventions', {})
    L += ['', f"## Conventions  (approved: {conv.get('approved', 'no')})"] + [f'- {x}' for x in conv.get('lines', [])]
    L += ['Exemplars: exemplars/test.md, exemplars/mock.md, exemplars/register.md']
    from .seams import render as render_seams
    L += ['', '## Test seams (decided; use only these; change only on the user\'s explicit request)']
    L += render_seams(kb.get('seams', {})) + ['Catalogue and how-to: resources/test-seams.md']
    L += ['', '## Modules', '| Module | File | Tests | Cards |', '|---|---|---|---|']
    for m in kb.get('modules', []):
        L.append(f"| {m['name']} | {m['file']} | {m.get('tests', '')} | modules/{m['name']}.cards.md |")
    notes = read(os.path.join(kb_dir, 'notes.md'))
    L += ['', '## Build notes and glossary (notes.md)', notes or '(none yet)']
    write(os.path.join(kb_dir, 'kb.md'), '\n'.join(L) + '\n')


def index_dir(kb_dir):
    return os.path.join(kb_dir, 'index')


def scan_paths(prof):
    seen = []
    for p in prof['code_paths'] + prof.get('header_paths', []) + prof['test_paths'] + prof['mock_paths']:
        if p not in seen:
            seen.append(p)
    return seen


def build_graph(kb_dir, root, prof, cdb=None):
    """build the code index (kb/<id>/index/index.json) from the Graphify graph"""
    gd = index_dir(kb_dir)
    cmd = [script('index.sh'), 'build'] + (['--cdb', os.path.join(root, cdb)] if cdb and cdb != 'none' else []) + [gd] + scan_paths(prof)
    rc, out = sh(cmd, cwd=root)
    return rc, out, gd


def make_diagrams(kb_dir, root):
    rc, out = sh([script('index.sh'), 'diagrams', index_dir(kb_dir), os.path.join(kb_dir, 'diagrams')], cwd=root)
    return out.strip().splitlines()[-1] if out.strip() else ''


def testscan(kb_dir, root, prof):
    paths = [os.path.join(root, p) for p in prof['test_paths'] + prof['mock_paths']]
    if not paths:
        return ''
    sh([script('testscan.sh'), kb_dir] + paths, cwd=root)
    return read(os.path.join(kb_dir, 'testscan.md'))


def section(md, title):
    m = re.search(r'^## ' + re.escape(title) + r'.*?$(.*?)(?=^## |\Z)', md, re.M | re.S)
    return m.group(1).strip() if m else ''


def conventions_from_scan(scan, prof):
    """<= 12 fact lines with counts"""
    lines = []
    fw = prof.get('framework', '')
    if fw:
        lines.append(f"Framework: {FRAMEWORKS[fw]['name']} ({prof.get('framework_counts', {}).get(fw, '?')} files); mocks: {prof.get('mock_style') or 'none seen'}")
    fn = section(scan, 'File naming')
    if fn:
        lines.append('Test file names: ' + '; '.join(l.strip() for l in fn.splitlines()[:3]))
    names = section(scan, 'Test-case names')
    m = re.search(r'Name pattern classes.*?\n((?:\s+\d+\s+.*\n?)+)', names, re.S)
    if m:
        lines.append('Test names: ' + '; '.join(l.strip() for l in m.group(1).strip().splitlines()[:2]))
    ex = re.findall(r'^\s+(TEST\S*\(.*\)|void test_\w+)', names, re.M)[:3]
    if ex:
        lines.append('Real examples: ' + ' | '.join(ex))
    asserts = [l.strip() for l in section(scan, 'Assertions').splitlines() if re.match(r'\s*\d+\s+\S', l)][:6]
    if asserts:
        lines.append('Asserts used (count name): ' + ', '.join(asserts))
    mocks = [l.strip() for l in section(scan, 'Mock / stub API').splitlines() if re.match(r'\s*\d+\s+\S', l)][:5]
    if mocks:
        lines.append('Mock API used: ' + ', '.join(mocks))
    fx = section(scan, 'Fixtures and setup')
    for row in fx.splitlines():
        if '|' in row and not row.startswith('| Item') and not row.startswith('|---'):
            cells = [c.strip() for c in row.strip('|').split('|')]
            if len(cells) == 2 and cells[1] not in ('0', '0 / 0'):
                lines.append(f'{cells[0]}: {cells[1]}')
    return lines[:12]


def annotate(text, fw):
    out = []
    for l in text.splitlines():
        note = next((n for p, n in LABELS if re.search(p, l)), '')
        out.append(f'{l:<70} // {note}' if note and len(l) < 70 else l)
    return '\n'.join(out)


def make_exemplars(kb_dir, root, prof, scan):
    cand = re.findall(r'^\s+score \d+\s+(\S+)\s+\(', section(scan, 'Exemplar candidates'), re.M)
    fw = prof.get('framework', '')
    ex_dir = os.path.join(kb_dir, 'exemplars')
    os.makedirs(ex_dir, exist_ok=True)
    if cand:
        f = cand[0]
        lines = read(os.path.join(root, f)).splitlines()
        # cut to <= 80 lines keeping the head and the first 2-3 tests
        cut = lines[:80] if len(lines) > 80 else lines
        write(os.path.join(ex_dir, 'test.md'), f'# Test exemplar: {f}  (approved: no; DRAFT picked by testscan)\n'
              'Copy this shape for every new test. Verbatim from the repo; the right column names each part.\n\n```cpp\n'
              + annotate('\n'.join(cut), fw) + '\n```\n')
    else:
        write(os.path.join(ex_dir, 'test.md'), '# Test exemplar: none yet (greenfield). The pilot creates it.\n')
    mocks = re.findall(r'^\s+(\S+)$', section(scan, 'Mock / stub files'), re.M)
    if mocks:
        f = mocks[0]; lines = read(os.path.join(root, f)).splitlines()[:60]
        write(os.path.join(ex_dir, 'mock.md'), f'# Mock exemplar: {f}\n\n```cpp\n' + annotate('\n'.join(lines), fw) + '\n```\n')
    else:
        write(os.path.join(ex_dir, 'mock.md'), '# Mock exemplar: none yet\n')
    # registration: where an existing test file name appears in build files
    reg = []
    if cand:
        base = os.path.basename(cand[0])
        for bf in ('CMakeLists.txt', 'Makefile', 'project.yml', 'meson.build', '*.cmake', '*.mk'):
            rc, out = sh(['grep', '-rn', '--include=' + bf, '--exclude-dir=build*', '--exclude-dir=CMakeFiles', '--exclude-dir=.git', '--exclude-dir=cmake-build*', base, root])
            reg += [norm(os.path.relpath(l.split(':', 1)[0], root)) + ':' + l.split(':', 1)[1] for l in out.splitlines() if ':' in l and '/build' not in l.split(':', 1)[0]][:6]
    write(os.path.join(ex_dir, 'register.md'), '# How a test file is registered in the build\n' +
          ('\n'.join(f'- {r}' for r in reg) if reg else '- not found by grep: check the build files (Ceedling finds test_*.c automatically)') + '\n')
    return cand[0] if cand else ''


def module_cards(kb_dir, root, prof, gd, files):
    mods = []
    os.makedirs(os.path.join(kb_dir, 'modules'), exist_ok=True)
    ir = index_root(gd) or root                      # all cards in one call (paths relative to the index root)
    sh([script('index.sh'), 'kb-cards', gd, kb_dir] + [norm(os.path.relpath(os.path.join(root, f), ir)) for f in files], cwd=root)
    for f in files:
        name = os.path.basename(f)
        card = read(os.path.join(kb_dir, 'modules', f'{name}.cards.md'))
        notes = os.path.join(kb_dir, 'modules', f'{name}.md')
        if not os.path.exists(notes):
            write(notes, f'# Module: {name}\nFile: {f}\nPurpose: (fill in)\n\n## Facts\n-\n\n## How to test this module\n-\n\n## Learnings\n-\n')
        tlines = re.findall(r'^Existing tests calling it directly: (.*)$', card, re.M)
        tfiles = sorted({m.group(1) for l in tlines for m in re.finditer(r'\(([^()\s]+\.(?:cpp|cxx|cc|c)\b):L\d+\)', l)})
        mods.append({'name': name, 'file': f, 'tests': ', '.join(tfiles) or 'none', 'test_files': tfiles})
    return mods


def index_root(gd):
    import json as _json
    try:
        return _json.load(open(os.path.join(gd, 'index.json'), encoding='utf-8'))['meta']['root']
    except (OSError, ValueError, KeyError):
        return ''


def test_name_pattern(kb_dir, prof, fw):
    """file name pattern from testscan (most common class), else the framework default"""
    scan = read(os.path.join(kb_dir, 'testscan.md'))
    m = re.search(r'^\s*\d+\s+(\S*<name>\S*)', section(scan, 'File naming'), re.M)
    exts = re.findall(r'\.(cpp|cc|c)\b', section(scan, 'Exemplar candidates')) or ['cpp' if FRAMEWORKS[fw]['lang'] == 'cpp' else 'c']
    if m:
        return m.group(1).replace('<name>', '{module}').replace('<ext>', max(set(exts), key=exts.count))
    return FRAMEWORKS[fw]['file_pattern']


def scope_files(root, prof):
    files = []
    for p in prof['code_paths']:
        for d, dirs, fs in os.walk(os.path.join(root, p)):
            dirs[:] = [x for x in dirs if not x.startswith('.')]
            files += [norm(os.path.relpath(os.path.join(d, x), root)) for x in fs if x.endswith(('.c', '.cc', '.cpp', '.cxx'))]
    return sorted(files)
