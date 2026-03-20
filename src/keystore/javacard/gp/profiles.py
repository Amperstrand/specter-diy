"""GlobalPlatform card profiles.

Each profile defines how to communicate with a specific JavaCard type.
Version 1 supports JCOP4 with GP default keys and SCP03.
"""

from binascii import hexlify

GP_DEFAULT_KEY = bytes.fromhex("404142434445464748494A4B4C4D4E4F")

JCOP4_PROFILE = {
    "name": "JCOP4",
    "atr_prefix": bytes.fromhex("3BD518FF8191FE1FC38073C821100A"),
    "isd_aid": bytes.fromhex("A000000151000000"),
    "scp": "scp03",
    "key_version": 0,
    "key_index": 0,
    "enc_key": GP_DEFAULT_KEY,
    "mac_key": GP_DEFAULT_KEY,
    "rmac_key": GP_DEFAULT_KEY,
    "dek_key": GP_DEFAULT_KEY,
    "privileges": bytes.fromhex("C900"),
}

PROFILES = [JCOP4_PROFILE]


def match_profile(atr):
    """Match a card ATR against known profiles. Returns profile dict or None."""
    for p in PROFILES:
        if atr[:len(p["atr_prefix"])] == p["atr_prefix"]:
            return p
    return None
