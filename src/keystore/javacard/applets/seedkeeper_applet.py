"""SeedKeeper JavaCard applet.

APDU commands for SeedKeeper cards: PIN management, secret listing,
export, card label, and status queries. Uses SatochipSecureChannel
for encrypted communication.
"""
from .applet import Applet, ISOException, AppletException
from .satochip_securechannel import SatochipSecureChannel
from binascii import hexlify
from embit import bip39


class SeedKeeperApplet(Applet):
    """Applet for communicating with SeedKeeper cards."""

    AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
    NAME = "SeedKeeper"
    CLA = 0xB0

    INS_VERIFY_PIN = 0x42
    INS_CHANGE_PIN = 0x44
    INS_CARD_LABEL = 0x3D
    INS_IMPORT_SECRET = 0xA1
    INS_EXPORT_SECRET = 0xA2
    INS_LIST_SECRETS = 0xA6
    INS_GET_STATUS = 0xA7
    INS_DELETE_SECRET = 0xA5

    SECRET_TYPE_MASTERSEED = 0x10
    SECRET_TYPE_BIP39 = 0x30
    SECRET_TYPE_BIP39_V2 = 0x31
    SECRET_TYPE_DESCRIPTOR = 0xC1

    def __init__(self, connection):
        super().__init__(connection, self.AID)
        self.sc = SatochipSecureChannel()

    def init_secure_channel(self):
        """Initialize secure channel. Must be called after select()."""
        self.sc.initiate(self.conn)

    def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
        """Send APDU via secure channel (INS 0x82)."""
        if not self.sc.is_initialized:
            raise AppletException("Secure channel not initialized")

        encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
        data = self.conn.transmit(encrypted_apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        sw = bytes([sw1, sw2])

        if sw == b"\x9c\x30" and retry:
            self.sc.initiate(self.conn)
            encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
            data = self.conn.transmit(encrypted_apdu)
            resp_data, sw1, sw2 = data[0], data[1], data[2]
            sw = bytes([sw1, sw2])

        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())

        if len(resp_data) > 0:
            return self.sc.decrypt_response(resp_data)
        return b''

    def get_card_status(self):
        """Get card status without secure channel (INS 0x3C)."""
        apdu = bytes([self.CLA, 0x3C, 0x00, 0x00])
        data = self.conn.transmit(apdu)
        return data[0], data[1], data[2]

    def get_seedkeeper_status(self):
        """Get card status: secret count, memory usage, logs.
        APDU: B0 A7 00 00
        Response: [nb_secrets(2)][total_mem(2)][free_mem(2)][nb_logs_total(2)][nb_logs_avail(2)]
        """
        apdu = bytes([self.CLA, self.INS_GET_STATUS, 0x00, 0x00])
        resp = self.secure_request(apdu)
        if len(resp) >= 10:
            return {
                'nb_secrets': (resp[0] << 8) | resp[1],
                'total_memory': (resp[2] << 8) | resp[3],
                'free_memory': (resp[4] << 8) | resp[5],
                'nb_logs_total': (resp[6] << 8) | resp[7],
                'nb_logs_avail': (resp[8] << 8) | resp[9],
            }
        return {}

    def verify_pin(self, pin):
        """Verify PIN to unlock the card.
        APDU: B0 42 00 00 [Lc] [PIN]
        Returns: (success_bool, attempts_remaining_or_None)
        """
        if isinstance(pin, str):
            pin = pin.encode()
        inner_apdu = bytes([self.CLA, self.INS_VERIFY_PIN, 0x00, 0x00, len(pin)]) + pin
        self.secure_request(inner_apdu)
        return (True, None)

    def change_pin(self, old_pin, new_pin):
        """Change PIN on the card.
        APDU: B0 44 00 00 [old_len(1)][old_pin][new_len(1)][new_pin]
        """
        if isinstance(old_pin, str):
            old_pin = old_pin.encode()
        if isinstance(new_pin, str):
            new_pin = new_pin.encode()
        apdu_data = bytes([len(old_pin)]) + old_pin + bytes([len(new_pin)]) + new_pin
        inner_apdu = bytes([self.CLA, self.INS_CHANGE_PIN, 0x00, 0x00, len(apdu_data)]) + apdu_data
        self.secure_request(inner_apdu)

    def get_card_label(self):
        """Read card label via INS 0x3D, p2=0x01."""
        apdu = bytes([self.CLA, self.INS_CARD_LABEL, 0x00, 0x01, 0x00])
        resp = self.secure_request(apdu)
        if len(resp) == 0:
            return ""
        label_len = resp[0]
        if label_len == 0 or len(resp) < 1 + label_len:
            return ""
        try:
            return bytes(resp[1:1 + label_len]).decode("utf-8")
        except Exception:
            return hexlify(bytes(resp[1:1 + label_len])).decode()

    def set_card_label(self, label):
        """Set card label via INS 0x3D, p2=0x00."""
        if label is None:
            label = ""
        if isinstance(label, str):
            label_bytes = label.encode("utf-8")
        else:
            label_bytes = bytes(label)
        if len(label_bytes) > 64:
            raise AppletException("Card label too long (max 64 bytes)")
        if len(label_bytes) == 0:
            apdu = bytes([self.CLA, self.INS_CARD_LABEL, 0x00, 0x00, 0x00])
        else:
            payload = bytes([len(label_bytes)]) + label_bytes
            apdu = bytes([self.CLA, self.INS_CARD_LABEL, 0x00, 0x00, len(payload)]) + payload
        self.secure_request(apdu)

    def list_secret_headers(self):
        """List all secret headers using INIT/NEXT iteration.
        Returns list of header dicts with id, type, label, fingerprint, etc.
        """
        headers = []
        p2 = 0x01  # INIT
        while True:
            apdu = bytes([self.CLA, self.INS_LIST_SECRETS, 0x00, p2])
            try:
                resp = self.secure_request(apdu)
            except ISOException as e:
                if str(e) == "9c12":
                    break
                raise
            if len(resp) == 0:
                break
            if len(resp) >= 15:
                headers.append(self._parse_header(resp))
            p2 = 0x02  # NEXT
        return headers

    def delete_secret(self, sid):
        """Delete a secret by ID.
        APDU: B0 A5 00 00 [sid_hi(1)][sid_lo(1)]
        """
        sid_bytes = bytes([(sid >> 8) & 0xFF, sid & 0xFF])
        apdu = bytes([self.CLA, self.INS_DELETE_SECRET, 0x00, 0x00, 0x02]) + sid_bytes
        self.secure_request(apdu)

    def import_secret(self, secret_data, secret_type=0x30, label=""):
        """Import a secret to the card using plaintext transport.

        Multi-step INIT/PROCESS/FINALIZE protocol.
        For BIP39: secret_data = entropy_len(2) || entropy bytes.

        Returns: (secret_id, fingerprint_hex) tuple.
        """
        if isinstance(label, str):
            label_bytes = label.encode("utf-8")
        else:
            label_bytes = bytes(label)
        if len(label_bytes) > 127:
            raise AppletException("Label too long (max 127 bytes)")

        secret_len = len(secret_data)
        padded_size = secret_len + (16 - secret_len % 16) % 16

        header = bytes([
            secret_type,
            0x01,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00, 0x00, 0x00, 0x00,
            0x00,
            0x00,
            len(label_bytes),
        ])

        init_data = header + label_bytes + bytes([padded_size >> 8, padded_size & 0xFF])
        init_apdu = bytes([self.CLA, self.INS_IMPORT_SECRET, 0x01, 0x01, len(init_data)]) + init_data
        resp = self.secure_request(init_apdu)

        chunk_size = 128
        offset = 0
        while offset < secret_len:
            remaining = secret_len - offset
            size = min(chunk_size, remaining)
            is_last = (offset + size >= secret_len)
            p2 = 0x03 if is_last else 0x02
            chunk = secret_data[offset:offset + size]
            chunk_apdu = bytes([
                self.CLA, self.INS_IMPORT_SECRET, 0x01, p2,
                2 + len(chunk)
            ]) + bytes([size >> 8, size & 0xFF]) + chunk
            resp = self.secure_request(chunk_apdu)
            offset += size

        if len(resp) >= 6:
            sid = (resp[0] << 8) | resp[1]
            fp = hexlify(bytes(resp[2:6])).decode()
            return sid, fp
        raise AppletException("Import failed: unexpected response")

    def _parse_header(self, data):
        """Parse a 15+ byte secret header.
        Format: id(2)|type(1)|origin(1)|export_rights(1)|export_nbplain(1)|
                export_nbsecure(1)|export_counter(1)|fingerprint(4)|subtype(1)|
                rfu(1)|label_len(1)|label(N)
        """
        header = {
            'id': (data[0] << 8) | data[1],
            'type': data[2],
            'origin': data[3],
            'export_rights': data[4],
            'export_nbplain': data[5],
            'export_nbsecure': data[6],
            'export_counter': data[7],
            'fingerprint': hexlify(bytes(data[8:12])).decode(),
            'subtype': data[12],
            'rfu': data[13],
            'label': ''
        }
        label_len = data[14]
        if label_len > 0 and len(data) >= 15 + label_len:
            try:
                header['label'] = bytes(data[15:15 + label_len]).decode('utf-8')
            except Exception:
                header['label'] = hexlify(bytes(data[15:15 + label_len])).decode()
        return header

    def export_secret(self, sid, include_header=False):
        """Export a secret by ID using multi-step INIT/UPDATE protocol.
        Returns: full secret payload bytes.
        """
        sid_bytes = bytes([(sid >> 8) & 0xFF, sid & 0xFF])

        # INIT - returns header only
        apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x01, 0x02]) + sid_bytes
        resp = self.secure_request(apdu)

        if len(resp) < 13:
            return b''

        header_label_len = resp[12]
        chunks = []

        chunk_num = 1
        while True:
            apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x02, 0x02]) + sid_bytes
            resp = self.secure_request(apdu)

            if len(resp) < 2:
                break

            chunk_size = (resp[0] << 8) | resp[1]
            if chunk_size > 0:
                chunks.append(resp[2:2 + chunk_size])

            # Last chunk has signature after data
            response_size = len(resp)
            if chunk_size + 2 < response_size:
                break

            chunk_num += 1
            if chunk_num > 50:
                break

        return b''.join(chunks)

    def _parse_masterseed_to_mnemonic(self, secret_data: bytes) -> str:
        """Parse MASTERSEED format to BIP39 mnemonic.
        Format: masterseed_size(1)|masterseed(N)|wordlist(1)|entropy_size(1)|entropy(M)
        """
        offset = 0
        offset += 1 + secret_data[offset]  # skip masterseed
        offset += 1  # skip wordlist
        entropy_size = secret_data[offset]
        offset += 1
        entropy = secret_data[offset:offset + entropy_size]
        return bip39.mnemonic_from_bytes(entropy)

    def get_bip39_secret(self, secret_id=None, secret_type=None):
        """Find and export a BIP39 secret, convert to mnemonic.
        Returns: mnemonic string
        """
        if secret_id is not None:
            if secret_type is None:
                for h in self.list_secret_headers():
                    if h['id'] == secret_id:
                        secret_type = h['type']
                        break
            secret_data = self.export_secret(secret_id)
            if secret_type == self.SECRET_TYPE_MASTERSEED:
                return self._parse_masterseed_to_mnemonic(secret_data)
            # BIP39 format: entropy_len(2) || entropy
            if len(secret_data) >= 2:
                entropy_len = (secret_data[0] << 8) | secret_data[1]
                return bip39.mnemonic_from_bytes(secret_data[2:2 + entropy_len])
            raise AppletException("Invalid BIP39 secret format")

        # Default: search for first BIP39 or MASTERSEED secret
        headers = self.list_secret_headers()
        for h in headers:
            if h['type'] in (self.SECRET_TYPE_BIP39, self.SECRET_TYPE_BIP39_V2, self.SECRET_TYPE_MASTERSEED):
                secret_data = self.export_secret(h['id'])
                if h['type'] == self.SECRET_TYPE_MASTERSEED:
                    return self._parse_masterseed_to_mnemonic(secret_data)
                if len(secret_data) >= 2:
                    entropy_len = (secret_data[0] << 8) | secret_data[1]
                    return bip39.mnemonic_from_bytes(secret_data[2:2 + entropy_len])

        raise AppletException("No BIP39 or MASTERSEED secrets found on card")

    def get_descriptor_secrets(self):
        """Find and export all wallet descriptor secrets (type 0xC1)."""
        headers = self.list_secret_headers()
        descriptors = []
        for h in headers:
            if h['type'] == self.SECRET_TYPE_DESCRIPTOR:
                try:
                    secret_data = self.export_secret(h['id'])
                    if len(secret_data) >= 2:
                        desc_len = (secret_data[0] << 8) | secret_data[1]
                        descriptor_str = secret_data[2:2 + desc_len].decode('utf-8', errors='replace')
                        descriptors.append({
                            'id': h['id'],
                            'label': h['label'],
                            'descriptor': descriptor_str
                        })
                except Exception:
                    pass
        return descriptors


def _is_bip39_header(h):
    """Check if a secret header represents a BIP39-compatible secret."""
    return h['type'] in (0x10, 0x30, 0x31) and (h['type'] != 0x10 or h.get('subtype') == 1)
