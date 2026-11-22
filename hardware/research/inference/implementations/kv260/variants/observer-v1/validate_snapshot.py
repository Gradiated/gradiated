"""Validate an idle observer-v1 snapshot against the frozen request geometry."""
def validate_snapshot(words, tokens):
    if type(tokens) is not int or not 1 <= tokens <= 256:
        raise ValueError('Completed context must contain 1..256 tokens')
    if (type(words) is not list or len(words) != 35 or
        any(type(v) is not int or not 0 <= v <= 0xffffffff for v in words)):
        raise ValueError('Expected 35 unsigned 32-bit register values')
    if words[:3] != [0x4b563031, 0, 0]:
        raise ValueError('Wrong ABI, busy snapshot or overflow')
    c = words[3:]
    checks = {
        'phase partition': c[0] > 0 and sum(c[1:20]) == c[0],
        'no fault': c[19] == 0,
        'accepted tokens': c[20] == tokens,
        'accepted scores': c[21] == 320*tokens,
        'cache transfers': c[25] == 32*tokens*(tokens+1) and c[25] <= c[8],
        'valid-score cycles': c[21]+c[22] <= c[18],
        'cache request bubbles': c[23] <= c[8],
        'cache response bubbles': c[24] <= c[8],
        'feed-forward subregions': all(c[i] > 0 for i in (26,27,28)) and sum(c[26:29]) <= c[14],
        'reserved zero': c[29] == 0,
        'read event bound': c[30] <= c[0],
        'write event bound': c[31] <= c[0],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError('Counter invariants differ: '+', '.join(failed))
    return {'abi':'KV01','tokens':tokens,'scores':320*tokens,'busy_cycles':c[0],
            'phase_cycles':c[1:20],'counters':c,'overflow':False}
