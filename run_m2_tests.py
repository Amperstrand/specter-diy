import os, sys
os.environ["USCARD_BACKEND"] = "sim"
sys.path.insert(1, "./src")
sys.path.insert(1, "./f469-disco/libs/common/embit/src")
sys.path.insert(1, "./f469-disco/libs/common")
sys.path.insert(1, "./f469-disco/libs/unix")
sys.path.append("./f469-disco/usermods/udisplay_f469/display_unixport")
sys.path.append("./test/tests")
import types as _types
class _DummyMeta(type):
    def __getattr__(cls, key): return _Dummy
    def __add__(cls, o): return _Dummy()
    def __radd__(cls, o): return _Dummy()
    def __or__(cls, o): return _Dummy()
    def __ror__(cls, o): return _Dummy()
class _Dummy(metaclass=_DummyMeta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, key): return _Dummy
    def __call__(self, *a, **k): return _Dummy()
    def __or__(self, o): return _Dummy()
    def __ror__(self, o): return _Dummy()
    def __add__(self, o): return _Dummy()
    def __radd__(self, o): return _Dummy()
    def __str__(self): return "<dummy>"
    def __len__(self): return 0
    def __iter__(self): return iter(())
    def __int__(self): return 0
def _dm(n):
    m = _types.ModuleType(n); m.__getattr__ = lambda a: _Dummy; return m
for n in ("lvgl", "display", "udisplay", "SDL", "qrcode"):
    sys.modules[n] = _dm(n)
_common = "./f469-disco/libs/common"
sys.path.remove(_common)
import asyncio as _stdlib_asyncio
sys.modules["asyncio"] = _stdlib_asyncio
sys.path.insert(1, _common)

import time as _t
if not hasattr(_t, "ticks_ms"):
    _t.ticks_ms = lambda: int(_t.monotonic() * 1000) & 0x3FFFFFFF
    _t.ticks_us = lambda: int(_t.monotonic() * 1_000_000) & 0x3FFFFFFF
    _t.ticks_diff = lambda a, b: a - b
    _t.ticks_add = lambda a, b: (a + b) & 0x3FFFFFFF
    _t.sleep_ms = lambda ms: _t.sleep(ms / 1000)

import unittest
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for mod in ("test_javacard_keystore", "test_secure_applet_base", "test_satochip_v016", "test_seedkeeper_eeprom_corruption"):
    try:
        m = __import__(mod)
        suite.addTests(loader.loadTestsFromModule(m))
    except Exception as e:
        print("COLLECT-FAIL %s: %r" % (mod, e))
runner = unittest.TextTestRunner(verbosity=1)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
