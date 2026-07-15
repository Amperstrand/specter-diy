"""Utility to scan a smartcard for known applets.

Probes the card for known JavaCard applets by attempting SELECT on each AID.
Used by the debug info screen during multi-keystore detection polling.
"""
from .applets.applet import Applet


KNOWN_APPLETS = [
    ("SatoChip", bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70, 0x00])),
    ("SeedKeeper", bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72, 0x00])),
    ("MemoryCard", b"\xB0\x0B\x51\x11\xCB\x01"),
]


def scan_card_applets(connection) -> dict:
    """Scan a smartcard for known applets.

    Returns dict with card_present (bool), applets (list[str]), status (str).
    Never raises exceptions to the caller.
    """
    result = {
        "card_present": False,
        "applets": [],
        "status": ""
    }
    try:
        if not connection.isCardInserted():
            return result
    except Exception:
        return result

    result["card_present"] = True
    try:
        conn.disconnect()
    except Exception:
        pass
    try:
        conn.connect(conn.T1_protocol)
    except Exception as e:
        result["status"] = "Connect failed: " + str(e)
        return result

    detected = []
    for name, aid in KNOWN_APPLETS:
        try:
            applet = Applet(connection, aid)
            applet.select()
            detected.append(name)
        except Exception:
            pass

    try:
        connection.disconnect()
    except Exception:
        pass

    result["applets"] = detected
    result["status"] = "%d applet(s) detected" % len(detected) if detected else "No known applets"
    return result
