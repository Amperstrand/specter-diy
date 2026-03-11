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
            
            self.assertEqual(ks.conn, conn)
            self.assertIsNotNone(ks.sc)
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
    
    def test_check_card_no_card(self):
        """Test check_card when no card inserted."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            
            conn = MockConnection()
            conn.card_inserted = False
            ks.check_card()
            
            # Should handle gracefully
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_check_card_with_card(self):
        """Test check_card when card is inserted."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            
            conn = MockConnection()
            conn.card_inserted = True
            ks.check_card()
            
            # Should proceed normally
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_unlock_flow(self):
        """Test unlock method with PIN."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            from keystore.core import PinError
            
            
            conn = MockConnection()
            ks = JavaCardKeyStore(conn)
            
            # Create mock applet
            ks.applet = MagicMock()
            ks.applet.verify_pin = MagicMock(side_effect=lambda pin: (True, None))
            
            result = ks.unlock('1234')
            
            self.assertTrue(result)
            ks.applet.verify_pin.assert_called_once_with('1234')
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")
    
    def test_unlock_wrong_pin_raises_pin_error(self):
        """Test unlock with wrong PIN raises PinError."""
        try:
            from keystore.javacard_keystore import JavaCardKeyStore
            from keystore.core import PinError
            
            
            conn = MockConnection()
            ks = JavaCardKeyStore(conn)
            
            # Create mock applet
            ks.applet = MagicMock()
            ks.applet.verify_pin = MagicMock(side_effect=lambda pin: False)
            ks._pin_unlocked = False
            
            # Call unlock
            with self.assertRaises(PinError):
                pass
        except ImportError:
            self.skipTest("JavaCardKeyStore not yet implemented")


if __name__ == '__main__':
    import unittest
    unittest.main()
