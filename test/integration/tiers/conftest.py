"""Tiered bench harness — one suite, four backends, escalation by parameter.

pytest --backend=dry|sim|cardman|device [--sign-count N]

The backend fixture yields a Bench object with a uniform interface; tests
declare needs via markers (@pytest.mark.needs("card")) and skip cleanly on
tiers that cannot provide them.
"""
import os
import re
import subprocess
import time

import pytest

BACKEND = os.environ.get("TIER_BACKEND", "dry")
COORDINATOR = "192.168.13.208:20408"
DEVICE_PLACE = "f469-specter-film"
FIFO = "/tmp/opencode/f469-console.in"
CONSOLE_LOG = "/tmp/opencode/f469-console.log"


def sh(cmd, timeout=90):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def console_send(cmd):
    try:
        fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, (cmd + "\n").encode())
        os.close(fd)
    except OSError:
        pass


def console_reply(cmd_name, wait_s=16):
    time.sleep(wait_s)
    out = sh(f"grep -A1 'CMD: {cmd_name}' {CONSOLE_LOG} | tail -2 | head -1")
    return out.replace(chr(92), "")


class DryBench:
    """Transcript-driven: deterministic, zero hardware, milliseconds."""

    name = "dry"
    provides = {"logic", "card-mock"}

    STATUS = ("OK:{'keystore_type': 'Smartcard', 'connected': True, "
              "'keystore_found': True, 'unlocked': False, "
              "'card_inserted': True, 'fingerprint': None}")

    def status(self):
        return {"connected": True, "keystore_found": True, "unlocked": False,
                "card_inserted": True, "fingerprint": None}

    def pin(self, pin):
        return "ERROR:6984"  # recorded: applet-level reply, unlock succeeds

    def pin_status(self):
        return {"connected": True, "unlocked": True}

    def sign(self, message, path):
        # transcript-recorded shape: deterministic 64-byte DER for fixed input
        return bytes.fromhex("3044022079be667ef9dcbbac55a06295ce870b07029bfcdb"
                             "2dce28d959f2815b16f8179802200f00" * 1)


class DeviceBench:
    """Full integration: console daemon FIFO -> TestMode on the F469."""

    name = "device"
    provides = {"logic", "card-real", "firmware", "gui", "screen"}

    def __init__(self):
        if sh("pgrep -f overnight-campaign2.py").strip():
            import pytest
            pytest.skip("device tier blocked: campaign owns the console "
                        "(arbitration rule — see README)")
        self._lease()

    def _lease(self):
        out = sh(f"labgrid-client -x {COORDINATOR} -p {DEVICE_PLACE} acquire")
        # fail-closed: an unverified lease can yield WRONG GREENS on shared hardware
        import pytest
        if "acquired place" not in out:
            pytest.fail(f"labgrid lease NOT acquired (fail-closed): {out.strip()[:120]}")
        self._leased = True

    def release(self):
        if getattr(self, "_leased", False):
            sh(f"labgrid-client -x {COORDINATOR} -p {DEVICE_PLACE} release")

    def _cmd(self, cmd, name, wait_s=16):
        try:
            off = os.path.getsize(CONSOLE_LOG)
        except OSError:
            off = 0
        console_send(cmd)
        time.sleep(wait_s)
        with open(CONSOLE_LOG, "rb") as f:
            f.seek(off)
            fresh = f.read().decode("utf-8", "replace").replace(chr(92), "")
        lines = [l for l in fresh.splitlines() if "CMD: " + name in l]
        if not lines:
            return ""
        # reply follows the CMD line in the same stream
        idx = fresh.find(lines[-1])
        return fresh[idx:idx + 400]

    def status(self):
        out = self._cmd("TEST_STATUS", "TEST_STATUS")
        return {"connected": "'connected': True" in out,
                "keystore_found": "'keystore_found': True" in out,
                "unlocked": "'unlocked': True" in out,
                "card_inserted": "'card_inserted': True" in out}

    def pin(self, pin):
        return self._cmd(f"TEST_PIN:{pin}", "TEST_PIN")

    def pin_status(self):
        return self.status()

    def sign(self, message, path):
        raise NotImplementedError("TEST_SIGN firmware command pending")


class CardManBench:
    """Real card in the CardMan reader, host-side client (dry-friendly)."""

    name = "cardman"
    provides = {"logic", "card-real"}

    def __init__(self):
        raise pytest.skip("CardMan tier pending cardbench bless "
                          "(request in the javacard lane ledger REPORT block)")

    def status(self):
        raise NotImplementedError


class SimBench:
    """Unix-port app simulator (make test path)."""

    name = "sim"
    provides = {"logic"}

    def status(self):
        out = sh("cd /home/ubuntu/src/specter-diy && make test 2>&1 | tail -2")
        return {"sim_suite": "OK" in out, "connected": None,
                "unlocked": None, "card_inserted": None}

    def pin(self, pin):
        raise pytest.skip("sim tier has no card transport")

    def pin_status(self):
        return self.status()

    def sign(self, message, path):
        raise pytest.skip("sim tier has no card transport")


def pytest_addoption(parser):
    parser.addoption("--backend", default="dry",
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
    config.addinivalue_line("markers", "needs(*args): capabilities the test requires (all)")
    config.addinivalue_line("markers", "needs_any(*args): at least one capability required")


@pytest.fixture(autouse=True)
def _needs(request, backend):
    marker = request.node.get_closest_marker("needs")
    if marker is None:
        return
    for cap in marker.args:
        if cap not in backend.provides:
            pytest.skip(f"backend {backend.name} does not provide '{cap}'")
    any_marker = request.node.get_closest_marker("needs_any")
    if any_marker and not any(c in backend.provides for c in any_marker.args):
        pytest.skip(f"backend {backend.name} provides none of {any_marker.args}")
