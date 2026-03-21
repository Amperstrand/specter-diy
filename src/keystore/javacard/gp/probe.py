"""GP Probe: non-destructive card detection.

Determines whether an inserted card is:
- A known applet (MemoryCard, SeedKeeper)
- A GP-provisionable card (supports SCP03, MemoryCard not installed)
- An unknown card
"""

from binascii import unhexlify
from .scp02 import SCP02Error, open_session, _select_isd
from .registry import find_aid
from .profiles import match_profile, JCOP4_PROFILE


MEMORYCARD_APPLET_AID = unhexlify("B00B5111CB01")
MEMORYCARD_PACKAGE_AID = unhexlify("B00B5111CB")


def probe_card(connection):
    """Non-destructively probe a smartcard.

    Steps:
    1. Check card presence
    2. Try SELECT for known applets (MemoryCard, SeedKeeper)
    3. If no known applet, try GP probe (SELECT ISD + INITIALIZE UPDATE)
    4. If GP works, check if MemoryCard is already installed

    Returns dict:
      kind: "memorycard" | "seedkeeper" | "gp_installable" | "gp_supported" | "unknown" | "no_card"
      atr: bytes (if card present)
      profile: dict (if GP supported)
      memorycard_installed: bool (if GP supported)
    """
    result = {
        "kind": "no_card",
        "atr": b"",
        "profile": None,
        "memorycard_installed": False,
    }

    try:
        if not connection.isCardInserted():
            return result
    except Exception:
        return result

    try:
        connection.connect(connection.T1_protocol)
    except Exception:
        return result

    atr = connection.getATR()
    result["atr"] = atr

    try:
        _check_known_applets(connection, result)
    except Exception:
        pass

    if result["kind"] != "unknown":
        try:
            connection.disconnect()
        except Exception:
            pass
        return result

    profile = match_profile(atr)
    if profile is None:
        try:
            connection.disconnect()
        except Exception:
            pass
        return result

    result["profile"] = profile

    try:
        session = open_session(connection, profile)
        result["kind"] = "gp_supported"

        mc_entry = find_aid(session, MEMORYCARD_APPLET_AID)
        if mc_entry is not None:
            result["memorycard_installed"] = True
            result["kind"] = "memorycard_gp"
        else:
            pkg_entry = find_aid(session, MEMORYCARD_PACKAGE_AID)
            if pkg_entry is not None:
                result["memorycard_installed"] = True
                result["kind"] = "gp_supported"
            else:
                result["kind"] = "gp_installable"
    except SCP02Error:
        result["kind"] = "unknown"
    except Exception:
        result["kind"] = "unknown"

    try:
        connection.disconnect()
    except Exception:
        pass

    return result


def _check_known_applets(connection, result):
    """Try to SELECT known applet AIDs."""
    from ..applets.applet import Applet

    known = [
        ("MemoryCard", unhexlify("B00B5111CB01"), "memorycard"),
        ("SeedKeeper", bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72]), "seedkeeper"),
    ]

    for name, aid, kind in known:
        try:
            applet = Applet(connection, aid)
            applet.select()
            result["kind"] = kind
            return
        except Exception:
            continue

    result["kind"] = "unknown"
