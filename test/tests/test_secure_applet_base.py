"""
Unit tests for SecureAppletBase class.

These tests verify the secure channel applet base class
that will be shared by SeedKeeperApplet and SatochipApplet.

Run with: python3 test/run_tests.py
"""
from unittest import TestCase
from unittest.mock import Mock, MagicMock, patch


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


class SecureAppletBaseTest(TestCase):
    """Tests for SecureAppletBase class."""
    
    def test_init_creates_secure_channel(self):
        """Test that __init__ creates a SeedKeeperSecureChannel."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            self.assertIsNotNone(applet.sc)
            self.assertEqual(applet.conn, conn)
            self.assertEqual(applet.aid, b'\x00\x01\x02\x03')
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_init_secure_channel(self):
        """Test init_secure_channel() calls sc.initiate()."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock the secure channel
            applet.sc.initiate = MagicMock()
            
            applet.init_secure_channel()
            
            applet.sc.initiate.assert_called_once_with(conn)
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_success(self):
        """Test secure_request() with successful response."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted_apdu')
            applet.sc.decrypt_response = MagicMock(return_value=b'decrypted_data')
            
            # Mock connection response
            conn.transmit = MagicMock(return_value=(b'encrypted_response', 0x90, 0x00))
            
            result = applet.secure_request(b'inner_apdu')
            
            self.assertEqual(result, b'decrypted_data')
            applet.sc.encrypt_apdu.assert_called_once_with(b'inner_apdu')
            applet.sc.decrypt_response.assert_called_once_with(b'encrypted_response')
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_not_initialized_raises(self):
        """Test secure_request() raises if secure channel not initialized."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            from keystore.javacard.applets.applet import AppletException
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            applet.sc.is_initialized = False
            
            with self.assertRaises(AppletException) as context:
                applet.secure_request(b'inner_apdu')
            
            self.assertIn("not initialized", str(context.exception))
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_9c30_retries(self):
        """Test secure_request() retries on 9c30 (secure channel corrupted)."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted')
            applet.sc.decrypt_response = MagicMock(return_value=b'decrypted')
            applet.sc.initiate = MagicMock()
            
            # First call returns 9c30, second call succeeds
            call_count = [0]
            def mock_transmit(apdu):
                call_count[0] += 1
                if call_count[0] == 1:
                    return (b'', 0x9c, 0x30)  # Secure channel corrupted
                return (b'response', 0x90, 0x00)
            
            conn.transmit = mock_transmit
            
            result = applet.secure_request(b'inner_apdu')
            
            # Should have retried after re-init
            self.assertEqual(call_count[0], 2)
            applet.sc.initiate.assert_called_once_with(conn)
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_9c30_no_retry(self):
        """Test secure_request() does NOT retry if retry=False."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            from keystore.javacard.applets.applet import ISOException
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted')
            applet.sc.initiate = MagicMock()
            
            # Returns 9c30
            conn.transmit = MagicMock(return_value=(b'', 0x9c, 0x30))
            
            with self.assertRaises(ISOException) as context:
                applet.secure_request(b'inner_apdu', retry=False)
            
            self.assertIn("9c30", str(context.exception).lower())
            applet.sc.initiate.assert_not_called()
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_iso_error_raises(self):
        """Test secure_request() raises ISOException on non-9000 SW."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            from keystore.javacard.applets.applet import ISOException
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted')
            
            # Returns error
            conn.transmit = MagicMock(return_value=(b'', 0x6a, 0x82))
            
            with self.assertRaises(ISOException) as context:
                applet.secure_request(b'inner_apdu')
            
            self.assertIn("6a82", str(context.exception).lower())
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_secure_request_empty_response(self):
        """Test secure_request() returns empty bytes for empty response."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Mock secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted')
            
            # Empty response with 9000
            conn.transmit = MagicMock(return_value=(b'', 0x90, 0x00))
            
            result = applet.secure_request(b'inner_apdu')
            
            self.assertEqual(result, b'')
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")
    
    def test_inherits_from_applet(self):
        """Test that SecureAppletBase inherits from Applet."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            from keystore.javacard.applets.applet import Applet
            
            self.assertTrue(issubclass(SecureAppletBase, Applet))
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")


class SecureAppletBaseIntegrationTest(TestCase):
    """Integration tests requiring mocked hardware."""
    
    def test_verify_pin_flow(self):
        """Test complete PIN verification flow."""
        try:
            from keystore.javacard.applets.secure_applet_base import SecureAppletBase
            
            conn = MockConnection()
            applet = SecureAppletBase(conn, b'\x00\x01\x02\x03')
            
            # Initialize secure channel
            applet.sc.is_initialized = True
            applet.sc.encrypt_apdu = MagicMock(return_value=b'encrypted')
            applet.sc.decrypt_response = MagicMock(return_value=b'')
            
            # PIN verify returns success
            conn.transmit = MagicMock(return_value=(b'', 0x90, 0x00))
            
            # Simulate verify PIN APDU
            inner_apdu = bytes([0xB0, 0x42, 0x00, 0x00, 4]) + b'1234'
            result = applet.secure_request(inner_apdu)
            
            self.assertEqual(result, b'')
        except ImportError:
            self.skipTest("SecureAppletBase not yet implemented")


if __name__ == '__main__':
    import unittest
    unittest.main()
