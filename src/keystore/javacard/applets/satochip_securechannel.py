"""
Satochip Secure Channel - Crypto primitives for SeedKeeper and Satochip applets.

Implements ECDH key exchange, AES-CBC encryption, and HMAC-SHA1 authentication.
This is the Satochip/SeedKeeper protocol, distinct from MemoryCard's SecureChannel
(which uses HMAC-SHA256 and a different key derivation scheme).
"""

import hashlib
import secp256k1
from ucryptolib import aes
from rng import get_random_bytes


AES_BLOCK = 16


def hmac_sha1(key: bytes, msg: bytes) -> bytes:
    BLOCK_SIZE = 64
    if len(key) > BLOCK_SIZE:
        key = hashlib.sha1(key).digest()
    elif len(key) < BLOCK_SIZE:
        key = key + b'\x00' * (BLOCK_SIZE - len(key))
    ipad = b'\x36' * BLOCK_SIZE
    opad = b'\x5c' * BLOCK_SIZE
    key_ipad = bytes(a ^ b for a, b in zip(key, ipad))
    key_opad = bytes(a ^ b for a, b in zip(key, opad))
    inner_hash = hashlib.sha1(key_ipad + msg).digest()
    return hashlib.sha1(key_opad + inner_hash).digest()


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def pkcs7_unpad(data: bytes) -> bytes:
    padding_len = data[-1]
    if padding_len == 0:
        raise ValueError("Invalid PKCS#7 padding")
    for i in range(1, padding_len + 1):
        if data[-i] != padding_len:
            raise ValueError("Invalid PKCS#7 padding")
    return data[:-padding_len]


class SatochipSecureChannel:
    """Secure channel for Satochip/SeedKeeper JavaCard applets.

    ECDH key exchange with AES-CBC encryption and HMAC-SHA1 authentication.
    """

    def __init__(self):
        self.aes_key = None
        self.mac_key = None
        self.iv_counter = 1
        self.is_initialized = False

    def initiate(self, connection, cla=0xB0):
        """Perform ECDH key exchange via INS 0x81."""
        try:
            from platform import hil_test_mode
        except Exception:
            hil_test_mode = False
        secret = get_random_bytes(32)
        if hil_test_mode:
            from debug_trace import log
            log("SC", "ECDH: generating pubkey...")
        pubkey = secp256k1.ec_pubkey_create(secret)
        pub_bytes = secp256k1.ec_pubkey_serialize(pubkey, secp256k1.EC_UNCOMPRESSED)

        apdu = bytes([cla, 0x81, 0x00, 0x00, 0x41]) + pub_bytes
        if hil_test_mode:
            log("SC", "ECDH: transmitting %d bytes..." % len(apdu))
        data = connection.transmit(apdu)
        if hil_test_mode:
            log("SC", "ECDH: got response, len=%d" % len(data))
        resp_data = data[0]
        sw1, sw2 = data[1], data[2]
        if hil_test_mode:
            log("SC", "ECDH: SW=%02X%02X" % (sw1, sw2))
        if sw1 != 0x90 or sw2 != 0x00:
            raise ValueError('INIT_SC failed: SW={:02X}{:02X}'.format(sw1, sw2))

        if hil_test_mode:
            log("SC", "ECDH: parsing card pubkey...")
        coordx_size = (resp_data[0] << 8) | resp_data[1]
        coordx = bytes(resp_data[2:2 + coordx_size])

        card_pubkey_compressed = bytes([0x02]) + coordx
        if hil_test_mode:
            log("SC", "ECDH: computing shared secret...")
        card_pubkey = secp256k1.ec_pubkey_parse(card_pubkey_compressed)

        shared_point = secp256k1.ec_pubkey_parse(
            secp256k1.ec_pubkey_serialize(card_pubkey)
        )
        secp256k1.ec_pubkey_tweak_mul(shared_point, secret)
        shared_bytes = secp256k1.ec_pubkey_serialize(shared_point, secp256k1.EC_UNCOMPRESSED)
        shared_secret = shared_bytes[1:33]

        self.aes_key = hmac_sha1(shared_secret, b'sc_key')[:16]
        self.mac_key = hmac_sha1(shared_secret, b'sc_mac')
        self.is_initialized = True
        if hil_test_mode:
            log("SC", "ECDH: secure channel initialized")

    def encrypt_apdu(self, inner_apdu: bytes, cla=0xB0) -> bytes:
        if not self.is_initialized:
            raise ValueError("Secure channel not initialized")

        iv = get_random_bytes(12) + self.iv_counter.to_bytes(4, 'big')
        if iv[15] % 2 == 0:
            iv = iv[:15] + bytes([iv[15] | 0x01])

        padded = pkcs7_pad(inner_apdu, AES_BLOCK)
        cipher = aes(self.aes_key, 2, iv)
        ciphertext = cipher.encrypt(padded)

        mac_data = iv + len(ciphertext).to_bytes(2, 'big') + ciphertext
        mac = hmac_sha1(self.mac_key, mac_data)

        payload = iv + len(ciphertext).to_bytes(2, 'big') + ciphertext + (20).to_bytes(2, 'big') + mac
        wrapped = bytes([cla, 0x82, 0x00, 0x00, len(payload)]) + payload

        self.iv_counter += 2
        return wrapped

    def decrypt_response(self, encrypted_response: bytes) -> bytes:
        card_iv = encrypted_response[:16]
        data_size = int.from_bytes(encrypted_response[16:18], 'big')
        ciphertext = encrypted_response[18:18 + data_size]

        cipher = aes(self.aes_key, 2, card_iv)
        plaintext = cipher.decrypt(ciphertext)
        return pkcs7_unpad(plaintext)
