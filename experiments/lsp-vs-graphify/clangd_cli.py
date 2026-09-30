#!/usr/bin/env python3
"""clangd_cli.py - ask clangd (the compiler's language server) about the code. Experiment arm "LSP".

  clangd_cli.py ROOT CDB_DIR find PATTERN        symbols whose name contains PATTERN (workspace/symbol)
  clangd_cli.py ROOT CDB_DIR def NAME            where NAME is defined
  clangd_cli.py ROOT CDB_DIR source NAME         the lines of NAME's definition (function, type, macro)
  clangd_cli.py ROOT CDB_DIR refs NAME           every reference to NAME
  clangd_cli.py ROOT CDB_DIR callers NAME        functions that call NAME, with call lines
  clangd_cli.py ROOT CDB_DIR callees NAME        functions NAME calls, with call lines
  clangd_cli.py ROOT CDB_DIR symbols FILE        the symbols of one file with line ranges
  clangd_cli.py ROOT CDB_DIR hover NAME          signature and type information
  clangd_cli.py ROOT CDB_DIR warm                build clangd's background index once (run before the queries)
NAME may be qualified (Class::method) and may carry @FILE:LINE to pick one overload.
clangd keeps its background index in CDB_DIR/.cache/clangd. Env: UT_CLANGD = clangd binary."""
import glob, json, os, re, shutil, subprocess, sys, threading, time
from urllib.parse import quote, unquote

SK = {1: 'file', 2: 'module', 3: 'namespace', 5: 'class', 6: 'method', 7: 'property', 8: 'field', 9: 'constructor',
      10: 'enum', 11: 'interface', 12: 'function', 13: 'variable', 14: 'constant', 22: 'enum member', 23: 'struct',
      26: 'type parameter'}


def find_clangd():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get('UT_CLANGD'), shutil.which('clangd')] + sorted(glob.glob('/usr/lib/llvm-*/bin/clangd'), reverse=True) \
        + glob.glob(os.path.join(here, '..', '..', '.agents', 'skills', 'ut', 'resources', 'vendor', 'graphify', '.venv', 'bin', 'clangd'))
    return next((c for c in cands if c and os.path.exists(c)), None)


def uri(p):
    return 'file://' + quote(os.path.abspath(p))


def path_of(u):
    return unquote(u[7:]) if u.startswith('file://') else u


class Client:
    def __init__(self, root, cdb_dir):
        clangd = find_clangd()
        if not clangd:
            sys.exit('clangd not found (set UT_CLANGD)')
        self.root = os.path.realpath(root)
        self.p = subprocess.Popen([clangd, '--background-index', '--log=error', f'--compile-commands-dir={cdb_dir}',
                                   '--limit-results=0', '--limit-references=0'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=self.root)
        self.id, self.replies, self.lock, self.progress, self.opened = 0, {}, threading.Lock(), {}, set()
        threading.Thread(target=self.reader, daemon=True).start()
        self.request('initialize', {'processId': os.getpid(), 'rootUri': uri(self.root), 'capabilities': {
            'window': {'workDoneProgress': True},
            'textDocument': {'callHierarchy': {}, 'references': {}, 'definition': {}, 'documentSymbol': {'hierarchicalDocumentSymbolSupport': True},
                             'hover': {'contentFormat': ['plaintext']}}}})
        self.notify('initialized', {})

    def send(self, msg):
        body = json.dumps(msg).encode()
        self.p.stdin.write(f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        self.p.stdin.flush()

    def reader(self):
        f = self.p.stdout
        while True:
            hdr = b''
            while not hdr.endswith(b'\r\n\r\n'):
                ch = f.read(1)
                if not ch:
                    return
                hdr += ch
            n = int(re.search(rb'Content-Length: (\d+)', hdr).group(1))
            msg = json.loads(f.read(n))
            if 'id' in msg and ('result' in msg or 'error' in msg):
                with self.lock:
                    self.replies[msg['id']] = msg
            elif 'id' in msg and 'method' in msg:
                self.send({'jsonrpc': '2.0', 'id': msg['id'], 'result': None})
            elif msg.get('method') == '$/progress':
                with self.lock:
                    self.progress[str(msg['params'].get('token'))] = msg['params'].get('value', {}).get('kind')

    def request(self, method, params, timeout=120):
        self.id += 1
        i = self.id
        self.send({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params})
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.lock:
                if i in self.replies:
                    return self.replies.pop(i).get('result')
            time.sleep(0.01)
        raise TimeoutError(method)

    def notify(self, method, params):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params})

    def open(self, path):
        path = os.path.realpath(path)
        if path in self.opened:
            return
        self.opened.add(path)
        text = open(path, encoding='utf-8', errors='replace').read()
        lang = 'c' if path.endswith(('.c', '.h')) else 'cpp'
        self.notify('textDocument/didOpen', {'textDocument': {'uri': uri(path), 'languageId': lang, 'version': 1, 'text': text}})

    def wait_index(self, timeout=600):
        t0, seen = time.time(), False
        while time.time() - t0 < timeout:
            with self.lock:
                st = dict(self.progress)
            if st:
                seen = True
                if all(v == 'end' for v in st.values()):
                    return True
            elif time.time() - t0 > 3 and not seen:
                return True
            time.sleep(0.2)
        return False

    def close(self):
        try:
            self.request('shutdown', None, 10)
            self.notify('exit', None)
        except Exception:  # noqa: BLE001
            pass
        self.p.kill()

    # ---------------------------------------------------------------- helpers
    def rel(self, p):
        p = os.path.realpath(p)
        return os.path.relpath(p, self.root) if p.startswith(self.root + os.sep) else p

    def loc(self, u, rng):
        return f"{self.rel(path_of(u))}:{rng['start']['line'] + 1}"

    def locate(self, name):
        """NAME[@FILE:LINE] -> (path, position) of its definition if clangd knows one, else its declaration"""
        name, _, where = name.partition('@')
        parts = name.split('::')
        short, container = parts[-1], '::'.join(parts[:-1])
        syms = self.request('workspace/symbol', {'query': short}) or []
        cands = [s for s in syms if s['name'] == short and (not container or (s.get('containerName') or '').split('::')[-1] == container.split('::')[-1]
                                                         or (s.get('containerName') or '').endswith(container))]
        if not cands:
            return None
        if where:
            f, _, l = where.rpartition(':')
            pick = [s for s in cands if self.rel(path_of(s['location']['uri'])).endswith(f) and abs(s['location']['range']['start']['line'] + 1 - int(l or 0)) < 400]
            cands = pick or cands
        src = [x for x in cands if not path_of(x['location']['uri']).endswith(('.h', '.hpp', '.hh', '.hxx'))]
        s = (src or cands)[0]
        path, pos = path_of(s['location']['uri']), s['location']['range']['start']
        self.open(path)
        if path.endswith(('.h', '.hpp', '.hh', '.hxx')):
            # a header hit may be a declaration: ask for the definition (asked AT a definition, clangd answers the
            # declaration instead, so only ask from headers)
            d = self.request('textDocument/definition', {'textDocument': {'uri': uri(path)}, 'position': pos}) or []
            d = d if isinstance(d, list) else [d]
            if d:
                path, pos = path_of(d[0]['uri']), d[0]['range']['start']
                self.open(path)
        return path, pos

    def symbol_range(self, path, pos):
        """full line range of the innermost document symbol containing pos"""
        syms = self.request('textDocument/documentSymbol', {'textDocument': {'uri': uri(path)}}) or []
        best = None
        stack = list(syms)
        while stack:
            s = stack.pop()
            r = s.get('range') or s.get('location', {}).get('range')
            if r and r['start']['line'] <= pos['line'] <= r['end']['line']:
                if best is None or (r['end']['line'] - r['start']['line']) < (best['end']['line'] - best['start']['line']):
                    best = r
            stack += s.get('children', [])
        return best


def main(a):
    if len(a) < 3:
        print(__doc__); sys.exit(2)
    root, cdb, cmd, arg = a[0], os.path.abspath(a[1]), a[2], (a[3] if len(a) > 3 else '')
    c = Client(root, cdb)
    try:
        ents = json.load(open(os.path.join(cdb, 'compile_commands.json')))
        if ents:            # clangd loads its stored index for a project only once a file of it is open
            c.open(os.path.join(ents[0]['directory'], ents[0]['file']))
        if cmd == 'warm':
            print('index ready' if c.wait_index(900) else 'index still building')
            return
        c.wait_index(120)
        for _ in range(100):                          # the stored index loads asynchronously: wait until it answers
            if c.request('workspace/symbol', {'query': 'a'}):
                break
            time.sleep(0.1)
        if cmd == 'find':
            syms = c.request('workspace/symbol', {'query': arg}) or []
            print(f'# {len(syms)} symbol(s) matching {arg!r} (clangd)')
            for s in syms[:60]:
                cont = (s.get('containerName') or '')
                print(f"- {cont + '::' if cont else ''}{s['name']}  {SK.get(s['kind'], s['kind'])}  {c.loc(s['location']['uri'], s['location']['range'])}")
            return
        if cmd == 'symbols':
            path = os.path.join(root, arg)
            c.open(path)
            syms = c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri(path)}}) or []
            print(f'# symbols of {arg} (clangd)')
            stack = [(s, 0) for s in reversed(syms)]
            while stack:
                s, d = stack.pop()
                r = s['range']
                print(f"{'  ' * d}- {s['name']}  {SK.get(s['kind'], s['kind'])}  {r['start']['line'] + 1}-{r['end']['line'] + 1}")
                stack += [(x, d + 1) for x in reversed(s.get('children', []))]
            return
        hit = c.locate(arg)
        if not hit:
            sys.exit(f'# {arg}: clangd knows no symbol with that name (try: find {arg.split("::")[-1]})')
        path, pos = hit
        td = {'textDocument': {'uri': uri(path)}, 'position': pos}
        if cmd == 'def':
            print(f"{c.rel(path)}:{pos['line'] + 1}")
        elif cmd == 'source':
            r = c.symbol_range(path, pos)
            lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
            a0, b0 = (r['start']['line'], r['end']['line']) if r else (pos['line'], pos['line'])
            print(f'// {arg}  {c.rel(path)}:{a0 + 1}-{b0 + 1}  (clangd)')
            for k in range(a0, min(b0, a0 + 199) + 1):
                print(f'{k + 1:>5}  {lines[k]}')
        elif cmd == 'hover':
            res = c.request('textDocument/hover', td) or {}
            v = res.get('contents', {})
            print(v.get('value', v) if isinstance(v, dict) else v)
        elif cmd == 'refs':
            res = c.request('textDocument/references', dict(td, context={'includeDeclaration': False})) or []
            print(f'# {len(res)} reference(s) to {arg} (clangd)')
            for r in sorted({c.loc(x['uri'], x['range']) for x in res}):
                print('- ' + r)
        elif cmd in ('callers', 'callees'):
            items = c.request('textDocument/prepareCallHierarchy', td) or []
            if not items:
                sys.exit(f'# {arg}: clangd has no call hierarchy for it')
            res = c.request('callHierarchy/incomingCalls' if cmd == 'callers' else 'callHierarchy/outgoingCalls', {'item': items[0]}) or []
            print(f'# {cmd} of {arg} (clangd)')
            for r in res:
                it = r.get('from') or r.get('to')
                sites = ', '.join(str(x['start']['line'] + 1) for x in r.get('fromRanges', [])[:8])
                name = it['name'] if '::' in it['name'] or not it.get('detail') else it['detail']
                print(f"- {name}  {c.loc(it['uri'], it['selectionRange'])}" + (f'  (call lines {sites})' if sites else ''))
        else:
            sys.exit('unknown command ' + cmd)
    finally:
        c.close()


if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main(sys.argv[1:])
