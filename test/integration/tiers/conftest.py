"""Tiered bench harness — one suite, four backends, escalation by parameter.

pytest --backend=dry|sim|cardman|device [--sign-count N]
(or TIER_BACKEND=device pytest …)

The backend fixture yields a Bench object with a uniform interface; tests
declare needs via markers (@pytest.mark.needs("card")) and skip cleanly on
tiers that cannot provide them.

2026-11-15 hardening (tiers-review.md items 1/2/4/5):
- lease: subprocess exit code decides, substring optimism does not; a
  run without the lease FAILS CLOSED instead of reading a stale console
  log while another lane drives the DUT.
- replies: each daemon log line is <ISO-ts> + b'…repr…'; TestMode emits
  J:{…} JSON result events ("cmd", "ok", "reply"). We unescape the repr
  layer (ast.literal_eval), JSON-parse the event, and correlate by
  timestamp taken BEFORE the send — a bounded poll (0.5 s tick), never a
  fixed sleep, never a reply from a previous run.
- capabilities: "card" = any card-shaped signing path (mock/recorded at
  dry); "card-real" = physical card (device/cardman only).
- authentikey_for() declared on every bench (NotImplementedError), so the
  cardman-day mismatch fails loudly at construction, not mid-test.
"""
import ast
import json
import os
import re
import subprocess
import sys
import time
import types
from datetime import datetime

import pytest

COORDINATOR = "192.168.13.208:20408"
DEVICE_PLACE = "f469-specter-film"
FIFO = "/tmp/opencode/f469-console.in"
CONSOLE_LOG = "/tmp/opencode/f469-console.log"

LOG_LINE_RE = re.compile(r"^(\S+)\s+b('.*')\s*$")
REPLY_WAIT_S = 30
RECORD = False
FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "device.jsonl")
FW_SHA = "unknown"
POLL_S = 0.5


def sh(cmd, timeout=90):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def console_send(cmd):
    """Write one command to the daemon FIFO. Returns False (and the caller
    must fail) when the daemon is not reading — never send-and-hope."""
    try:
        fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        os.write(fd, (cmd + "\n").encode())
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _parse_log_line(line):
    """Daemon log line -> (epoch_ts, decoded_content) or None."""
    m = LOG_LINE_RE.match(line.strip())
    if not m:
        return None
    try:
        content = ast.literal_eval("b" + m.group(2)).decode("utf-8", "replace")
        ts = datetime.fromisoformat(m.group(1)).timestamp()
    except (ValueError, SyntaxError):
        return None
    return ts, content


def console_reply(cmd_name, sent_ts, wait_s=REPLY_WAIT_S):
    """Poll for the J:{…} result event of cmd_name logged AFTER sent_ts.

    A single daemon log line can bundle several console reads, each ending
    in its own J:{…} event — parse ALL of them per line, match by cmd
    name (TestMode suffixes arguments: cmd == 'TEST_PIN:1234' for name
    'TEST_PIN'). Returns the reply string, or None on timeout.
    """
    deadline = time.time() + wait_s
    while time.time() < deadline:
        for line in reversed(sh(f"tail -n 400 {CONSOLE_LOG}").splitlines()):
            parsed = _parse_log_line(line)
            if parsed is None:
                continue
            ts, content = parsed
            if ts < sent_ts - 0.5 or "J:{" not in content:
                continue
            for m in re.finditer(r"J:(\{[^\n]*?\})(?=\n|$)", content):
                try:
                    event = json.loads(m.group(1))
                except ValueError:
                    continue
                if event.get("event") == "result" and (
                        event.get("cmd") == cmd_name
                        or (event.get("cmd") or "").startswith(cmd_name + ":")):
                    return event.get("reply", "")
        time.sleep(POLL_S)
    return None


class DryBench:
    """Transcript-driven: deterministic, zero hardware, milliseconds.

    MOCK: canned reply shapes (a recorded-status transcript, a recorded
    DER) — exercises test/parse code, no card protocol. The sign battery
    at this tier is the verifier CONTROL (host-key tautology by design).
    """

    name = "dry"
    provides = {"logic", "card", "card-mock"}

    def satochip_get_status(self):
        """GET_STATUS (INS 0x3C) via the Satochip channel or plaintext."""
        if self._is_satochip():
            # plaintext GET_STATUS works on real Satochip (no SC needed)
            try:
                data, sw1, sw2 = self.conn.transmit(
                    [0xB0, 0x3C, 0x00, 0x00])
                if sw1 == 0x90 and len(data) >= 8:
                    d = list(data)
                    return {"connected": True, "keystore_found": True,
                            "unlocked": d[4] > 0, "card_inserted": True,
                            "fingerprint": None,
                            "protocol": f"{d[0]}.{d[1]}",
                            "applet": f"{d[2]}.{d[3]}",
                            "pin_tries": d[4], "puk_tries": d[5],
                            "is_seeded": len(d) > 9 and d[9] != 0}
            except Exception:
                pass
        return {"connected": False, "keystore_found": False,
                "unlocked": False, "card_inserted": True,
                "fingerprint": None}

    def status(self):
        return {"connected": True, "keystore_found": True, "unlocked": False,
                "card_inserted": True, "fingerprint": None}

    def pin(self, pin):
        return "ERROR:6984"  # recorded: applet-level reply, unlock succeeds

    def pin_status(self):
        return {"connected": True, "unlocked": True, "keystore_found": True,
                "card_inserted": True, "fingerprint": None}

    def sign(self, message, path):
        return bytes.fromhex("3044022079be667ef9dcbbac55a06295ce870b07029bfcdb"
                             "2dce28d959f2815b16f8179802200f00")

    def authentikey_for(self, path):
        raise NotImplementedError("dry tier has no real card keys")


class DeviceBench:
    """Full integration: console daemon FIFO -> TestMode on the F469."""

    name = "device"
    provides = {"logic", "card", "card-real", "firmware", "gui", "screen"}

    def __init__(self):
        self._lease()

    def _lease(self):
        # release any stale hold first (ours or inherited), then acquire clean
        sh(f"labgrid-client -x {COORDINATOR} -p {DEVICE_PLACE} release 2>/dev/null")
        proc = subprocess.run(
            ["labgrid-client", "-x", COORDINATOR, "-p", DEVICE_PLACE,
             "acquire"], capture_output=True, text=True, timeout=60)
        out = proc.stdout + proc.stderr
        # rc==0 is the ONLY success signal — labgrid's held-place FAILURE
        # message ("…already acquired by …") contains 'acquired' too.
        self._leased = proc.returncode == 0
        if not self._leased:
            pytest.fail(f"labgrid lease on {DEVICE_PLACE} not obtained "
                        f"(rc={proc.returncode}): {out.strip()[:300]}. "
                        f"Refusing to run device-tier assertions against a "
                        f"bench another lane may be driving.")

    def release(self):
        if getattr(self, "_leased", False):
            sh(f"labgrid-client -x {COORDINATOR} -p {DEVICE_PLACE} release")

    def _cmd(self, cmd, name, wait_s=REPLY_WAIT_S):
        sent_ts = time.time()
        if not console_send(cmd):
            pytest.fail(f"FIFO {FIFO} not accepting writes — console daemon "
                        f"down? Refusing to read a stale log.")
        reply = console_reply(name, sent_ts, wait_s)
        if reply is None:
            pytest.fail(f"no J-result for {name} within {wait_s}s "
                        f"(sent {datetime.fromtimestamp(sent_ts).isoformat()})")
        if RECORD:
            os.makedirs(os.path.dirname(FIXTURES), exist_ok=True)
            with open(FIXTURES, "a") as f:
                f.write(json.dumps({"cmd": cmd, "reply": reply,
                                    "t": datetime.fromtimestamp(sent_ts).isoformat(),
                                    "fw": FW_SHA}) + "\n")
        return reply

    def satochip_get_status(self):
        """GET_STATUS (INS 0x3C) via the Satochip channel or plaintext."""
        if self._is_satochip():
            # plaintext GET_STATUS works on real Satochip (no SC needed)
            try:
                data, sw1, sw2 = self.conn.transmit(
                    [0xB0, 0x3C, 0x00, 0x00])
                if sw1 == 0x90 and len(data) >= 8:
                    d = list(data)
                    return {"connected": True, "keystore_found": True,
                            "unlocked": d[4] > 0, "card_inserted": True,
                            "fingerprint": None,
                            "protocol": f"{d[0]}.{d[1]}",
                            "applet": f"{d[2]}.{d[3]}",
                            "pin_tries": d[4], "puk_tries": d[5],
                            "is_seeded": len(d) > 9 and d[9] != 0}
            except Exception:
                pass
        return {"connected": False, "keystore_found": False,
                "unlocked": False, "card_inserted": True,
                "fingerprint": None}

    def status(self):
        reply = self._cmd("TEST_STATUS", "TEST_STATUS")
        m = re.search(r"OK:(\{.*\})", reply.replace("\r", ""))
        if not m:
            pytest.fail(f"TEST_STATUS reply not OK-dict shaped: {reply!r}")
        status = ast.literal_eval(m.group(1))
        return {k: status.get(k) for k in
                ("connected", "keystore_found", "unlocked", "card_inserted",
                 "fingerprint")}

    def pin(self, pin):
        # Post-reboot card settle is real (~30s detect incl. GUI, observed
        # longer) — bounded wait for card_inserted before the PIN round-trip.
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.status().get("card_inserted") is True:
                break
            time.sleep(2)
        else:
            pytest.fail("card not inserted/connected within 60s "
                        "(mechanical presence flake? see f469-blame.sh)")
        return self._cmd(f"TEST_PIN:{pin}", "TEST_PIN")

    def pin_status(self):
        return self.status()

    def sign(self, message, path):
        pytest.skip("TEST_SIGN firmware command pending (specter-diy #56)")

    def authentikey_for(self, path):
        pytest.skip("TEST_SIGN/authentikey export pending (specter-diy #56)")


class CardManBench:
    """Real card in the CardMan reader, host-side client."""

    name = "cardman"
    provides = {"logic", "card", "card-real"}

    def __init__(self):
        raise pytest.skip("CardMan tier pending cardbench bless "
                          "(request in the javacard lane ledger REPORT block)")

    def satochip_get_status(self):
        """GET_STATUS (INS 0x3C) via the Satochip channel or plaintext."""
        if self._is_satochip():
            # plaintext GET_STATUS works on real Satochip (no SC needed)
            try:
                data, sw1, sw2 = self.conn.transmit(
                    [0xB0, 0x3C, 0x00, 0x00])
                if sw1 == 0x90 and len(data) >= 8:
                    d = list(data)
                    return {"connected": True, "keystore_found": True,
                            "unlocked": d[4] > 0, "card_inserted": True,
                            "fingerprint": None,
                            "protocol": f"{d[0]}.{d[1]}",
                            "applet": f"{d[2]}.{d[3]}",
                            "pin_tries": d[4], "puk_tries": d[5],
                            "is_seeded": len(d) > 9 and d[9] != 0}
            except Exception:
                pass
        return {"connected": False, "keystore_found": False,
                "unlocked": False, "card_inserted": True,
                "fingerprint": None}

    def status(self):
        raise NotImplementedError

    def authentikey_for(self, path):
        raise NotImplementedError


class VpcdBench:
    """vpcd tier (L2): jCardSim applet classes behind a pcscd vpcd reader.

    Full host client stack — pyscard -> pcscd -> libifdvpcd-jcardsim.so
    (mutex-fixed driver; see specter-javacard/tests/host/) ->
    tests/tests/util/vicc.py -> jcsimcli -> SecureApplet — the SAME pcscd
    API the cardman tier will use, zero physical card. The secure-channel
    client is the ORIGINAL util/securechannel.py (proven on simulator +
    real card).

    Bench setup (fails closed with this pointer if not up):
      1. reader slot: specter-javacard/tests/host/build_libifdvpcd_jcardsim.sh
         build+deploy+setup, pcscd restart under the bench flock
      2. adapter: tmux new-session -d -s jcardsim-vpcd \
           'cd specter-javacard/tests/tests/util && python3 vicc.py'
    Provides "card-mock" (a virtual card, not "card-real"); the sign
    battery skips per-test until a sign-capable applet (m2 SatoChip) is
    served here.
    """

    name = "vpcd"
    provides = {"logic", "card", "card-mock"}

    # Version farm: maps version names to (reader_name, aid_hex)
    FARM_VERSIONS = {
        "sato-v0.6-0.3":   ("Farm sato-v0.6-0.3", "5361746f43686970"),
        "sato-v0.7-0.1":   ("Farm sato-v0.7-0.1", "5361746f43686970"),
        "sato-v0.7-0.2":   ("Farm sato-v0.7-0.2", "5361746f43686970"),
        "sato-v0.8-0.1":   ("Farm sato-v0.8-0.1", "5361746f43686970"),
        "sato-v0.9-0.1":   ("Farm sato-v0.9-0.1", "5361746f43686970"),
        "sato-v0.10-0.1":  ("Farm sato-v0.10-0.1", "5361746f43686970"),
        "sato-v0.10-0.4":  ("Farm sato-v0.10-0.4", "5361746f43686970"),
        "sato-v0.11":      ("Farm sato-v0.11", "5361746f43686970"),
        "sato-v0.12":      ("Farm sato-v0.12", "5361746f43686970"),
        "sato-v0.14-0.1":  ("Farm sato-v0.14-0.1", "5361746f43686970"),
        "sato-v0.14-0.2":  ("Farm sato-v0.14-0.2", "5361746f43686970"),
        "sato-v0.15-0.0":  ("Farm sato-v0.15-0.0", "5361746f43686970"),
        "sato-v0.15-0.1":  ("Farm sato-v0.15-0.1", "5361746f43686970"),
        "sato-v0.16-0.1":  ("Farm sato-v0.16-0.1", "5361746f43686970"),
        "v016":            ("jCardSim VPCD v016", "5361746f43686970"),
        "v014":            ("jCardSim VPCD 00 01", "5361746f43686970"),
        "sk-v0.1":         ("Farm sk-v0.1", "536565644b6565706572"),
        "sk-v0.2-0.1":     ("Farm sk-v0.2-0.1", "536565644b6565706572"),
        "mc-current":      ("Farm mc-current", "4d656d6f727943617264"),
        "secure-current":  ("Farm secure-current", "4d656d6f727943617264"),
    }

    def _resolve_reader_aid(self, applet_version):
        """Pick reader + AID from --applet-version or env vars."""
        if applet_version and applet_version in self.FARM_VERSIONS:
            reader, aid = self.FARM_VERSIONS[applet_version]
            return reader + " 00 00", aid
        # default: the working v016 reader (the base jCardSim VPCD lost its
        # pcscd slot to the driver-dedup issue after the farm deploy)
        return (os.environ.get("TIER_VPCD_READER", "jCardSim VPCD v016 00 00"),
                os.environ.get("TIER_VPCD_AID", "5361746f43686970"))
    JAVACARD_TESTS = os.environ.get(
        "TIER_SPECTER_JAVACARD",
        "/home/ubuntu/src/specter-javacard/tests/tests")

    def __init__(self, applet_version=None):
        self.READER, self.AID = self._resolve_reader_aid(applet_version)
        if self.JAVACARD_TESTS not in sys.path:
            sys.path.insert(0, self.JAVACARD_TESTS)
        self.conn = self._connect()
        self._select()
        self.sc = None
        self._sato_sc = None

    def _connect(self):
        from smartcard.CardConnection import CardConnection
        from smartcard.Exceptions import (CardConnectionException,
                                          NoCardException)
        from smartcard.System import readers
        deadline = time.time() + 30
        while True:
            rs = [r for r in readers() if self.READER in str(r)]
            if not rs:
                pytest.fail(f"reader '{self.READER}' not in pcscd list — "
                            "run build_libifdvpcd_jcardsim.sh setup + "
                            "restart pcscd (tiers README §vpcd)")
            try:
                conn = rs[0].createConnection()
                conn.connect(CardConnection.T1_protocol)
                return conn
            except (NoCardException, CardConnectionException):
                if time.time() > deadline:
                    pytest.fail(f"'{self.READER}' present but no card for "
                                "30s — is the vicc.py adapter running? "
                                "(tiers README §vpcd)")
                time.sleep(1)

    def _select(self):
        aid = bytes.fromhex(self.AID)
        data, sw1, sw2 = self.conn.transmit(
            [0x00, 0xA4, 0x04, 0x00, len(aid)] + list(aid))
        if (sw1, sw2) != (0x90, 0x00):
            pytest.fail(f"applet SELECT {self.AID} -> {sw1:02x}{sw2:02x} — "
                        "adapter serving a different applet?")

    def _request(self, apdu):
        from util.simulator import ISOException
        data, sw1, sw2 = self.conn.transmit(list(apdu))
        if (sw1, sw2) != (0x90, 0x00):
            raise ISOException(f"{sw1:02x}{sw2:02x}")
        return bytes(data)

    def _is_satochip(self):
        """True if the current reader serves a Satochip-family applet."""
        return self.AID.upper() == "5361746F43686970".upper()

    def _ensure_satochip_channel(self):
        """Open a Satochip secure channel (INS 0x81/0x82, HMAC-SHA1 KDF).

        Uses the m2 client's SeedKeeperSecureChannel — proven against
        jCardSim SatoChip by hil-next's battery (25/25, 2026-11-15).
        Falls back to the bench SC established via the m2 tree if the
        m2 imports fail.
        """
        if self._sato_sc is not None:
            return self._sato_sc
        M2_SRC = "/home/ubuntu/src/specter-diy-m2/src"
        M2_F469 = "/home/ubuntu/src/specter-diy-m2/f469-disco/libs/common"
        for p_ in (M2_SRC, M2_F469):
            if p_ not in sys.path:
                sys.path.insert(0, p_)
        try:
            from keystore.javacard.applets.seedkeeper_securechannel import (
                SeedKeeperSecureChannel)
        except ImportError:
            pytest.skip("m2 client not importable for Satochip channel")

        # stub micropython-only modules that the m2 tree imports at module level
        for mod_name, attrs in {
            "pyb": {"Pin": type("Pin", (), {}), "UART": type("UART", (), {})},
            "uscard": {"Reader": type("Reader", (), {}),
                       "SmartcardException": type("SmartcardException", (Exception,), {})},
            "lvgl": {"lv": types.SimpleNamespace()},
            "ucryptolib": {"aes": lambda *a, **k: type("C", (), {
                "encrypt": lambda s, d: d, "decrypt": lambda s, d: d})()},
            "uio": {"StringIO": __import__("io").StringIO},
            "micropython": {"const": lambda x: x},
            "display": {fn: (lambda *a, **k: None) for fn in
                        ("init", "width", "height", "backlight", "buffer",
                         "send", "commit", "clear", "fill", "draw_image",
                         "draw_text", "get")},
        }.items():
            if mod_name not in sys.modules:
                m = types.ModuleType(mod_name)
                for k, v in attrs.items():
                    setattr(m, k, v)
                sys.modules[mod_name] = m
        import time as _t
        if "utime" not in sys.modules:
            _ut = types.ModuleType("utime")
            _ut.ticks_ms = lambda: int(_t.monotonic() * 1000)
            _ut.ticks_diff = lambda a, b: a - b
            _ut.localtime = lambda ts=None: _t.localtime(
                ts if ts is not None else _t.time()) + (0,)
            _ut.sleep_ms = lambda ms: _t.sleep(ms / 1000)
            sys.modules["utime"] = _ut

        # connection adapter: the m2 channel calls conn.transmit(apdu_bytes)
        # and expects (resp_bytes, sw1, sw2) back — same as pyscard
        class _VpcdCard:
            def __init__(self, vpcd_bench):
                self._b = vpcd_bench

            def transmit(self, apdu):
                data, sw1, sw2 = self._b.conn.transmit(list(bytes(apdu)))
                return bytes(data), sw1, sw2

            def isCardInserted(self):
                return True

        # ecdsa-backed secp256k1 adapter (the zero-point stub poison fix)
        import hashlib as _hl
        import ecdsa as _ecdsa
        _ec_mod = types.ModuleType("secp256k1")
        _ec_mod.EC_UNCOMPRESSED = 0
        _ec_mod.EC_COMPRESSED = 1
        _P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F

        def _decomp(d33):
            x = int.from_bytes(d33[1:], "big")
            y2 = (pow(x, 3, _P) + 7) % _P
            y = pow(y2, (_P + 1) // 4, _P)
            if pow(y, 2, _P) != y2:
                raise ValueError("point not on curve")
            if (y & 1) != (d33[0] & 1):
                y = _P - y
            return x, y

        def _parse(data):
            d = bytes(data)
            if len(d) == 33:
                x, y = _decomp(d)
            else:
                x = int.from_bytes(d[1:33], "big")
                y = int.from_bytes(d[33:65], "big")
            return _ecdsa.VerifyingKey.from_string(
                x.to_bytes(32, "big") + y.to_bytes(32, "big"),
                curve=_ecdsa.SECP256k1)

        class _Pub:
            def __init__(self, vk):
                self.vk = vk

        def _ser(vk_or_pub, flag=0):
            vk = vk_or_pub.vk if isinstance(vk_or_pub, _Pub) else vk_or_pub
            if not isinstance(vk, _ecdsa.VerifyingKey):
                vk = _parse(vk)
            pt = vk.pubkey.point
            if flag == 0:
                return b"\x04" + pt.x().to_bytes(32, "big") + pt.y().to_bytes(32, "big")
            return (b"\x03" if pt.y() & 1 else b"\x02") + pt.x().to_bytes(32, "big")

        def _tweak(pub, scalar):
            base = (pub.vk if isinstance(pub, _Pub) else pub)
            if not isinstance(base, _ecdsa.VerifyingKey):
                base = _parse(base)
            from ecdsa.ellipticcurve import Point
            pt = Point(_ecdsa.SECP256k1.curve, base.pubkey.point.x(),
                       base.pubkey.point.y(), _ecdsa.SECP256k1.order)
            n = int.from_bytes(bytes(scalar)[:32], "big") * pt
            pub.vk = _ecdsa.VerifyingKey.from_string(
                n.x().to_bytes(32, "big") + n.y().to_bytes(32, "big"),
                curve=_ecdsa.SECP256k1)
            return None

        def _sig_parse(der):
            return _ecdsa.util.sigdecode_der(bytes(der), _ecdsa.SECP256k1.order)

        def _verify(sig, digest, pub):
            from ecdsa.util import sigencode_string
            raw = sigencode_string(sig[0], sig[1], order=_ecdsa.SECP256k1.order)
            vk = pub.vk if isinstance(pub, _Pub) else pub
            if not isinstance(vk, _ecdsa.VerifyingKey):
                vk = _parse(vk)
            return vk.verify_digest(
                _ecdsa.ecdsa.Signature.from_string(raw), bytes(digest))

        _ec_mod.ec_pubkey_create = lambda sk: _ecdsa.SigningKey.from_string(
            bytes(sk)[:32], curve=_ecdsa.SECP256k1).get_verifying_key()
        _ec_mod.ec_pubkey_parse = lambda d: _Pub(_parse(d))
        _ec_mod.ec_pubkey_serialize = _ser
        _ec_mod.ec_pubkey_tweak_mul = _tweak
        _ec_mod.ecdsa_signature_parse_der = _sig_parse
        _ec_mod.ecdsa_verify = _verify
        sys.modules["secp256k1"] = _ec_mod

        sc = SeedKeeperSecureChannel()
        sc.initiate(_VpcdCard(self))
        self._sato_sc = sc
        return sc

    def _ensure_channel(self):
        from util.securechannel import SecureChannel
        if self.sc is not None and self.sc.is_open:
            return self.sc
        for attempt in range(2):
            try:
                card = types.SimpleNamespace(request=self._request)
                self.sc = SecureChannel(card)
                self.sc.open()
                return self.sc
            except Exception as e:
                if attempt == 1:
                    pytest.fail(f"secure channel failed to open: {e!r}")
                # session churn — re-establish transport, retry once
                self.conn = self._connect()
                self._select()
        raise RuntimeError("unreachable")

    def _pin_status(self):
        sc = self._ensure_channel()
        left, total, is_set = list(sc.request(b"\x03\x00"))
        return left, total, is_set

    def satochip_get_status(self):
        """GET_STATUS (INS 0x3C) via the Satochip channel or plaintext."""
        if self._is_satochip():
            # plaintext GET_STATUS works on real Satochip (no SC needed)
            try:
                data, sw1, sw2 = self.conn.transmit(
                    [0xB0, 0x3C, 0x00, 0x00])
                if sw1 == 0x90 and len(data) >= 8:
                    d = list(data)
                    return {"connected": True, "keystore_found": True,
                            "unlocked": d[4] > 0, "card_inserted": True,
                            "fingerprint": None,
                            "protocol": f"{d[0]}.{d[1]}",
                            "applet": f"{d[2]}.{d[3]}",
                            "pin_tries": d[4], "puk_tries": d[5],
                            "is_seeded": len(d) > 9 and d[9] != 0}
            except Exception:
                pass
        return {"connected": False, "keystore_found": False,
                "unlocked": False, "card_inserted": True,
                "fingerprint": None}

    def status(self):
        if self._is_satochip():
            return self.satochip_get_status()
        _, _, is_set = self._pin_status()
        return {"connected": True, "keystore_found": True,
                "unlocked": is_set == 2, "card_inserted": True,
                "fingerprint": None}

    def pin(self, pin):
        if self._is_satochip():
            pytest.skip("Satochip PIN via dedicated SC (test_satochip_versions)")
        sc = self._ensure_channel()
        pin_b = pin.encode() if isinstance(pin, str) else bytes(pin)
        _, _, is_set = list(sc.request(b"\x03\x00"))
        if is_set == 0:
            sc.request(b"\x03\x04" + pin_b)      # set (unlocks)
        elif is_set == 1:
            sc.request(b"\x03\x01" + pin_b)      # verify (unlocks)
        _, _, is_set = list(sc.request(b"\x03\x00"))
        return "OK" if is_set == 2 else "ERROR:locked"

    def pin_status(self):
        return self.status()

    def sign(self, message, path):
        pytest.skip("SecureApplet has no sign INS — m2 SatoChip applet "
                    "on the vpcd tier is the follow-up (owner priority 2/3)")

    def authentikey_for(self, path):
        raise NotImplementedError("vpcd tier: SecureApplet authentikey "
                                  "export pending")


class SimBench:
    """Unix-port app simulator (make test path)."""

    name = "sim"
    provides = {"logic"}

    def satochip_get_status(self):
        """GET_STATUS (INS 0x3C) via the Satochip channel or plaintext."""
        if self._is_satochip():
            # plaintext GET_STATUS works on real Satochip (no SC needed)
            try:
                data, sw1, sw2 = self.conn.transmit(
                    [0xB0, 0x3C, 0x00, 0x00])
                if sw1 == 0x90 and len(data) >= 8:
                    d = list(data)
                    return {"connected": True, "keystore_found": True,
                            "unlocked": d[4] > 0, "card_inserted": True,
                            "fingerprint": None,
                            "protocol": f"{d[0]}.{d[1]}",
                            "applet": f"{d[2]}.{d[3]}",
                            "pin_tries": d[4], "puk_tries": d[5],
                            "is_seeded": len(d) > 9 and d[9] != 0}
            except Exception:
                pass
        return {"connected": False, "keystore_found": False,
                "unlocked": False, "card_inserted": True,
                "fingerprint": None}

    def status(self):
        out = sh("cd /home/ubuntu/src/specter-diy && make test 2>&1 | tail -2")
        return {"sim_suite": "OK" in out, "connected": None,
                "unlocked": None, "card_inserted": None, "fingerprint": None}

    def pin(self, pin):
        raise pytest.skip("sim tier has no card transport")

    def pin_status(self):
        return self.status()

    def sign(self, message, path):
        raise pytest.skip("sim tier has no card transport")

    def authentikey_for(self, path):
        raise NotImplementedError("sim tier has no card transport")


def pytest_addoption(parser):
    parser.addoption("--backend",
                     default=os.environ.get("TIER_BACKEND", "dry"),
                     choices=["dry", "sim", "cardman", "device", "vpcd"])
    parser.addoption("--sign-count", type=int, default=8)
    parser.addoption("--record", action="store_true",
                     help="capture device replies into dry-tier fixtures")
    parser.addoption("--applet-version", default=None,
                     help="target a specific applet version in the version farm "
                          "(e.g. v0.14-0.2, v0.16-0.1, sk-v0.2-0.1, mc-current). "
                          "Overrides TIER_VPCD_READER/AID env vars.")


@pytest.fixture(scope="session")
def backend(request):
    tier = request.config.getoption("--backend")
    if tier == "dry":
        yield DryBench()
    elif tier == "sim":
        yield SimBench()
    elif tier == "cardman":
        yield CardManBench()
    elif tier == "vpcd":
        yield VpcdBench(request.config.getoption("--applet-version"))
    elif tier == "device":
        b = DeviceBench()
        try:
            yield b
        finally:
            b.release()


def pytest_configure(config):
    global RECORD, FW_SHA
    RECORD = config.getoption("--record") if hasattr(config, "getoption") else False
    try:
        import hashlib
        FW_SHA = hashlib.sha256(open("/tmp/opencode/v2218.bin", "rb").read()).hexdigest()[:12]
    except OSError:
        pass
    config.addinivalue_line("markers", "needs(*args): capabilities the test requires (ALL must be provided)")
    config.addinivalue_line("markers",
                            "needs_any(*args): capabilities the test requires "
                            "(ANY one suffices — e.g. needs_any('card-real', 'card-mock'))")


@pytest.fixture(autouse=True)
def _needs(request, backend):
    marker = request.node.get_closest_marker("needs")
    if marker is not None:
        for cap in marker.args:
            if cap not in backend.provides:
                pytest.skip(f"backend {backend.name} does not provide '{cap}'")
    any_marker = request.node.get_closest_marker("needs_any")
    if any_marker is not None:
        if not any(cap in backend.provides for cap in any_marker.args):
            pytest.skip(f"backend {backend.name} provides none of "
                        f"{sorted(any_marker.args)}")
