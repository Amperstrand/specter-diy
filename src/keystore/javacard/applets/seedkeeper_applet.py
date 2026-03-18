from .applet import Applet, ISOException, AppletException
from .satochip_securechannel import SatochipSecureChannel
from binascii import hexlify
from embit import bip39
from debug_trace import log


def _debug(msg):
    log("SeedKeeper", msg)


def _debug2(msg, *args):
    """Debug with multiple args - joins them with spaces."""
    log("SeedKeeper", str(msg) + " " + " ".join(str(a) for a in args))


class SeedKeeperApplet(Applet):
    """Applet for communicating with SeedKeeper cards.
    
    Inherits from Applet and implements secure channel functionality inline.
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

    # =============================================================================
    # SeedKeeper Secret Types
    # =============================================================================
    # SeedKeeper stores secrets in a dictionary indexed by secret ID. Each secret
    # has a type code that determines its format and use case.
    #
    # MASTERSEED (0x10) - BIP32 master seed with full wallet metadata:
    #   This is a comprehensive secret type that bundles everything needed for
    #   wallet recovery in one atomic object:
    #   - 64-byte BIP32 master seed (derived from mnemonic via PBKDF2)
    #   - BIP39 entropy bytes (original random bytes before PBKDF2)
    #   - Wordlist index (English=0, etc.)
    #   - Optional passphrase
    #   - Optional wallet descriptor
    #
    #   WARNING: The masterseed contains the DERIVED seed, not just entropy.
    #   If you only have the masterseed without the entropy, you cannot recover
    #   the original mnemonic words. The entropy field is optional in some
    #   implementations. This type is powerful but requires careful handling.
    #
    #   Format: [seed_len(1)][seed][wordlist(1)][entropy_len(1)][entropy][pass_len(1)][passphrase][desc_len(2)][descriptor]
    #
    # BIP39_MNEMONIC (0x30) - Raw BIP39 entropy:
    #   Stores only the original entropy bytes (16-32 bytes) that can be
    #   converted to mnemonic words. This is the safest format for backup
    #   because the entropy directly maps to the 12/24 recovery words.
    #
    #   Format: [entropy_len(2)][entropy][pass_len(2)][passphrase]
    #
    # BIP39_MNEMONIC_V2 (0x31) - Enhanced BIP39 format:
    #   Same as 0x30 but with additional metadata fields in newer applet versions.
    #   Parsing is identical to 0x30 for entropy extraction.
    #
    # ELECTRUM_MNEMONIC (0x40) - Electrum-specific seed format:
    #   Not currently supported. Electrum uses a different seed derivation
    #   (versioned mnemonics with optional seed_type prefix).
    #
    # WALLET_DESCRIPTOR (0xC1) - Bitcoin output descriptor:
    #   Stores a wallet descriptor string (e.g., "wsh(sortedmulti(2,[fp]xpub...,[fp]xpub...))").
    #   Used for multisig wallet configuration backup. Displayed as debug text.
    #
    #   Format: [size(2)][descriptor_string]
    #
    # Other types (not currently supported):
    #   0x50 - Shamir Secret Share (SLIP-39)
    #   0x60 - Private Key (raw ECC/RSA)
    #   0x70 - Public Key
    #   0x80 - Symmetric Key (AES/HMAC)
    #   0x90 - Password (password manager entries)
    #   0xB0 - 2FA Secret (TOTP/HOTP)
    #   0xC0 - Generic Data (arbitrary bytes)
    # =============================================================================
    
    SECRET_TYPE_MASTERSEED = 0x10      # BIP32 master seed + metadata (see above)
    SECRET_TYPE_BIP39 = 0x30           # BIP39 entropy bytes
    SECRET_TYPE_BIP39_V2 = 0x31        # BIP39 entropy bytes (v2 format)
    SECRET_TYPE_ELECTRUM = 0x40        # Electrum mnemonic (not supported)
    SECRET_TYPE_DESCRIPTOR = 0xC1      # Wallet output descriptor

    def __init__(self, connection):
        """Initialize with card connection."""
        super().__init__(connection, self.AID)
        # Secure channel instance
        self.sc = SatochipSecureChannel()
        _debug("Applet initialized")

    def init_secure_channel(self):
        """
        Initialize secure channel with the card.
        
        Must be called after select() and before any secure commands.
        
        Note: SELECT MUST be called BEFORE init_secure_channel().
        NEVER re-select after secure channel initialization.
        """
        _debug("Establishing secure channel...")
        self.sc.initiate(self.conn)
        _debug("Secure channel established")

    def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
        """
        Send APDU via secure channel (INS 0x82).
        
        Encrypts the inner APDU, sends it to the card, and decrypts the response.
        Automatically re-establishes secure channel on 9c30 error if retry=True.
        
        Args:
            inner_apdu: The plaintext APDU to send
            retry: If True, retry on 9c30 (secure channel corrupted)
        
        Returns:
            Decrypted response data from the card
        
        Raises:
            AppletException: If secure channel not initialized
            ISOException: If card returns non-9000 status word
        """
        if not self.sc.is_initialized:
            raise AppletException("Secure channel not initialized")
        
        # Encrypt the inner APDU
        encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
        
        # Transmit to card
        data = self.conn.transmit(encrypted_apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        sw = bytes([sw1, sw2])
        
        # Handle 9c30 - Secure Channel Required (corrupted channel)
        if sw == b"\x9c\x30" and retry:
            _debug("Secure channel corrupted (9c30), re-establishing...")
            # Re-establish secure channel
            self.sc.initiate(self.conn)
            # Retry command once with fresh encryption
            encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
            data = self.conn.transmit(encrypted_apdu)
            resp_data, sw1, sw2 = data[0], data[1], data[2]
            sw = bytes([sw1, sw2])
        
        # Check final status word
        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        
        # Decrypt and return response (if any data)
        if len(resp_data) > 0:
            return self.sc.decrypt_response(resp_data)
        return b''

    def get_card_status(self):
        """Get card status without secure channel (INS 0x3C). Byte 11 = needs_secure_channel flag."""
        apdu = bytes([self.CLA, 0x3C, 0x00, 0x00])
        data = self.conn.transmit(apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        return resp_data, sw1, sw2

    def get_seedkeeper_status(self):
        """
        Get card status including PIN attempts and secret count.
        APDU: B0 A7 00 00
        Response: [nb_secrets(2)][total_mem(2)][free_mem(2)][nb_logs_total(2)][nb_logs_avail(2)] SW
        """
        apdu = bytes([self.CLA, self.INS_GET_STATUS, 0x00, 0x00])
        _debug("TX (encrypted): GET_STATUS")

        resp = self.secure_request(apdu)

        if len(resp) >= 10:
            status = {
                'nb_secrets': (resp[0] << 8) | resp[1],
                'total_memory': (resp[2] << 8) | resp[3],
                'free_memory': (resp[4] << 8) | resp[5],
                'nb_logs_total': (resp[6] << 8) | resp[7],
                'nb_logs_avail': (resp[8] << 8) | resp[9],
            }
            _debug("Status: %s" % status)
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
        _debug("TX (encrypted): VERIFY_PIN")

        self.secure_request(inner_apdu)
        _debug("PIN verified successfully")
        return (True, None)

    def get_card_label(self):
        """Read card-level label via INS 0x3D, p2=0x01."""
        apdu = bytes([self.CLA, self.INS_CARD_LABEL, 0x00, 0x01, 0x00])
        _debug("TX (encrypted): CARD_LABEL GET")
        resp = self.secure_request(apdu)
        if len(resp) == 0:
            return ""
        label_len = resp[0]
        if label_len == 0:
            return ""
        if len(resp) < 1 + label_len:
            _debug("CARD_LABEL GET: malformed response")
            return ""
        try:
            label = bytes(resp[1:1 + label_len]).decode("utf-8")
        except Exception:
            label = hexlify(bytes(resp[1:1 + label_len])).decode()
        _debug("Card label: %s" % label)
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
        _debug("TX (encrypted): CARD_LABEL SET")
        self.secure_request(apdu)
        _debug("Card label updated")

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
            _debug("TX (encrypted): LIST_SECRETS " + ("(INIT)" if p2 == 0x01 else "(NEXT)"))

            try:
                resp = self.secure_request(apdu)
            except ISOException as e:
                # 9c12 = no more secrets (end of list)
                if str(e) == "9c12":
                    _debug("End of secret list (no more)")
                    break
                raise

            # Empty response = end of list
            if len(resp) == 0:
                _debug("End of secret list")
                break

            if len(resp) >= 15:
                header = self._parse_header(resp)
                _debug("Found secret: %s" % header)
                headers.append(header)

            p2 = 0x02  # NEXT for subsequent calls

        _debug("Total secrets found: %s" % len(headers))
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
        _debug("TX (encrypted): EXPORT INIT")

        resp = self.secure_request(apdu)
        _debug("EXPORT INIT response (header): %s" % ''.join('{:02x}'.format(b) for b in resp) if len(resp) > 0 else "empty")
        
        # Parse header to get label length (so we know where data starts in header)
        # Header format: id(2) | type(1) | origin(1) | export_rights(1) | export_nbplain(1) |
        #                export_nbsecure(1) | export_counter(1) | fingerprint(4) | subtype(1) |
        #                rfu(1) | label_len(1) | label(N)
        # Total header size = 13 + label_len
        if len(resp) < 13:
            _debug("ERROR: INIT response too short")
            return b''
        
        header_label_len = resp[12]  # label_len is at offset 12
        header_size = 13 + header_label_len
        _debug("Header size: %d (label_len: %d)" % (header_size, header_label_len))
        
        # Collect chunks from UPDATE calls
        chunks = []
        
        # UPDATE loop - this is where actual secret data comes from
        chunk_num = 1
        while True:
            apdu = bytes([self.CLA, self.INS_EXPORT_SECRET, 0x01, 0x02, 0x02]) + sid_bytes
            _debug("TX (encrypted): EXPORT UPDATE")

            resp = self.secure_request(apdu)

            if len(resp) < 2:
                _debug("UPDATE response too short, stopping")
                break
                
            # Response format: [chunk_size(2b) | chunk_data | sig_size(2b) | sig]
            chunk_size = (resp[0] << 8) | resp[1]
            _debug("Chunk %d len: %d" % (chunk_num, chunk_size))
            
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
                _debug("Final chunk detected (has signature, size: %d)" % sig_size)
                break
            
            chunk_num += 1

            # Safety limit
            if chunk_num > 50:
                _debug("WARNING: Too many chunks, aborting")
                break

        result = b''.join(chunks)
        _debug("Exported secret total length: %s" % len(result))
        return result

    def _parse_masterseed_to_mnemonic(self, secret_data: bytes) -> str:
        """
        Parse MASTERSEED secret data to BIP39 mnemonic.
        
        MASTERSEED format (type 0x10 with BIP39 subtype):
        Format: masterseed_size(1) | masterseed(N) | wordlist(1) | entropy_size(1) | entropy(M) | passphrase_size(1) | passphrase
        
        Args:
            secret_data: Raw secret data bytes
            
        Returns:
            Mnemonic string
        """
        _debug("Parsing MASTERSEED format...")
        
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
        
        _debug("MASTERSEED: masterseed_size=%s wordlist=%s entropy_size=%s" % (masterseed_size, wordlist, entropy_size))
        _debug("Entropy (hex): %s" % ''.join('{:02x}'.format(b) for b in entropy))
        
        return bip39.mnemonic_from_bytes(entropy)

    def get_bip39_secret(self, secret_id=None, secret_type=None):
        """
        Convenience method: find first BIP39 secret (type 0x30), export it,
        extract entropy bytes, and convert to mnemonic via embit.
        Returns: mnemonic string
        
        Args:
            secret_id: Optional secret ID to directly export. If provided, skips header search.
            secret_type: Optional secret type for parsing when secret_id is provided.
        """
        _debug("get_bip39_secret called with secret_id: %s secret_type: %s" % (secret_id, hex(secret_type) if secret_type else None))
        
        # If secret_id provided, use it directly instead of searching headers
        if secret_id is not None:
            # Get secret type from header if not provided
            if secret_type is None:
                headers = self.list_secret_headers()
                for h in headers:
                    if h['id'] == secret_id:
                        secret_type = h['type']
                        break
            
            _debug("Direct export with secret_id: %s type: %s" % (secret_id, hex(secret_type) if secret_type else None))
            
            # Export the secret directly
            secret_data = self.export_secret(secret_id)
            
            # Parse based on secret type
            if secret_type == self.SECRET_TYPE_MASTERSEED:
                return self._parse_masterseed_to_mnemonic(secret_data)
            else:
                # BIP39 secret format: entropy_len(2) || entropy || [passphrase_len(2) || passphrase]
                _debug("Parsing BIP39 format...")
                if len(secret_data) >= 2:
                    entropy_len = (secret_data[0] << 8) | secret_data[1]
                    entropy = secret_data[2:2 + entropy_len]
                    _debug("Entropy length: %s" % entropy_len)

                    # Convert to mnemonic
                    mnemonic = bip39.mnemonic_from_bytes(entropy)
                    _debug("Successfully converted to mnemonic")
                    return mnemonic

            raise AppletException("Invalid BIP39 secret format")
        
        # Default: search for first BIP39 or MASTERSEED secret
        _debug("Searching for BIP39 secrets...")
        headers = self.list_secret_headers()

        # Find first BIP39 or MASTERSEED secret (can both be converted to mnemonic)
        bip39_header = None
        for h in headers:
            if h['type'] == self.SECRET_TYPE_BIP39 or h['type'] == self.SECRET_TYPE_MASTERSEED:
                bip39_header = h
                break

        if bip39_header is None:
            _debug("No BIP39/MASTERSEED secrets found")
            raise AppletException("No BIP39 or MASTERSEED secrets found on card")

        _debug("Found secret, id: %s type: %s label: %s" % (bip39_header['id'], hex(bip39_header['type']), bip39_header['label']))

        # Export the secret
        secret_data = self.export_secret(bip39_header['id'])

        # Parse based on secret type
        if bip39_header['type'] == self.SECRET_TYPE_MASTERSEED:
            return self._parse_masterseed_to_mnemonic(secret_data)
        else:
            # BIP39 secret format: entropy_len(2) || entropy || [passphrase_len(2) || passphrase]
            _debug("Parsing BIP39 format...")
            if len(secret_data) >= 2:
                entropy_len = (secret_data[0] << 8) | secret_data[1]
                entropy = secret_data[2:2 + entropy_len]
                _debug("Entropy length: %s" % entropy_len)

                # Convert to mnemonic
                mnemonic = bip39.mnemonic_from_bytes(entropy)
                _debug("Successfully converted to mnemonic")
                return mnemonic

        raise AppletException("Invalid BIP39 secret format")

    def get_descriptor_secrets(self):
        """Find and export all wallet descriptor secrets (type 0xC1).
        
        Wallet descriptors are Bitcoin output descriptors that describe
        multisig wallet configurations. They are stored as text strings.
        
        Returns: list of dicts with 'id', 'label', 'descriptor' keys
        """
        _debug("Searching for descriptor secrets...")
        headers = self.list_secret_headers()
        
        descriptors = []
        for h in headers:
            if h['type'] == self.SECRET_TYPE_DESCRIPTOR:
                _debug("Found descriptor secret id: %s label: %s" % (h['id'], h['label']))
                try:
                    secret_data = self.export_secret(h['id'])
                    # Descriptor format: [size(2)][descriptor_string]
                    if len(secret_data) >= 2:
                        desc_len = (secret_data[0] << 8) | secret_data[1]
                        descriptor_str = secret_data[2:2 + desc_len].decode('utf-8', errors='replace')
                        descriptors.append({
                            'id': h['id'],
                            'label': h['label'],
                            'descriptor': descriptor_str
                        })
                        _debug("Descriptor: %s" % descriptor_str[:50] + "..." if len(descriptor_str) > 50 else descriptor_str)
                except Exception as e:
                    _debug("Failed to export descriptor %s: %s" % (h['id'], e))
        
        _debug("Found %d descriptor secrets" % len(descriptors))
        return descriptors
