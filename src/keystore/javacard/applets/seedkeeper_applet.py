from .secure_applet_base import SecureAppletBase
from .applet import ISOException, AppletException
from binascii import hexlify
from embit import bip39
class SeedKeeperApplet(SecureAppletBase):
    """Applet for communicating with SeedKeeper cards.
    
    Inherits secure channel functionality from SecureAppletBase.
    """

    # SeedKeeper AID (Application Identifier) - ASCII "SeedKeeper"
    AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
    NAME = "SeedKeeper"

    # CLA byte for SeedKeeper commands
    CLA = 0xB0

    # Instruction bytes
    INS_VERIFY_PIN = 0x42
    INS_CARD_LABEL = 0x3D
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
        print("[SeedKeeper] Applet initialized")


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

    def get_card_label(self):
        """Read card-level label via INS 0x3D, p2=0x01."""
        apdu = bytes([self.CLA, self.INS_CARD_LABEL, 0x00, 0x01, 0x00])
        print("[SeedKeeper] TX (encrypted): CARD_LABEL GET")
        resp = self.secure_request(apdu)
        if len(resp) == 0:
            return ""
        label_len = resp[0]
        if label_len == 0:
            return ""
        if len(resp) < 1 + label_len:
            print("[SeedKeeper] CARD_LABEL GET: malformed response")
            return ""
        try:
            label = bytes(resp[1:1 + label_len]).decode("utf-8")
        except Exception:
            label = hexlify(bytes(resp[1:1 + label_len])).decode()
        print("[SeedKeeper] Card label:", label)
        return label

    def set_card_label(self, label):
        """Set card-level label via INS 0x3D, p2=0x00."""
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
        print("[SeedKeeper] TX (encrypted): CARD_LABEL SET")
        self.secure_request(apdu)
        print("[SeedKeeper] Card label updated")

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
        Export a secret by ID using multi-step INIT/UPDATE protocol.
        
        Protocol (from Java applet exportSecret() line 2175):
        - INIT (p2=0x01): Returns [id(2b) | header(13b) | label | IV(16b, secure only)]
          NO data chunks in INIT response!
        - UPDATE (p2=0x02): Returns [chunk_size(2b) | chunk_data | sig_size(2b) | sig] on last chunk,
          or [chunk_size(2b) | chunk_data] for intermediate chunks.
        
        Returns: full secret bytes (just the secret payload, not header)
        """
        sid_bytes = bytes([(sid >> 8) & 0xFF, sid & 0xFF])

        # INIT - returns header only, NOT chunk data!
        # Response format: [id(2b) | header(13b) | label(N) | IV(16b, optional)]
        apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x01, 0x02]) + sid_bytes
        print("[SeedKeeper] TX (encrypted): EXPORT INIT")

        resp = self.secure_request(apdu)
        print("[SeedKeeper] EXPORT INIT response (header):", ''.join('{:02x}'.format(b) for b in resp) if len(resp) > 0 else "empty")
        
        # Parse header to get label length (so we know where data starts in header)
        # Header format: id(2) | type(1) | origin(1) | export_rights(1) | export_nbplain(1) |
        #                export_nbsecure(1) | export_counter(1) | fingerprint(4) | subtype(1) |
        #                rfu(1) | label_len(1) | label(N)
        # Total header size = 13 + label_len
        if len(resp) < 13:
            print("[SeedKeeper] ERROR: INIT response too short")
            return b''
        
        header_label_len = resp[12]  # label_len is at offset 12
        header_size = 13 + header_label_len
        print("[SeedKeeper] Header size:", header_size, "(label_len:", header_label_len, ")")
        
        # Collect chunks from UPDATE calls
        chunks = []
        
        # UPDATE loop - this is where actual secret data comes from
        chunk_num = 1
        while True:
            apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x02, 0x02]) + sid_bytes
            print("[SeedKeeper] TX (encrypted): EXPORT UPDATE")

            resp = self.secure_request(apdu)

            if len(resp) < 2:
                print("[SeedKeeper] UPDATE response too short, stopping")
                break
                
            # Response format: [chunk_size(2b) | chunk_data | sig_size(2b) | sig]
            chunk_size = (resp[0] << 8) | resp[1]
            print("[SeedKeeper] Chunk", chunk_num, "len:", chunk_size)
            
            if chunk_size > 0:
                chunk_data = resp[2:2 + chunk_size]
                chunks.append(chunk_data)
            
            # Check if this is the last chunk (signature follows data)
            # Last chunk format: [chunk_size(2b) | chunk_data | sig_size(2b) | sig]
            # So if response_size > chunk_size + 2, we have a signature = last chunk
            response_size = len(resp)
            if chunk_size + 2 < response_size:
                sig_offset = 2 + chunk_size
                sig_size = (resp[sig_offset] << 8) | resp[sig_offset + 1]
                print("[SeedKeeper] Final chunk detected (has signature, size:", sig_size, ")")
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

    def get_bip39_secret(self, secret_id=None, secret_type=None):
        """
        Convenience method: find first BIP39 secret (type 0x30), export it,
        extract entropy bytes, and convert to mnemonic via embit.
        Returns: mnemonic string
        
        Args:
            secret_id: Optional secret ID to directly export. If provided, skips header search.
            secret_type: Optional secret type for parsing when secret_id is provided.
        """
        print("[SeedKeeper] get_bip39_secret called with secret_id:", secret_id, "secret_type:", hex(secret_type))
        
        # If secret_id provided, use it directly instead of searching headers
        if secret_id is not None:
            # Get secret type from header if not provided
            if secret_type is None:
                headers = self.list_secret_headers()
                for h in headers:
                    if h['id'] == secret_id:
                        secret_type = h['type']
                        break
            
            print("[SeedKeeper] Direct export with secret_id:", secret_id, "type:", hex(secret_type))
            
            # Export the secret directly
            secret_data = self.export_secret(secret_id)
            
            # Parse based on secret type
            if secret_type == self.SECRET_TYPE_MASTERSEED:
                # MASTERSEED format (type 0x10 with BIP39 subtype):
                # Format: masterseed_size(1) | masterseed(N) | wordlist(1) | entropy_size(1) | entropy(M) | passphrase_size(1) | passphrase
                print("[SeedKeeper] Parsing MASTERSEED format...")
                
                # Dynamic offset parsing
                offset = 0
                masterseed_size = secret_data[offset]
                offset += 1
                offset += masterseed_size  # Skip masterseed bytes
                
                wordlist = secret_data[offset]
                offset += 1
                
                entropy_size = secret_data[offset]
                offset += 1
                
                entropy = secret_data[offset:offset + entropy_size]
                
                print("[SeedKeeper] MASTERSEED: masterseed_size=", masterseed_size, 
                      "wordlist=", wordlist, "entropy_size=", entropy_size)
                print("[SeedKeeper] Entropy (hex):", ''.join('{:02x}'.format(b) for b in entropy))
                mnemonic = bip39.mnemonic_from_bytes(entropy)
                print("[SeedKeeper] Successfully converted to mnemonic")
                return mnemonic
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
        
        # Default: search for first BIP39 or MASTERSEED secret
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
            # Format: masterseed_size(1) | masterseed(N) | wordlist(1) | entropy_size(1) | entropy(M) | passphrase_size(1) | passphrase
            print("[SeedKeeper] Parsing MASTERSEED format...")
            
            # Dynamic offset parsing
            offset = 0
            masterseed_size = secret_data[offset]
            offset += 1
            offset += masterseed_size  # Skip masterseed bytes
            
            wordlist = secret_data[offset]
            offset += 1
            
            entropy_size = secret_data[offset]
            offset += 1
            
            entropy = secret_data[offset:offset + entropy_size]
            
            print("[SeedKeeper] MASTERSEED: masterseed_size=", masterseed_size, 
                  "wordlist=", wordlist, "entropy_size=", entropy_size)
            print("[SeedKeeper] Entropy (hex):", ''.join('{:02x}'.format(b) for b in entropy))
            mnemonic = bip39.mnemonic_from_bytes(entropy)
            print("[SeedKeeper] Successfully converted to mnemonic")
            return mnemonic
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
