"""GP Card Management Hardware Test.

Run via: mpremote connect /dev/ttyACM1 exec "from keystore.javacard.gp.test_gp_flow import main; main()"

Tests the full GlobalPlatform lifecycle on JCOP4 via SCP02:
  1. SCP02 session establishment
  2. GET STATUS (all 4 element types)
  3. AID lookup (SatoChip, MemoryCard)
  4. Generic DGP install (any DGP from /flash/gp/)
  5. Verify installation
  6. DELETE applet + package
  7. Verify deletion

DGP files must be uploaded to /flash/gp/ before running.
Generate DGP files: make dgps
Upload: mpremote cp bin/applets/<name>.dgp :/flash/gp/
"""

from binascii import hexlify, unhexlify

passed = 0
failed = 0


def report(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("[PASS] %s" % name)
    else:
        failed += 1
        print("[FAIL] %s" % name)
    if detail:
        print("       %s" % detail)


def get_reader():
    from pyb import Pin
    import uscard as sc
    return sc.Reader(
        name="Specter card reader",
        ifaceId=2,
        ioPin=Pin.cpu.A2,
        clkPin=Pin.cpu.A4,
        rstPin=Pin.cpu.G10,
        presPin=Pin.cpu.C2,
        pwrPin=Pin.cpu.C5,
    )


def open_gp_session(conn):
    from keystore.javacard.gp.profiles import JCOP4_PROFILE
    from keystore.javacard.gp.scp02 import open_session
    return open_session(conn, JCOP4_PROFILE)


def find_dgp_file():
    """Find the first DGP file in /flash/gp/."""
    import os
    try:
        files = os.listdir("/flash/gp")
    except Exception:
        return None
    for f in sorted(files):
        if f.endswith(".dgp"):
            return "/flash/gp/" + f
    return None


def test_dgp_install(session, dgp_path, sd_aid):
    """Run full install-load-verify-delete lifecycle on a DGP file."""
    from keystore.javacard.gp.loader import (
        install_from_dgp, verify_install, extract_applet_aid, extract_package_aid,
    )
    from keystore.javacard.gp.deleter import delete_aid
    from keystore.javacard.gp.registry import find_aid
    import time
    import gc

    gc.collect()
    print("--- DGP Install: %s ---" % dgp_path)

    f = open(dgp_path, "rb")
    dgp_data = f.read()
    f.close()
    report("DGP loaded", True, "%d bytes" % len(dgp_data))

    pkg_aid = extract_package_aid(dgp_data)
    report("Package AID extracted", True, hexlify(pkg_aid).decode())

    applet_aid = extract_applet_aid(dgp_data)
    report("Applet AID extracted", True, hexlify(applet_aid).decode())

    pre = find_aid(session, applet_aid)
    if pre:
        print("       Cleaning up leftover installation...")
        try:
            delete_aid(session, applet_aid)
            report("Cleanup instance", True)
        except Exception as e:
            err = str(e)
            if "6985" in err:
                report("Cleanup instance", True, "SW=6985 (applet protected, trying package)")
            else:
                report("Cleanup instance", False, err)
        try:
            delete_aid(session, pkg_aid)
            report("Cleanup package", True)
        except Exception as e:
            report("Cleanup package", False, str(e))

    gc.collect()
    t0 = time.ticks_ms()
    try:
        installed = install_from_dgp(session, dgp_data, sd_aid)
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        blocks = (len(dgp_data) + 254) // 255
        report("Install + LOAD", True,
               "%d bytes, %d blocks, %d ms" % (len(dgp_data), blocks, elapsed))
    except Exception as e:
        report("Install + LOAD", False, str(e))
        return

    found = verify_install(session, applet_aid)
    report("Verification", found)

    from keystore.javacard.gp.registry import list_all, format_registry
    try:
        reg = list_all(session)
        print(format_registry(reg))
    except Exception:
        pass

    try:
        sw1, sw2 = delete_aid(session, applet_aid)
        if sw1 == 0x90:
            report("DELETE instance", True, "SW=9000")
        elif sw1 == 0x69 and sw2 == 0x85:
            report("DELETE instance", True, "SW=6985 (applet protected, deleting package)")
        else:
            report("DELETE instance", False, "SW=%02X%02X" % (sw1, sw2))
    except Exception as e:
        err = str(e)
        if "6985" in err:
            report("DELETE instance", True, "SW=6985 (applet protected, deleting package)")
        else:
            report("DELETE instance", False, err)

    try:
        sw1, sw2 = delete_aid(session, pkg_aid)
        report("DELETE package", sw1 == 0x90, "SW=%02X%02X" % (sw1, sw2))
    except Exception as e:
        report("DELETE package", False, str(e))

    try:
        found2 = verify_install(session, applet_aid)
        report("Deletion verified", not found2)
    except Exception as e:
        report("Deletion verified", False, str(e))


def main():
    print("=" * 50)
    print("GP Card Management Hardware Test")
    print("=" * 50)

    print()
    print("--- Test 1: SCP02 Session ---")
    reader = get_reader()
    conn = reader.createConnection()
    conn.connect(conn.T1_protocol)
    atr = conn.getATR()
    report("Card present", len(atr) > 0, "ATR: %s" % hexlify(atr).decode())

    try:
        session = open_gp_session(conn)
        report("SCP02 session", True)
    except Exception as e:
        report("SCP02 session", False, str(e))
        return

    print()
    print("--- Test 2: GET STATUS ---")
    from keystore.javacard.gp.registry import list_all, format_registry

    try:
        reg = list_all(session)
        text = format_registry(reg)
        has_isd = len(reg.get("isd", [])) > 0
        report("GET STATUS parsed", has_isd)
        if has_isd:
            isd = reg["isd"][0]
            report("ISD lifecycle",
                   isd.get("lifecycle") is not None,
                   "LC=%02X" % (isd.get("lifecycle") or 0))
            report("ISD privileges",
                   isd.get("privileges") is not None,
                   hexlify(isd.get("privileges", b"")).decode())
        report("Apps found", len(reg.get("apps", [])) > 0,
               "%d entries" % len(reg.get("apps", [])))
        report("Load files found", len(reg.get("load_files", [])) > 0,
               "%d entries" % len(reg.get("load_files", [])))
        report("Packages found", len(reg.get("packages", [])) > 0,
               "%d entries" % len(reg.get("packages", [])))
        print()
        print(text)
    except Exception as e:
        report("GET STATUS parsed", False, str(e))

    print()
    print("--- Test 3: AID Lookup ---")
    from keystore.javacard.gp.registry import find_aid

    sato = unhexlify("5361746f4368697000")
    mc = unhexlify("B00B5111CB01")
    try:
        sato_entry = find_aid(session, sato)
        report("SatoChip found", sato_entry is not None)
    except Exception as e:
        report("SatoChip found", False, str(e))

    try:
        mc_entry = find_aid(session, mc)
        report("MemoryCard absent", mc_entry is None)
    except Exception as e:
        report("MemoryCard absent", False, str(e))

    print()
    print("--- Test 4: Generic DGP Install ---")
    dgp_path = find_dgp_file()
    if dgp_path is None:
        report("DGP file found", False,
               "no DGP in /flash/gp/ (make dgps && mpremote cp)")
    else:
        report("DGP file found", True, dgp_path)
        sd_aid = unhexlify("A000000151000000")
        test_dgp_install(session, dgp_path, sd_aid)

    try:
        conn.disconnect()
    except Exception:
        pass

    print()
    print("=" * 50)
    total = passed + failed
    print("Results: %d/%d passed, %d failed" % (passed, total, failed))
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 50)


main()
