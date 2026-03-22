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


APPLET_AIDS = {
    "seedkeeper": {
        "name": "SeedKeeper",
        "package_aid": _hex("536565644b6565706572"),  # "SeedKeeper"
        "applet_aid": _hex("536565644b656570657200"),  # "SeedKeeper\0"
        "dgp_file": "/flash/gp/SeedKeeper.dgp",
        "sha256": "e447e45f37cafeb751fff1fdd71002c4e5cf0e837a9586ed6cea51369c841128",
        "size": 18641,
    },
    "teapot": {
        "name": "TeapotApplet",
        "package_aid": _hex("B00B5111CA"),
        "applet_aid": _hex("B00B5111CA01"),
        "dgp_file": "/flash/gp/TeapotApplet.dgp",
        "sha256": "ef5dda7b70d3bfc563d3cd19c7543eda8978bd11545592d324ab3cc1b18b143d",
        "size": 7644,
    },
    "satochip": {
        "name": "SatoChip",
        "package_aid": _hex("5361746f4368697000"),
        "applet_aid": _hex("5361746f4368697000"),
        # SatoChip is pre-installed, no DGP file
    },
    "memorycard": {
        "name": "MemoryCard",
        "package_aid": _hex("B00B5111CB"),
        "applet_aid": _hex("B00B5111CB01"),
        # MemoryCard DGP is large (63KB), typically frozen in firmware
    },
}


def match_profile(atr):
    """Match a card ATR against known profiles. Returns profile dict or None."""
    for p in PROFILES:
        if atr[:len(p["atr_prefix"])] == p["atr_prefix"]:
            return p
    return None


def get_applet_aid(name):
    """Get applet info by name. Returns dict or None."""
    return APPLET_AIDS.get(name)
