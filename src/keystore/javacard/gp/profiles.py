"""GlobalPlatform card profiles.

Each profile defines how to communicate with a specific JavaCard type.
Version 1 supports JCOP4 with GP default keys and SCP03.
"""

from binascii import hexlify, unhexlify


def _hex(s):
    return unhexlify(s.encode())


GP_DEFAULT_KEY = _hex("404142434445464748494A4B4C4D4E4F")

JCOP4_PROFILE = {
    "name": "JCOP4",
    "atr_prefix": _hex("3BD518FF8191FE1FC38073C821100A"),
    "isd_aid": _hex("A000000151000000"),
    "scp": "scp02",
    "key_version": 0,
    "key_index": 0,
    "enc_key": GP_DEFAULT_KEY,
    "mac_key": GP_DEFAULT_KEY,
    "rmac_key": GP_DEFAULT_KEY,
    "dek_key": GP_DEFAULT_KEY,
    "privileges": _hex("C900"),
}

PROFILES = [JCOP4_PROFILE]


def match_profile(atr):
    """Match a card ATR against known profiles. Returns profile dict or None."""
    for p in PROFILES:
        if atr[:len(p["atr_prefix"])] == p["atr_prefix"]:
            return p
    return None
