"""Record/check farm golden vectors — deterministic contract fixtures.

Records the deterministic subset of the card's answers (zero-value test
seed => same keys on every personalization): GET_STATUS bytes and
per-path (chaincode, coordx) derivations, per farm member, into
specter-javacard/tests/host/spec/vectors/satochip-<tag>.yaml.

  python3 record-farm-vectors.py            # record both members
  python3 record-farm-vectors.py --check    # re-derive + compare (CI/sync loop)

coordx is parity-independent (the python client's even-Y fallback makes
its full pubkeys unreliable; exact recovery lives in the Rust client).
"""
import importlib.util
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = "/home/ubuntu/src/specter-javacard/tests/host/spec/vectors"
PROTOCOL = "/home/ubuntu/src/specter-javacard/tests/host/spec/satochip-protocol.yaml"

spec = importlib.util.spec_from_file_location(
    "cardman_battery_shims", os.path.join(HERE, "cardman-battery.py"))
cmb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmb)

from keystore.javacard.applets.satochip_applet import SatochipApplet  # noqa: E402

PATHS = ["m/84h/0h/0h/0/%d" % i for i in range(3)]


def collect(reader):
    conn = cmb.PyscardConnection(reader)
    applet = SatochipApplet(conn)
    applet.select()
    st_raw, sw1, sw2 = applet.get_card_status()
    assert (sw1, sw2) == (0x90, 0x00)
    applet.init_secure_channel()
    applet.verify_pin("1234")
    paths = {}
    for p in PATHS:
        pub, cc = applet.get_extended_key(p, for_signing=True)
        paths[p] = {"chaincode": bytes(cc).hex(), "coordx": bytes(pub)[1:33].hex()}
    conn.disconnect()
    return {"get_status_hex": bytes(st_raw).hex(), "paths": paths}


def main():
    check = "--check" in sys.argv
    protocol = yaml.safe_load(open(PROTOCOL))
    failures = 0
    for tag, ver in protocol["versions"].items():
        reader = ver["farm_reader"]
        data = collect(reader)
        data.update({"tag": tag, "farm_reader": reader})
        path = os.path.join(SPEC_DIR, "satochip-%s.yaml" % tag)
        if check:
            expected = yaml.safe_load(open(path))
            if expected == data:
                print("%s: vectors match" % tag)
            else:
                print("%s: VECTOR DRIFT\n  expected: %r\n  actual:   %r"
                      % (tag, expected, data))
                failures += 1
        else:
            with open(path, "w") as fh:
                yaml.safe_dump(data, fh, sort_keys=True)
            print("recorded %s -> %s" % (tag, path))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
