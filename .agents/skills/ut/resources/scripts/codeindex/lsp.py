"""lsp INDEX_JSON (callers|callees|refs|def|hover) NAME [--cdb-dir DIR] [--timeout S]
Ask clangd (the compiler-accurate language server) about ONE function, for interactive work: the orchestrator,
a stronger model doing a decomposition, or a human. The index says where NAME is defined; clangd answers with the
build's flags (compile_commands.json). Batch facts for every function come from the index backends, not from here.
clangd: $UT_CLANGD, the skill venv (index.sh setup clangd), or PATH."""
import json, os, re, shutil, subprocess, sys, threading, time
from urllib.parse import quote, unquote
from .model import Index

HERE = os.path.dirname(os.path.abspath(__file__))


def find_clangd():
    cands = [os.environ.get('UT_CLANGD'),
             os.path.join(HERE, '..', '..', 'vendor', 'graphify', '.venv', 'bin', 'clangd'),
             os.path.join(HERE, '..', '..', 'vendor', 'graphify', '.venv', 'Scripts', 'clangd.exe'),
             shutil.which('clangd')] + sorted(__import__('glob').glob('/usr/lib/llvm-*/bin/clangd'), reverse=True)
    return next((os.path.abspath(c) for c in cands if c and os.path.exists(c)), None)


def uri(p):
    return 'file://' + quote(os.path.abspath(p))


def path_of(u):
    return unquote(u[7:]) if u.startswith('file://') else u


class Client:
    def __init__(self, clangd, root, cdb_dir):
        # background index: needed for callers/references in OTHER files; clangd keeps it in <compile DB dir>/.cache/clangd
        args = [clangd, '--background-index', '--log=error'] + ([f'--compile-commands-dir={cdb_dir}'] if cdb_dir else [])
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=root)
        self.id, self.replies, self.lock = 0, {}, threading.Lock()
        self.progress = {}
        threading.Thread(target=self.reader, daemon=True).start()
        self.request('initialize', {'processId': os.getpid(), 'rootUri': uri(root), 'capabilities': {
            'window': {'workDoneProgress': True},
            'textDocument': {'callHierarchy': {}, 'references': {}, 'definition': {}, 'hover': {'contentFormat': ['plaintext']}}}})
        self.notify('initialized', {})

    def wait_index(self, timeout):
        """wait until clangd reports its background index finished (or nothing to do)"""
        t0 = time.time()
        seen = False
        while time.time() - t0 < timeout:
            with self.lock:
                st = dict(self.progress)
            if st:
                seen = True
                if all(v == 'end' for v in st.values()):
                    return True
            elif time.time() - t0 > 3 and not seen:
                return True                      # already indexed: clangd did not start any work
            time.sleep(0.2)
        return False

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
            elif 'id' in msg and 'method' in msg:           # server -> client request (e.g. workDoneProgress/create)
                self.send({'jsonrpc': '2.0', 'id': msg['id'], 'result': None})
            elif msg.get('method') == '$/progress':
                v = msg['params'].get('value', {})
                with self.lock:
                    self.progress[str(msg['params'].get('token'))] = v.get('kind')

    def request(self, method, params, timeout=60):
        self.id += 1
        i = self.id
        self.send({'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params})
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.lock:
                if i in self.replies:
                    r = self.replies.pop(i)
                    return r.get('result')
            time.sleep(0.02)
        raise TimeoutError(method)

    def notify(self, method, params):
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params})

    def open(self, path):
        text = open(path, encoding='utf-8', errors='replace').read()
        ext = os.path.splitext(path)[1].lower()
        self.notify('textDocument/didOpen', {'textDocument': {'uri': uri(path), 'languageId': 'c' if ext in ('.c', '.h') else 'cpp',
                                                              'version': 1, 'text': text}})
        return text

    def close(self):
        try:
            self.request('shutdown', None, 10)
            self.notify('exit', None)
        except Exception:  # noqa: BLE001
            pass
        self.p.kill()


def position(text, line, name):
    """0-based position of NAME's short identifier on or after LINE (1-based)"""
    short = re.split(r'::', name)[-1]
    lines = text.splitlines()
    for l in range(line - 1, min(line + 5, len(lines))):
        m = re.search(r'\b' + re.escape(short) + r'\s*\(', lines[l])
        if m:
            return {'line': l, 'character': m.start()}
    return {'line': line - 1, 'character': 0}


def loc(root, item):
    p = path_of(item.get('uri', ''))
    rel = os.path.relpath(p, root) if p.startswith(root) else p
    ln = (item.get('range') or item.get('selectionRange') or {}).get('start', {}).get('line', -1) + 1
    return f'{rel}:{ln}'


def main(a):
    if len(a) < 3:
        print(__doc__); sys.exit(2)
    ix = Index.load(a[0])
    what, name = a[1], a[2]
    root = ix.meta['root']
    cdb_dir = a[a.index('--cdb-dir') + 1] if '--cdb-dir' in a else (os.path.dirname(ix.meta.get('cdb') or '') or None)
    timeout = int(a[a.index('--timeout') + 1]) if '--timeout' in a else 120
    clangd = find_clangd()
    if not clangd:
        sys.exit('lsp: clangd not found (index.sh setup clangd, or set UT_CLANGD)')
    hits = [h for h in ix.find(name, include_tests=True) if h in ix.functions]
    if not hits:
        sys.exit(f'lsp: {name} is not in the index')
    fn = ix.functions[hits[0]]
    path = os.path.join(root, fn['file'])
    c = Client(clangd, root, cdb_dir)
    try:
        text = c.open(path)
        if what in ('callers', 'refs') and not c.wait_index(timeout):
            print(f'(clangd still indexing after {timeout}s: results may be incomplete)')
        pos = position(text, fn['line'], fn['name'])
        td = {'textDocument': {'uri': uri(path)}, 'position': pos}
        if what in ('callers', 'callees'):
            items = c.request('textDocument/prepareCallHierarchy', td, timeout) or []
            if not items:
                sys.exit('lsp: clangd found no call hierarchy item at ' + f"{fn['file']}:{pos['line'] + 1}")
            method = 'callHierarchy/incomingCalls' if what == 'callers' else 'callHierarchy/outgoingCalls'
            res = c.request(method, {'item': items[0]}, timeout) or []
            print(f"# {what} of {fn['name']} ({fn['file']}:{fn['line']}) - clangd")
            for r in res:
                it = r.get('from') or r.get('to')
                sites = ', '.join(str(x['start']['line'] + 1) for x in r.get('fromRanges', [])[:6])
                print(f"- {it.get('detail') or it['name']}  {loc(root, it)}"
                      + (f'  (call lines {sites})' if sites else ''))
        elif what == 'refs':
            res = c.request('textDocument/references', dict(td, context={'includeDeclaration': False}), timeout) or []
            print(f"# references to {fn['name']} - clangd ({len(res)})")
            for r in res:
                print('- ' + loc(root, r))
        elif what == 'def':
            res = c.request('textDocument/definition', td, timeout) or []
            for r in (res if isinstance(res, list) else [res]):
                print(loc(root, r))
        elif what == 'hover':
            res = c.request('textDocument/hover', td, timeout) or {}
            v = res.get('contents', {})
            print(v.get('value', v) if isinstance(v, dict) else v)
        else:
            sys.exit('lsp: callers | callees | refs | def | hover')
    finally:
        c.close()
