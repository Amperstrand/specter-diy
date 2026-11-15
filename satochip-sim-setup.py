"""Personalize a Satochip applet build served by the version farm.

Drives SETUP (INS 0x2A), VERIFY_PIN (0x42) and BIP32 IMPORT_SEED (0x6C)
against any pcscd reader (default: the vpcd sim readers; CARDMAN_BATTERY_READER
selects). Wire formats decoded from Toporin SatochipApplet v0.14-0.2
CardEdge.java (setup(), importBIP32Seed()); all three commands ride the
secure channel (only GET_STATUS/0x81/0x82 are plaintext-accepted).

The seed is a FIXED zero-value test vector — this tool is for SIMULATOR
cards (jcardsim via vicc.py) and freshly-flashed test cards, never for
cards holding real value.
"""
import hashlib
import os
import sys

import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "cardman_battery_shims", os.path.join(_HERE, "cardman-battery.py"))
cmb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmb)  # installs the host shims + sys.modules patches

from keystore.javacard.applets.satochip_applet import SatochipApplet  # noqa: E402

CLA = 0xB0
INS_SETUP = 0x2A
INS_VERIFY_PIN = 0x42
INS_IMPORT_SEED = 0x6C

DEFAULT_PIN = b"1234"
DEFAULT_PUK = b"12345678"
# zero-value test seed: BIP32 master material for sim/test cards only
TEST_SEED = hashlib.sha256(b"amperstrand version-farm test seed v1").digest()


def _pin_slot(pin, puk, tries=3):
    return (bytes([tries, tries, len(pin)]) + pin
            + bytes([len(puk)]) + puk)


def setup_data(pin=DEFAULT_PIN, puk=DEFAULT_PUK, secmem_size=0x0100):
    """[len|current-default-pin|slot0|slot1|secmem(2)|RFU(2)|RFU(1)x3]"""
    d = bytes([8]) + b"Muscle00"          # install-time PIN, checked first
    d += _pin_slot(pin, puk)              # PIN/PUK slot 0
    d += _pin_slot(pin, puk)              # PIN/PUK slot 1
    d += secmem_size.to_bytes(2, "big")   # bip32 secure-memory size
    d += b"\x00\x00"                      # mem_size (RFU)
    d += b"\x00\x00\x00"                  # create_*_ACL (RFU)
    return d


def main():
    reader = os.environ.get("CARDMAN_BATTERY_READER", "jCardSim VPCD 00 01")
    pin = os.environ.get("SIM_SETUP_PIN", DEFAULT_PIN.decode()).encode()
    seed = bytes.fromhex(os.environ.get("SIM_SETUP_SEED", TEST_SEED.hex()))
    print("target reader:", reader)

    conn = cmb.PyscardConnection(reader)
    applet = SatochipApplet(conn)
    applet.select()
    print("applet selected")

    st, sw1, sw2 = applet.get_card_status()
    if (sw1, sw2) == (0x90, 0x00):
        print("pre-setup status:", applet.parse_status(bytes(st)))
    else:
        print("GET_STATUS SW=%02x%02x" % (sw1, sw2))

    applet.init_secure_channel()
    print("secure channel up")

    inner = bytes([CLA, INS_SETUP, 0x00, 0x00, len(setup_data(pin))]) \
        + setup_data(pin)
    resp = applet.secure_request(inner)
    print("SETUP ok (%d-byte response)" % len(resp))

    applet.verify_pin(pin.decode())
    print("PIN verified")

    inner = bytes([CLA, INS_IMPORT_SEED, len(seed), 0x00, len(seed)]) + seed
    resp = applet.secure_request(inner)
    print("IMPORT_SEED ok — authentikey coordx:", bytes(resp)[2:10].hex(), "…")

    st, sw1, sw2 = applet.get_card_status()
    status = applet.parse_status(bytes(st))
    print("post-setup status:", status)
    assert status.get("is_seeded") and status.get("setup_done"), status
    print("PERSONALIZATION COMPLETE")
    conn.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
