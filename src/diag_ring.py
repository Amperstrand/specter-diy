# D7: pre-allocated diagnostic ring — GC-safe, no allocation after init
# 16 slots, 120 chars each, append-only. Flushed to screen when GUI is up.

_ring = [""] * 16
_idx = 0

def trace(tag, msg=""):
    global _idx
    slot = _idx % 16
    try:
        _ring[slot] = tag + ":" + msg[:110]
    except Exception:
        _ring[slot] = tag + ":<write-error>"
    _idx += 1

def flush_text():
    out = []
    start = max(0, _idx - 16)
    for i in range(start, _idx):
        out.append(_ring[i % 16])
    return "\n".join(out)

def count():
    return _idx
