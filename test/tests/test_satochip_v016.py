"""Satochip client vs applet protocol v0.16-0.1 (2026-10-16) conformance.

v0.16 release notes (Toporin/SatochipApplet v0.16-0.1) removed/changed
several instructions. These tests pin our client's wire behavior to the
v0.16-compatible subset and guard against reintroducing deprecated INS
bytes. Mock-based; no hardware.
"""
from unittest import TestCase
from unittest.mock import MagicMock

CLA = 0xB0


class RecordingConnection:
    def __init__(self):
        self.apdus = []

    def isCardInserted(self):
        return True

    def transmit(self, apdu):
        self.apdus.append(bytes(apdu))
        return (b'', 0x90, 0x00)


def _applet(conn):
    from keystore.javacard.applets.satochip_applet import SatochipApplet

    applet = SatochipApplet(conn)
    applet.sc.is_initialized = True
    applet.sc.encrypt_apdu = MagicMock(side_effect=lambda inner: bytes(inner))
    applet.sc.decrypt_response = MagicMock(side_effect=lambda resp: bytes(resp))
    return applet


class SatochipV016ConformanceTest(TestCase):
    def test_verify_pin_uses_p1_zero(self):
        """v0.16: single PIN/PUK - P1 must be 0x00 in VerifyPIN."""
        conn = RecordingConnection()
        applet = _applet(conn)
        applet.verify_pin(b'1234')
        inner = conn.apdus[-1]
        self.assertEqual(inner[1], 0x42)
        self.assertEqual(inner[2], 0x00)

    def test_factory_reset_apdu_shape(self):
        """v0.16 factory reset: INS 0xFD, P1=0xAA, P2=0x55, over SC, no data."""
        conn = RecordingConnection()
        applet = _applet(conn)
        applet.factory_reset()
        inner = conn.apdus[-1]
        self.assertEqual(list(inner[:4]), [CLA, 0xFD, 0xAA, 0x55])
        self.assertEqual(len(inner), 4)

    def test_signing_uses_0x7a_not_removed_instructions(self):
        """Sign via 0x7A; 0x6F (SignTransaction) and 0x6E (signMessage) are
        removed in v0.16 and must never appear on the wire."""
        conn = RecordingConnection()
        applet = _applet(conn)
        tx_hash = bytes(32)
        applet.sign_transaction_hash(0xFF, tx_hash)
        inner = conn.apdus[-1]
        self.assertEqual(inner[1], 0x7A)
        for apdu in conn.apdus:
            self.assertNotIn(apdu[1], (0x6F, 0x6E))

    def test_no_removed_instruction_constants(self):
        """The client must not carry constants for removed instructions."""
        from keystore.javacard.applets import satochip_applet as mod
        self.assertFalse(hasattr(mod.SatochipApplet, 'INS_SIGN_MESSAGE'))

    def test_sign_hash_derives_before_signing(self):
        """v0.16: derived keys are transient (cleared on deselect/reset) -
        sign_hash must set the derivation path in the same session."""
        conn = RecordingConnection()

        def transmit(apdu):
            conn.apdus.append(bytes(apdu))
            if bytes(apdu)[1] == 0x6D:  # chaincode(32)|coordx_size(2)|coordx(32)|sig_size(2)|auth_size(2)
                resp = bytes(32) + (32).to_bytes(2, 'big') + bytes(32) + (0).to_bytes(2, 'big') + (0).to_bytes(2, 'big')
                return (resp, 0x90, 0x00)
            return (b'', 0x90, 0x00)

        conn.transmit = transmit
        applet = _applet(conn)
        applet.sign_transaction_hash = MagicMock(wraps=applet.sign_transaction_hash)

        from keystore.satochip import Satochip
        ks = Satochip.__new__(Satochip)  # bypass async init
        ks.applet = applet
        ks._pin_unlocked = True
        ks.sign_hash("m/44h/0h/0h/0/0", bytes(32))

        derive_idx = next(i for i, a in enumerate(conn.apdus) if a[1] == 0x6D)
        sign_idx = next(i for i, a in enumerate(conn.apdus) if a[1] == 0x7A)
        self.assertLess(derive_idx, sign_idx)
        applet.sign_transaction_hash.assert_called_once_with(0xFF, bytes(32))


if __name__ == '__main__':
    import unittest
    unittest.main()
