"""check INDEX_JSON [plain]: the self-test fixture's known answers, for ANY backend's index"""
import sys
from .model import Index, decisions


def main(a):
    ix = Index.load(a[0])
    plain = len(a) > 1 and a[1] == 'plain'
    backend = ix.meta.get('backend')

    def node(name):
        hits = [i for i in ix.find(name, include_tests=True)]
        return hits[0] if hits else None

    def n(name):
        i = node(name)
        return ix.node(i) if i else {}

    def calls(a_, b_, line=None):
        i = node(a_)
        return any(ix.label(c['to'])[:-2] == b_ or ix.node(c['to']) and ix.node(c['to']).get('name') == b_
                   for c in ix.out.get(i, []) if line is None or c.get('line') == line) if i else False

    def target(ptr, fn):
        i = node(ptr)
        return bool(i) and any(ix.node(c['to']) and ix.node(c['to']).get('name') == fn for c in ix.out.get(i, []))

    R = []

    def check(name, ok, applies=True):
        if applies:
            R.append((name, bool(ok)))
    check('STATIC helper marked static', n('uart_wait_ready').get('static') is True)
    check('crc16 is an external function declared in lib/crc/crc.h',
          n('crc16').get('kind') == 'function' and n('crc16').get('declared_in') == 'lib/crc/crc.h')
    check('proto_frame_done -> crc16 at original line 11', calls('proto_frame_done', 'crc16', 11))
    check('only the active #if variant: uart_flush -> hal_dma_start, not uart_send',
          calls('uart_flush', 'hal_dma_start') and not calls('uart_flush', 'uart_send'), not plain)
    check('FW_ASSERT expanded to fw_assert_failed', calls('uart_send', 'fw_assert_failed'), not plain)
    check('designated initializer: s_ops->write may call uart_write', target('s_ops->write', 'uart_write'))
    check('positional initializer: s_events.on_error may call drv_on_error', target('s_events.on_error', 'drv_on_error'))
    check('registered callback: s_cb may call drv_uart_cb', target('s_cb', 'drv_uart_cb'))
    check('C++ interface method is pure virtual', n('IBus::write').get('pure') is True, not plain)
    check('Logger::emit defined in src/logger.cpp and calls IBus::write',
          n('Logger::emit').get('file') == 'src/logger.cpp' and calls('Logger::emit', 'IBus::write'), not plain)
    check('TEST block node calls proto_feed', calls('TEST(Proto, Feed_StartByte_ReturnsZero)', 'proto_feed'))
    check('TEST block reaches Logger::log through a typed local', calls('TEST(Logger, Log_Writes)', 'Logger::log'))
    check('no node points outside the repository', not any((x.get('file') or '').startswith(('/', '..')) for x in ix.functions.values()))
    # outline facts every backend with a parser must get
    fe = n('proto_feed').get('outline')
    if fe is not None:
        sw = [s for s in decisions(fe) if s['t'] == 'switch']
        check('outline: proto_feed switch has P_IDLE..P_CRC + default',
              bool(sw) and sw[0].get('default') and [c['v'] for c in sw[0]['cases']][:4] == ['P_IDLE', 'P_LEN', 'P_DATA', 'P_CRC'])
        dw = n('drv_write_all').get('outline') or []
        order = [s.get('f') for s in dw if s['t'] == 'call']
        check('outline: drv_write_all calls open, write, close in order', order[:3] == ['s_ops->open', 's_ops->write', 's_ops->close'])
    for name, ok in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    bad = sum(1 for _, ok in R if not ok)
    print(f"self-test [{backend}]: {len(R) - bad}/{len(R)} passed" + (' (plain mode: no compile DB)' if plain else ''))
    sys.exit(1 if bad else 0)
