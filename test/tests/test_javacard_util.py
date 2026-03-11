"""
Unit tests for JavaCard utility functions.

These tests verify the utility functions that will be extracted
from the JavaCard keystore implementations during refactoring.

Run with: python3 test/run_tests.py
"""
from unittest import TestCase
import hashlib


class PubKeyCompressionTest(TestCase):
    """Tests for compress_pubkey() utility function."""
    
    def test_compress_uncompressed_pubkey(self):
        """Test compressing a 65-byte uncompressed pubkey to 33 bytes."""
        # Sample uncompressed pubkey (65 bytes: 04 + x + y)
        uncompressed = bytes([
            0x04,  # Uncompressed prefix
            # X coordinate (32 bytes)
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
            # Y coordinate (32 bytes) - even value
            0x48, 0x3A, 0xDA, 0x77, 0x26, 0xA3, 0xC4, 0x65,
            0x5D, 0xA4, 0xFB, 0xFC, 0x0E, 0x11, 0x08, 0xA8,
            0xFD, 0x17, 0xB4, 0x48, 0xA6, 0x85, 0x54, 0x19,
            0x9C, 0x47, 0xD0, 0x8F, 0xFB, 0x10, 0xD4, 0xB8,
        ])
        
        # Expected compressed (33 bytes: 02 + x) - even y
        expected = bytes([
            0x02,  # Even y prefix
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
        ])
        
        # Import and test (will fail until function is implemented)
        try:
            from keystore.javacard.util import compress_pubkey
            result = compress_pubkey(uncompressed)
            self.assertEqual(result, expected)
            self.assertEqual(len(result), 33)
        except ImportError:
            self.skipTest("compress_pubkey not yet implemented")
    
    def test_compress_uncompressed_pubkey_odd_y(self):
        """Test compressing pubkey with odd Y coordinate."""
        # Sample uncompressed pubkey with odd Y
        uncompressed = bytes([
            0x04,
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
            # Odd Y (last byte is odd)
            0x48, 0x3A, 0xDA, 0x77, 0x26, 0xA3, 0xC4, 0x65,
            0x5D, 0xA4, 0xFB, 0xFC, 0x0E, 0x11, 0x08, 0xA8,
            0xFD, 0x17, 0xB4, 0x48, 0xA6, 0x85, 0x54, 0x19,
            0x9C, 0x47, 0xD0, 0x8F, 0xFB, 0x10, 0xD4, 0xB9,  # B9 is odd
        ])
        
        expected = bytes([
            0x03,  # Odd y prefix
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
        ])
        
        try:
            from keystore.javacard.util import compress_pubkey
            result = compress_pubkey(uncompressed)
            self.assertEqual(result, expected)
        except ImportError:
            self.skipTest("compress_pubkey not yet implemented")
    
    def test_already_compressed_passthrough(self):
        """Test that already compressed pubkey passes through unchanged."""
        compressed = bytes([
            0x02,
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
        ])
        
        try:
            from keystore.javacard.util import compress_pubkey
            result = compress_pubkey(compressed)
            self.assertEqual(result, compressed)
        except ImportError:
            self.skipTest("compress_pubkey not yet implemented")
    
    def test_invalid_length_raises_error(self):
        """Test that invalid pubkey length raises ValueError."""
        invalid = b'\x04' + b'\x00' * 30  # 31 bytes - invalid
        
        try:
            from keystore.javacard.util import compress_pubkey
            with self.assertRaises(ValueError):
                compress_pubkey(invalid)
        except ImportError:
            self.skipTest("compress_pubkey not yet implemented")


class FingerprintDerivationTest(TestCase):
    """Tests for derive_fingerprint() utility function."""
    
    def test_derive_fingerprint_from_compressed(self):
        """Test fingerprint derivation from compressed pubkey."""
        # Compressed pubkey
        pubkey = bytes([
            0x02,
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
        ])
        
        try:
            from keystore.javacard.util import derive_fingerprint
            result = derive_fingerprint(pubkey)
            
            # Fingerprint should be 4 bytes
            self.assertEqual(len(result), 4)
            
            # Verify it's hash160[:4]
            sha256_hash = hashlib.sha256(pubkey).digest()
            ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
            expected = ripemd160[:4]
            self.assertEqual(result, expected)
        except ImportError:
            self.skipTest("derive_fingerprint not yet implemented")
    
    def test_fingerprint_is_deterministic(self):
        """Test that same pubkey always gives same fingerprint."""
        pubkey = bytes([
            0x02,
            0x79, 0xBE, 0x66, 0x7E, 0xF9, 0xDC, 0xBB, 0xAC,
            0x55, 0xA0, 0x62, 0x95, 0xCE, 0x87, 0x0B, 0x07,
            0x02, 0x9B, 0xFC, 0xDB, 0x2D, 0xCE, 0x28, 0xD9,
            0x59, 0xF2, 0x81, 0x5B, 0x16, 0xF8, 0x17, 0x98,
        ])
        
        try:
            from keystore.javacard.util import derive_fingerprint
            result1 = derive_fingerprint(pubkey)
            result2 = derive_fingerprint(pubkey)
            self.assertEqual(result1, result2)
        except ImportError:
            self.skipTest("derive_fingerprint not yet implemented")


class PathToBytesTest(TestCase):
    """Tests for path_to_bytes() utility function."""
    
    def test_path_m(self):
        """Test conversion of root path 'm'."""
        try:
            from keystore.javacard.util import path_to_bytes
            result = path_to_bytes("m")
            self.assertEqual(result, b'')
        except ImportError:
            self.skipTest("path_to_bytes not yet implemented")
    
    def test_path_simple(self):
        """Test conversion of simple path m/44h/0h/0h."""
        try:
            from keystore.javacard.util import path_to_bytes
            result = path_to_bytes("m/44h/0h/0h")
            
            # Expected: 44h = 0x8000002C, 0h = 0x80000000, 0h = 0x80000000
            expected = bytes([
                0x80, 0x00, 0x00, 0x2C,  # 44h
                0x80, 0x00, 0x00, 0x00,  # 0h
                0x80, 0x00, 0x00, 0x00,  # 0h
            ])
            self.assertEqual(result, expected)
        except ImportError:
            self.skipTest("path_to_bytes not yet implemented")
    
    def test_path_mixed_hardened(self):
        """Test path with both h and ' hardened notation."""
        try:
            from keystore.javacard.util import path_to_bytes
            result1 = path_to_bytes("m/44h/0'/0h")
            result2 = path_to_bytes("m/44'/0h/0'")
            # Both should give same result
            self.assertEqual(result1, result2)
        except ImportError:
            self.skipTest("path_to_bytes not yet implemented")
    
    def test_path_non_hardened(self):
        """Test path with non-hardened derivation."""
        try:
            from keystore.javacard.util import path_to_bytes
            result = path_to_bytes("m/44h/0h/0h/0/0")
            
            # Last two are non-hardened
            expected = bytes([
                0x80, 0x00, 0x00, 0x2C,  # 44h
                0x80, 0x00, 0x00, 0x00,  # 0h
                0x80, 0x00, 0x00, 0x00,  # 0h
                0x00, 0x00, 0x00, 0x00,  # 0 (non-hardened)
                0x00, 0x00, 0x00, 0x00,  # 0 (non-hardened)
            ])
            self.assertEqual(result, expected)
        except ImportError:
            self.skipTest("path_to_bytes not yet implemented")


class PinExceptionHandlingTest(TestCase):
    """Tests for handle_pin_iso_exception() utility function."""
    
    def test_bricked_card_9c0c(self):
        """Test 9C0C status word raises CriticalError."""
        try:
            from keystore.javacard.util import handle_pin_iso_exception
            from keystore.javacard.applets.applet import ISOException
            from platform import CriticalErrorWipeImmediately
            
            e = ISOException("9c0c")
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            self.assertEqual(attempts, 0)
            self.assertTrue(should_raise)
            self.assertIsInstance(exc, type(CriticalErrorWipeImmediately("")))
        except ImportError:
            self.skipTest("handle_pin_iso_exception not yet implemented")
    
    def test_bricked_card_6983(self):
        """Test 6983 status word raises CriticalError."""
        try:
            from keystore.javacard.util import handle_pin_iso_exception
            from keystore.javacard.applets.applet import ISOException
            from platform import CriticalErrorWipeImmediately
            
            e = ISOException("6983")
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            self.assertEqual(attempts, 0)
            self.assertTrue(should_raise)
            self.assertIsInstance(exc, type(CriticalErrorWipeImmediately("")))
        except ImportError:
            self.skipTest("handle_pin_iso_exception not yet implemented")
    
    def test_wrong_pin_63c5(self):
        """Test 63C5 status word returns 5 attempts left."""
        try:
            from keystore.javacard.util import handle_pin_iso_exception
            from keystore.javacard.applets.applet import ISOException
            from keystore.core import PinError
            
            e = ISOException("63c5")
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            self.assertEqual(attempts, 5)
            self.assertTrue(should_raise)
            self.assertIsInstance(exc, PinError)
            self.assertIn("5", str(exc))
        except ImportError:
            self.skipTest("handle_pin_iso_exception not yet implemented")
    
    def test_wrong_pin_63c1(self):
        """Test 63C1 status word returns 1 attempt left."""
        try:
            from keystore.javacard.util import handle_pin_iso_exception
            from keystore.javacard.applets.applet import ISOException
            from keystore.core import PinError
            
            e = ISOException("63c1")
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            self.assertEqual(attempts, 1)
            self.assertTrue(should_raise)
            self.assertIn("1", str(exc))
        except ImportError:
            self.skipTest("handle_pin_iso_exception not yet implemented")
    
    def test_unknown_sw_reraises(self):
        """Test unknown status word re-raises original exception."""
        try:
            from keystore.javacard.util import handle_pin_iso_exception
            from keystore.javacard.applets.applet import ISOException
            
            e = ISOException("6a82")  # File not found
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            self.assertTrue(should_raise)
            self.assertIs(exc, e)  # Returns original exception
        except ImportError:
            self.skipTest("handle_pin_iso_exception not yet implemented")


class CardDetectionTest(TestCase):
    """Tests for card type detection (Phase 4)."""
    
    def test_aid_constants_exist(self):
        """Test that AID constants are defined."""
        try:
            from keystore.javacard.applets.memorycard import MemoryCardApplet
            from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
            from keystore.javacard.applets.satochip_applet import SatochipApplet
            
            # Verify AIDs are bytes
            self.assertIsInstance(MemoryCardApplet.AID, bytes)
            self.assertIsInstance(SeedKeeperApplet.AID, bytes)
            self.assertIsInstance(SatochipApplet.AID, bytes)
            
            # Verify lengths
            self.assertEqual(len(MemoryCardApplet.AID), 6)
            self.assertEqual(len(SeedKeeperApplet.AID), 10)
            self.assertEqual(len(SatochipApplet.AID), 8)
            
        except ImportError as e:
            self.skipTest(f"Applet not available: {e}")


if __name__ == '__main__':
    import unittest
    unittest.main()
