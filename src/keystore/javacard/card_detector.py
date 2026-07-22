"""
CardDetector - Detects JavaCard applet type by AID selection.

This module provides positive card type detection by trying to SELECT
each known applet AID. This ensures we correctly identify which
type of card is inserted before attempting to use it.

Usage:
    from keystore.javacard.card_detector import CardDetector
    
    detector = CardDetector(connection)
    card_type = detector.detect_card_type()
    
    if card_type == 'seedkeeper':
        keystore = SeedKeeper()
    elif card_type == 'satochip':
        keystore = Satochip()
    elif card_type == 'memorycard':
        keystore = MemoryCard()
    elif card_type == 'unknown':
        # Show error - unknown card
        pass
    else:
        # No card inserted
        pass
"""
from binascii import hexlify


class CardDetector:
    """Detects JavaCard applet type by trying to SELECT each known AID."""
    
    # Known AIDs (Application Identifiers)
    # MemoryCard: B0 0B 51 11 CB 01 (6 bytes)
    AID_MEMORYCARD = bytes([0xB0, 0x0B, 0x51, 0x11, 0xCB, 0x01])
    
    # SeedKeeper: ASCII "SeedKeeper" (10 bytes)
    AID_SEEDKEEPER = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
    
    # Satochip: ASCII "SatoChip" (8 bytes)
    AID_SATOCHIP = bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70])
    
    # Detection order - try in this sequence
    # MemoryCard first for backward compatibility
    DETECTION_ORDER = [
        ('memorycard', AID_MEMORYCARD),
        ('seedkeeper', AID_SEEDKEEPER),
        ('satochip', AID_SATOCHIP),
    ]
    
    def __init__(self, connection):
        """Initialize detector with card connection.
        
        Args:
            connection: Card connection object with transmit() method
        """
        self.connection = connection
        self._last_detected = None
    
    def _make_select_apdu(self, aid: bytes) -> bytes:
        """Create a SELECT APDU for the given AID.
        
        Args:
            aid: Application Identifier bytes
            
        Returns:
            Complete APDU bytes
        """
        cla = 0x00
        ins = 0xA4  # SELECT instruction
        p1 = 0x04  # Select by AID
        p2 = 0x00  # Return FCI template
        lc = len(aid)
        return bytes([cla, ins, p1, p2, lc]) + aid
    
    def _try_select_aid(self, aid: bytes) -> bool:
        """Try to SELECT an applet by AID.
        
        Args:
            aid: Application Identifier to select
            
        Returns:
            True if SELECT succeeded (SW 9000), False otherwise
        """
        try:
            apdu = self._make_select_apdu(aid)
            data, sw1, sw2 = self.connection.transmit(apdu)
            sw = (sw1 << 8) | sw2
            # 0x9000 = success
            return sw == 0x9000
        except Exception as e:
            print('[CardDetector] SELECT failed for AID ' + str(hexlify(aid).decode()) + ': ' + str(e))
            return False
    
    def detect_card_type(self, disconnect_after=True) -> str:
        """Detect the type of card inserted.
        
        Tries to SELECT each known AID in order.
        Returns the type of the first AID that responds successfully.
        
        Args:
            disconnect_after: If True, disconnect after detection
                              (default True to allow proper connection later)
            
        Returns:
            str: 'memorycard', 'seedkeeper', 'satochip', 'unknown', or None
                  - 'memorycard'/'seedkeeper'/'satochip': Known card detected
                  - 'unknown': Card inserted but no known AID found
                  - None: No card inserted
        """
        # Check if card is inserted
        if not self.connection.isCardInserted():
            return None
        
        # Try to connect
        try:
            self.connection.connect(self.connection.T1_protocol)
        except Exception as e:
            print('[CardDetector] Failed to connect: ' + str(e))
            return None
        
        detected_type = 'unknown'
        
        try:
            # Try each AID in order
            for card_type, aid in self.DETECTION_ORDER:
                if self._try_select_aid(aid):
                    detected_type = card_type
                    print('[CardDetector] Detected card type: ' + str(card_type))
                    break
            
            if detected_type == 'unknown':
                print('[CardDetector] Unknown card - no known AID responded')
        
        finally:
            # Always disconnect to allow proper connection by keystore
            if disconnect_after:
                try:
                    self.connection.disconnect()
                except:
                    pass
        
        self._last_detected = detected_type
        return detected_type
    
    def get_aid_for_type(self, card_type: str) -> bytes:
        """Get the AID for a card type.
        
        Args:
            card_type: 'memorycard', 'seedkeeper', or 'satochip'
            
        Returns:
            AID bytes or None if unknown type
        """
        aids = {
            'memorycard': self.AID_MEMORYCARD,
            'seedkeeper': self.AID_SEEDKEEPER,
            'satochip': self.AID_SATOCHIP,
        }
        return aids.get(card_type)
    
    @classmethod
    def get_all_aids(cls) -> dict:
        """Get all known AIDs.
        
        Returns:
            dict: Mapping of card type to AID bytes
        """
        return {
            'memorycard': cls.AID_MEMORYCARD,
            'seedkeeper': cls.AID_SEEDKEEPER,
            'satochip': cls.AID_SATOCHIP,
        }
