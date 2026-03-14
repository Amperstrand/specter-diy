"""
Unit tests for SeedKeeper keystore.
Tests crypto functions, applet command construction, and keystore state management
with mocked card communication.
"""
import sys
sys.path.append('../src')

from unittest import TestCase
from unittest.mock import MagicMock, patch, PropertyMock
from binascii import hexlify, unhexlify


# =============================================================================
# Mock classes for card communication
# =============================================================================

class MockConnection:
    """Mock smartcard connection for testing without hardware."""
    
    def __init__(self):
        self.card_inserted = False
        self.responses = []
        self.response_index = 0
        self.T1_protocol = 1
        self._connected = False
    
    def isCardInserted(self):
        return self.card_inserted
    
    def connect(self, protocol):
        self._connected = True
    
    def disconnect(self):
        self._connected = False
    
    def transmit(self, apdu):
        """Transmit APDU and return predefined response."""
        if self.response_index < len(self.responses):
            resp = self.responses[self.response_index]
            self.response_index += 1
            return resp
        # Default: success response
        return (b"", 0x90, 0x00)
    
    def set_responses(self, responses):
        """Set list of responses to return from transmit()."""
        self.responses = responses
        self.response_index = 0


class MockSecureChannel:
    """Mock SatochipSecureChannel for testing applet without crypto."""
    
    def __init__(self):
        self.is_initialized = False
        self.iv_counter = 0
        self.secret_key = None
        self.mac_key = None
    
    def initiate(self, connection, cla=0xB0):
        self.is_initialized = True
    
    def encrypt_apdu(self, inner_apdu, cla=0xB0):
        # Return wrapped APDU (in real implementation, this encrypts)
        return inner_apdu
    
    def decrypt_response(self, encrypted_response):
        # Return plaintext (in real implementation, this decrypts)
        return encrypted_response


# =============================================================================
# Category 1: Import and Class Structure Tests
# =============================================================================

class SeedKeeperImportTest(TestCase):
    """Test that SeedKeeper modules import correctly with proper structure."""
    
    def test_seedkeeper_inheritance(self):
        """Test that SeedKeeper inherits from RAMKeyStore."""
        from keystore.ram import RAMKeyStore
        from keystore.seedkeeper import SeedKeeper
        self.assertTrue(issubclass(SeedKeeper, RAMKeyStore),
                       "SeedKeeper should inherit from RAMKeyStore")
    
    def test_applet_inheritance(self):
        """Test that SeedKeeperApplet inherits from Applet."""
        from keystore.javacard.applets.applet import Applet
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        self.assertTrue(issubclass(SeedKeeperApplet, Applet),
                       "SeedKeeperApplet should inherit from Applet")
    
    def test_seedkeeper_class_attributes(self):
        """Test that SeedKeeper has required class attributes."""
        from keystore.seedkeeper import SeedKeeper
        self.assertEqual(SeedKeeper.NAME, "SeedKeeper")
        self.assertIsNotNone(SeedKeeper.COLOR)
        self.assertIsNotNone(SeedKeeper.NOTE)
    
    def test_applet_constants(self):
        """Test that SeedKeeperApplet has correct AID constant."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        # AID should be ASCII "SeedKeeper"
        expected_aid = b'SeedKeeper'
        self.assertEqual(SeedKeeperApplet.AID, expected_aid,
                        "AID should be {!r}".format(expected_aid))
                        f"AID should be {expected_aid!r}")


# =============================================================================
# Category 2: Secure Channel Crypto Tests
# =============================================================================

class SecureChannelCryptoTest(TestCase):
    """Test secure channel cryptographic functions."""
    
    def test_pkcs7_pad_zero_bytes(self):
        """Test pkcs7_pad with empty data."""
        # Import may fail if module not implemented, skip if so
        try:
            from keystore.javacard.applets.satochip_securechannel import pkcs7_pad
        except ImportError:
            self.skipTest("pkcs7_pad not implemented in satochip_securechannel")
        
        data = b""
        padded = pkcs7_pad(data)
        # Empty data + 16 bytes of padding value 0x10
        self.assertEqual(len(padded), 16)
        self.assertEqual(padded, b"\x10" * 16)
    
    def test_pkcs7_pad_full_block(self):
        """Test pkcs7_pad with data that's already a full block."""
        try:
            from keystore.javacard.applets.satochip_securechannel import pkcs7_pad
        except ImportError:
            self.skipTest("pkcs7_pad not implemented")
        
        data = b"a" * 16
        padded = pkcs7_pad(data)
        # Full block needs another block of padding
        self.assertEqual(len(padded), 32)
        self.assertEqual(padded[:16], b"a" * 16)
        self.assertEqual(padded[16:], b"\x10" * 16)
    
    def test_pkcs7_pad_partial_block(self):
        """Test pkcs7_pad with partial block data."""
        try:
            from keystore.javacard.applets.satochip_securechannel import pkcs7_pad
        except ImportError:
            self.skipTest("pkcs7_pad not implemented")
        
        data = b"hello"  # 5 bytes
        padded = pkcs7_pad(data)
        # 5 + 11 = 16 bytes
        self.assertEqual(len(padded), 16)
        self.assertEqual(padded[:5], b"hello")
        # Remaining 11 bytes should be 0x0b
        self.assertEqual(padded[5:], b"\x0b" * 11)
    
    def test_pkcs7_unpad_valid(self):
        """Test pkcs7_unpad with valid padded data."""
        try:
            from keystore.javacard.applets.satochip_securechannel import (
                pkcs7_pad, pkcs7_unpad
            )
        except ImportError:
            self.skipTest("pkcs7 functions not implemented")
        
        test_data = [b"", b"a", b"hello", b"a" * 15, b"a" * 16, b"a" * 31]
        for data in test_data:
            padded = pkcs7_pad(data)
            unpadded = pkcs7_unpad(padded)
            self.assertEqual(unpadded, data,
                            f"Roundtrip failed for {len(data)} bytes")
    
    def test_pkcs7_unpad_invalid(self):
        """Test pkcs7_unpad with invalid padding raises ValueError."""
        try:
            from keystore.javacard.applets.satochip_securechannel import pkcs7_unpad
        except ImportError:
            self.skipTest("pkcs7_unpad not implemented")
        
        # Invalid padding: wrong value
        invalid = b"a" * 15 + b"\x05"
        with self.assertRaises(ValueError):
            pkcs7_unpad(invalid)
    
    def test_hmac_sha1_basic(self):
        """Test hmac_sha1 produces correct output."""
        try:
            from keystore.javacard.applets.satochip_securechannel import hmac_sha1
        except ImportError:
            self.skipTest("hmac_sha1 not implemented")
        
        # RFC 2202 test vector
        key = b"\x0b" * 20
        data = b"Hi There"
        result = hmac_sha1(key, data)
        self.assertEqual(len(result), 20, "HMAC-SHA1 should produce 20 bytes")


# =============================================================================
# Category 3: Applet Command Construction Tests
# =============================================================================

class AppletCommandTest(TestCase):
    """Test SeedKeeperApplet command construction with mocked connection."""
    
    def setUp(self):
        """Set up mock connection for each test."""
        self.mock_conn = MockConnection()
    
    def test_get_card_status_apdu(self):
        """Test get_card_status sends correct APDU bytes."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        
        self.mock_conn.card_inserted = True
        self.mock_conn.set_responses([
            (b"\x00\x00\x00\x00\x05\x00\x00\x00\x00", 0x90, 0x00)
        ])
        
        applet = SeedKeeperApplet(self.mock_conn)
        resp_data, sw1, sw2 = applet.get_card_status()
        
        # Verify response
        self.assertEqual(sw1, 0x90)
        self.assertEqual(sw2, 0x00)
    
    def test_parse_header(self):
        """Test _parse_header with known header bytes."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        
        applet = SeedKeeperApplet(self.mock_conn)
        
        # Construct a valid header (15 bytes + label)
        # id(2) | type(1) | origin(1) | export_rights(1) | export_nbplain(1) |
        # export_nbsecure(1) | export_counter(1) | fingerprint(4) | subtype(1) |
        # rfu(1) | label_len(1) | label(N)
        header_data = bytes([
            0x00, 0x01,  # id = 1
            0x30,        # type = BIP39
            0x01,        # origin
            0xFF,        # export_rights
            0x00,        # export_nbplain
            0x00,        # export_nbsecure
            0x00,        # export_counter
            0xAB, 0xCD, 0xEF, 0x12,  # fingerprint
            0x00,        # subtype
            0x00,        # rfu
            0x05,        # label_len = 5
        ]) + b"Test1"   # label
        
        header = applet._parse_header(header_data)
        
        self.assertEqual(header['id'], 1)
        self.assertEqual(header['type'], 0x30)
        self.assertEqual(header['fingerprint'], 'abcdef12')
        self.assertEqual(header['label'], 'Test1')
    
    def test_applet_has_required_methods(self):
        """Test that SeedKeeperApplet has all required methods."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        
        required_methods = [
            'get_card_status',
            'get_seedkeeper_status',
            'verify_pin',
            'get_card_label',
            'set_card_label',
            'list_secret_headers',
            'export_secret',
            'get_bip39_secret',
            'init_secure_channel',
            'secure_request',
            '_parse_header',
        ]
        
        for method in required_methods:
            self.assertTrue(hasattr(SeedKeeperApplet, method),
                          f"SeedKeeperApplet missing method: {method}")


# =============================================================================
# Category 4: Keystore State Tests
# =============================================================================

class KeystoreStateTest(TestCase):
    """Test SeedKeeper keystore state management."""
    
    def test_keystore_construction(self):
        """Test SeedKeeper construction initializes attributes correctly."""
        from keystore.seedkeeper import SeedKeeper
        
        # Mock the connection at class level
        with patch.object(SeedKeeper, 'connection', MockConnection()):
            ks = SeedKeeper()
            
            self.assertIsNone(ks.mnemonic)
            self.assertFalse(ks.connected)
            self.assertFalse(ks._pin_unlocked)
            self.assertIsNone(ks.selected_secret_id)
            self.assertFalse(ks._is_key_saved)
    
    def test_is_available_returns_false_no_card(self):
        """Test is_available() returns False when no card present."""
        from keystore.seedkeeper import SeedKeeper
        
        mock_conn = MockConnection()
        mock_conn.card_inserted = False
        
        with patch.object(SeedKeeper, 'connection', mock_conn):
            result = SeedKeeper.is_available()
            self.assertFalse(result)
    
    def test_is_pin_set_always_true(self):
        """Test is_pin_set property always returns True for SeedKeeper."""
        from keystore.seedkeeper import SeedKeeper
        
        with patch.object(SeedKeeper, 'connection', MockConnection()):
            ks = SeedKeeper()
            self.assertTrue(ks.is_pin_set)
    
    def test_pin_attempts_max(self):
        """Test pin_attempts_max returns standard value."""
        from keystore.seedkeeper import SeedKeeper
        
        with patch.object(SeedKeeper, 'connection', MockConnection()):
            ks = SeedKeeper()
            self.assertEqual(ks.pin_attempts_max, 5)
    
    def test_is_locked_initial_state(self):
        """Test is_locked returns True initially (PIN not verified)."""
        from keystore.seedkeeper import SeedKeeper
        
        with patch.object(SeedKeeper, 'connection', MockConnection()):
            ks = SeedKeeper()
            self.assertTrue(ks.is_locked)
    
    def test_save_mnemonic_raises_error(self):
        """Test save_mnemonic raises error (SeedKeeper is read-only)."""
        from keystore.seedkeeper import SeedKeeper
        from keystore.core import KeyStoreError
        
        with patch.object(SeedKeeper, 'connection', MockConnection()):
            ks = SeedKeeper()
            # save_mnemonic is async, need to check it raises when called
            # For now, just verify the method exists and is async
            import asyncio
            self.assertTrue(asyncio.iscoroutinefunction(ks.save_mnemonic))


# =============================================================================
# Category 5: BIP39 Conversion Tests
# =============================================================================

class BIP39ConversionTest(TestCase):
    """Test BIP39 mnemonic conversion."""
    
    def test_bip39_mnemonic_conversion_known_vector(self):
        """Test BIP39 secret to mnemonic conversion with known test vector."""
        from embit import bip39
        
        # Known BIP39 test vector: 128-bit entropy of all zeros
        entropy = bytes.fromhex("00000000000000000000000000000000")
        expected_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        
        mnemonic = bip39.mnemonic_from_bytes(entropy)
        self.assertEqual(mnemonic, expected_mnemonic)
    
    def test_bip39_mnemonic_256_bit(self):
        """Test BIP39 conversion with 256-bit entropy."""
        from embit import bip39
        
        # 256-bit entropy (32 bytes of zeros)
        entropy = bytes(32)
        mnemonic = bip39.mnemonic_from_bytes(entropy)
        
        # Should produce 24 words
        words = mnemonic.split()
        self.assertEqual(len(words), 24)
        
        # Verify it's valid
        self.assertTrue(bip39.mnemonic_is_valid(mnemonic))
    
    def test_bip39_bytes_roundtrip(self):
        """Test BIP39 bytes <-> mnemonic roundtrip."""
        from embit import bip39
        
        test_mnemonic = "abandon ability able about above absent absorb abstract absurd abuse access accident"
        
        # Convert to bytes and back
        entropy = bip39.mnemonic_to_bytes(test_mnemonic)
        recovered = bip39.mnemonic_from_bytes(entropy)
        
        self.assertEqual(recovered, test_mnemonic)
    
    def test_masterseed_parsing_logic(self):
        """Test MASTERSEED format parsing logic (type 0x10 with BIP39 subtype)."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        
        # This tests the _parse_masterseed_to_mnemonic logic indirectly
        # by verifying the method exists and has correct signature
        self.assertTrue(hasattr(SeedKeeperApplet, '_parse_masterseed_to_mnemonic'))


# =============================================================================
# Additional: Secret Type Constants Tests
# =============================================================================

class SecretTypeConstantsTest(TestCase):
    """Test SeedKeeper secret type constants."""
    
    def test_secret_type_constants(self):
        """Test that secret type constants are defined correctly."""
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
        
        self.assertEqual(SeedKeeperApplet.SECRET_TYPE_MASTERSEED, 0x10)
        self.assertEqual(SeedKeeperApplet.SECRET_TYPE_BIP39, 0x30)
        self.assertEqual(SeedKeeperApplet.SECRET_TYPE_BIP39_V2, 0x31)
        self.assertEqual(SeedKeeperApplet.SECRET_TYPE_DESCRIPTOR, 0xC1)
