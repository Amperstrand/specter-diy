"""SCP03 Secure Channel Protocol (GlobalPlatform Card Specification v2.3).

All-AES secure channel: AES-128 for key derivation (AES-CMAC-KDF),
AES-128-CBC for encryption, AES-CMAC for message authentication.

Reference: kaoh/globalplatform/src/crypto.c, OpenJavaCard SCP03Derivation.java
"""

from ucryptolib import aes as _aes
from rng import get_random_bytes
from .aes_cmac import aes_cmac

from binascii import hexlify

AES_BLOCK = 16


class SCP03Error(Exception):
    pass


class _KDF:
    """NIST SP 800-108 KDF in Counter Mode with AES-CMAC as PRF."""

    @staticmethod
    def derive(key, constant, context=b"", length=16):
        label = b'\x00' * 11 + bytes([constant]) + b'\x00'
        label += (length >> 8 & 0xFF).to_bytes(1, 'big')
        label += (length & 0xFF).to_bytes(1, 'big')

        n = (length + 15) // 16
        output = b""
        for i in range(1, n + 1):
            inp = label + bytes([i]) + context
            output += aes_cmac(key, inp)

        return output[:length]


def _derive_session_keys(enc_key, mac_key, rmac_key, host_chal, card_chal):
    context = host_chal + card_chal
    s_enc = _KDF.derive(enc_key, 0x04, context, 16)
    s_mac = _KDF.derive(mac_key, 0x06, context, 16)
    s_rmac = _KDF.derive(rmac_key, 0x07, context, 16)
    return s_enc, s_mac, s_rmac


def _verify_card_cryptogram(s_mac, host_chal, card_chal, expected):
    context = host_chal + card_chal
    computed = _KDF.derive(s_mac, 0x00, context, 8)
    if computed != expected:
        raise SCP03Error("Card cryptogram mismatch: expected %s got %s"
                         % (hexlify(expected).decode(), hexlify(computed).decode()))


def _compute_host_cryptogram(s_mac, host_chal, card_chal):
    context = host_chal + card_chal
    return _KDF.derive(s_mac, 0x01, context, 8)


def _select_isd(conn, isd_aid):
    """SELECT the Issuer Security Domain (Card Manager).

    Uses P1=04 (select by DF name) with no data field to auto-select
    the ISD, matching the behavior of gp.jar.
    """
    apdu = bytes([0x00, 0xA4, 0x04, 0x00, 0x00])
    resp = conn.transmit(apdu)
    if isinstance(resp[0], bytes):
        resp_data = resp[0]
    else:
        resp_data = resp[:-2]
    sw1, sw2 = resp[-2], resp[-1]
    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP03Error("SELECT ISD failed: SW=%02X%02X" % (sw1, sw2))
    return resp_data


def _parse_init_update_response(resp_data, expected_kvi):
    if len(resp_data) < 28:
        raise SCP03Error("INIT UPDATE response too short: %d bytes" % len(resp_data))

    kdd = resp_data[0:10]
    kvi = resp_data[10]
    scp_id = resp_data[11]
    scp_impl = resp_data[12]
    card_chal = resp_data[13:21]
    card_crypto = resp_data[21:29]

    if scp_id != 0x03:
        raise SCP03Error("Card reports SCP%02X, expected SCP03" % scp_id)

    if expected_kvi is not None and kvi != expected_kvi:
        raise SCP03Error("Key version mismatch: card=%02X expected=%02X"
                         % (kvi, expected_kvi))

    seq_counter = None
    if len(resp_data) >= 32:
        seq_counter = resp_data[29:32]

    return {
        "kdd": kdd,
        "kvi": kvi,
        "scp_id": scp_id,
        "scp_impl": scp_impl,
        "card_challenge": card_chal,
        "card_cryptogram": card_crypto,
        "seq_counter": seq_counter,
    }


def _transmit_raw(conn, apdu):
    """Send raw APDU and return (data_bytes, sw1, sw2)."""
    resp = conn.transmit(apdu)
    if isinstance(resp[0], bytes):
        return resp[0], resp[1], resp[2]
    data = resp[:-2]
    sw1, sw2 = resp[-2], resp[-1]
    return data, sw1, sw2


class SCP03Session:
    """An active SCP03 secure channel session."""

    def __init__(self, s_enc, s_mac, s_rmac, conn, rmac_supported=False,
                 renc_supported=False):
        self.s_enc = s_enc
        self.s_mac = s_mac
        self.s_rmac = s_rmac
        self.conn = conn
        self.rmac_supported = rmac_supported
        self.renc_supported = renc_supported
        self.enc_counter = 0
        self.last_c_mac = b'\x00' * 16
        self.last_r_mac = b'\x00' * 16
        self.security_level = 0x01

    def _compute_icv(self, key, counter):
        block = bytearray(16)
        if counter & 1:
            block[0] = 0x80
        block[12] = (counter >> 24) & 0xFF
        block[13] = (counter >> 16) & 0xFF
        block[14] = (counter >> 8) & 0xFF
        block[15] = counter & 0xFF
        c = _aes(key, 1)
        return c.encrypt(bytes(block))

    def _pad_data(self, data):
        return data + b'\x80' + b'\x00' * ((-len(data) - 1) % 16)

    def wrap_command(self, cla, ins, p1, p2, data=b""):
        """Wrap an APDU with SCP03 secure messaging.

        Security level 0x01 (C-MAC): add MAC only.
        Security level 0x03 (C-DEC+C-MAC): encrypt data, then MAC.
        """
        sm_cla = cla | 0x04
        level = self.security_level

        if level >= 0x03 and len(data) > 0:
            self.enc_counter += 1
            icv = self._compute_icv(self.s_enc, self.enc_counter)
            padded = self._pad_data(data)
            c = _aes(self.s_enc, 2, icv)
            enc_data = c.encrypt(padded)
            apdu_data = enc_data
        else:
            apdu_data = data

        lc = len(apdu_data) + 8
        mac_input = (self.last_c_mac
                     + bytes([sm_cla, ins, p1, p2, lc])
                     + apdu_data)
        mac = aes_cmac(self.s_mac, mac_input)
        self.last_c_mac = mac

        apdu = bytes([sm_cla, ins, p1, p2, lc]) + apdu_data + mac[:8] + bytes([0x00])
        return apdu

    def unwrap_response(self, resp_data, sw1, sw2):
        """Verify R-MAC and optionally decrypt R-ENC response."""
        if self.rmac_supported and len(resp_data) >= 8:
            mac_received = resp_data[-8:]
            payload = resp_data[:-8]
            mac_input = self.last_r_mac + payload + bytes([sw1, sw2])
            mac_computed = aes_cmac(self.s_rmac, mac_input)
            self.last_r_mac = mac_computed
            if mac_computed[:8] != mac_received:
                raise SCP03Error("R-MAC verification failed")

            if self.renc_supported and len(payload) > 0:
                self.enc_counter += 1
                icv = self._compute_icv(self.s_enc, self.enc_counter)
                c = _aes(self.s_enc, 2, icv)
                payload = c.decrypt(payload)
                pad_len = payload[-1]
                if pad_len > 0 and pad_len <= 16:
                    check = payload[-pad_len:]
                    if check[0] == 0x80 and all(b == 0 for b in check[1:]):
                        payload = payload[:-pad_len]
            return payload
        return resp_data

    def send_command(self, cla, ins, p1, p2, data=b"", le=None):
        """Send a wrapped command and unwrap the response."""
        apdu = self.wrap_command(cla, ins, p1, p2, data)
        resp_data, sw1, sw2 = _transmit_raw(self.conn, apdu)
        resp_data = self.unwrap_response(resp_data, sw1, sw2)
        return resp_data, sw1, sw2

    def send_command_plain(self, cla, ins, p1, p2, data=b""):
        """Send an unwrapped command (before secure channel is established)."""
        lc = len(data)
        apdu = bytes([cla, ins, p1, p2, lc]) + data + bytes([0x00])
        return _transmit_raw(self.conn, apdu)


def open_session(conn, profile):
    """Open an SCP03 secure channel with the card.

    Steps:
    1. SELECT ISD
    2. INITIALIZE UPDATE
    3. Derive session keys
    4. Verify card cryptogram
    5. Compute host cryptogram
    6. EXTERNAL AUTHENTICATE

    Returns an SCP03Session ready for secure messaging.
    """
    isd_aid = profile["isd_aid"]
    key_version = profile["key_version"]
    key_index = profile["key_index"]
    enc_key = profile["enc_key"]
    mac_key = profile["mac_key"]
    rmac_key = profile["rmac_key"]

    _select_isd(conn, isd_aid)

    host_chal = get_random_bytes(8)
    init_apdu = bytes([0x80, 0x50, key_version, key_index, 0x08]) + host_chal + bytes([0x00])
    resp_data, sw1, sw2 = _transmit_raw(conn, init_apdu)

    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP03Error("INITIALIZE UPDATE failed: SW=%02X%02X" % (sw1, sw2))

    params = _parse_init_update_response(resp_data, key_version)
    card_chal = params["card_challenge"]
    card_crypto = params["card_cryptogram"]

    s_enc, s_mac, s_rmac = _derive_session_keys(
        enc_key, mac_key, rmac_key, host_chal, card_chal)

    _verify_card_cryptogram(s_mac, host_chal, card_chal, card_crypto)

    host_crypto = _compute_host_cryptogram(s_mac, host_chal, card_chal)

    rmac_supported = bool(params["scp_impl"] & 0x20)
    renc_supported = bool(params["scp_impl"] & 0x40)

    session = SCP03Session(s_enc, s_mac, s_rmac, conn, rmac_supported, renc_supported)

    mac_input = (b'\x00' * 16
                 + bytes([0x84, 0x82, 0x01, 0x00, 0x10])
                 + host_crypto)
    mac = aes_cmac(s_mac, mac_input)
    session.last_c_mac = mac

    ext_auth_apdu = bytes([0x84, 0x82, 0x01, 0x00, 0x18]) + host_crypto + mac[:8] + bytes([0x00])
    resp_data, sw1, sw2 = _transmit_raw(conn, ext_auth_apdu)

    if sw1 != 0x90 or sw2 != 0x00:
        raise SCP03Error("EXTERNAL AUTHENTICATE failed: SW=%02X%02X" % (sw1, sw2))

    session.enc_counter = 0

    return session
