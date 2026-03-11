"""
SecureAppletBase - Base class for applets using SeedKeeperSecureChannel.

This class provides secure channel functionality for JavaCard applets
that use the SeedKeeper/Satochip secure channel protocol (ECDH + AES-CBC + HMAC-SHA1).

Both SeedKeeperApplet and SatochipApplet inherit from this class,
eliminating duplicated secure_request() and init_secure_channel() implementations.
"""
from .applet import Applet, ISOException, AppletException
from .seedkeeper_securechannel import SeedKeeperSecureChannel
from binascii import hexlify


class SecureAppletBase(Applet):
    """
    Base class for applets using SeedKeeperSecureChannel.
    
    This class provides:
    - Secure channel initialization
    - Secure request/response handling with automatic retry on 9c30
    - Shared infrastructure for SeedKeeper and Satochip applets
    
    Subclasses must:
    - Set AID class attribute
    - Set NAME class attribute
    - Implement applet-specific methods
    """
    
    # Subclasses should override these
    AID = None
    NAME = "SecureAppletBase"
    
    def __init__(self, connection, aid=None):
        """
        Initialize secure applet with connection and AID.
        
        Args:
            connection: Card connection object with transmit() method
            aid: Applet AID (uses class AID if None)
        """
        if aid is None:
            aid = self.AID
        super().__init__(connection, aid)
        # Secure channel instance
        self.sc = SeedKeeperSecureChannel()
    
    def init_secure_channel(self):
        """
        Initialize secure channel with the card.
        
        Must be called after select() and before any secure commands.
        
        Note: SELECT MUST be called BEFORE init_secure_channel().
        NEVER re-select after secure channel initialization.
        """
        print(f"[{self.NAME}] Establishing secure channel...")
        self.sc.initiate(self.conn)
        print(f"[{self.NAME}] Secure channel established")
    
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
        
        Note:
            The secure channel uses INS 0x82 for all encrypted commands.
            The 9c30 error indicates the secure channel state is corrupted
            (e.g., due to card reset or IV mismatch), requiring re-initialization.
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
            print(f"[{self.NAME}] Secure channel corrupted (9c30), re-establishing...")
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
    
    def is_secure_channel_open(self) -> bool:
        """
        Check if secure channel is initialized and ready.
        
        Returns:
            True if secure channel can be used for commands
        """
        return self.sc.is_initialized
    
    def close_secure_channel(self):
        """
        Close the secure channel.
        
        Should be called when done with the card to reset state.
        """
        self.sc.is_initialized = False
        self.sc.aes_key = None
        self.sc.mac_key = None
        self.sc.iv_counter = 1
