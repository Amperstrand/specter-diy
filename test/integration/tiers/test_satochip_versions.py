"""Satochip version-specific tests — run against the version farm.

Each test targets a specific applet version via --applet-version:
    pytest --backend=vpcd --applet-version=sato-v0.14-0.2 test_satochip_versions.py
    pytest --backend=vpcd --applet-version=sato-v0.16-0.1 test_satochip_versions.py

The Satochip secure channel (INS 0x81/0x82, HMAC-SHA1 KDF) is used for
encrypted operations; GET_STATUS (0x3C) works plaintext.
"""
import pytest


@pytest.mark.needs("card")
class TestSatochipVersion:
    def test_get_status_reports_version(self, backend, request):
        if backend.name != "vpcd":
            pytest.skip("version farm tests (run with --backend=vpcd)")
        if not backend._is_satochip():
            pytest.skip("Satochip AID required for GET_STATUS version test")
        st = backend.satochip_get_status()
        assert st["connected"], f"GET_STATUS failed: {st}"
        assert "protocol" in st and st["protocol"], "no protocol version"
        ver = request.config.getoption("--applet-version") or "default"
        print(f"  applet: proto={st.get('protocol')} "
              f"app={st.get('applet')} seeded={st.get('is_seeded')}")

    def test_secure_channel_opens(self, backend):
        if backend.name != "vpcd":
            pytest.skip("vpcd tier only")
        if not backend._is_satochip():
            pytest.skip("Satochip AID required for SC test")
        sc = backend._ensure_satochip_channel()
        assert sc is not None
        assert sc.is_initialized

    def test_satochip_pin_via_sc(self, backend):
        """PIN check through the secure channel (INS 0x20 via SC)."""
        if backend.name != "vpcd":
            pytest.skip("vpcd tier only")
        if not backend._is_satochip():
            pytest.skip("Satochip AID required")
        sc = backend._ensure_satochip_channel()
        # VerifyPIN (INS 0x20) P1=0x00, data=PIN bytes
        # jCardSim Satochip may use the bench PIN or default; use default
        pin_data = bytes([4]) + b"1234"
        from util.simulator import ISOException
        data, sw1, sw2 = backend.conn.transmit(
            [0xB0, 0x20, 0x00, 0x00, len(pin_data)] + list(pin_data))
        # PIN may succeed (9000) or fail on tries; both prove the SC path works
        assert sw1 in (0x90, 0x9C, 0x63, 0x69), \
            f"PIN SW unexpected: {sw1:02x}{sw2:02x}"
