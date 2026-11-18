"""CardMan/virtual/replay backends for the javacard program suite (P6 tier).

Tiers:
- cardman: real J3R180 in the OMNIKEY via pcscd (USCARD_BACKEND=pyscard); skips
  without hardware (reader/card missing or explicit CARDBENCH_SKIP_CARD=1)
- replay: hardware-free — deterministic vector session (SUITE_DETERMINISTIC
  capture), client drift guarded by the replay backend's byte-exact matching
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(1, os.path.join(REPO, "src"))
sys.path.insert(1, os.path.join(REPO, "f469-disco/libs/common/embit/src"))
sys.path.insert(1, os.path.join(REPO, "f469-disco/libs/common"))
sys.path.insert(1, os.path.join(REPO, "f469-disco/libs/unix"))
sys.path.append(os.path.join(REPO, "f469-disco/usermods/udisplay_f469/display_unixport"))

import types as _types


class _DummyMeta(type):
    def __getattr__(cls, key):
        return _Dummy

    def __add__(cls, o):
        return _Dummy()

    def __radd__(cls, o):
        return _Dummy()

    def __or__(cls, o):
        return _Dummy()

    def __ror__(cls, o):
        return _Dummy()


class _Dummy(metaclass=_DummyMeta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, key):
        return _Dummy

    def __call__(self, *a, **k):
        return _Dummy()

    def __or__(self, o):
        return _Dummy()

    def __ror__(self, o):
        return _Dummy()

    def __add__(self, o):
        return _Dummy()

    def __radd__(self, o):
        return _Dummy()

    def __str__(self):
        return "<dummy>"

    def __len__(self):
        return 0

    def __iter__(self):
        return iter(())

    def __int__(self):
        return 0


def _dummy_module(name):
    m = _types.ModuleType(name)
    m.__getattr__ = lambda attr: _Dummy
    return m


for _name in ("lvgl", "display", "udisplay", "SDL", "qrcode"):
    sys.modules.setdefault(_name, _dummy_module(_name))

# pytest pre-imports stdlib platform into sys.modules, so path order cannot
# shadow it for the device code - swap in src/platform.py explicitly
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "platform", os.path.join(REPO, "src", "platform.py"))
_device_platform = _ilu.module_from_spec(_spec)
sys.modules["platform"] = _device_platform
_spec.loader.exec_module(_device_platform)

import time as _t

if not hasattr(_t, "ticks_ms"):
    _t.ticks_ms = lambda: int(_t.monotonic() * 1000) & 0x3FFFFFFF
    _t.ticks_us = lambda: int(_t.monotonic() * 1_000_000) & 0x3FFFFFFF
    _t.ticks_diff = lambda a, b: a - b
    _t.ticks_add = lambda a, b: (a + b) & 0x3FFFFFFF
    _t.sleep_ms = lambda ms: _t.sleep(ms / 1000)

VECTORS = os.path.join(os.path.dirname(__file__), "vectors")

import pytest


def _seed_rng():
    import hashlib
    import rng
    ctr = [0]

    def seeded(n):
        ctr[0] += 1
        return hashlib.sha256(b"cardbench-replay-%d" % ctr[0]).digest()[:n]

    rng.get_random_bytes = seeded


def _connection(backend, reader=None):
    # uscard binds its backend at import time; tiers can share a pytest process
    # only if we re-execute the binding (and util's cached handle on it)
    import importlib
    os.environ["USCARD_BACKEND"] = backend
    if reader:
        os.environ["USCARD_READER"] = reader
    import uscard as _uscard
    importlib.reload(_uscard)
    import keystore.javacard.util as util
    importlib.reload(util)
    return util.get_connection()


@pytest.fixture(scope="function")
def cardman_conn():
    if os.environ.get("CARDBENCH_SKIP_CARD") == "1":
        pytest.skip("card tier disabled (CARDBENCH_SKIP_CARD=1)")
    try:
        conn = _connection("pyscard", os.environ.get("CARDBENCH_READER", "OMNIKEY"))
        conn.getATR()
    except Exception as e:
        pytest.skip("no CardMan card available: %r" % e)
    import suite
    suite.identify(conn)  # CPLC allowlist gate before any applet traffic
    return conn


@pytest.fixture(scope="session")
def replay_conn():
    vec = os.path.join(VECTORS, "cardman-full-session.jsonl")
    if not os.path.exists(vec):
        pytest.skip("no vector session captured")
    os.environ["USCARD_TRANSCRIPT"] = vec
    _seed_rng()
    return _connection("replay")

# filmspike capture contract: (step, timestamp, frame, event) tuples as JSONL
# consumed by the test-films 3-way sync renderer; coordinate format via REPORT block
import json as _json

_EVENTS_PATH = os.environ.get("CARDBENCH_EVENTS")


def _emit(step, event="ok", frame=None):
    if not _EVENTS_PATH:
        return
    with open(_EVENTS_PATH, "a") as f:
        f.write(_json.dumps({"step": step, "ts": _t.time(),
                             "frame": frame, "event": event}) + "\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        _emit(item.name, "pass" if rep.passed else "fail",
              frame=getattr(item, "card_frame", None))
    elif rep.when == "setup" and rep.skipped:
        _emit(item.name, "skip", rep.longrepr and str(rep.longrepr) or "")
