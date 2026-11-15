"""vpcd-tier specifics: the L2 bridge proven inside the suite.

Every assertion here exercises the FULL host client stack — pyscard ->
pcscd -> libifdvpcd-jcardsim.so -> vicc.py -> jcsimcli -> applet classes
— the same pcscd API the cardman tier uses against the real CardMan.
The bridge-level wire facts (driver, adapter, desync root cause) live in
specter-javacard/tests/host/ and tests/tests/util/vicc.py.
"""
import types

import pytest


def _vpcd_only(backend):
    if backend.name != "vpcd":
        pytest.skip("vpcd-tier assertions (run with --backend=vpcd)")


@pytest.mark.needs("card")
class TestVpcdBridge:
    def test_atr_is_j3r180_shape(self, backend):
        _vpcd_only(backend)
        atr = bytes(backend.conn.getATR()).hex().upper()
        assert atr == "3B858131FE458073C8211084", atr

    def test_secure_channel_echo(self, backend):
        _vpcd_only(backend)
        sc = backend._ensure_channel()
        assert sc.request(b"\x00\x00ping") == b"ping"

    def test_secure_random(self, backend):
        _vpcd_only(backend)
        sc = backend._ensure_channel()
        d1 = sc.request(b"\x01\x00")
        d2 = sc.request(b"\x01\x00")
        assert len(d1) == 32 and d1 != d2

    def test_get_pubkey_shape(self, backend):
        _vpcd_only(backend)
        sc = backend._ensure_channel()
        pub = backend._request(b"\xB0\xB2\x00\x00")
        assert pub[0] == 0x04 and len(pub) == 65

    def test_duplicate_channel_invalidates_previous(self, backend):
        _vpcd_only(backend)
        from util.securechannel import SecureChannel
        sc1 = backend._ensure_channel()
        sc2 = SecureChannel(
            types.SimpleNamespace(request=backend._request))
        sc2.open()
        backend.sc = sc2
        with pytest.raises(Exception):
            sc1.request(b"\x01\x00")
