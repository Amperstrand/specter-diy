"""
Satochip applet for Satochip hardware wallet communication.
Inherits from SecureAppletBase for secure channel functionality.
"""
from .secure_applet_base import SecureAppletBase
from .satochip_securechannel import SatochipSecureChannel
from .applet import ISOException, AppletException
from binascii import hexlify


class SatochipApplet(SecureAppletBase):
    """Applet for communicating with Satochip cards.
    
    Inherits secure channel functionality from SecureAppletBase.
    """

    # Satochip AID (Application Identifier) - ASCII "SatoChip"
    AID = b"SatoChip\x00"  # instance AID 5361746F4368697000 (NOT the package AID)
    NAME = "Satochip"

    # CLA byte for Satochip commands
    CLA = 0xB0

    # Instruction bytes
    INS_VERIFY_PIN = 0x42
    INS_GET_STATUS = 0x3C
    INS_BIP32_GET_AUTHENTIKEY = 0x73
    INS_BIP32_GET_EXTENDED_KEY = 0x6D
    INS_SIGN_TRANSACTION_HASH = 0x7A  # Direct hash signing; 0x6F/0x6E are removed in applet v0.16 (SW_INS_DEPRECATED 0x9C26)
    INS_FACTORY_RESET = 0xFD  # applet v0.16+: single APDU, P1=0xAA P2=0x55, secure channel, no PIN

    def __init__(self, connection):
        super().__init__(connection, self.AID)
        self._sato_sc = SatochipSecureChannel()

    def init_secure_channel(self):
        if not self._sato_sc.is_initialized:
            self._sato_sc.initiate(self.conn, cla=self.CLA)

    def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
        self.init_secure_channel()
        wrapped = self._sato_sc.encrypt_apdu(inner_apdu, cla=self.CLA)
        data = bytes(self.conn.transmit(wrapped))
        resp, sw = data[:-2], data[-2:]
        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        if len(resp) == 0:
            return b""  # v0.14 setup acknowledges with a bare 9000
        return self._sato_sc.decrypt_response(resp)

    def factory_reset(self):
        """Reset card to factory defaults. v0.16+ only (INS 0xFD absent in v0.14;
        a single APDU P1=0xAA P2=0x55 over the secure channel, no PIN)."""
        st = self.parse_status(self.get_card_status())
        if (st["protocol_major_version"], st["protocol_minor_version"]) < (0x00, 0x10):
            raise AppletException(
                "factory_reset requires applet protocol >= 0.10 (v0.16); card runs 0.%02x"
                % st["protocol_minor_version"]
            )
        self.secure_request(bytes([self.CLA, self.INS_FACTORY_RESET, 0xAA, 0x55]))

    def get_card_status(self):
        """Get card status without secure channel (INS 0x3C)."""
        apdu = bytes([self.CLA, self.INS_GET_STATUS, 0x00, 0x00])
        data = bytes(self.conn.transmit(apdu))
        resp_data, sw = data[:-2], data[-2:]
        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        return resp_data

    def parse_status(self, resp_data):
        """Parse GET_STATUS response into dict."""
        if len(resp_data) < 8:
            return {}
        status = {
            'protocol_major_version': resp_data[0],
            'protocol_minor_version': resp_data[1],
            'applet_major_version': resp_data[2],
            'applet_minor_version': resp_data[3],
            'PIN0_remaining_tries': resp_data[4],
            'PUK0_remaining_tries': resp_data[5],
            'PIN1_remaining_tries': resp_data[6],
            'PUK1_remaining_tries': resp_data[7],
        }
        if len(resp_data) >= 10:
            status['is_seeded'] = resp_data[9] != 0x00
        if len(resp_data) >= 11:
            status['setup_done'] = resp_data[10] != 0x00
        if len(resp_data) >= 12:
            status['needs_secure_channel'] = resp_data[11] != 0x00
        return status

    def verify_pin(self, pin):
        """Verify PIN to unlock the card."""
        if isinstance(pin, str):
            pin = pin.encode()

        inner_apdu = bytes([self.CLA, self.INS_VERIFY_PIN, 0x00, 0x00, len(pin)]) + pin

        self.secure_request(inner_apdu)
        return (True, None)

    def get_authentikey(self):
        """Get authentikey for fingerprint derivation (INS 0x73)."""
        apdu = bytes([self.CLA, self.INS_BIP32_GET_AUTHENTIKEY, 0x00, 0x00])

        resp = self.secure_request(apdu)
        return resp  # Returns raw pubkey bytes (65 bytes uncompressed)

    def get_extended_key(self, path):
        """Get extended key (pubkey + chaincode) at derivation path (INS 0x6D).
        
        Args:
            path: Derivation path as bytes (4 bytes per level, big-endian)
                  e.g., m/44h/0h/0h = b'\x80\x00\x00\x2c\x80\x00\x00\x00\x80\x00\x00\x00'
        
        Returns:
            tuple: (pubkey_bytes, chaincode_bytes)
                   pubkey is 33 bytes compressed
                   chaincode is 32 bytes
        
        Response format from card:
            chaincode(32) | coordx_size(2) | coordx(32) | sign_size(2) | self-sign | auth_sign_size(2) | auth-sign
        """
        # Use shared utility function
        from ..util import path_to_bytes
        
        if isinstance(path, str):
            path = path_to_bytes(path)
        
        # P1 = path depth (number of derivation levels)
        depth = len(path) // 4
        # P2 = option flag: 0x40 = optimization for non-hardened child derivation
        p2 = 0x40
        
        apdu = bytes([self.CLA, self.INS_BIP32_GET_EXTENDED_KEY, depth, p2, len(path)]) + path
        
        resp = self.secure_request(apdu)
        
        # Parse response: chaincode(32) | coordx_size(2) | coordx | ...
        if len(resp) < 66:
            raise AppletException("Invalid extended key response: %d bytes" % len(resp))
        
        chaincode = resp[0:32]
        coordx_size = int.from_bytes(resp[32:34], 'big')
        
        if coordx_size != 32:
            raise AppletException(
                "unexpected coordx_size %d (secp256k1 expects 32)" % coordx_size
            )
        coordx = resp[34:34+coordx_size]
        
        # Construct compressed pubkey: 0x02 or 0x03 prefix + coordx
        # We default to 0x02 (even y) - if signature verification fails, try 0x03
        # For now, use 0x02 as default
        pubkey = b'\x02' + coordx
        
        return (pubkey, chaincode)
    
    def _path_to_bytes(self, path_str):
        """Convert derivation path string to bytes - DEPRECATED, uses util.path_to_bytes."""
        from ..util import path_to_bytes
        return path_to_bytes(path_str)
    
    def sign_transaction_hash(self, keynbr, tx_hash):
        """Sign a transaction hash directly (INS 0x7A).
        
        This is simpler than INS 0x6F which requires full transaction parsing.
        
        Args:
            keynbr: Key number (0xFF for BIP32 derived key from current path)
            tx_hash: 32-byte transaction hash to sign
        
        Returns:
            bytes: DER-encoded signature (typically 70-72 bytes)
        """
        if len(tx_hash) != 32:
            raise AppletException("Invalid tx_hash length: %d, expected 32" % len(tx_hash))
        
        # APDU: CLA INS P1 P2 Lc [tx_hash]
        # P1 = keynbr (0xFF for BIP32)
        # P2 = 0x00
        # No 2FA (chalresponse=None) for basic signing
        apdu = bytes([self.CLA, self.INS_SIGN_TRANSACTION_HASH, keynbr, 0x00, len(tx_hash)]) + tx_hash
        
        resp = self.secure_request(apdu)
        
        # Response is DER-encoded signature
        return resp
    
    def get_xpub(self, path_str, xtype='p2wpkh', is_mainnet=True):
        """Get full xpub at derivation path.
        
        This method constructs the full xpub including depth, fingerprint, 
        child_number, chaincode, and pubkey - matching the format expected
        by specter-diy wallet code.
        
        Args:
            path_str: Derivation path like "m/44h/0h/0h"
            xtype: Extended key type ('standard', 'p2wpkh-p2sh', 'p2wpkh', etc.)
            is_mainnet: True for mainnet, False for testnet
        
        Returns:
            HDKey: Extended public key object
        """
        from embit import bip32
        
        # Convert path to bytes using utility function
        from ..util import path_to_bytes, derive_fingerprint
        path_bytes = path_to_bytes(path_str)
        depth = len(path_bytes) // 4
        
        # Get extended key from card
        pubkey, chaincode = self.get_extended_key(path_bytes)
        
        if depth == 0:
            # Master key - fingerprint is 0x00000000, child_number is 0x00000000
            parent_fingerprint = b'\x00\x00\x00\x00'
            child_number = b'\x00\x00\x00\x00'
        else:
            # Get parent key for fingerprint
            parent_path = path_bytes[:-4]  # Remove last 4 bytes
            parent_pubkey, _ = self.get_extended_key(parent_path)
            # Use shared utility for fingerprint derivation
            parent_fingerprint = derive_fingerprint(parent_pubkey)
            # Child number = last 4 bytes of path
            child_number = path_bytes[-4:]
        
        # Build xpub - we need to construct the full 78-byte extended key
        # Format: version(4) | depth(1) | fingerprint(4) | child_number(4) | chaincode(32) | pubkey(33)
        
        # Version bytes based on xtype and network
        XPUB_VERSIONS = {
            'standard': (b'\x04\x88\xb2\x1e', b'\x04\x35\x87\xcf'),      # xpub, tpub
            'p2wpkh-p2sh': (b'\x04\x9d\x7c\xb2', b'\x04\x4a\x52\x66'),  # ypub, upub
            'p2wpkh': (b'\x04\xb2\x47\x46', b'\x04\x5f\x1c\xf6'),        # zpub, vpub
            'p2wsh-p2sh': (b'\x02\x95\xb4\x3f', b'\x02\x42\x89\xef'),    # Ypub, Upub
            'p2wsh': (b'\x02\xaa\x7e\xd3', b'\x02\x57\x54\x83'),        # Zpub, Vpub
        }
        
        version = XPUB_VERSIONS.get(xtype, XPUB_VERSIONS['p2wpkh'])
        version = version[0] if is_mainnet else version[1]
        
        # Construct extended key data
        xpub_data = version + bytes([depth]) + parent_fingerprint + child_number + chaincode + pubkey
        
        # Parse as HDKey using read_from with BytesIO
        from io import BytesIO
        stream = BytesIO(xpub_data)
        xpub = bip32.HDKey.read_from(stream)
        
        return xpub
