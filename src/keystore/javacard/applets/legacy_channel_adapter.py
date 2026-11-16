"""Legacy secure channel adapter — wraps the original SecureChannel
(INS 0xB2-0xB7, sha256 KDF) to match the SeedKeeperSecureChannel API
used by SecureAppletBase.secure_request().

This enables pre-v0.11 Satochip applets to use the same client code
path as v0.11+ applets: init_secure_channel() detects the protocol
version and picks the right channel implementation.
"""
from binascii import hexlify

# The original securechannel.py imports micropython-only modules.
# On device they resolve natively; on host (CPython) we stub them.
import sys
if "secp256k1" not in sys.modules:
    try:
        import secp256k1  # noqa: F401 — micropython native
    except ImportError:
        # host-side: minimal stubs for the original channel's crypto
        import hashlib as _hl
        import hmac as _hmac
        import types as _types
        import os as _os

        _stub = _types.ModuleType("secp256k1")
        _stub.EC_UNCOMPRESSED = 0
        _stub.EC_COMPRESSED = 1
        # these are populated by the caller's EC adapter (e.g., the tier
        # harness's ecdsa-backed adapter or the m2 battery's adapter)
        # if not populated, the legacy channel can't open on host —
        # which is correct (the original channel needs real EC math)
        sys.modules.setdefault("secp256k1", _stub)

        _rng = _types.ModuleType("rng")
        _rng.get_random_bytes = lambda n: _os.urandom(n)
        sys.modules.setdefault("rng", _rng)

        _uc = _types.ModuleType("ucryptolib")
        _uc.aes = lambda key, mode, IV=None: _types.SimpleNamespace(
            encrypt=lambda d, iv=None: d,  # no-op (host stub — real crypto
            decrypt=lambda d, iv=None: d,  # needs the device or ecdsa lib)
        )
        _uc.AES_CBC = 2
        sys.modules.setdefault("ucryptolib", _uc)

from .securechannel import SecureChannel, SecureError


class LegacyChannelAdapter:
    """Adapts the original SecureChannel to the SeedKeeper-style interface.

    The original channel uses applet.request() for transport (bytes → bytes,
    raising on error). The SeedKeeper channel uses conn.transmit() (returning
    (data, sw1, sw2)). This adapter bridges them.
    """

    def __init__(self):
        self._channel = None
        self.is_initialized = False

    def initiate(self, connection):
        """Open the original secure channel via the connection.

        The original channel expects an applet-like object with .request(),
        but we have a connection with .transmit(). Wrap it.
        """
        class _ConnAdapter:
            def __init__(self, conn):
                self._conn = conn

            def request(self, apdu_bytes):
                data, sw1, sw2 = self._conn.transmit(list(apdu_bytes))
                if (sw1, sw2) != (0x90, 0x00):
                    from .applet import ISOException
                    raise ISOException(
                        f"{sw1:02x}{sw2:02x}")
                return bytes(data)

        self._channel = SecureChannel(_ConnAdapter(connection))
        self._channel.open(mode="es")
        self.is_initialized = True

    def encrypt_apdu(self, inner_apdu):
        """Encrypt for transport — wraps the original channel's encrypt."""
        return self._channel.encrypt(inner_apdu)

    def decrypt_response(self, encrypted_response):
        """Decrypt a response — wraps the original channel's decrypt."""
        return self._channel.decrypt(encrypted_response)

    def request(self, inner_apdu):
        """Secure request — same API as SeedKeeperSecureChannel usage."""
        return self._channel.request(inner_apdu)
