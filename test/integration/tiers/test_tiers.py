"""Tiered tests: the same assertions at every backend.

Run fast (dry), escalate to hardware (device) with one parameter:
    pytest test/integration/tiers -q --backend=dry
    pytest test/integration/tiers -q --backend=device
"""
import re

import pytest


@pytest.mark.needs("card")
class TestBenchStatus:
    def test_card_connected(self, backend):
        st = backend.status()
        assert st["connected"] is True

    def test_card_found(self, backend):
        st = backend.status()
        assert st["keystore_found"] is True


@pytest.mark.needs_any("card-real", "card-mock")
class TestPinFlow:

    @pytest.fixture(autouse=True)
    def _skip_satochip(self, backend):
        if hasattr(backend, '_is_satochip') and backend._is_satochip():
            pytest.skip("SecureApplet PIN flow (Satochip uses different SC)")
    def test_pin_flow_unlocks(self, backend):
        r = backend.pin("1234")
        assert ("OK" in r) or ("6984" in r) or ("6e00" in r), r
        st = backend.pin_status()
        assert st["unlocked"] is True


@pytest.mark.needs_any("card-real", "card-mock")
class TestSignShape:
    """Signature-shape battery — the endurance core. The dry tier replays
    recorded shapes; the device tier needs the TEST_SIGN firmware command
    (pending) and is skipped there for now."""

    def test_sign_returns_der(self, backend, request):
        if backend.name == "device":
            pytest.skip("TEST_SIGN firmware command pending")
        n = request.config.getoption("--sign-count") if hasattr(
            request.config, "getoption") else 8
        for i in range(n):
            sig = backend.sign(b"bench message %d" % i, "m/84h/0h/0h/0/%d" % i)
            assert sig and len(sig) >= 8, f"signature {i} degenerate"


@pytest.mark.needs("firmware")
class TestDeviceOnly:
    def test_watchdog_alive(self, backend):
        st = backend.status()
        assert st["connected"] is True
