"""Knowledge-base operations on the index (called by index.sh and the ut tool)
  kb-cards  OUT_DIR KB_DIR FILE...   modules/<file>.cards.md = cards + dependencies of each file
  refresh   OUT_DIR                  rebuild with the last arguments; regenerate cards (+ diagrams if present); delta
  functions OUT_DIR                  'file<TAB>name' of every function (for deltas)"""
import datetime, io, os, re, subprocess, sys
from contextlib import redirect_stdout
from .model import Index

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_args(out_dir):
    d = {'path': []}
    for l in open(os.path.join(out_dir, 'BUILD_ARGS'), encoding='utf-8').read().splitlines():
        k, _, v = l.partition('=')
        if k == 'path':
            d['path'].append(v)
        else:
            d[k] = v
    return d


def card_text(ix_path, target):
    import graphify_ut as G
    from .query import cmd_card
    ix = Index.load(ix_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            G.cmd_deps([ix_path, target])
        except SystemExit:
            pass
    return cmd_card(ix, target) + '\n' + buf.getvalue()


def kb_cards(out_dir, kb_dir, files):
    ixp = os.path.join(out_dir, 'index.json')
    os.makedirs(os.path.join(kb_dir, 'modules'), exist_ok=True)
    for f in files:
        open(os.path.join(kb_dir, 'modules', os.path.basename(f) + '.cards.md'), 'w', encoding='utf-8').write(card_text(ixp, f))


def functions(ix):
    return sorted(f"{n['file']}\t{n['name']}" for n in ix.functions.values() if n.get('kind') == 'function')


def refresh(out_dir):
    out_dir = os.path.abspath(out_dir)
    a = read_args(out_dir)
    ixp = os.path.join(out_dir, 'index.json')
    before = functions(Index.load(ixp)) if os.path.exists(ixp) else []
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    cmd = [os.path.join(SCRIPTS, 'index.sh'), 'build', '--backend', a.get('backend', 'auto')] + \
          (['--cdb', a['cdb']] if a.get('cdb') else []) + [out_dir] + a['path']
    r = subprocess.run(cmd, cwd=a.get('cwd') or None, capture_output=True, text=True, errors='replace')
    print('\n'.join(l for l in (r.stdout + r.stderr).splitlines() if re.search(r'index:|FAILED|WARNING|error', l))[:2000])
    if r.returncode != 0 or not os.path.exists(ixp):
        sys.exit('refresh: rebuild FAILED')
    ix = Index.load(ixp)
    after = functions(ix)
    kb = os.path.dirname(out_dir)
    L = [f'# Last refresh: {stamp}', f"Index rebuilt with backend {ix.meta.get('backend')} and the arguments of the last build: {' '.join(a['path'])}"
         + (f" (compile DB: {a['cdb']})" if a.get('cdb') else ''), '', '## Functions added / removed since the previous index']
    add = sorted(set(after) - set(before)); rem = sorted(set(before) - set(after))
    L += [f'+ {x}' for x in add] + [f'- {x}' for x in rem] or ['(none)']
    tpaths = [os.path.join(a.get('cwd') or '.', p) for p in a['path'] if re.search(r'test|mock|stub|fake', p, re.I)]
    if tpaths:                                     # the test scan is cheap: keep conventions/exemplar candidates current
        subprocess.run([os.path.join(SCRIPTS, 'testscan.sh'), kb] + tpaths, cwd=a.get('cwd') or None, capture_output=True)
    L += ['', '## Cards regenerated (changed lines per file)']
    mods = os.path.join(kb, 'modules')
    for fn in sorted(os.listdir(mods)) if os.path.isdir(mods) else []:
        if not fn.endswith('.cards.md'):
            continue
        p = os.path.join(mods, fn)
        old = open(p, encoding='utf-8').read()
        m = re.match(r'# Cards for (\S+)', old)
        if not m:
            continue
        new = card_text(ixp, m.group(1))
        if 'definition not found in the index' in new:
            L.append(f'- {fn}: could not regenerate ({m.group(1)} is not in the index any more)'); continue
        L.append(f'- {fn}: {len(set(old.splitlines()) ^ set(new.splitlines()))} changed lines')
        open(p, 'w', encoding='utf-8').write(new)
    dg = os.path.join(kb, 'diagrams')
    if os.path.isdir(dg):
        from . import mermaid as M, coverage as C
        rows, sc = M.diagrams(ix, dg, C.load(ixp))
        L.append(f'\nDiagrams regenerated: {sum(1 for r in rows if r[3])} flowcharts, {sum(1 for r in rows if r[4])} sequences, {len(sc)} scenarios.')
    open(os.path.join(kb, 'last-refresh.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    with open(os.path.join(kb, 'refresh.log'), 'a', encoding='utf-8') as fh:
        fh.write(f'{stamp} refresh ({ix.meta.get("backend")}): +{len(add)} -{len(rem)} functions; cards regenerated\n')
    print(f"delta: {os.path.join(kb, 'last-refresh.md')}")
    print('\n'.join(L[3:40]))


def main(cmd, a):
    if cmd == 'kb-cards':
        kb_cards(a[0], a[1], a[2:])
    elif cmd == 'refresh':
        refresh(a[0])
    elif cmd == 'functions':
        print('\n'.join(functions(Index.load(os.path.join(a[0], 'index.json')))))
