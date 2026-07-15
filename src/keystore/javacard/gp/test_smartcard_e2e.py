"""Smartcard E2E test: full MemoryCard install/use/delete lifecycle.

Run via:
  mpremote connect /dev/ttyACM1 exec "from keystore.javacard.gp.test_smartcard_e2e import main; main()"

REQUIRES:
  - JCOP4 card with GP default keys
  - MemoryCard.dgp uploaded to /flash/gp/
  - No MemoryCard currently installed (test cleans up after itself)

DESTRUCTIVE: installs and deletes MemoryCard applet.
Run on a test card only.

Tests:
  Group A: Card Detection
    1. GP probe (card responds to default keys)
    2. GP status (ISD + SatoChip visible)

  Group B: Install Lifecycle
    3. Install MemoryCard from DGP
    4. Verify SELECT after install
    5. Verify via GP status

  Group C: Secure Channel
    6. Open secure channel
    7. Ping (echo test)
    8. Check PIN not set
    9. Set PIN
    10. Verify PIN set
    11. Unlock with correct PIN
    12. Lock
    13. Reconnect + unlock
    14. Wrong PIN (verify error)
    15. Unlock after wrong PIN

  Group D: Data Operations
    16. Get secret (empty)
    17. Save secret
    18. Get secret (non-empty)
    19. Delete secret via save empty

  Group E: Cleanup
    20. DELETE applet + package
    21. Verify deletion
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


def reconnect(conn):
    try:
        conn.disconnect()
    except Exception:
        pass
    import time as _time
    _time.sleep_ms(500)
    conn.connect(conn.T1_protocol)


def open_mc_applet(conn):
    from keystore.javacard.applets.memorycard import MemoryCardApplet
    applet = MemoryCardApplet(conn)
    applet.select()
    applet.open_secure_channel()
    return applet


def _file_exists(path):
    import os
    try:
        os.stat(path)
        return True
    except Exception:
        return False


def group_a_detection(conn):
    print("\n--- Group A: Card Detection ---")

    from keystore.javacard.gp.probe import probe_card
    r = probe_card(conn)
    has_profile = r.get("profile") is not None
    report("GP probe", has_profile,
           "kind=%s" % r.get("kind"))
    if not has_profile:
        return False

    from keystore.javacard.gp.profiles import JCOP4_PROFILE
    from keystore.javacard.gp.scp02 import open_session
    from keystore.javacard.gp.registry import list_all, format_registry
    reconnect(conn)
    session = open_session(conn, JCOP4_PROFILE)
    try:
        registry = list_all(session)
        text = format_registry(registry)
        has_isd = "A000000151" in text or "ISD" in text.upper()
        report("GP status", has_isd, text[:80])
    except Exception as e:
        report("GP status", False, str(e))
    finally:
        try:
            session.end_session()
        except Exception:
            pass
        try:
            conn.disconnect()
        except Exception:
            pass

    return True


def group_b_install(conn, session):
    print("\n--- Group B: Install Lifecycle ---")

    import os
    dgp_path = "/flash/gp/MemoryCard.dgp"
    if not _file_exists(dgp_path):
        report("Install MemoryCard", False, "DGP not found at %s" % dgp_path)
        return False

    f = open(dgp_path, "rb")
    dgp_data = f.read()
    f.close()
    try:
        from keystore.javacard.gp.loader import install_from_dgp
        sd_aid = unhexlify("A000000151000000")
        install_from_dgp(session, dgp_data, sd_aid)
        report("Install MemoryCard", True, "%d bytes" % len(dgp_data))
    except Exception as e:
        report("Install MemoryCard", False, str(e))
        return False

    session.end_session()
    conn.disconnect()

    reconnect(conn)
    from keystore.javacard.applets.applet import Applet
    try:
        applet = Applet(conn, unhexlify("B00B5111CB01"))
        applet.select()
        report("Verify SELECT", True)
    except Exception as e:
        report("Verify SELECT", False, str(e))
        return False

    conn.disconnect()
    reconnect(conn)
    session = open_gp_session(conn)
    try:
        from keystore.javacard.gp.registry import list_all, format_registry
        registry = list_all(session)
        text = format_registry(registry)
        has_mc = "B00B5111CB01" in text or "B00B5111CB" in text
        report("Status shows MC", has_mc, text[:80])
    except Exception as e:
        report("Status shows MC", False, str(e))
    finally:
        try:
            session.end_session()
        except Exception:
            pass
        try:
            conn.disconnect()
        except Exception:
            pass

    return True


def group_c_secure_channel(conn):
    print("\n--- Group C: Secure Channel ---")

    reconnect(conn)
    try:
        applet = open_mc_applet(conn)
    except Exception as e:
        report("Open secure channel", False, str(e))
        return None

    report("Open secure channel", applet.is_secure_channel_open)

    try:
        applet.ping()
        report("Ping", True)
    except Exception as e:
        report("Ping", False, str(e))

    pin_set = applet.is_pin_set
    report("PIN not set", not pin_set,
           "status=%d attempts=%d/%d" % (applet._pin_status, applet.pin_attempts_left, applet.pin_attempts_max))
    if pin_set:
        report("PIN already set - skipping set test", False, "clean card first")
        return applet

    try:
        applet.set_pin("1234")
        report("Set PIN", applet.is_pin_set, "status=%d" % applet._pin_status)
    except Exception as e:
        report("Set PIN", False, str(e))
        return applet

    try:
        applet.lock()
        assert applet.is_locked
        applet.unlock("1234")
        report("Unlock with PIN", not applet.is_locked)
    except Exception as e:
        report("Unlock with PIN", False, str(e))

    try:
        applet.lock()
        report("Lock", applet.is_locked)
    except Exception as e:
        report("Lock", False, str(e))

    try:
        conn.disconnect()
        reconnect(conn)
        applet2 = open_mc_applet(conn)
        assert applet2.is_locked
        applet2.unlock("1234")
        report("Reconnect + unlock", not applet2.is_locked)
        applet2.lock()
        conn.disconnect()
    except Exception as e:
        report("Reconnect + unlock", False, str(e))
        return None

    try:
        reconnect(conn)
        applet3 = open_mc_applet(conn)
        assert applet3.is_locked
        try:
            applet3.unlock("wrong")
            report("Wrong PIN error", False, "should have raised")
        except Exception as e:
            ok = "0502" in str(e) or "PIN" in str(e).upper() or "wrong" in str(e).lower()
            report("Wrong PIN error", ok, str(e)[:60])

        applet3.unlock("1234")
        report("Unlock after wrong PIN", not applet3.is_locked)
        applet3.lock()
        conn.disconnect()
    except Exception as e:
        report("Unlock after wrong PIN", False, str(e))

    return True


def group_d_data(conn):
    print("\n--- Group D: Data Operations ---")

    reconnect(conn)
    try:
        applet = open_mc_applet(conn)
    except Exception as e:
        report("Open secure channel", False, str(e))
        return False

    try:
        applet.unlock("1234")
    except Exception as e:
        report("Unlock", False, str(e))
        return False

    try:
        secret = applet.get_secret()
        report("Get secret (empty)", len(secret) == 0, "%d bytes" % len(secret))
    except Exception as e:
        report("Get secret (empty)", False, str(e))

    test_data = b"\x01\x02\x03\x04\x05\x06\x07\x08" * 4
    try:
        applet.save_secret(test_data)
        report("Save secret", True, "%d bytes" % len(test_data))
    except Exception as e:
        report("Save secret", False, str(e))
        return False

    try:
        secret = applet.get_secret()
        report("Get secret (non-empty)", len(secret) > 0, "%d bytes" % len(secret))
    except Exception as e:
        report("Get secret (non-empty)", False, str(e))

    try:
        applet.save_secret(b"")
        secret = applet.get_secret()
        report("Delete secret (save empty)", len(secret) == 0, "%d bytes" % len(secret))
    except Exception as e:
        report("Delete secret (save empty)", False, str(e))

    try:
        applet.lock()
        conn.disconnect()
    except Exception:
        pass

    return True


def cleanup(conn):
    print("\n--- Cleanup ---")
    from keystore.javacard.gp.deleter import delete_aid
    from keystore.javacard.applets.applet import Applet

    try:
        reconnect(conn)
        session = open_gp_session(conn)

        try:
            delete_aid(session, unhexlify("B00B5111CB01"))
            report("Cleanup: delete applet", True)
        except Exception as e:
            report("Cleanup: delete applet", False, str(e))

        try:
            delete_aid(session, unhexlify("B00B5111CB"))
            report("Cleanup: delete package", True)
        except Exception as e:
            report("Cleanup: delete package", False, str(e))

        try:
            session.end_session()
        except Exception:
            pass
    except Exception as e:
        report("Cleanup: GP reconnect", False, str(e))
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass

    reconnect(conn)
    try:
        applet = Applet(conn, unhexlify("B00B5111CB01"))
        applet.select()
        report("Cleanup: verify deleted", False, "SELECT still works!")
    except Exception:
        report("Cleanup: verify deleted", True)

    try:
        conn.disconnect()
    except Exception:
        pass


def main():
    global passed, failed

    print("=" * 50)
    print("Smartcard E2E Test")
    print("=" * 50)
    print()
    print("WARNING: Destructive test - installs/deletes MemoryCard")
    print("Use a test card with GP default keys only.")
    print()

    conn = None
    session = None

    try:
        reader = get_reader()
        conn = reader.createConnection()
        conn.connect(conn.T1_protocol)

        if not group_a_detection(conn):
            print("\nDetection failed - aborting")
            conn.disconnect()
            return

        reconnect(conn)
        session = open_gp_session(conn)

        if not group_b_install(conn, session):
            print("\nInstall failed - aborting")
            try:
                session.end_session()
            except Exception:
                pass
            conn.disconnect()
            return

        group_c_secure_channel(conn)
        group_d_data(conn)

    except Exception as e:
        print("\n[FATAL] %s" % e)
        import sys
        sys.print_exception(e)
    finally:
        if conn is not None:
            cleanup(conn)

    print()
    print("=" * 50)
    print("Results: %d passed, %d failed" % (passed, failed))
    print("=" * 50)
