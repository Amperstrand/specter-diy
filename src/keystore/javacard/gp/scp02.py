"""SCP02 Secure Channel Protocol (GlobalPlatform Card Specification v2.2.1).

3DES-based secure channel: 3DES-CBC for encryption,
DES-CBC-MAC (ISO 9797-1 algorithm 3) for authentication.

Reference: martinpaljak/GlobalPlatformPro SCP02Wrapper.java, PlaintextKeys.java
"""

from rng import get_random_bytes
from binascii import hexlify

from .des3 import (
    des3_ecb_encrypt, des3_ecb_decrypt,
    des3_cbc_encrypt_raw, des3_cbc_decrypt_raw,
    des_cbc_encrypt_raw,
    _des_encrypt_block,
)


class SCP02Error(Exception):
    pass


_SCP02_CONSTANTS = {
    "enc":  bytes([0x01, 0x82]),
    "mac":  bytes([0x01, 0x01]),
    "rmac": bytes([0x01, 0x02]),
    "dek":  bytes([0x01, 0x81]),
}


def _derive_session_key(card_key, purpose, sequence_counter):
    """Derive an SCP02 session key.

    card_key: 16 bytes (2-key 3DES card key)
    purpose: one of "enc", "mac", "rmac", "dek"
    sequence_counter: 2 bytes
    Returns: 16 bytes
    """
    constant = _SCP02_CONSTANTS[purpose]
    derivation_data = constant + sequence_counter + b'\x00' * 12
    return des3_cbc_encrypt_raw(card_key, b'\x00' * 8, derivation_data)


def _mac_des_3des(mac_key, data, icv):
    """DES-CBC-MAC using ISO 9797-1 algorithm 3 (full triple DES MAC).

    Pads data with 0x80 + 0x00s to 8-byte boundary.
    If padded data > 8 bytes: single-DES-CBC on all but last block,
    take last 8 bytes as new ICV.
    Then 3DES-CBC on last block with new ICV.

    mac_key: 16 bytes
    data: bytes (unpadded)
    icv: 8 bytes
    Returns: 8 bytes MAC
    """
    padded = data + b'\x80'
    if len(padded) % 8 != 0:
        padded += b'\x00' * (8 - (len(padded) % 8))

    current_iv = icv
    if len(padded) > 8:
        current_iv = des_cbc_encrypt_raw(
            mac_key[:8], current_iv, padded[:-8])[-8:]

    last_block = padded[-8:]
    block = bytes(a ^ b for a, b in zip(last_block, current_iv))
    return des3_ecb_encrypt(mac_key, block)


def _mac_3des(enc_key, data, iv):
    """Full 3DES-CBC-MAC (ISO 9797-1 algorithm 1).

    Used for card/host cryptogram verification.
    Pads data with 0x80 + 0x00s, then 3DES-CBC, return last 8 bytes.

    enc_key: 16 bytes
    data: bytes
    iv: 8 bytes
    Returns: 8 bytes
    """
    padded = data + b'\x80'
    if len(padded) % 8 != 0:
        padded += b'\x00' * (8 - (len(padded) % 8))
    ct = des3_cbc_encrypt_raw(enc_key, iv, padded)
    return ct[-8:]


def _select_isd(conn):
    """SELECT the Issuer Security Domain (Card Manager).

    Uses P1=04 (select by DF name) with no data field to auto-select
    the ISD, matching gp.jar behavior.
    """
    apdu = bytes([0x00, 0xA4, 0x04, 0x00, 0x00])
    resp = conn.transmit(apdu)
    if isinstance(resp[0], bytes):
        resp_data = resp[0]
    else:
        resp_data = resp[:-2]
    sw1, sw2 = resp[-2], resp[-1]
    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP02Error("SELECT ISD failed: SW=%02X%02X" % (sw1, sw2))
    return resp_data


def _transmit_raw(conn, apdu):
    """Send raw APDU and return (data_bytes, sw1, sw2)."""
    resp = conn.transmit(apdu)
    if isinstance(resp[0], bytes):
        return resp[0], resp[1], resp[2]
    data = resp[:-2]
    sw1, sw2 = resp[-2], resp[-1]
    return data, sw1, sw2


def _parse_init_update_response(resp_data):
    """Parse SCP02 INITIALIZE UPDATE response.

    Format (GP 2.2.1, 28 bytes for SCP02):
      diversification_data (10 bytes)
      key_version (1 byte)
      scp_id (1 byte)
      card_challenge (8 bytes)
      card_cryptogram (8 bytes)

    The sequence counter is embedded in the first 2 bytes of
    the card challenge (per GPPro/GP spec convention).
    """
    if len(resp_data) < 28:
        raise SCP02Error("INIT UPDATE response too short: %d bytes"
                         % len(resp_data))

    kdd = resp_data[0:10]
    kvi = resp_data[10]
    scp_id = resp_data[11]
    card_challenge = resp_data[12:20]
    card_cryptogram = resp_data[20:28]
    seq_counter = card_challenge[0:2]

    return {
        "kdd": kdd,
        "kvi": kvi,
        "scp_id": scp_id,
        "seq_counter": seq_counter,
        "card_challenge": card_challenge,
        "card_cryptogram": card_cryptogram,
    }


class SCP02Session:
    """An active SCP02 secure channel session."""

    def __init__(self, s_enc, s_mac, s_rmac, conn):
        self.s_enc = s_enc
        self.s_mac = s_mac
        self.s_rmac = s_rmac
        self.conn = conn
        self.icv = None
        self.ricv = None
        self.mac = True
        self.enc = False
        self.rmac = False

    def _compute_icv(self):
        """Encrypt the current ICV with single-DES for next MAC computation."""
        if self.icv is None:
            self.icv = b'\x00' * 8
        else:
            self.icv = _des_encrypt_block(self.s_mac[:8], self.icv)

    def wrap_command(self, cla, ins, p1, p2, data=b""):
        """Wrap an APDU with SCP02 secure messaging (C-MAC mode).

        Sets CLA bit 2, appends 8-byte MAC after data.
        """
        self._compute_icv()

        sm_cla = cla | 0x04
        lc = len(data) + 8

        mac_input = bytes([sm_cla, ins, p1, p2, lc]) + data
        self.icv = _mac_des_3des(self.s_mac, mac_input, self.icv)

        result = bytes([sm_cla, ins, p1, p2, lc]) + data + self.icv + bytes([0x00])
        return result

    def send_command(self, cla, ins, p1, p2, data=b""):
        """Send a wrapped command and return response."""
        apdu = self.wrap_command(cla, ins, p1, p2, data)
        resp_data, sw1, sw2 = _transmit_raw(self.conn, apdu)
        return resp_data, sw1, sw2

    def send_command_plain(self, cla, ins, p1, p2, data=b""):
        """Send an unwrapped command."""
        lc = len(data)
        apdu = bytes([cla, ins, p1, p2, lc]) + data + bytes([0x00])
        return _transmit_raw(self.conn, apdu)

    def end_session(self):
        """Send GP END SESSION to cleanly terminate secure channel."""
        try:
            apdu = self.wrap_command(0x80, 0x82, 0x80, 0x00)
            _transmit_raw(self.conn, apdu)
        except Exception:
            pass


def open_session(conn, profile):
    """Open an SCP02 secure channel with the card.

    Steps:
    1. SELECT ISD
    2. INITIALIZE UPDATE (with diversification data returned)
    3. Derive session keys from sequence counter
    4. Verify card cryptogram (3DES-MAC over host||card challenge)
    5. Compute host cryptogram (3DES-MAC over card||host challenge)
    6. EXTERNAL AUTHENTICATE (with C-MAC)

    Returns an SCP02Session ready for secure messaging.
    """
    enc_key = profile["enc_key"]
    mac_key = profile["mac_key"]

    _select_isd(conn)

    host_chal = get_random_bytes(8)
    kvi = profile.get("key_version", 0)
    ki = profile.get("key_index", 0)

    init_apdu = bytes([0x80, 0x50, kvi, ki, 0x08]) + host_chal + bytes([0x00])
    resp_data, sw1, sw2 = _transmit_raw(conn, init_apdu)

    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP02Error("INITIALIZE UPDATE failed: SW=%02X%02X" % (sw1, sw2))

    params = _parse_init_update_response(resp_data)
    card_chal = params["card_challenge"]
    card_crypto = params["card_cryptogram"]
    seq_counter = params["seq_counter"]

    s_enc = _derive_session_key(enc_key, "enc", seq_counter)
    s_mac = _derive_session_key(mac_key, "mac", seq_counter)
    s_rmac = _derive_session_key(mac_key, "rmac", seq_counter)

    expected_card_crypto = _mac_3des(s_enc, host_chal + card_chal, b'\x00' * 8)
    if expected_card_crypto != card_crypto:
        raise SCP02Error("Card cryptogram mismatch: expected %s got %s"
                         % (hexlify(expected_card_crypto).decode(),
                            hexlify(card_crypto).decode()))

    host_crypto = _mac_3des(s_enc, card_chal + host_chal, b'\x00' * 8)

    session = SCP02Session(s_enc, s_mac, s_rmac, conn)

    ext_auth_data = host_crypto
    mac_input = bytes([0x84, 0x82, 0x01, 0x00, 0x10]) + ext_auth_data
    session.icv = _mac_des_3des(s_mac, mac_input, b'\x00' * 8)

    ext_auth_apdu = (bytes([0x84, 0x82, 0x01, 0x00, 0x10])
                     + ext_auth_data
                     + session.icv
                     + bytes([0x00]))
    resp_data, sw1, sw2 = _transmit_raw(conn, ext_auth_apdu)

    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP02Error("EXTERNAL AUTHENTICATE failed: SW=%02X%02X"
                         % (sw1, sw2))

    return session
