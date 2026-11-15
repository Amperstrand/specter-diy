"""Host-side Satochip signing battery on the CardMan seat.

Real card, host-emulated everything else, zero bench-device involvement.
Uses the m2-satochip client (with the P2=0x00 signing fix) over a pyscard
adapter. Verifies every signature against the card's authentikey-derived
pubkey, host-side, with embit.

Owner-sanctioned 2026-11-15; cardbench coordination note in their ledger.
PIN discipline: single verify with the recorded bench PIN; abort on any
PIN error without retry (retry counters are precious).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "f469-disco", "libs", "common"))

# stub the micropython-only modules BEFORE importing the client tree
import types
for name, attrs in {
    "pyb": {"Pin": type("Pin", (), {"cpu": types.SimpleNamespace()}), "UART": type("UART", (), {})},
    "uscard": {"Reader": type("Reader", (), {}),
               "SmartcardException": type("SmartcardException", (Exception,), {})},
    "lvgl": {"lv": types.SimpleNamespace()},
}.items():
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m

_mp = types.ModuleType("micropython")
_mp.const = lambda x: x
sys.modules["micropython"] = _mp

# gui stubs BEFORE the client tree import
_disp = types.ModuleType("display")
for fn in ("init", "width", "height", "backlight", "buffer", "send",
           "commit", "clear", "fill", "draw_image", "draw_text", "get"):
    setattr(_disp, fn, lambda *a, **k: None)
sys.modules["display"] = _disp

# remaining micropython stdlib shims
import hashlib as _hashlib

# REAL AES-128-CBC for ucryptolib.aes(key, 2, IV). The previous identity
# stub is the REAL root cause of the "KDF mismatch" misdiagnosis: the
# channel MAC is computed over the WIRE bytes (iv||len||ct), so an
# identity cipher still produces a MAC the card verifies — the card then
# AES-decrypts "ciphertext" that was never encrypted, gets garbage, and
# the inner INS dispatch returns 6D00 (observed 2026-11-15). pysaudit
# (2026-11-04) proved the channel crypto byte-for-byte conformant to the
# v0.14-0.2 applet; Toporin v0.14-0.1/-0.2/v0.16 tags share the same
# HMAC-SHA160 sc_key/sc_mac KDF — there is no v0.14/v0.16 KDF split.
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class _AESCipher:
    def __init__(self, key, mode, IV=None):
        if mode != 2:
            raise ValueError("host shim: ucryptolib CBC(2) only")
        self._key = bytes(key)
        self._iv = bytes(IV) if IV is not None else b"\x00" * 16

    def encrypt(self, data):
        enc = Cipher(algorithms.AES(self._key),
                     modes.CBC(self._iv)).encryptor()
        return enc.update(bytes(data)) + enc.finalize()

    def decrypt(self, data):
        dec = Cipher(algorithms.AES(self._key),
                     modes.CBC(self._iv)).decryptor()
        return dec.update(bytes(data)) + dec.finalize()


_uc = types.ModuleType("ucryptolib")
_uc.aes = lambda key, mode, IV=None: _AESCipher(key, mode, IV)
sys.modules["ucryptolib"] = _uc
_uio = types.ModuleType("uio")
_uio.StringIO = __import__("io").StringIO
sys.modules["uio"] = _uio
_utime = types.ModuleType("utime")
import time as _t
_utime.ticks_ms = lambda: int(_t.monotonic() * 1000)
_utime.ticks_diff = lambda a, b: a - b
_utime.sleep_ms = lambda ms: _t.sleep(ms / 1000)
_utime.localtime = lambda ts=None: _t.localtime(ts if ts is not None else _t.time()) + (0,)
_utime.time = _t.time
sys.modules["utime"] = _utime

# REAL secp256k1 adapter over the python-ecdsa package — the channel needs
# genuine EC serialization (native_support's stub emits zero points, which
# the card rejects with 6F00; the host embit install lacks its C lib)
import hashlib as _hl
import ecdsa as _ecdsa

_ec = types.ModuleType("secp256k1")
_ec.EC_UNCOMPRESSED = 0
_ec.EC_COMPRESSED = 1


def _vk_from(obj):
    """obj: ecdsa VerifyingKey or bytes — normalize to VerifyingKey."""
    if isinstance(obj, _ecdsa.VerifyingKey):
        return obj
    return _ecdsa.VerifyingKey.from_string(bytes(obj)[-64:], curve=_ecdsa.SECP256k1)


_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F


def _decompress(d33):
    """Compressed (0x02/0x03|x) -> (x, y) — secp256k1, p = 3 mod 4."""
    x = int.from_bytes(d33[1:], "big")
    y2 = (pow(x, 3, _P) + 7) % _P
    y = pow(y2, (_P + 1) // 4, _P)
    if pow(y, 2, _P) != y2:
        raise ValueError("point not on curve")
    if (y & 1) != (d33[0] & 1):
        y = _P - y
    return x, y


def _pub_parse(data):
    d = bytes(data)
    if len(d) == 33:
        x, y = _decompress(d)
    else:
        x = int.from_bytes(d[1:33], "big")
        y = int.from_bytes(d[33:65], "big")
    return _ecdsa.VerifyingKey.from_string(
        x.to_bytes(32, "big") + y.to_bytes(32, "big"), curve=_ecdsa.SECP256k1)


def _pub_serialize(vk, flag=_ec.EC_UNCOMPRESSED):
    pt = vk.pubkey.point
    x, y = pt.x(), pt.y()
    if flag == _ec.EC_UNCOMPRESSED:
        return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")
    hdr = b"\x03" if y & 1 else b"\x02"
    return hdr + x.to_bytes(32, "big")


def _sig_parse(der):
    r, s = _ecdsa.util.sigdecode_der(bytes(der), _ecdsa.SECP256k1.order)
    return (r, s)


def _verify(sig_rs, digest, vk):
    from ecdsa.util import sigencode_string
    if isinstance(sig_rs, tuple):
        raw = sigencode_string(sig_rs[0], sig_rs[1], _ecdsa.SECP256k1.order)
    else:
        raw = bytes(sig_rs)
    return vk.verify_digest(_ecdsa.ecdsa.Signature.from_bytes(raw), bytes(digest))


_ec.ec_pubkey_create = lambda secret: _ecdsa.SigningKey.from_string(bytes(secret)[:32], curve=_ecdsa.SECP256k1).get_verifying_key()
_ec.ec_pubkey_parse = _pub_parse
_ec.ec_pubkey_serialize = _pub_serialize
class _Pub:
    """Mutable pubkey wrapper: tweak_mul replaces the inner vk in place."""

    def __init__(self, vk):
        self.vk = vk


def _tm(pub, scalar):
    if isinstance(pub, _Pub):
        base = pub.vk.pubkey.point
    else:
        base = _vk_from(pub).pubkey.point
    from ecdsa.ellipticcurve import Point
    pt = Point(_ecdsa.SECP256k1.curve, base.x(), base.y(), _ecdsa.SECP256k1.order)
    res = int.from_bytes(bytes(scalar)[:32], "big") * pt
    pub.vk = _ecdsa.VerifyingKey.from_string(
        res.x().to_bytes(32, "big") + res.y().to_bytes(32, "big"),
        curve=_ecdsa.SECP256k1)
    return None


_ec.ec_pubkey_tweak_mul = _tm

# pubkey objects must round-trip through serialize/parse as _Pub
_orig_serialize = _pub_serialize
_orig_parse = _pub_parse


def _ser2(vk_or_pub, flag=_ec.EC_UNCOMPRESSED):
    vk = vk_or_pub.vk if isinstance(vk_or_pub, _Pub) else _vk_from(vk_or_pub)
    return _orig_serialize(vk, flag)


def _parse2(data):
    return _Pub(_orig_parse(data))


_ec.ec_pubkey_serialize = _ser2
_ec.ec_pubkey_parse = _parse2
_vk_from_orig = _vk_from


def _vk_from2(obj):
    return obj.vk if isinstance(obj, _Pub) else _vk_from_orig(obj)


_vk_from = _vk_from2
_ec.ecdsa_signature_parse_der = _sig_parse
_ec.ecdsa_verify = lambda sig, digest, pub: _verify(sig, digest, _vk_from(pub))
sys.modules["secp256k1"] = _ec

# sys.path for the client tree + the repo's native stubs (embit.ec on CPython)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "test"))
from native_support import setup_native_stubs  # noqa: E402
setup_native_stubs()
# native_support clobbers sys.modules['secp256k1'] with zero-point stubs —
# re-install the real adapter AFTER it
sys.modules["secp256k1"] = _ec

from smartcard.System import readers  # noqa: E402
from smartcard.CardConnection import CardConnection  # noqa: E402


class PyscardConnection:
    """Adapter: the m2 client's connection interface over pyscard."""

    def __init__(self):
        for r in readers():
            if "CardMan" in str(r):
                self.conn = r.createConnection()
                self.conn.connect()
                self.T1_protocol = 1
                return
        raise RuntimeError("CardMan reader not found")

    def isCardInserted(self):
        return True

    def transmit(self, apdu):
        resp, sw1, sw2 = self.conn.transmit(list(bytes(apdu)))
        return bytes(resp), sw1, sw2

    def connect(self, proto=None):
        pass

    def disconnect(self):
        try:
            self.conn.disconnect()
        except Exception:
            pass


def main(sign_count=25):
    from keystore.javacard.applets.satochip_applet import SatochipApplet
    conn = PyscardConnection()
    applet = SatochipApplet(conn)
    applet.select()
    print("applet selected")
    # applet version first — plaintext GET_STATUS (INS 0x3C), no SC needed
    resp, sw1, sw2 = applet.get_card_status()
    if sw1 == 0x90:
        st = applet.parse_status(bytes(resp))
        print("CARD STATUS:", st)
    else:
        print(f"GET_STATUS SW={sw1:02x}{sw2:02x}")
    applet.init_secure_channel()
    print("secure channel up")

    # PIN first: v0.14 requires verification before any key op (9C06)
    try:
        applet.verify_pin("1234")
        print("PIN verified")
    except Exception as e:
        print("PIN ERROR — ABORT (no retries):", str(e)[:160])
        return 2

    # applet status after PIN (tries remaining)
    try:
        resp, sw1, sw2 = applet.get_card_status()
        st = applet.parse_status(bytes(resp))
        print("status:", {k: st[k] for k in
                          ("PIN0_remaining_tries", "is_seeded",
                           "setup_done")})
    except Exception as e:
        print("get_card_status:", str(e)[:120])

    # authentikey via xpub of the master path
    pub0, cc0 = applet.get_extended_key(b"")  # master, P2=0x40 (watch-only ok)
    print("master pubkey:", pub0.hex()[:24], "…")

    # signing battery: derive full keys (P2=0x00) + sign + verify host-side.
    # Pubkey parity: the coordx response may lack the self-signature
    # (no-cache 0x80 derivations) — the signature itself pins the parity,
    # so verify against both and count a match on either.
    def _vk_for(prefix, pub33):
        x, y = _decompress(prefix + bytes(pub33)[1:])
        return _ecdsa.VerifyingKey.from_string(
            x.to_bytes(32, "big") + y.to_bytes(32, "big"),
            curve=_ecdsa.SECP256k1)

    ok = fail = 0
    for i in range(sign_count):
        path = "m/84h/0h/0h/0/%d" % i
        import hashlib
        digest = hashlib.sha256(b"cardman battery %d" % i).digest()
        try:
            pub, _cc = applet.get_extended_key(path, for_signing=True)
            sig = applet.sign_transaction_hash(0xFF, digest)
            r, s = _sig_parse(sig)
            if (r, s) != (min(r, _ecdsa.SECP256k1.order - r),
                          min(s, _ecdsa.SECP256k1.order - s)):
                print(f"  HIGH-S at {path}")
            raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
            verified = False
            for prefix in (b"\x02", b"\x03"):
                try:
                    if _vk_for(prefix, pub).verify_digest(raw_sig, digest):
                        verified = True
                        break
                except _ecdsa.BadSignatureError:
                    continue
            if verified:
                ok += 1
            else:
                fail += 1
                print(f"  SIGN MISMATCH at {path}")
        except Exception as e:
            fail += 1
            print(f"  op failed at {path}: {str(e)[:100]}")
    print(f"BATTERY: {ok} verified / {fail} failed (of {sign_count})")
    conn.disconnect()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 25))
