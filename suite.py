"""cardbench dev-suite: one-command real-card gate for the v0.14-focused javacard program.

Runs applet stories against a physical J3R180 through the specter-diy unix-sim
client stack + cardbench/unix-pyscard-backend. Exit 0 = all green.

Env:
  USCARD_BACKEND=pyscard (required for real card)
  USCARD_READER=<pcscd reader substring>   (default OMNIKEY)
Baseline discipline:
  MemoryCard ends at PIN='1234' + fixed sentinel secret (deterministic state,
  safe to re-run; never guesses an unknown PIN - if PIN is set to something
  else, that story FAILS loudly instead of retrying).
"""
import os
import sys
import time

sys.path.insert(1, "./src")
sys.path.insert(1, "./f469-disco/libs/common/embit/src")
sys.path.insert(1, "./f469-disco/libs/common")
sys.path.insert(1, "./f469-disco/libs/unix")
sys.path.append("./f469-disco/usermods/udisplay_f469/display_unixport")

# --- headless stubs (GUI chain pulled by keystore/__init__) ---
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
    sys.modules[_name] = _dummy_module(_name)

import time as _t

if not hasattr(_t, "ticks_ms"):
    _t.ticks_ms = lambda: int(_t.monotonic() * 1000) & 0x3FFFFFFF
    _t.ticks_us = lambda: int(_t.monotonic() * 1_000_000) & 0x3FFFFFFF
    _t.ticks_diff = lambda a, b: a - b
    _t.ticks_add = lambda a, b: (a + b) & 0x3FFFFFFF
    _t.sleep_ms = lambda ms: _t.sleep(ms / 1000)

if os.environ.get("USCARD_BACKEND") == "replay" or os.environ.get("SUITE_DETERMINISTIC") == "1":
    # byte-exact replay needs deterministic client randomness (channel-open sends
    # a fresh ephemeral pubkey); patch rng BEFORE keystore modules bind `from rng import`
    # SUITE_DETERMINISTIC=1 => vector-capture mode: record WITH the seed for later replay
    import hashlib as _hl
    import rng as _rng

    _ctr = [0]

    def _seeded(nbytes):
        _ctr[0] += 1
        return _hl.sha256(b"cardbench-replay-%d" % _ctr[0]).digest()[:nbytes]

    _rng.get_random_bytes = _seeded

from keystore.javacard.util import get_connection
from keystore.javacard.applets.memorycard import MemoryCardApplet

PIN_BASELINE = "1234"
SECRET_SENTINEL = b"cardbench-suite-sentinel-v1"

FAILURES = []


def raw_transmit(conn, hexstr):
    resp = conn.transmit(bytes.fromhex(hexstr))
    sw = resp[-2:]
    if sw != b"\x90\x00":
        raise RuntimeError("SW=%s for %s" % (sw.hex().upper(), hexstr))
    return resp[:-2]


# ---------- identify first (pure read; no GP auth anywhere in this suite) ----------

def identify(conn):
    # CPLC only answers at ISD context; a warm connect after an applet session
    # can leave another applet selected, so re-select the ISD first (pure read).
    raw_transmit(conn, "00A4040008A000000151000000")
    cplc = raw_transmit(conn, "80CA9F7F00")
    body = cplc[3:]  # strip 9F 7F 2A (tag + length byte)
    # bench convention (ledger ccid-firmware-rs#127): serial = value[12:16], batch = value[16:18]
    serial = body[12:16].hex().upper()
    batch = body[16:18].hex().upper()
    known = {"50972320": "seat1/OmniKey", "50942720": "seat2/Cherry-F469"}
    if serial not in known:
        raise RuntimeError("unknown card CPLC %s - refusing (identify-first doctrine)" % serial)
    print("card: CPLC serial %s batch %s (%s) ATR %s"
          % (serial, batch, known[serial], conn.getATR().hex().upper()))
    return serial


# ---------- stories ----------

def story_teapot(conn):
    data = raw_transmit(conn, "00A4040006B00B5111CA0100")
    got = raw_transmit(conn, "B0A10000")
    raw_transmit(conn, "B0A200001474617267657462656e63682d73756974652d7631")
    back = raw_transmit(conn, "B0A10000")
    assert back == b"targetbench-suite-v1", back
    return "select+get+put+get roundtrip"


def story_memorycard(conn):
    app = MemoryCardApplet(conn)
    app.select()
    app.open_secure_channel()
    app.ping()
    pub = app.card_pubkey
    app.get_pin_status()
    if not app.is_pin_set:
        app.set_pin(PIN_BASELINE)
    else:
        app.unlock(PIN_BASELINE)  # fails loudly if PIN != baseline (no guessing)
    app.save_secret(SECRET_SENTINEL)
    got = app.get_secret()
    assert got == SECRET_SENTINEL, "secret mismatch"
    app.lock()
    assert app.is_locked
    return "channel+pin(%s)+secret-roundtrip pub=%s.." % (PIN_BASELINE, pub.hex()[:12])


def story_singleusekey(conn):
    raw_transmit(conn, "00A4040006B00B5111CD0100")
    rnd = raw_transmit(conn, "B0B10000")
    assert len(rnd) == 32, rnd.hex()
    return "select+unsecure-random(32B)"


def story_blindoracle(conn):
    raw_transmit(conn, "00A4040006B00B5111CE0100")
    pub = raw_transmit(conn, "B0B20000")
    assert len(pub) == 65 and pub[0] == 0x04, pub.hex()
    return "select+static-pubkey(65B) %s.." % pub.hex()[:12]


def story_satochip(conn):
    import hashlib
    from keystore.javacard.applets.satochip_applet import SatochipApplet
    from embit.util import secp256k1

    seed = None
    try:
        from embit.bip39 import mnemonic_to_seed
        seed = mnemonic_to_seed(
            "abandon abandon abandon abandon abandon abandon abandon "
            "abandon abandon abandon abandon about"
        )
    except ImportError:
        seed = None
    if seed is None:
        raise RuntimeError("embit bip39 unavailable - cannot derive canonical seed")
    app = SatochipApplet(conn)
    app.select()
    st = app.parse_status(app.get_card_status())
    assert (st["protocol_major_version"], st["protocol_minor_version"]) == (0x00, 0x0E), st
    assert (st["applet_major_version"], st["applet_minor_version"]) == (0x00, 0x02), st

    if not st["setup_done"]:
        pin, puk = b"1234", b"12345678"
        d = bytes([8]) + b"Muscle00" + bytes([3, 3])
        d += bytes([len(pin)]) + pin + bytes([len(puk)]) + puk + bytes([3, 3])
        d += bytes([len(pin)]) + pin + bytes([len(puk)]) + puk
        d += (32).to_bytes(2, "big") + b"\x00\x00" + b"\x00\x00\x00" + b"\x00\x00"
        app.init_secure_channel()
        try:
            app.secure_request(bytes([app.CLA, 0x2A, 0x00, 0x00, len(d)]) + d)
        except Exception:
            # recovery path: a previously crashed setup leaves pin0 already rotated
            d = bytes([4]) + pin + d[9:]
            app.init_secure_channel()
            app.secure_request(bytes([app.CLA, 0x2A, 0x00, 0x00, len(d)]) + d)
        st = app.parse_status(app.get_card_status())
        assert st["setup_done"], st

    app.init_secure_channel()
    app.verify_pin("1234")

    if not st.get("is_seeded"):
        app.secure_request(bytes([app.CLA, 0x6C, len(seed), 0x00, len(seed)]) + seed)
        st = app.parse_status(app.get_card_status())
        assert st["is_seeded"], st
    # v0.14-0.2 hazard: resetBIP32Seed (0x77) permanently breaks derivation on-card
    # (clears bip32_extendedkey curve params; only setup() restores them).

    try:
        auth = bytes(app.get_authentikey())
    except (ValueError, Exception):
        _ar = bytes(app.secure_request(bytes([app.CLA, 0x73, 0x00, 0x00])))
        auth = _ar  # raw [len|coordx|sig_size|sig] — format checked below
    if auth[:2] == b"\x00\x20":
        assert len(auth) > 40, auth.hex()  # v0.14 raw format: [len|coordx|sig]
    elif auth[:1] in (b"\x02", b"\x03") and len(auth) == 33:
        pass  # recovered compressed pubkey (javacard's Y-parity fix)
    else:
        raise AssertionError("unexpected authentikey format: %s" % auth.hex())

    try:
        pub, cc = app.get_extended_key("m/44'/0'/0'/0/0")
    except (ValueError, Exception):
        # v0.14: 0x6D returns x-only (no self-sig for Y-parity recovery);
        # parse raw response directly
        from keystore.javacard.util import path_to_bytes
        _path = path_to_bytes("m/44'/0'/0'/0/0")
        _depth = len(_path) // 4
        _apdu = bytes([app.CLA, 0x6D, _depth, 0x40, len(_path)]) + _path
        _resp = bytes(app.secure_request(_apdu))
        cc = _resp[0:32]
        _xsize = int.from_bytes(_resp[32:34], "big")
        pub = b"\x02" + _resp[34:34 + _xsize]
    pub, cc = bytes(pub), bytes(cc)
    from embit.bip32 import HDKey
    leaf = HDKey.from_seed(seed).derive("m/44'/0'/0'/0/0").to_public()
    # v0.14 returns x-only pubkeys (no parity bit); the client defaults to 0x02.
    assert pub[1:] == leaf.key.serialize()[1:], "card x != embit x: %s vs %s" % (
        pub.hex(), leaf.key.serialize().hex())
    assert cc == leaf.chain_code, "card chaincode != embit"

    msghash = hashlib.sha256(b"cardbench sign test v1").digest()
    sig = bytes(app.sign_transaction_hash(0xFF, msghash))
    sig_obj = secp256k1.ecdsa_signature_normalize(
        secp256k1.ecdsa_signature_parse_der(sig))
    verified = any(
        secp256k1.ecdsa_verify(sig_obj, msghash, secp256k1.ec_pubkey_parse(p + pub[1:]))
        for p in (b"\x02", b"\x03")
    )
    assert verified, "signature does not verify under either parity of the card pubkey"
    return "proto0.14 channel+setup+pin+seed+authentikey+xpub+sign(verified)"


def story_seedkeeper(conn):
    from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
    from keystore.javacard.applets.applet import ISOException as SKISO

    mnemonic = ("abandon " * 11 + "about").encode()
    seed64 = bytes.fromhex(
        "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc1"
        "9a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4")
    app = SeedKeeperApplet(conn)
    app.select()
    app.init_secure_channel()
    try:
        headers = app.list_secret_headers()
    except Exception as e:  # 9c04=fresh card, 9c06=pin needed - neither burns PIN tries
        if "9c04" in str(e):
            app.setup()
            app.verify_pin("1234")
            headers = []
        elif "9c06" in str(e):
            app.verify_pin("1234")
            headers = []
        else:
            raise
    have = {h.get("label") for h in (headers or [])}
    if "cardbench-bip39" not in have:
        app.import_secret(SeedKeeperApplet.SECRET_TYPE_BIP39_MNEMONIC,
                          "cardbench-bip39", mnemonic)
    if "cardbench-seed64" not in have:
        app.import_secret(SeedKeeperApplet.SECRET_TYPE_MASTER_SEED,
                          "cardbench-seed64", seed64)
    by_label = {h["label"]: h for h in app.list_secret_headers()}
    assert "cardbench-bip39" in by_label and "cardbench-seed64" in by_label, sorted(by_label)
    assert bytes(app.export_secret(by_label["cardbench-bip39"]["id"])) == mnemonic
    assert bytes(app.export_secret(by_label["cardbench-seed64"]["id"])) == seed64
    st = app.get_seedkeeper_status()
    assert st.get("nb_secrets", 0) >= 2, st
    return "channel+pin+2-secrets store/list/export roundtrip (%d secrets)" % st["nb_secrets"]


STORIES = [
    ("teapot", story_teapot),
    ("memorycard", story_memorycard),
    ("singleusekey", story_singleusekey),
    ("blindoracle", story_blindoracle),
    ("satochip-v0.14-0.2", story_satochip),
    ("seedkeeper-v0.2-0.1", story_seedkeeper),
]


def main():
    backend = os.environ.get("USCARD_BACKEND", "sim")
    virtual = os.environ.get("SUITE_TARGET") == "virtual"
    if backend not in ("pyscard", "replay") and not (backend == "sim" and virtual):
        print("refusing: USCARD_BACKEND=%r - real-card gate (pyscard), card-less replay, or"
              " sim+differential only with SUITE_TARGET=virtual" % backend)
        return 2
    conn = get_connection()
    print("reader: %s" % os.environ.get("USCARD_READER", "OMNIKEY"))
    print("backend: %s" % type(conn).__name__)
    if virtual:
        print("target: VIRTUAL (differential run - identify gate relaxed)")
    else:
        identify(conn)
    wanted = [s.strip() for s in os.environ.get("SUITE_STORIES", "").split(",") if s.strip()]
    stories = [(n, f) for n, f in STORIES if not wanted or n in wanted]
    t_all = time.perf_counter()
    import uscard
    for name, fn in stories:
        uscard.annotate(name)
        t0 = time.perf_counter()
        try:
            detail = fn(conn) or ""
            print("PASS %-24s (%6.1f ms) %s" % (name, (time.perf_counter() - t0) * 1000, detail))
        except Exception as e:
            FAILURES.append((name, repr(e)))
            print("FAIL %-24s (%6.1f ms) %r" % (name, (time.perf_counter() - t0) * 1000, e))
    print("-" * 60)
    print("SUITE: %d/%d stories green in %.1f s"
          % (len(stories) - len(FAILURES), len(stories), time.perf_counter() - t_all))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
