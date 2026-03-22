"""GP Card Management Hardware Test.

Run via: mpremote connect /dev/ttyACM1 exec test_gp_flow.py

Tests the full GlobalPlatform lifecycle on JCOP4 via SCP02:
  1. SCP02 session establishment
  2. GET STATUS (all 4 element types)
  3. AID lookup
  4. INSTALL FOR LOAD
  5. Chunked LOAD of CAP data
  6. INSTALL FOR INSTALL
  7. Verify installation
  8. DELETE applet + package
  9. Verify deletion
  10. SeedKeeper install (optional, requires SeedKeeper.dgp)

Requires: TeapotApplet.dgp uploaded to /flash/gp/
Optional: SeedKeeper.dgp uploaded to /flash/gp/ for SeedKeeper install test
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


def main():
    print("=" * 50)
    print("GP Card Management Hardware Test")
    print("=" * 50)

    # --- Test 1: SCP02 session ---
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

    # --- Test 2: GET STATUS ---
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
        has_apps = len(reg.get("apps", [])) > 0
        report("Apps found", has_apps,
               "%d entries" % len(reg.get("apps", [])))
        has_lf = len(reg.get("load_files", [])) > 0
        report("Load files found", has_lf,
               "%d entries" % len(reg.get("load_files", [])))
        has_pkg = len(reg.get("packages", [])) > 0
        report("Packages found", has_pkg,
               "%d entries" % len(reg.get("packages", [])))
        print()
        print(text)
    except Exception as e:
        report("GET STATUS parsed", False, str(e))

    # --- Test 3: AID lookup ---
    print()
    print("--- Test 3: AID Lookup ---")
    from keystore.javacard.gp.registry import find_aid

    sato = unhexlify("5361746f4368697000")
    mc = unhexlify("B00B5111CB01")
    teapot_pkg = unhexlify("B00B5111CA")
    teapot_inst = unhexlify("B00B5111CA01")

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

    try:
        teapot_entry = find_aid(session, teapot_inst)
        teapot_already = teapot_entry is not None
        report("TeapotApplet pre-check",
               True,
               "installed=%s" % teapot_already)
    except Exception as e:
        teapot_already = False
        report("TeapotApplet pre-check", False, str(e))

    # Clean up any leftover teapot from previous run
    if teapot_already:
        print("       Cleaning up leftover TeapotApplet...")
        from keystore.javacard.gp.deleter import delete_aid
        try:
            delete_aid(session, teapot_inst)
            report("Cleanup instance", True)
        except Exception as e:
            report("Cleanup instance", False, str(e))
        try:
            delete_aid(session, teapot_pkg)
            report("Cleanup package", True)
        except Exception as e:
            report("Cleanup package", False, str(e))

    # --- Test 4: INSTALL FOR LOAD ---
    print()
    print("--- Test 4: INSTALL FOR LOAD ---")
    from keystore.javacard.gp.loader import install_for_load

    sd_aid = unhexlify("A000000151000000")
    try:
        install_for_load(session, teapot_pkg, sd_aid)
        report("INSTALL for load", True)
    except Exception as e:
        report("INSTALL for load", False, str(e))

    # --- Test 5: LOAD CAP ---
    print()
    print("--- Test 5: LOAD CAP ---")
    from keystore.javacard.gp.loader import load_cap

    import os
    cap_path = "/flash/gp/TeapotApplet.dgp"
    try:
        f = open(cap_path, "rb")
        cap_data = f.read()
        f.close()
        cap_size = len(cap_data)
    except Exception:
        report("CAP file load", False, "%s not found" % cap_path)
        return
    report("CAP file loaded", True, "%d bytes from %s" % (cap_size, cap_path))

    import time
    try:
        t0 = time.ticks_ms()
        load_cap(session, cap_data)
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        blocks = (cap_size + 254) // 255
        report("LOAD CAP", True, "%d bytes in %d blocks, %d ms" % (
            cap_size, blocks, elapsed))
    except Exception as e:
        report("LOAD CAP", False, str(e))

    # --- Test 6: INSTALL FOR INSTALL ---
    print()
    print("--- Test 6: INSTALL FOR INSTALL ---")
    from keystore.javacard.gp.loader import install_for_install

    try:
        install_for_install(session, teapot_pkg, teapot_inst, teapot_inst)
        report("INSTALL for install", True)
    except Exception as e:
        report("INSTALL for install", False, str(e))

    # --- Test 7: Verify installation ---
    print()
    print("--- Test 7: Verify Installation ---")
    from keystore.javacard.gp.loader import verify_install

    try:
        found = verify_install(session, teapot_inst)
        report("TeapotApplet installed", found)
    except Exception as e:
        report("TeapotApplet installed", False, str(e))

    try:
        reg2 = list_all(session)
        text2 = format_registry(reg2)
        print(text2)
    except Exception:
        pass

    # --- Test 8: DELETE ---
    print()
    print("--- Test 8: DELETE ---")
    from keystore.javacard.gp.deleter import delete_aid

    try:
        sw1, sw2 = delete_aid(session, teapot_inst)
        report("DELETE instance", sw1 == 0x90, "SW=%02X%02X" % (sw1, sw2))
    except Exception as e:
        report("DELETE instance", False, str(e))

    try:
        sw1, sw2 = delete_aid(session, teapot_pkg)
        report("DELETE package", sw1 == 0x90, "SW=%02X%02X" % (sw1, sw2))
    except Exception as e:
        report("DELETE package", False, str(e))

    # --- Test 9: Verify deletion ---
    print()
    print("--- Test 9: Verify Deletion ---")
    try:
        found2 = verify_install(session, teapot_inst)
        report("TeapotApplet removed", not found2)
    except Exception as e:
        report("TeapotApplet removed", False, str(e))

    # --- Test 10: SeedKeeper Install (optional) ---
    print()
    print("--- Test 10: SeedKeeper Install ---")
    seedkeeper_path = "/flash/gp/SeedKeeper.dgp"
    seedkeeper_pkg = unhexlify("536565644b6565706572")  # "SeedKeeper"
    seedkeeper_inst = seedkeeper_pkg + b"\x00"  # "SeedKeeper\0" (from Applet.cap)

    # Check if SeedKeeper.dgp exists
    try:
        f = open(seedkeeper_path, "rb")
        f.close()
        sk_exists = True
    except Exception:
        sk_exists = False
        print("       Skipping: %s not found" % seedkeeper_path)
        print("       To test SeedKeeper install, copy the DGP file:")
        print("       mpremote cp SeedKeeper.dgp :/flash/gp/")

    if sk_exists:
        # Check if already installed
        try:
            sk_entry = find_aid(session, seedkeeper_inst)
            sk_already = sk_entry is not None
            report("SeedKeeper pre-check", True, "installed=%s" % sk_already)
        except Exception as e:
            sk_already = False
            report("SeedKeeper pre-check", False, str(e))

        if sk_already:
            report("SeedKeeper already installed", True, "skipping install")
        else:
            # Install SeedKeeper using install_from_dgp
            from keystore.javacard.gp.loader import install_from_dgp

            try:
                f = open(seedkeeper_path, "rb")
                sk_data = f.read()
                f.close()
                report("SeedKeeper DGP loaded", True, "%d bytes" % len(sk_data))
            except Exception as e:
                report("SeedKeeper DGP loaded", False, str(e))
                sk_data = None

            if sk_data:
                try:
                    t0 = time.ticks_ms()
                    pkg_aid = install_from_dgp(session, sk_data, sd_aid)
                    elapsed = time.ticks_diff(time.ticks_ms(), t0)
                    blocks = (len(sk_data) + 254) // 255
                    report("SeedKeeper install", True, "%d bytes in %d blocks, %d ms" % (
                        len(sk_data), blocks, elapsed))
                except Exception as e:
                    report("SeedKeeper install", False, str(e))

                # Verify installation
                try:
                    sk_found = verify_install(session, seedkeeper_inst)
                    report("SeedKeeper verified", sk_found)
                except Exception as e:
                    report("SeedKeeper verified", False, str(e))

                # Note: We don't delete SeedKeeper - leave it installed for use
                print("       SeedKeeper left installed for keystore use")

    # --- Cleanup ---
    try:
        conn.disconnect()
    except Exception:
        pass

    # --- Summary ---
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
