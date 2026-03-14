"""Utility to scan a smartcard for known applets.

This module provides card scanning functionality for the debug/info screen
displayed during keystore detection. It probes the smartcard for known
JavaCard applets (SeedKeeper, MemoryCard) and reports their presence.

Spec reference:
    - .sisyphus/plans/seedkeeper-support.md: Debug screen shows card presence
      and detected applets during select_keystore() polling loop.

See also:
    - src/keystore/javacard/applets/seedkeeper_applet.py (SeedKeeper AID)
    - src/keystore/javacard/applets/memorycard.py (MemoryCard AID)
"""
from .applets.applet import Applet
from binascii import hexlify

# Known applet AIDs and their display names.
# These match the AID constants defined in the respective applet modules.
# - SeedKeeper AID: ASCII "SeedKeeper" = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
# - MemoryCard AID: b"\xB0\x0B\x51\x11\xCB\x01"
KNOWN_APPLETS = [
    ("SeedKeeper", bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])),
    ("MemoryCard", b"\xB0\x0B\x51\x11\xCB\x01"),
]


def scan_card_applets(connection) -> dict:
    """
    Scan a smartcard for known applets.
    
    Probes the inserted smartcard for known JavaCard applets by attempting
    to SELECT each applet AID. Used by the debug info screen to display
    card status during keystore detection.
    
    Args:
        connection: Smartcard connection object with interface:
            - isCardInserted() -> bool
            - connect(protocol) -> None
            - disconnect() -> None  
            - transmit(apdu) -> (data, sw1, sw2)
    
    Returns:
        dict with keys:
            - card_present (bool): True if card is inserted
            - applets (list[str]): Names of detected applets
            - status (str): Human-readable status message
    
    Note:
        This function handles all card communication errors internally
        and never raises exceptions to the caller.
    """
    result = {
        "card_present": False,
        "applets": [],
        "status": ""
    }
    
    # Check if card is inserted
    # Note: Broad exception handling is intentional here - we want to
    # gracefully handle any card/reader issue and report status, not crash
    try:
        if not connection.isCardInserted():
            return result
    except Exception:
        # Card reader communication failed
        return result
    
    result["card_present"] = True
    detected = []
    
    # Try to connect and scan applets
    try:
        connection.connect(connection.T1_protocol)
    except Exception as e:
        result["status"] = "Connect failed: " + str(e)
        return result
    
    # Scan for each known applet by attempting SELECT
    for name, aid in KNOWN_APPLETS:
        try:
            applet = Applet(connection, aid)
            applet.select()
            detected.append(name)
        except Exception:
            # Applet not present or selection failed - this is expected
            # for most applets, so we silently continue
            pass
    
    # Disconnect after scanning
    try:
        connection.disconnect()
    except Exception:
        pass
    
    result["applets"] = detected
    
    # Build status text
    if detected:
        result["status"] = "%d applet(s) detected" % len(detected)
    else:
        result["status"] = "No known applets"
    
    return result
