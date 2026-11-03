"""
Unit tests for JavaCardKeyStore base class.

These tests verify the keystore base class
that will be shared by all JavaCard-based keystores (SeedKeeper, Satochip, and The tests use mocked connections to simulate the card behavior without actual hardware.

Run with: python3 test/run_tests.py
"""
from unittest import TestCase
from unittest.mock import Mock, MagicMock


class MockConnection:
    """Mock connection for testing."""
    
    def __init__(self):
        self.transmit_calls = []
        self.card_inserted = True
    
    def isCardInserted(self):
        return self.card_inserted
    
    def transmit(self, apdu):
        """Record APDU and return mock response."""
        self.transmit_calls.append(apdu)
        # Default success response
        return (b'', 0x90, 0x00)


class JavaCardKeyStoreBaseTest(TestCase):
    """Tests for JavaCardKeyStore base class."""
    
    def test_init_creates_keystore(self):
        """Test __init__ creates keystore instance."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_init_with_connection(self):
        """Test __init__ with connection."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            
            conn = MockConnection()
            ks = JavaCardKeyStore(conn)
            
            self.assertEqual(ks.connection, conn)
            self.assertIsNone(ks.applet)
            self.assertFalse(ks._pin_unlocked)
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_is_pin_set(self):
        """Test is_pin_set property returns True for JavaCard keystores."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            
            conn = MockConnection()
            ks = JavaCardKeyStore(conn)
            
            # is_pin_set should be True for JavaCards
            self.assertTrue(ks.is_pin_set)
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_is_locked(self):
        """Test is_locked property."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            
            conn = MockConnection()
            ks = JavaCardKeyStore(conn)
            
            # is_locked should initially be True (not unlocked)
            self.assertTrue(ks.is_locked)
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_check_card_no_card_shows_wait_screen(self):
        """check_card with no card routes to the wait-for-card screen."""
        import sys
        if sys.implementation.name != 'cpython':
            self.skipTest("async harness: native-only")
        from keystore.javacard_keystore import JavaCardKeyStore

        conn = MockConnection()
        conn.card_inserted = False
        ks = JavaCardKeyStore(conn)
        ks.applet = MagicMock()
        ks.applet.NAME = "Test"

        shown = []

        class StopShow(Exception):
            pass

        async def fake_show(scr):
            shown.append(type(scr).__name__)
            raise StopShow()

        ks.show = fake_show
        ks.show_loader = lambda *a, **k: None

        import keystore.javacard_keystore as jck

        class Progress:
            def __init__(self, *a, **k):
                pass

        orig_progress = jck.Progress
        jck.Progress = Progress
        try:
            import asyncio
            with self.assertRaises(StopShow):
                asyncio.run(ks.check_card())
        finally:
            jck.Progress = orig_progress

        self.assertFalse(ks.connected)
        self.assertIn("Progress", shown)

    def test_check_card_with_card_connects(self):
        """check_card with card present connects and selects the applet."""
        import sys
        if sys.implementation.name != 'cpython':
            self.skipTest("async harness: native-only")
        from keystore.javacard_keystore import JavaCardKeyStore

        conn = MagicMock()
        conn.isCardInserted.return_value = True
        conn.T1_protocol = 1
        ks = JavaCardKeyStore(conn)
        ks.applet = MagicMock()
        ks._init_secure_channel = MagicMock()

        async def fake_show(scr):
            pass

        import asyncio
        asyncio.run(_check_card_driver(ks, fake_show))

        self.assertTrue(ks.connected)
        ks.applet.select.assert_called_once()
        ks._init_secure_channel.assert_called_once()

    def test_unlock_pin_sets_unlocked_state(self):
        """_unlock verifies PIN through the applet and flips is_locked."""
        from keystore.javacard_keystore import JavaCardKeyStore

        conn = MockConnection()
        ks = JavaCardKeyStore(conn)
        ks.applet = MagicMock()
        ks._on_pin_verified = MagicMock()

        ks._verify_pin = MagicMock(return_value=(True, None))
        ks._unlock('1234')

        ks._verify_pin.assert_called_once_with('1234')
        self.assertTrue(ks._pin_unlocked)
        self.assertFalse(ks.is_locked)
        ks._on_pin_verified.assert_called_once()

    def test_unlock_wrong_pin_raises_pin_error(self):
        """_unlock with card-refused PIN surfaces PinError with attempts."""
        from keystore.javacard_keystore import JavaCardKeyStore
        from keystore.core import PinError

        conn = MockConnection()
        ks = JavaCardKeyStore(conn)
        ks.applet = MagicMock()

        ks._verify_pin = MagicMock(return_value=(False, 2))
        with self.assertRaises(PinError):
            ks._unlock('0000')
        self.assertTrue(ks.is_locked)


async def _check_card_driver(ks, fake_show):
    ks.show = fake_show
    ks.show_loader = lambda *a, **k: None
    await ks.check_card()


if __name__ == '__main__':
    import unittest
    unittest.main()
