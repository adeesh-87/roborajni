"""Phase 2: verified commands, compile DB, baseline build + run."""
import os, re
from .util import sh, read, norm, say
from .frameworks import FRAMEWORKS, parse_summary, failures, first_errors
from .state import now


def find_test_binaries(root, prof):
    """executables produced by the build that look like test runners"""
    rc, out = sh(['find', root, '-maxdepth', '4', '-type', 'f', '-perm', '-u+x', '-not', '-path', '*/.git/*', '-not', '-name', '*.sh', '-not', '-name', '*.py', '-not', '-name', '*.o'])
    cands = [norm(os.path.relpath(x, root)) for x in out.split() if re.search(r'test|Test|TEST|AllTests|unit', os.path.basename(x)) and '/CMakeFiles/' not in x]
    return cands[:10]


def single_test_template(prof, binaries):
    fw = prof.get('framework') or ''
    if not fw or fw == 'parasoft':
        return ''
    if prof.get('build_system') == 'ceedling':
        return 'ceedling test:{group}'
    b = binaries[0] if binaries else '<test binary>'
    return FRAMEWORKS[fw]['filter'](b, '{group}', '')


def run_baseline(st, root, kb):
    prof = st['profile']
    cmds = kb.get('commands', {}) or {}
    c = {'env_setup': cmds.get('env_setup', {}).get('cmd', prof.get('env_setup', 'none')),
         'build': cmds.get('build', {}).get('cmd', prof['build_cmd']), 'run': cmds.get('run', {}).get('cmd', prof['run_cmd']),
         'clean': cmds.get('clean', {}).get('cmd', prof.get('clean_cmd', ''))}
    st['commands'] = c
    pre = (c['env_setup'] + ' && ') if c['env_setup'] not in ('', 'none') else ''
    res = {'date': now()}
    if c['build'] in ('', '?'):
        res['build'] = 'UNKNOWN COMMAND'; st['baseline'] = res; return res
    rc, bout = sh(pre + c['build'], cwd=root)
    open(os.path.join(st.dir, 'logs', 'build-baseline.log'), 'w').write(bout)
    res['build'] = 'OK' if rc == 0 else 'FAILED'
    res['problems'] = [f'build: {e}' for e in first_errors(bout)] if rc != 0 else []
    if rc == 0:
        rc2, rout = sh(pre + c['run'], cwd=root)
        open(os.path.join(st.dir, 'logs', 'run-baseline.log'), 'w').write(rout)
        fw = prof.get('framework') or ''
        summ = parse_summary(fw, rout) if fw else None
        res['tests'] = f"{summ['passed']}/{summ['total']} passed, {summ['failed']} failed" if summ else ('exit 0' if rc2 == 0 else f'exit {rc2}')
        res['problems'] += [f'test: {f}' for f in failures(fw, rout)] if fw else []
        if not fw and 'No tests were found' in rout or (summ is None and fw and 'test' not in rout.lower()):
            res['tests'] = 'none (greenfield?)'
    # compile DB
    cdb = prof.get('compile_db', 'none')
    if cdb == 'none' and prof.get('build_system') == 'cmake':
        m = re.search(r'-B\s*(\S+)', c['build'])
        b = m.group(1) if m else 'build'
        if os.path.exists(os.path.join(root, b, 'compile_commands.json')):
            cdb = norm(os.path.join(b, 'compile_commands.json'))
    prof['compile_db'] = cdb
    bins = find_test_binaries(root, prof)
    m = re.search(r'-B\s*(\S+)', c['build'])
    if m:                                                   # binaries of the configured build dir first
        bins = sorted(bins, key=lambda b: 0 if b.startswith(m.group(1).rstrip('/') + '/') else 1)
    st['baseline'] = res
    st['baseline']['single_test_cmd'] = single_test_template(prof, bins)
    st['baseline']['test_binaries'] = bins
    # record in KB
    kb.setdefault('commands', {})
    for k in ('env_setup', 'build', 'run', 'clean'):
        if c[k] and c[k] != 'none':
            kb['commands'][k] = {'cmd': c[k], 'verified': now() if res['build'] == 'OK' else 'FAILED ' + now()}
    kb['commands']['single_test'] = {'cmd': st['baseline']['single_test_cmd'], 'verified': ''}
    kb['commands']['compile_db'] = {'cmd': cdb, 'verified': now()}
    m = re.search(r'-B\s*(\S+)', c['build'])
    kb['build_paths'] = sorted(set([m.group(1)] if m else []) | set(os.path.dirname(b) for b in bins))
    if res['build'] == 'OK':
        kb['summary_example'] = next((l for l in read(os.path.join(st.dir, 'logs', 'run-baseline.log')).splitlines() if re.search(r'OK \(|PASSED|Tests .*Failures|Errors \(', l)), '')
    return res
