"""
Satochip Secure Channel - Crypto primitives for SeedKeeper and Satochip applets.

Implements ECDH key exchange, AES-CBC encryption, and HMAC-SHA1 authentication.
This is the Satochip/SeedKeeper protocol, distinct from MemoryCard's SecureChannel
(which uses HMAC-SHA256 and a different key derivation scheme).

Protocol reference: Toporin/pysatochip CardConnector.py + SecureChannel.py
"""

import hashlib
import secp256k1
from ucryptolib import aes
from rng import get_random_bytes


AES_BLOCK = 16
MAC_SIZE = 20


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


def der_sig_to_compact(der_sig: bytes) -> bytes:
    """Convert a DER-encoded ECDSA signature to 64-byte compact format.

    DER format: 0x30 <total_len> 0x02 <r_len> <r> 0x02 <s_len> <s>
    Compact format: r(32 bytes, big-endian) + s(32 bytes, big-endian)

    Used for pysatochip challenge-response verification, which returns
    DER-encoded signatures per the Satochip protocol specification.
    """
    idx = 0
    if der_sig[idx] != 0x30:
        raise ValueError("Invalid DER signature: missing SEQUENCE tag")
    idx += 1
    total_len = der_sig[idx]
    idx += 1

    if der_sig[idx] != 0x02:
        raise ValueError("Invalid DER signature: missing INTEGER tag for r")
    idx += 1
    r_len = der_sig[idx]
    idx += 1
    r = der_sig[idx:idx + r_len]
    idx += r_len

    if der_sig[idx] != 0x02:
        raise ValueError("Invalid DER signature: missing INTEGER tag for s")
    idx += 1
    s_len = der_sig[idx]
    idx += 1
    s = der_sig[idx:idx + s_len]

    r_padded = (b'\x00' * (32 - len(r))) + r
    s_padded = (b'\x00' * (32 - len(s))) + s
    return r_padded + s_padded


class SatochipSecureChannel:
    """Secure channel for Satochip/SeedKeeper JavaCard applets.

    ECDH key exchange with AES-CBC encryption and HMAC-SHA1 authentication.
    Matches pysatochip SecureChannel protocol (Toporin/pysatochip).
    """

    def __init__(self):
        self.aes_key = None
        self.mac_key = None
        self.iv_counter = 1
        self.is_initialized = False
        self.card_pubkey = None

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

        card_pubkey = None
        for prefix in (b'\x02', b'\x03'):
            card_pubkey_compressed = prefix + coordx
            try:
                card_pubkey = secp256k1.ec_pubkey_parse(card_pubkey_compressed)
                break
            except Exception:
                continue
        if card_pubkey is None:
            raise ValueError("Failed to parse card pubkey from x-coordinate")
        self.card_pubkey = card_pubkey

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

    def reset(self):
        self.aes_key = None
        self.mac_key = None
        self.iv_counter = 1
        self.is_initialized = False
        self.card_pubkey = None

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

        payload = iv + len(ciphertext).to_bytes(2, 'big') + ciphertext + MAC_SIZE.to_bytes(2, 'big') + mac
        wrapped = bytes([cla, 0x82, 0x00, 0x00, len(payload)]) + payload

        self.iv_counter += 2
        return wrapped

    def decrypt_response(self, encrypted_response: bytes) -> bytes:
        if not self.is_initialized:
            raise ValueError("Secure channel not initialized")

        if len(encrypted_response) < 18:
            raise ValueError("Encrypted response too short")

        card_iv = encrypted_response[:16]
        data_size = int.from_bytes(encrypted_response[16:18], 'big')

        if 18 + data_size + 2 > len(encrypted_response):
            raise ValueError("Encrypted response truncated: expected %d data bytes, have %d" % (data_size, len(encrypted_response) - 18))

        ciphertext = encrypted_response[18:18 + data_size]

        mac_len_offset = 18 + data_size
        if mac_len_offset + 2 > len(encrypted_response):
            raise ValueError("Encrypted response missing MAC length field")
        mac_size = int.from_bytes(encrypted_response[mac_len_offset:mac_len_offset + 2], 'big')

        if mac_len_offset + 2 + mac_size > len(encrypted_response):
            raise ValueError("Encrypted response truncated: expected %d MAC bytes, have %d" % (mac_size, len(encrypted_response) - mac_len_offset - 2))
        received_mac = encrypted_response[mac_len_offset + 2:mac_len_offset + 2 + mac_size]

        mac_data = card_iv + encrypted_response[16:18] + ciphertext
        expected_mac = hmac_sha1(self.mac_key, mac_data)
        if received_mac != expected_mac:
            raise ValueError("MAC verification failed on card response")

        cipher = aes(self.aes_key, 2, card_iv)
        plaintext = cipher.decrypt(ciphertext)
        return pkcs7_unpad(plaintext)

    def verify_card_authenticity(self, connection, cla=0xB0):
        """Perform ECDSA challenge-response to verify card identity.

        Sends a 32-byte random challenge to the card via INS 0x9A. The card
        responds with its own 32-byte challenge + a DER-encoded ECDSA signature
        over SHA-256("Challenge:" || card_challenge || host_challenge).

        Returns True if the card's ECDSA signature is valid, proving the card
        holds the private key corresponding to the pubkey from the ECDH handshake.

        This matches pysatochip's card_challenge_response_pki() protocol but
        uses the MicroPython secp256k1 binding directly instead of the ecdsa library.
        """
        if self.card_pubkey is None:
            raise ValueError("No card pubkey — call initiate() first")

        host_challenge = get_random_bytes(32)

        apdu = bytes([cla, 0x9A, 0x00, 0x00, 0x20]) + host_challenge
        data = connection.transmit(apdu)
        resp_data = data[0]
        sw1, sw2 = data[1], data[2]
        if sw1 != 0x90 or sw2 != 0x00:
            raise ValueError('CHALLENGE_RESPONSE failed: SW={:02X}{:02X}'.format(sw1, sw2))

        card_challenge = bytes(resp_data[0:32])
        sig_size = (resp_data[32] << 8) | resp_data[33]
        sig_der = bytes(resp_data[34:34 + sig_size])

        challenge = hashlib.sha256(b"Challenge:" + card_challenge + host_challenge).digest()

        sig_compact = der_sig_to_compact(sig_der)

        pubkey_raw = secp256k1.ec_pubkey_serialize(self.card_pubkey, secp256k1.EC_UNCOMPRESSED)[1:]
        if len(pubkey_raw) != 64:
            raise ValueError("Unexpected pubkey length: %d" % len(pubkey_raw))

        return secp256k1.ecdsa_verify(sig_compact, challenge, pubkey_raw)
