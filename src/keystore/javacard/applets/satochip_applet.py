"""
Satochip applet for Satochip hardware wallet communication.
Inherits from Applet and uses SeedKeeperSecureChannel for secure communication.
"""
from .applet import Applet, ISOException, AppletException
from binascii import hexlify
from .seedkeeper_securechannel import SeedKeeperSecureChannel


class SatochipApplet(Applet):
    """Applet for communicating with Satochip cards."""

    # Satochip AID (Application Identifier) - ASCII "SatoChip"
    AID = bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70])
    NAME = "Satochip"

    # CLA byte for Satochip commands
    CLA = 0xB0

    # Instruction bytes
    INS_VERIFY_PIN = 0x42
    INS_GET_STATUS = 0x3C
    INS_BIP32_GET_AUTHENTIKEY = 0x73

    def __init__(self, connection):
        """Initialize with card connection."""
        super().__init__(connection, self.AID)
        self.sc = SeedKeeperSecureChannel()
        print("[Satochip] Applet initialized")

    def init_secure_channel(self):
        """Initialize secure channel. WARNING: select() MUST precede this."""
        print("[Satochip] Establishing secure channel...")
        self.sc.initiate(self.conn)
        print("[Satochip] Secure channel established")
    def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
        """Send APDU via secure channel (INS 0x82).
        If retry=True and card returns 9c30 (Secure Channel Required),
        re-establish secure channel and retry once.
        """
        if not self.sc.is_initialized:
            raise AppletException("Secure channel not initialized")

        encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
        data = self.conn.transmit(encrypted_apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        sw = bytes([sw1, sw2])

        # Handle 9c30 - Secure Channel Required (corrupted channel)
        if sw == b"\x9c\x30" and retry:
            print("[Satochip] Secure channel corrupted (9c30), re-establishing...")
            # Re-establish secure channel
            self.sc.initiate(self.conn)
            # Retry command once with fresh encryption
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
        apdu = bytes([self.CLA, self.INS_GET_STATUS, 0x00, 0x00])
        data = self.conn.transmit(apdu)
        resp_data, sw1, sw2 = data[0], data[1], data[2]
        print("[Satochip] GET_STATUS response:", len(resp_data), "bytes")
        return resp_data, sw1, sw2
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
        print("[Satochip] Parsed status:", status)
        return status
    def verify_pin(self, pin):
        """Verify PIN to unlock the card."""
        if isinstance(pin, str):
            pin = pin.encode()

        inner_apdu = bytes([self.CLA, self.INS_VERIFY_PIN, 0x00, 0x00, len(pin)]) + pin
        print("[Satochip] TX (encrypted): VERIFY_PIN")

        self.secure_request(inner_apdu)
        print("[Satochip] PIN verified successfully")
        return (True, None)
    def get_authentikey(self):
        """Get authentikey for fingerprint derivation (INS 0x73)."""
        apdu = bytes([self.CLA, self.INS_BIP32_GET_AUTHENTIKEY, 0x00, 0x00])
        print("[Satochip] TX (encrypted): GET_AUTHENTIKEY")

        resp = self.secure_request(apdu)
        print("[Satochip] Authentikey received:", len(resp), "bytes")
        return resp  # Returns raw pubkey bytes (65 bytes uncompressed)
