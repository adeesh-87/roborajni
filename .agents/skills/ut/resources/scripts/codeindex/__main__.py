"""python -m codeindex COMMAND ...   (index.sh is the normal entry point; it picks the Python)"""
import os, sys


def need(argv, n, usage):
    if len(argv) < n:
        sys.exit('usage: ' + usage)


def main(argv):
    if not argv:
        print(__doc__); sys.exit(2)
    cmd, a = argv[0], argv[1:]
    from .model import Index
    if cmd == 'export-graphify':
        need(a, 2, 'export-graphify GRAPHIFY_DIR INDEX_JSON')
        from .be_graphify import export
        ix = export(a[0], a[1]); print(f"index: {a[1]}  {ix.stats()}")
    elif cmd == 'card':
        need(a, 2, 'card INDEX_JSON FUNCTION|FILE')
        from .query import cmd_card
        print(cmd_card(Index.load(a[0]), a[1]))
    elif cmd in ('find', 'defs', 'list', 'source', 'refs'):
        need(a, 2, f'{cmd} INDEX_JSON NAME|FILE|PATTERN')
        from . import query as Q
        ix = Index.load(a[0])
        print({'find': lambda: Q.cmd_find(ix, a[1]), 'defs': lambda: Q.cmd_find(ix, a[1], exact=True),
               'list': lambda: Q.cmd_list(ix, a[1]), 'source': lambda: Q.cmd_source(ix, a[1]),
               'refs': lambda: Q.cmd_refs(ix, a[1])}[cmd]())
    elif cmd in ('deps', 'tests', 'impact'):
        import graphify_ut as G
        if cmd == 'impact':
            G.cmd_impact([a[0], '-'] + a[1:])
        else:
            {'deps': G.cmd_deps, 'tests': G.cmd_tests}[cmd](a)
    elif cmd in ('flow', 'seq', 'scenarios', 'diagrams'):
        from . import mermaid as M
        M.main(cmd, a)
    elif cmd == 'cov-import':
        from . import coverage as C
        C.main(a)
    elif cmd == 'uncovered':
        from . import coverage as C
        C.cmd_uncovered(a)
    elif cmd == 'trace':
        from . import trace as T
        T.main(a)
    elif cmd == 'check':
        from . import selfcheck as S
        S.main(a)
    elif cmd in ('kb-cards', 'refresh', 'functions'):
        from . import kbops as K
        K.main(cmd, a)
    elif cmd == 'mkcdb':
        import graphify_ut as G
        G.cmd_mkcdb(a)
    elif cmd == 'stats':
        print(Index.load(a[0]).stats())
    else:
        sys.exit(f'unknown command {cmd}')


if __name__ == '__main__':
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    main(sys.argv[1:])
