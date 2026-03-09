"""
SeedKeeper applet for Satochip SeedKeeper card communication.
Inherits from Applet (NOT SecureApplet) - SeedKeeper uses its own PIN protocol.
"""
from .applet import Applet, ISOException, AppletException
from binascii import hexlify
from embit import bip39
from .seedkeeper_securechannel import SeedKeeperSecureChannel

class SeedKeeperApplet(Applet):
    """Applet for communicating with SeedKeeper cards."""

    # SeedKeeper AID (Application Identifier) - ASCII "SeedKeeper"
    AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
    NAME = "SeedKeeper"

    # CLA byte for SeedKeeper commands
    CLA = 0xB0

    # Instruction bytes
    INS_VERIFY_PIN = 0x42
    INS_EXPORT_SECRET = 0xA2
    INS_LIST_SECRETS = 0xA6
    INS_GET_STATUS = 0xA7

    # Secret types
    SECRET_TYPE_MASTERSEED = 0x10
    SECRET_TYPE_BIP39 = 0x30
    SECRET_TYPE_BIP39_V2 = 0x31

    def __init__(self, connection):
        """Initialize with card connection."""
        super().__init__(connection, self.AID)
        self.sc = SeedKeeperSecureChannel()
        print("[SeedKeeper] Applet initialized")

    def init_secure_channel(self):
        """Initialize secure channel. WARNING: select() MUST precede this. NEVER re-select after SC init."""
        print("[SeedKeeper] Establishing secure channel...")
        self.sc.initiate(self.conn)
        print("[SeedKeeper] Secure channel established")

    def secure_request(self, inner_apdu: bytes) -> bytes:
        """Send APDU via secure channel (INS 0x82)."""
        if not self.sc.is_initialized:
            raise AppletException("Secure channel not initialized")

        encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
        data = self.conn.transmit(encrypted_apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        sw = bytes([sw1, sw2])
        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        if len(resp_data) > 0:
            return self.sc.decrypt_response(resp_data)
        return b''

    def get_seedkeeper_status(self):
        """
        Get card status including PIN attempts and secret count.
        APDU: B0 A7 00 00
        Response: [nb_secrets(2)][total_mem(2)][free_mem(2)][nb_logs_total(2)][nb_logs_avail(2)] SW
        """
        apdu = bytes([self.CLA, self.INS_GET_STATUS, 0x00, 0x00])
        print("[SeedKeeper] TX (encrypted): GET_STATUS")

        resp = self.secure_request(apdu)

        if len(resp) >= 10:
            status = {
                'nb_secrets': (resp[0] << 8) | resp[1],
                'total_memory': (resp[2] << 8) | resp[3],
                'free_memory': (resp[4] << 8) | resp[5],
                'nb_logs_total': (resp[6] << 8) | resp[7],
                'nb_logs_avail': (resp[8] << 8) | resp[9],
            }
            print("[SeedKeeper] Status:", status)
            return status
        return {}

    def verify_pin(self, pin):
        """
        Verify PIN to unlock the card.
        APDU: B0 42 00 00 [Lc] [PIN]
        Returns: (success_bool, attempts_remaining_or_None)
        """
        if isinstance(pin, str):
            pin = pin.encode()

        inner_apdu = bytes([self.CLA, self.INS_VERIFY_PIN, 0x00, 0x00, len(pin)]) + pin
        print("[SeedKeeper] TX (encrypted): VERIFY_PIN")

        self.secure_request(inner_apdu)
        print("[SeedKeeper] PIN verified successfully")
        return (True, None)

    def list_secret_headers(self):
        """
        List all secret headers using INIT/NEXT iteration.
        INIT: B0 A6 00 01
        NEXT: B0 A6 00 02 (repeat until empty response)
        Returns: list of header dicts with id, type, label, etc.
        """
        headers = []
        p2 = 0x01  # INIT

        while True:
            apdu = bytes([self.CLA, self.INS_LIST_SECRETS, 0x00, p2])
            print("[SeedKeeper] TX (encrypted): LIST_SECRETS", "(INIT)" if p2 == 0x01 else "(NEXT)")

            try:
                resp = self.secure_request(apdu)
            except ISOException as e:
                # 9c12 = no more secrets (end of list)
                if str(e) == "9c12":
                    print("[SeedKeeper] End of secret list (no more)")
                    break
                raise

            # Empty response = end of list
            if len(resp) == 0:
                print("[SeedKeeper] End of secret list")
                break

            if len(resp) >= 15:
                header = self._parse_header(resp)
                print("[SeedKeeper] Found secret:", header)
                headers.append(header)

            p2 = 0x02  # NEXT for subsequent calls

        print("[SeedKeeper] Total secrets found:", len(headers))
        return headers

    def _parse_header(self, data):
        """
        Parse a secret header (15 bytes + label).
        Format: id(2) | type(1) | origin(1) | export_rights(1) | export_nbplain(1) |
                export_nbsecure(1) | export_counter(1) | fingerprint(4) | subtype(1) |
                rfu(1) | label_len(1) | label(N)
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
            except:
                header['label'] = hexlify(bytes(data[15:15 + label_len])).decode()

        return header

    def export_secret(self, sid, include_header=False):
        """
        Export a secret by ID using multi-step INIT/UPDATE/FINALIZE protocol.
        INIT: B0 A2 01 01 02 [sid(2)]
        UPDATE: B0 A2 01 02 02 [sid(2)] (repeat)
        FINALIZE: detected when signature appears in response
        Returns: full secret bytes
        """
        sid_bytes = bytes([(sid >> 8) & 0xFF, sid & 0xFF])

        # INIT
        apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x01, 0x02]) + sid_bytes
        print("[SeedKeeper] TX (encrypted): EXPORT INIT")

        resp = self.secure_request(apdu)

        # Collect chunks
        chunks = []

        # Parse first chunk: len(2) || data || [sig_len(2) || sig]
        print("[SeedKeeper] EXPORT INIT response:", ''.join('{:02x}'.format(b) for b in resp) if len(resp) > 0 else "empty")
        if len(resp) >= 2:
            chunk_len = (resp[0] << 8) | resp[1]
            print("[SeedKeeper] Chunk 1 len:", chunk_len)
            if chunk_len > 0:
                chunk_data = resp[2:2 + chunk_len] if len(resp) >= 2 + chunk_len else resp[2:]
                chunks.append(chunk_data)
                # Check if this is the final chunk (has signature)
                remaining = resp[2 + chunk_len:]
                if len(remaining) >= 2:
                    sig_len = (remaining[0] << 8) | remaining[1]
                    if sig_len > 0 and chunk_len > 0:
                        print("[SeedKeeper] Final chunk (has signature), export complete")
                        result = b''.join(chunks)
                        print("[SeedKeeper] Exported secret length:", len(result))
                        return result

        # UPDATE loop
        chunk_num = 2
        while True:
            apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x02, 0x02]) + sid_bytes
            print("[SeedKeeper] TX (encrypted): EXPORT UPDATE")

            resp = self.secure_request(apdu)

            if len(resp) >= 2:
                chunk_len = (resp[0] << 8) | resp[1]
                chunk_data = resp[2:2 + chunk_len] if len(resp) >= 2 + chunk_len else resp[2:]
                chunks.append(chunk_data)
                print("[SeedKeeper] Chunk", chunk_num, "len:", chunk_len)

                # Check if this is the final chunk (has signature appended)
                remaining = resp[2 + chunk_len:]
                if len(remaining) >= 2:
                    sig_len = (remaining[0] << 8) | remaining[1]
                    if sig_len > 0:
                        print("[SeedKeeper] Final chunk (has signature), export complete")
                        break

            chunk_num += 1

            # Safety limit
            if chunk_num > 50:
                print("[SeedKeeper] WARNING: Too many chunks, aborting")
                break

        result = b''.join(chunks)
        print("[SeedKeeper] Exported secret total length:", len(result))
        return result

    def get_card_status(self):
        """Get card status without secure channel (INS 0x3C). Byte 11 = needs_secure_channel flag."""
        apdu = bytes([self.CLA, 0x3C, 0x00, 0x00])
        data = self.conn.transmit(apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        return resp_data, sw1, sw2

    def get_bip39_secret(self):
        """
        Convenience method: find first BIP39 secret (type 0x30), export it,
        extract entropy bytes, and convert to mnemonic via embit.
        Returns: mnemonic string
        """
        print("[SeedKeeper] Searching for BIP39 secrets...")
        headers = self.list_secret_headers()

        # Find first BIP39 or MASTERSEED secret (can both be converted to mnemonic)
        bip39_header = None
        for h in headers:
            if h['type'] == self.SECRET_TYPE_BIP39 or h['type'] == self.SECRET_TYPE_MASTERSEED:
                bip39_header = h
                break

        if bip39_header is None:
            print("[SeedKeeper] No BIP39/MASTERSEED secrets found")
            raise AppletException("No BIP39 or MASTERSEED secrets found on card")

        print("[SeedKeeper] Found secret, id:", bip39_header['id'], "type:", hex(bip39_header['type']), "label:", bip39_header['label'])

        # Export the secret
        secret_data = self.export_secret(bip39_header['id'])

        # Parse based on secret type
        if bip39_header['type'] == self.SECRET_TYPE_MASTERSEED:
            # MASTERSEED format (type 0x10 with BIP39 subtype):
            # masterseed_size(1) || masterseed(64) || wordlist(1) || entropy_size(1) || entropy(32) || ...
            # Entropy is at offset 67-98 (after 1+64+1+1 bytes)
            print("[SeedKeeper] Parsing MASTERSEED format...")
            if len(secret_data) >= 99:
                masterseed_size = secret_data[0]
                wordlist = secret_data[65]
                entropy_size = secret_data[66]
                entropy = secret_data[67:67 + entropy_size]
                print("[SeedKeeper] MASTERSEED: masterseed_size=", masterseed_size, "wordlist=", wordlist, "entropy_size=", entropy_size)
                print("[SeedKeeper] Entropy (hex):", ''.join('{:02x}'.format(b) for b in entropy))
                mnemonic = bip39.mnemonic_from_bytes(entropy)
                print("[SeedKeeper] Successfully converted to mnemonic")
                return mnemonic
            else:
                raise AppletException("Invalid MASTERSEED secret format (too short)")
        else:
            # BIP39 secret format: entropy_len(2) || entropy || [passphrase_len(2) || passphrase]
            print("[SeedKeeper] Parsing BIP39 format...")
            if len(secret_data) >= 2:
                entropy_len = (secret_data[0] << 8) | secret_data[1]
                entropy = secret_data[2:2 + entropy_len]
                print("[SeedKeeper] Entropy length:", entropy_len)

                # Convert to mnemonic
                mnemonic = bip39.mnemonic_from_bytes(entropy)
                print("[SeedKeeper] Successfully converted to mnemonic")
                return mnemonic

        raise AppletException("Invalid BIP39 secret format")
