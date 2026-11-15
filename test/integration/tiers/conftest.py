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
import time
from datetime import datetime

import pytest

COORDINATOR = "192.168.13.208:20408"
DEVICE_PLACE = "f469-specter-film"
FIFO = "/tmp/opencode/f469-console.in"
CONSOLE_LOG = "/tmp/opencode/f469-console.log"

LOG_LINE_RE = re.compile(r"^(\S+)\s+b('.*')\s*$")
REPLY_WAIT_S = 30
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
        return reply

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

    def status(self):
        raise NotImplementedError

    def authentikey_for(self, path):
        raise NotImplementedError


class SimBench:
    """Unix-port app simulator (make test path)."""

    name = "sim"
    provides = {"logic"}

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
                     choices=["dry", "sim", "cardman", "device"])
    parser.addoption("--sign-count", type=int, default=8)


@pytest.fixture(scope="session")
def backend(request):
    tier = request.config.getoption("--backend")
    if tier == "dry":
        yield DryBench()
    elif tier == "sim":
        yield SimBench()
    elif tier == "cardman":
        yield CardManBench()
    elif tier == "device":
        b = DeviceBench()
        try:
            yield b
        finally:
            b.release()


def pytest_configure(config):
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
