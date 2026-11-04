"""Regression tests for issue #22 — SeedKeeper EEPROM corruption after rapid
import/delete cycles (https://github.com/Amperstrand/specter-diy/issues/22).

Observed on hardware (2026-03-20): after ~25 duplicate imports + deletes in
one power session, every secure operation returns SW 9C06 (SW_UNAUTHORIZED)
even with a verified PIN and a freshly established secure channel. GPIO
power-cycle (TEST_CARD_RESET) does not clear it; only physical card removal
does. The reference pysatochip connector answers 9c06 with automatic PIN
re-verification, which is useless here and hammers a corrupted object
manager — our client must instead raise a typed, actionable error and stop.

These tests reproduce the failure signature at the client layer with a
stateful mock card, under the native pytest infrastructure.
"""
from unittest import TestCase
from unittest.mock import MagicMock

CORRUPTION_THRESHOLD = 25


class CorruptibleSeedKeeperMock:
    """Stateful card mock implementing the #22 failure mode.

    Tracks import/delete operations within one power session. At
    CORRUPTION_THRESHOLD ops every secure-channel command answers 9c06
    regardless of PIN state or channel freshness — the on-card signature of
    the corrupted EEPROM object manager. Physical reinsertion clears it.
    """

    def __init__(self):
        self.write_ops = 0
        self.corrupted = False
        self.transmit_count = 0

    def physical_reinsert(self):
        self.write_ops = 0
        self.corrupted = False

    def transmit(self, apdu):
        self.transmit_count += 1
        if self.corrupted:
            return (b'', 0x9C, 0x06)
        ins = apdu[1] if len(apdu) > 1 else 0
        # 0xA1 import / 0xA5 delete are the EEPROM-writing ops from the issue
        if ins in (0xA1, 0xA5):
            self.write_ops += 1
            if self.write_ops >= CORRUPTION_THRESHOLD:
                self.corrupted = True
        return (b'\x90\x00', 0x90, 0x00)


class EEPROMCorruptionTest(TestCase):
    def _applet(self, card):
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet

        applet = SeedKeeperApplet(card)
        applet.sc.is_initialized = True
        applet.sc.encrypt_apdu = MagicMock(
            side_effect=lambda inner: bytes([0xB0, inner[1], 0x00, 0x00])
        )
        applet.sc.decrypt_response = MagicMock(return_value=b'')
        applet.sc.initiate = MagicMock()
        return applet

    def test_9c06_after_import_delete_storm_is_typed_and_actionable(self):
        """#22 signature: after >=25 write ops, LIST_SECRETS raises CardStateError
        pointing at physical reinsertion — not a bare ISOException."""
        from keystore.javacard.applets.applet import CardStateError
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet

        card = CorruptibleSeedKeeperMock()
        applet = self._applet(card)
        cla = SeedKeeperApplet.CLA if hasattr(SeedKeeperApplet, 'CLA') else 0xB0
        import_apdu = bytes([cla, 0xA1, 0x00, 0x00])
        delete_apdu = bytes([cla, 0xA5, 0x00, 0x00])

        # given: a card driven through >=25 write ops (corruption onset may
        # arrive mid-storm - that transition is itself the #22 signature)
        from keystore.javacard.applets.applet import CardStateError as StormError

        for _ in range(CORRUPTION_THRESHOLD):
            for apdu in (import_apdu, delete_apdu):
                try:
                    applet.secure_request(apdu)
                except StormError:
                    pass

        # when: LIST_SECRETS is attempted on the corrupted card
        # then: typed, actionable error (assertions below)
        with self.assertRaises(CardStateError) as ctx:
            applet.secure_request(bytes([cla, 0xA6, 0x00, 0x01]))
        self.assertIn('9c06', str(ctx.exception).lower())
        self.assertIn('pin', str(ctx.exception).lower())

    def test_no_retry_storm_on_9c06(self):
        """The client must not answer 9c06 with channel re-init or PIN retry
        loops — exactly one transmit per secure_request."""
        from keystore.javacard.applets.applet import CardStateError

        card = CorruptibleSeedKeeperMock()
        card.corrupted = True
        applet = self._applet(card)

        before = card.transmit_count
        with self.assertRaises(CardStateError):
            applet.secure_request(bytes([0xB0, 0xA6, 0x00, 0x01]))
        self.assertEqual(card.transmit_count - before, 1)
        applet.sc.initiate.assert_not_called()

    def test_physical_reinsertion_recovers(self):
        """Documents the only working recovery: physical card removal."""
        card = CorruptibleSeedKeeperMock()
        card.corrupted = True
        applet = self._applet(card)

        card.physical_reinsert()
        resp = applet.secure_request(bytes([0xB0, 0xA6, 0x00, 0x01]))
        self.assertEqual(resp, b'')

    def test_list_secret_headers_still_terminates_on_9c12(self):
        """No regression: end-of-list 9c12 keeps terminating header iteration."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        from keystore.javacard.applets.applet import ISOException

        class EndOfListCard:
            def __init__(self):
                self.calls = 0

            def transmit(self, apdu):
                self.calls += 1
                if self.calls > 1:
                    return (b'', 0x9C, 0x12)
                header = bytes([0x00, 0x01, 0x30]) + bytes(11) + bytes([0x00])
                return (header, 0x90, 0x00)

        applet = SeedKeeperApplet(EndOfListCard())
        applet.sc.is_initialized = True
        applet.sc.encrypt_apdu = MagicMock(return_value=bytes([0xB0, 0xA6, 0x00, 0x01]))
        applet.sc.decrypt_response = MagicMock(
            side_effect=lambda resp: bytes([0x00, 0x01, 0x30]) + bytes(11) + bytes([0x00])
            if b'\x90' not in bytes(resp[:1])
            else b''
        )
        headers = applet.list_secret_headers()
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0]['id'], 1)


if __name__ == '__main__':
    import unittest
    unittest.main()
