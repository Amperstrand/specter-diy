"""
Satochip Secure Channel Applet - Crypto Primitives

Implements HMAC-SHA1 and PKCS#7 padding for JavaCard secure channel.

RFC 2104: HMAC = H(K XOR opad || H(K XOR ipad || text))
"""

import hashlib
import secp256k1
from ucryptolib import aes
from rng import get_random_bytes


# Constants
AES_BLOCK = 16
IV_SIZE = 16
MAC_SIZE = 20
AES_CBC = 2


def hmac_sha1(key: bytes, msg: bytes) -> bytes:
    """
    Compute HMAC-SHA1 as per RFC 2104.

    Args:
        key: The secret key (bytes)
        msg: The message to authenticate (bytes)

    Returns:
        20-byte HMAC-SHA1 digest

    RFC 2104: HMAC = H((K' ⊕ opad) || H((K' ⊕ ipad) || m))
    """
    # Block size for SHA-1 is 64 bytes
    BLOCK_SIZE = 64

    # Transform key if necessary
    if len(key) > BLOCK_SIZE:
        key = hashlib.sha1(key).digest()
    elif len(key) < BLOCK_SIZE:
        key = key + b'\x00' * (BLOCK_SIZE - len(key))
    # Inner and outer pads
    ipad = b'\x36' * BLOCK_SIZE
    opad = b'\x5c' * BLOCK_SIZE

    # Inner hash: H(K XOR ipad || msg)
    # XOR key with ipad and opad
    key_ipad = bytes(a ^ b for a, b in zip(key, ipad))
    key_opad = bytes(a ^ b for a, b in zip(key, opad))

    # Inner hash: H((K XOR ipad) || msg)
    inner_hash = hashlib.sha1(key_ipad + msg).digest()

    # Outer hash: H((K XOR opad) || inner_hash)
    return hashlib.sha1(key_opad + inner_hash).digest()


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """
    PKCS#7 pad data to a multiple of block_size.

    Args:
        data: Input data to pad (bytes)
        block_size: Block size in bytes (default 16 for AES)

    Returns:
        Padded data

    Algorithm: pad_len = block_size - (len(data) % block_size)
              return data + bytes([pad_len] * pad_len)
    """
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    """
    Remove PKCS#7 padding from data.

    Args:
        data: Padded data (bytes)

    Returns:
        Unpadded data

    Raises:
        ValueError: If padding is invalid
    """
    # Last byte is padding length
    padding_len = data[-1]

    # Validate padding (all bytes must equal padding_len)
    if padding_len == 0:
        raise ValueError("Invalid PKCS#7 padding: padding length is 0")

    # Check all padding bytes
    for i in range(1, padding_len + 1):
        if data[-i] != padding_len:
            raise ValueError("Invalid PKCS#7 padding: expected {}, got {}".format(padding_len, data[-i]))

    return data[:-padding_len]


class SatochipSecureChannel:
    """
    Secure channel implementation for Satochip/SeedKeeper JavaCard applet.
    
    Implements ECDH key exchange with AES-CBC encryption and HMAC-SHA1 authentication.
    """
    
    def __init__(self):
        """Initialize secure channel state."""
        self.aes_key = None
        self.mac_key = None
        self.iv_counter = 1
        self.is_initialized = False

    def initiate(self, connection, cla=0xB0):
        """
        Perform ECDH key exchange via INS 0x81.
        
        Args:
            connection: Card connection object with transmit() method
            cla: Class byte (default 0xB0)
        
        Returns:
            None (keys are stored in instance attributes)
        
        Note: Does NOT verify card's ECDSA signatures (MVP simplification).
        """
        # 1. Generate ephemeral keypair
        secret = get_random_bytes(32)
        pubkey = secp256k1.ec_pubkey_create(secret)
        pub_bytes = secp256k1.ec_pubkey_serialize(pubkey, secp256k1.EC_UNCOMPRESSED)  # 65 bytes
        
        # 2. Send INIT_SC APDU (INS 0x81)
        apdu = bytes([cla, 0x81, 0x00, 0x00, 0x41]) + pub_bytes
        data = connection.transmit(apdu)
        resp_data = data[0]  # bytes object
        sw1, sw2 = data[1], data[2]
        if sw1 != 0x90 or sw2 != 0x00:
            raise ValueError('INIT_SC failed: SW={:02X}{:02X}'.format(sw1, sw2))
        coordx_size = (resp_data[0] << 8) | resp_data[1]
        coordx = bytes(resp_data[2:2+coordx_size])
        
        # 4. Reconstruct card's compressed pubkey (assume even Y = 0x02 prefix)
        card_pubkey_compressed = bytes([0x02]) + coordx
        card_pubkey = secp256k1.ec_pubkey_parse(card_pubkey_compressed)
        
        # 5. Compute ECDH shared secret: tweak_mul(card_pubkey, our_secret)
        # Note: ec_pubkey_tweak_mul modifies in place and returns None, so we need to copy first
        # Copy the pubkey by serializing and re-parsing (see securechannel.py for pattern)
        shared_point = secp256k1.ec_pubkey_parse(
            secp256k1.ec_pubkey_serialize(card_pubkey)
        )
        secp256k1.ec_pubkey_tweak_mul(shared_point, secret)  # Modifies in place
        shared_bytes = secp256k1.ec_pubkey_serialize(shared_point, secp256k1.EC_UNCOMPRESSED)
        shared_secret = shared_bytes[1:33]  # X-coordinate only (skip 0x04 prefix)
        
        # 6. Derive keys using HMAC-SHA1
        self.aes_key = hmac_sha1(shared_secret, b'sc_key')[:16]
        self.mac_key = hmac_sha1(shared_secret, b'sc_mac')
        self.is_initialized = True

    def encrypt_apdu(self, inner_apdu: bytes, cla=0xB0) -> bytes:
        """
        Encrypt APDU for secure channel (INS 0x82).
        
        Args:
            inner_apdu: The plaintext APDU to encrypt
            cla: Class byte (default 0xB0)
        
        Returns:
            Wrapped encrypted APDU ready for transmission
        
        Raises:
            ValueError: If secure channel not initialized
        """
        if not self.is_initialized:
            raise ValueError("Secure channel not initialized")
        
        # 1. Generate IV: 12 random + 4-byte counter (big-endian)
        iv = get_random_bytes(12) + self.iv_counter.to_bytes(4, 'big')
        
        # 2. Ensure IV last byte is ODD (required by SeedKeeper protocol)
        if iv[15] % 2 == 0:
            iv = iv[:15] + bytes([iv[15] | 0x01])
        
        # 3. Pad and encrypt with AES-CBC
        padded = pkcs7_pad(inner_apdu, AES_BLOCK)
        cipher = aes(self.aes_key, AES_CBC, iv)
        ciphertext = cipher.encrypt(padded)
        
        # 4. Compute MAC: HMAC(iv || len(ct) || ct)
        mac_data = iv + len(ciphertext).to_bytes(2, 'big') + ciphertext
        mac = hmac_sha1(self.mac_key, mac_data)
        
        # 5. Build payload: iv + len(ct)(2) + ct + len(mac)(2) + mac
        payload = iv + len(ciphertext).to_bytes(2, 'big') + ciphertext + (20).to_bytes(2, 'big') + mac
        
        # 6. Wrap as INS 0x82 APDU
        wrapped = bytes([cla, 0x82, 0x00, 0x00, len(payload)]) + payload
        
        # 7. Increment counter by 2 (SeedKeeper protocol requirement)
        self.iv_counter += 2
        
        return wrapped

    def decrypt_response(self, encrypted_response: bytes) -> bytes:
        """
        Decrypt card's encrypted response.
        
        Args:
            encrypted_response: Raw encrypted response from card
        
        Returns:
            Decrypted plaintext response
        
        Note: Card responses don't include MAC verification.
        """
        # 1. Parse: IV(16) + data_size(2) + ciphertext
        card_iv = encrypted_response[:16]
        data_size = int.from_bytes(encrypted_response[16:18], 'big')
        ciphertext = encrypted_response[18:18+data_size]
        
        # 2. Decrypt with AES-CBC
        cipher = aes(self.aes_key, AES_CBC, card_iv)
        plaintext = cipher.decrypt(ciphertext)
        
        # 3. Unpad and return
        return pkcs7_unpad(plaintext)
