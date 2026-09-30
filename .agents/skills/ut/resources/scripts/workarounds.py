#!/usr/bin/env python3
"""workarounds.py REPO --code DIR... --tests DIR... [--build FILE_OR_DIR...] [--since 2y] : the test workarounds and
design choices this project already made, found in the code, the test build and the git history.

Prints Markdown for SKILL-MAKER.md step 8b: one line per category found, with a count and up to 3 file:line examples,
then the comments and the commits that explain them. Each category names the learning (resources/learnings.md) it
belongs to. The agent turns every line into a row of KB_DIR/workarounds.md (what, why, rule for new tests, the error it
prevents); nothing here is a decision by itself."""
import os, re, subprocess, sys

EXT = ('.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.hh', '.inc')
BUILD = ('CMakeLists.txt', 'Makefile', 'makefile', 'GNUmakefile', 'project.yml', 'meson.build')
BUILD_EXT = ('.cmake', '.mk', '.make', '.yml', '.yaml', '.ini', '.sh', '.bat', '.py')

# (category, where: code|tests|build, regex, meaning, learning IDs)
PATTERNS = [
    ('leak detection off', 'tests+build', r'turnOffNewDeleteOverloads|saveAndDisableNewDeleteOverloads|CPPUTEST_USE_MEM_LEAK_DETECTION\s*[:=]?\s*(?:N\b|0|OFF)|MEM_LEAK_DETECTION_DISABLED|IGNORE_ALL_LEAKS_IN_TEST|EXPECT_N_LEAKS',
     'CppUTest leak detection is disabled or bypassed somewhere: find out why (a leak in the code under test, a library, mocks)', 'L07 L11'),
    ('forced include', 'build', r'(?:^|\s)-include\s+\S+|/FI\S+|MemoryLeakDetector(?:Malloc|New)Macros',
     'a header is force-included into every test source: it changes what every file sees (leak macros, test hooks)', 'L11'),
    ('include source file', 'tests', r'#\s*include\s*[<"][^">]+\.(?:c|cc|cpp|cxx)[">]', 'tests include production .c/.cpp files (seam A2)', 'L13'),
    ('private -> public', 'tests+build', r'#\s*define\s+(?:private|protected)\s+public|-D\s*private=public|-fno-access-control', 'access to private members by redefining the keyword (seam A4)', 'L13'),
    ('friend test', 'code', r'friend\s+class\s+\w*Test\w*|FRIEND_TEST|TEST_FRIEND', 'production classes befriend test classes (seam A5)', 'L13'),
    ('test hooks in production', 'code', r'#\s*if(?:n?def)?\s*(?:\(?\s*defined\s*\(?\s*)?\(?\s*(?:UNIT_TEST|UNITTEST|UT_BUILD|UNIT_TESTING|TESTING|TEST_BUILD|CPPUTEST)\b|#\s*define\s+(?:STATIC|PRIVATE)\b',
     'production code changes under a test macro (seams A3, E2, D2): a test build compiles different code than the product', 'L13 L14'),
    ('weak symbols', 'code+tests', r'__attribute__\s*\(\(\s*weak|#\s*pragma\s+weak|\b__weak\b|\bWEAK\s+\w', 'weak definitions replaced by strong ones in tests (seam B4)', 'L13'),
    ('linker wrap', 'build+tests', r'--wrap[=,]\w+|__wrap_\w+|__real_\w+', 'the shared --wrap stubs (seam C2): run wrapcheck.py, step 6b', 'L15 L16 L17 L18 L19 L20 L21'),
    ('loosened link', 'build', r'--allow-multiple-definition|-z\s*muldefs|--unresolved-symbols|--defsym|--gc-sections|/FORCE', 'the test link tolerates duplicates or missing symbols: a real error can pass silently', 'L32'),
    ('function pointer swap', 'tests', r'UT_PTR_SET', 'function pointers swapped per test (seams B3, C1)', 'L12'),
    ('strict / lenient mocks', 'tests', r'strictOrder|ignoreOtherCalls|expectedCallsLeft|mock\(\)\s*\.\s*disable|crashOnFailure|ignoreOtherParameters',
     'how strict the mocks are: order, extra calls, parameters', 'L09 L10 L15 L16'),
    ('mock teardown', 'tests', r'mock\(\)\s*\.\s*(?:clear|checkExpectations|removeAllComparatorsAndCopiers)|mock\(\)\.clear', 'what every teardown must do', 'L07'),
    ('comparators', 'tests', r'installComparator|installCopier|withParameterOfType|withOutputParameterOfType', 'custom parameter types in mocks', 'L08'),
    ('ignored tests', 'tests', r'\bIGNORE_TEST\s*\(|\bDISABLED_\w+|TEST_IGNORE\s*\(', 'tests switched off: each is a known problem, ask why', 'L33'),
    ('compiler keywords neutralised', 'tests+build', r'#\s*define\s+(?:__IO|__I|__O|__STATIC_INLINE|__INLINE|__weak|__packed|__ASM|__asm|__irq|__interrupt|__root|__no_init|__ramfunc|__near|__far|__attribute__|__NOP|__DSB|__ISB|__WFI|__disable_irq|__enable_irq)\b|-D\s*(?:__IO|__packed|__irq|__interrupt|__root|__no_init|__ramfunc)=',
     'target compiler keywords or intrinsics defined away for the host build', 'L28'),
    ('register fakes', 'tests+build', r'#\s*define\s+\w*(?:_BASE|_ADDR|_REG)\w*\s+\(?\s*(?:\(\s*\w+\s*\*\s*\)\s*)?&|-D\s*\w*_BASE=|fake_?regs?\b|\bFAKE_REG', 'hardware registers redirected to RAM (seams D1, D2)', 'L29'),
    ('host shims', 'build', r'-m32\b|-D\s*(?:HOST|SIMULATION|SIM_BUILD|UNIT_TEST|PC_BUILD|NATIVE)\w*|-D\s*__(?:arm|ARM|ICCARM|CC_ARM)__|-U\s*__\w+__',
     'the host test build pretends to be (or not to be) the target', 'L28'),
    ('optimisation / inlining', 'build', r'-fno-inline\w*|-O0\b|-fno-builtin|-fno-elide-constructors|-fno-exceptions|-fno-rtti|-fkeep-inline-functions|-fno-lto|-fno-omit-frame-pointer',
     'code generation forced for tests (inline functions bypass --wrap; coverage wants -O0)', 'L18 L26'),
    ('sanitizers', 'build', r'-fsanitize=\w+', 'sanitizers in the test build: note which, and which tests they exclude', 'L31'),
    ('extern C around includes', 'tests', r'extern\s+"C"\s*\{', 'C headers included from C++ tests', 'L30'),
    ('time and delay stubs', 'tests', r'\b(?:HAL_GetTick|HAL_Delay|osDelay|vTaskDelay|xTaskGetTickCount|delay_ms|delay_us|usleep|nanosleep|k_sleep|k_uptime_get)\s*\(', 'time and delays faked in tests', 'L29'),
    ('state reset hooks', 'tests+code', r'\w+_(?:reset|deinit|clear)_?(?:for_?test|state)\s*\(|\bresetForTest\w*\s*\(', 'module state reset between tests (seams E1, E2)', 'L14'),
    ('repeat / fork runs', 'build', r'(?:\s-r\d|\s-p\b)', 'tests run repeated (-r) or one process per test (-p, seam E3)', 'L14'),
]
COMMENT = re.compile(r'(?://|/\*|^\s*\*|(?:^|\s)#\s).*\b(?:workaround|work-around|hack|kludge|fixme|xxx|temporar\w*|do not|don\'t|must not|note:|important|flaky|race condition|leak\w*|crash\w*|disabled?|avoid|needed for|required for|ugly|bug|compiler|linker|cpputest|gtest)\b', re.I)
COMMIT = re.compile(r'\b(?:fix|workaround|work-around|flaky|flake|leak|crash|mock|stub|wrap|disable|ignore|revert|link|undefined|multiple definition|include order|cpputest|gtest|coverage|ctc)\w*', re.I)


def walk(root, dirs, pred):
    for d in dirs:
        p0 = os.path.join(root, d)
        if os.path.isfile(p0):
            if pred(p0):
                yield p0
            continue
        for dp, dn, fn in os.walk(p0):
            dn[:] = [x for x in dn if not x.startswith(('build', '.', '_deps', 'cmake-build'))]
            for f in fn:
                p = os.path.join(dp, f)
                if pred(p):
                    yield p


def main(a):
    if '--code' not in a or '--tests' not in a:
        print(__doc__); sys.exit(2)
    root = os.path.abspath(a[0])

    def opt(name):
        if name not in a:
            return []
        i, out = a.index(name) + 1, []
        while i < len(a) and not a[i].startswith('--'):
            out.append(a[i]); i += 1
        return out
    code, tests, builds = opt('--code'), opt('--tests'), opt('--build')
    since = (opt('--since') or ['3 years'])[0]
    is_build = lambda p: os.path.basename(p) in BUILD or p.endswith(BUILD_EXT)
    groups = {
        'code': list(walk(root, code, lambda p: p.endswith(EXT))),
        'tests': list(walk(root, tests, lambda p: p.endswith(EXT))),
        'build': sorted(set(walk(root, tests + builds + ['.'] if not builds else tests + builds, is_build))),
    }
    # the root build files only (not the whole repo) when --build is not given
    groups['build'] = [p for p in groups['build'] if builds or os.path.dirname(p) == root or any(
        p.startswith(os.path.join(root, t)) for t in tests)]
    text = {}
    for g in groups.values():
        for p in g:
            if p not in text:
                try:
                    text[p] = open(p, errors='replace').read().splitlines()
                except OSError:
                    text[p] = []
    rel = lambda p: os.path.relpath(p, root)
    out = ['## Workarounds and design choices found (workarounds.py)', '',
           f"Scanned {len(groups['code'])} code, {len(groups['tests'])} test and {len(groups['build'])} build files. "
           'Learning IDs refer to resources/learnings.md.', '']
    found = 0
    for cat, where, rx, meaning, lids in PATTERNS:
        files = [p for w in where.split('+') for p in groups[w]]
        hits = []
        for p in dict.fromkeys(files):
            for n, line in enumerate(text[p], 1):
                if re.search(rx, line):
                    hits.append(f'{rel(p)}:{n}')
        if hits:
            found += 1
            nf = len({h.rsplit(':', 1)[0] for h in hits})
            out.append(f"- **{cat}** ({len(hits)} lines in {nf} files; {lids}): {meaning}. e.g. {', '.join(hits[:3])}")
    if not found:
        out.append('- no known workaround pattern found')

    out += ['', '### Comments that explain a choice (tests, mocks, test build)', '']
    com = []
    for p in groups['tests'] + groups['build']:
        for n, line in enumerate(text[p], 1):
            if COMMENT.search(line) and len(line.strip()) > 12:
                com.append(f'- {rel(p)}:{n}: `{line.strip()[:150]}`')
    out += com[:40] + ([f'- … {len(com) - 40} more (rerun with a narrower --tests)'] if len(com) > 40 else []) or ['- none']

    out += ['', f'### Commits touching the tests whose subject names a fix or workaround (since {since})', '']
    tp = [t for t in tests if os.path.exists(os.path.join(root, t))]
    r = subprocess.run(['git', '-C', root, 'log', f'--since={since} ago', '--no-merges', '--format=%h %ad %s', '--date=short', '--'] + tp,
                       capture_output=True, text=True)
    commits = [l for l in r.stdout.splitlines() if COMMIT.search(l.split(' ', 2)[-1])]
    total = len(r.stdout.splitlines())
    out += [f'- {l[:160]}' for l in commits[:30]] or ['- none (or not a git repository)']
    if len(commits) > 30:
        out.append(f'- … {len(commits) - 30} more')
    out.append(f'\n{len(commits)} of {total} commits to the test paths look like fixes. Read the diffs of the ones that '
               'changed build files, stubs or fixtures: `git show --stat <sha>`, then `git show <sha> -- <file>`.')
    print('\n'.join(out))


if __name__ == '__main__':
    main(sys.argv[1:])
