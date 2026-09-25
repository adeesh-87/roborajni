"""Find and load libclang for the Python bindings (clang.cindex).
Order: UT_LIBCLANG env -> the bindings' own library (pip package `libclang` bundles one) -> system LLVM installs."""
import glob, os, re


def candidates():
    pats = ['/usr/lib/llvm-*/lib/libclang.so*', '/usr/lib/llvm-*/lib/libclang-*.so*', '/usr/lib/x86_64-linux-gnu/libclang-*.so*',
            '/usr/lib/aarch64-linux-gnu/libclang-*.so*', '/usr/lib64/libclang.so*', '/usr/lib/libclang.so*', '/usr/local/lib/libclang.so*',
            '/opt/homebrew/opt/llvm/lib/libclang.dylib', '/usr/local/opt/llvm/lib/libclang.dylib',
            '/Library/Developer/CommandLineTools/usr/lib/libclang.dylib',
            'C:/Program Files/LLVM/bin/libclang.dll', 'C:/Program Files (x86)/LLVM/bin/libclang.dll']
    out = []
    for p in pats:
        out += sorted(glob.glob(p), key=lambda s: [int(x) for x in re.findall(r'\d+', s)] or [0], reverse=True)
    return [p for p in out if 'libclang-cpp' not in p]


_loaded = {}


def load():
    """-> clang.cindex module with a working library, or raises ImportError with the reason"""
    if 'ci' in _loaded:
        return _loaded['ci']
    try:
        import clang.cindex as ci
    except ImportError as e:
        raise ImportError('Python bindings for libclang are missing (index.sh setup clang installs them)') from e
    tried = []
    lib = os.environ.get('UT_LIBCLANG')
    options = ([lib] if lib else []) + [None] + candidates()
    for cand in options:
        try:
            if cand:
                ci.Config.loaded = False
                ci.Config.library_file = None
                ci.Config.set_library_file(cand)
            ci.Index.create()
            _loaded['ci'] = ci
            _loaded['lib'] = cand or '(default search)'
            return ci
        except Exception as e:  # noqa: BLE001 - try the next candidate
            tried.append(f'{cand or "default"}: {str(e)[:80]}')
            ci.Config.loaded = False
    raise ImportError('libclang not found; set UT_LIBCLANG=/path/to/libclang.so. Tried: ' + '; '.join(tried[:4]))


def system_major():
    """major version of the newest system libclang, or None"""
    for c in candidates():
        m = re.search(r'llvm-(\d+)|libclang-(\d+)|libclang\.so\.(\d+)', c)
        if m:
            return next(g for g in m.groups() if g)
    return None
