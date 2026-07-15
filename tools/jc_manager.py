#!/usr/bin/env python3
"""Interactive Java Card manager using gp.jar.

IMPORTANT: Only use GlobalPlatformPro v25.10.20 or newer.
The old v20.01.23 from nix store has known issues:
  - The --key flag hangs indefinitely
  - Takes ~20s per command (timeout-prone)
  - May cause cryptogram mismatch errors that increment the card's
    error counter, potentially permanently blocking the key.

Card: NXP JCOP4 (J3H145) via Gemalto PC Twin Reader.
Protocol: SCP02, key version 1.

Usage:
  Interactive:  python3 tools/jc_manager.py
  CLI:          python3 tools/jc_manager.py --list
                python3 tools/jc_manager.py --detect
                python3 tools/jc_manager.py --detect-factory
                python3 tools/jc_manager.py --delete <AID>
                python3 tools/jc_manager.py --install <file.cap>
                python3 tools/jc_manager.py --load <file.cap>
                python3 tools/jc_manager.py --info
                python3 tools/jc_manager.py --apdu <hex>
                python3 tools/jc_manager.py --secure-apdu <hex>
                python3 tools/jc_manager.py --set-default-keys
                python3 tools/jc_manager.py --unlock
"""

import subprocess
import sys
import os
import re
import argparse

GP_JAR_PATHS = [
    "/home/ubuntu/src/record/specter-flash/gp.jar",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "record", "specter-flash", "gp.jar"),
]
GP_JAR = None
for p in GP_JAR_PATHS:
    if os.path.exists(p):
        GP_JAR = os.path.abspath(p)
        break

if GP_JAR is None:
    GP_JAR = "gp.jar"

DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"

FACTORY_KEYS = {
    "enc": "5A9E63D03BADBC2A240FE8F534709EDF",
    "mac": "7CCC1E79D64FC5FA263B8F2955282998",
    "dek": "B040703EC3DE23EE8AE4CFB6D632AA80",
}

KNOWN_AIDS = {
    "A000000151000000": ("Gemalto ISD (Issuer Security Domain)", "Proprietary", "Card OS - cannot delete"),
    "A0000001515350":   ("GlobalPlatform Card Manager package", "Proprietary", "Card OS - cannot delete"),
    "A000000151535041": ("GlobalPlatform Card Manager applet", "Proprietary", "Card OS - cannot delete"),
    "A000000308000010": ("Gemalto/Thales MultiApp OS package", "Proprietary", "Card OS - cannot delete"),
    "A000000308000010000100": ("Gemalto/Thales MultiApp OS applet", "Proprietary", "Card OS - cannot delete"),
    "A00000016443446F634C697465": ("dCDocLite package", "Proprietary", "Card OS - cannot delete"),
    "A00000016443446F634C69746501": ("dCDocLite applet", "Proprietary", "Card OS - cannot delete"),
    "A0000000620202": ("javacardx.biometry package", "Proprietary", "Card OS - cannot delete"),
    "A0000000620204": ("javacardx.biometry1toN package", "Proprietary", "Card OS - cannot delete"),
    "5361746F4368697000": ("SatoChip", "Open Source (github.com/Toporin/SatoChip-Applet)", "Bitcoin hardware wallet"),
    "5361746F44696D6500": ("SatoDim", "Open Source (github.com/Toporin/SatoChip-Applet)", "Payment card manager"),
    "5361746F43686970":   ("SatoChip Package", "Open Source", "Bitcoin hardware wallet"),
    "5361746F44696D65":   ("SatoDim Package", "Open Source", "Payment card manager"),
    "D27600012401":   ("SmartPGP Package", "Open Source (github.com/philips-smartcard/SmartPGP)", "PGP smart card"),
    "D276000124010304AFAF000000000000": ("SmartPGP Applet", "Open Source", "PGP smart card"),
}

_session = {
    "key_type": None,
    "key": None,
    "key_enc": None,
    "key_mac": None,
    "key_dek": None,
    "gp_version": None,
    "card_detected": False,
}


def _run_gp(args, timeout=30):
    cmd = ["java", "-jar", GP_JAR] + args
    if _session["key_enc"]:
        cmd += ["--key-enc", _session["key_enc"],
                "--key-mac", _session["key_mac"],
                "--key-dek", _session["key_dek"]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout + result.stderr, False
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s.\n  This may mean the card is not responding or the keys are wrong.\n  Command was: {' '.join(cmd)}", True


def _check_gp_version():
    out, timed_out = _run_gp(["--version"], timeout=10)
    if timed_out:
        print("  WARNING: gp.jar version check timed out.")
        return
    for line in out.splitlines():
        if "GlobalPlatformPro" in line:
            ver = line.strip().lstrip("#").strip()
            _session["gp_version"] = ver
            major = ver.split("v")[1].split(".")[0] if "v" in ver else "0"
            if int(major) < 25:
                print(f"  WARNING: {ver} is OLD (< v25).")
                print("  The old v20 gp.jar has known bugs that can BRICK your card.")
                print(f"  Current path: {GP_JAR}")
                print("  Install v25.10.20 from: https://github.com/martinpaljak/GlobalPlatformPro/releases")
            else:
                print(f"  gp.jar version: {ver}")
            return


def _parse_error(output):
    if "cryptogram invalid" in output.lower() or "cryptogram" in output.lower() and "invalid" in output.lower():
        return "AUTH_FAILED", "Card cryptogram mismatch. The keys are wrong or the key version has been permanently blocked by too many failed attempts."
    if "6982" in output:
        return "AUTH_FAILED", "Security status not satisfied (SW 6982). Wrong keys."
    if "6985" in output:
        return "CONDITIONS", "Conditions not satisfied (SW 6985). Operation not allowed in current card state."
    if "6A80" in output:
        return "INVALID_DATA", "Invalid data (SW 6A80). Check AIDs and parameters."
    if "6A82" in output:
        return "NOT_FOUND", "File/applet not found (SW 6A82)."
    if "Could not connect" in output or "PC/SC" in output:
        return "NO_CARD", "Could not connect to card. Check reader and card insertion."
    if "DO NOT RE-TRY" in output:
        return "BRICK_RISK", "gp.jar warns that retrying may permanently block the card key. STOP and use different keys."
    return None, None


def _print_output(output):
    for line in output.strip().splitlines():
        if line.strip():
            print(f"  {line}")


def parse_list_output(text):
    entries = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(ISD|APP|PKG):\s+([0-9A-Fa-f]+)\s+\((\w+)\)", line)
        if m:
            kind, aid, state = m.group(1), m.group(2), m.group(3)
            current = {"kind": kind, "aid": aid, "state": state, "props": {}}
            entries.append(current)
            continue
        if current is not None:
            pm = re.match(r"(\w+):\s+(.*)", line)
            if pm:
                current["props"][pm.group(1)] = pm.group(2).strip()
    return entries


def aid_info(aid):
    return KNOWN_AIDS.get(aid.upper(), ("Unknown", "Unknown", ""))


def aid_to_ascii(aid):
    try:
        return bytes.fromhex(aid).decode("ascii", errors="replace").strip("\x00")
    except Exception:
        return aid


def print_entries(entries):
    if not entries:
        print("  (nothing found)")
        return
    print()
    print(f"  {'Type':<5} {'AID':<42} {'State':<12} {'Name'}")
    print(f"  {'-'*5} {'-'*42} {'-'*12} {'-'*30}")
    for e in entries:
        name, license_, notes = aid_info(e["aid"])
        ascii_name = aid_to_ascii(e["aid"])
        display = ascii_name if ascii_name != e["aid"] else name
        print(f"  {e['kind']:<5} {e['aid']:<42} {e['state']:<12} {display}")
        if notes:
            print(f"        {license_} | {notes}")
    print()


def _set_key(key_type, key_enc=None, key_mac=None, key_dek=None, key=None):
    if key:
        _session["key_type"] = key_type
        _session["key"] = key
        _session["key_enc"] = key
        _session["key_mac"] = key
        _session["key_dek"] = key
    else:
        _session["key_type"] = key_type
        _session["key_enc"] = key_enc
        _session["key_mac"] = key_mac
        _session["key_dek"] = key_dek


def _clear_key():
    _session["key_type"] = None
    _session["key"] = None
    _session["key_enc"] = None
    _session["key_mac"] = None
    _session["key_dek"] = None


def _key_label():
    if _session["key_type"] == "default":
        return "default (404142...4F)"
    elif _session["key_type"] == "factory":
        return "Gemalto factory transport keys"
    elif _session["key_type"] == "custom":
        return _session["key"]
    return "none"


def cmd_detect():
    print("Detecting card with default GP test keys...")
    _clear_key()
    output, timed_out = _run_gp(["-l"], timeout=30)
    if timed_out:
        print("  Timed out. Card may not be inserted or reader not connected.")
        _session["card_detected"] = False
        return

    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        if err_code in ("AUTH_FAILED", "BRICK_RISK"):
            print("  The card's default key version may be permanently blocked.")
            print("  This happens after too many failed auth attempts.")
            print("  Try factory keys instead (menu option [2]).")
        _session["card_detected"] = False
        return

    if "ISD:" in output:
        _set_key("default", key=DEFAULT_KEY)
        _session["card_detected"] = True
        print("  SUCCESS: Card uses default GP test keys (404142...4F)")
        entries = parse_list_output(output)
        print(f"  Found {len(entries)} entries on card.")
    else:
        print("  Unexpected response:")
        _print_output(output)
        _session["card_detected"] = False


def cmd_detect_factory():
    print("WARNING: This will send ONE authentication attempt with Gemalto factory transport keys.")
    print("  If the keys are wrong, this increments the card's error counter.")
    print("  Too many failed attempts will PERMANENTLY BLOCK the key on the card.")
    try:
        confirm = input("  Proceed? [y/N]: ").strip().lower()
    except EOFError:
        confirm = "n"
    if confirm != "y":
        print("  Cancelled.")
        return

    print("Probing card with factory keys (single attempt)...")
    _clear_key()
    _session["key_enc"] = FACTORY_KEYS["enc"]
    _session["key_mac"] = FACTORY_KEYS["mac"]
    _session["key_dek"] = FACTORY_KEYS["dek"]
    output, timed_out = _run_gp(["-l"], timeout=30)
    _clear_key()

    if timed_out:
        print("  Timed out. Factory keys are not accepted.")
        _session["card_detected"] = False
        return

    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        if err_code in ("AUTH_FAILED", "BRICK_RISK"):
            print("  Factory keys were rejected. The card does not use factory keys.")
        _session["card_detected"] = False
        return

    if "ISD:" in output:
        _set_key("factory",
                 key_enc=FACTORY_KEYS["enc"],
                 key_mac=FACTORY_KEYS["mac"],
                 key_dek=FACTORY_KEYS["dek"])
        _session["card_detected"] = True
        print("  SUCCESS: Card has FACTORY keys (fresh/unmodified card)")
        entries = parse_list_output(output)
        print(f"  Found {len(entries)} entries on card.")

        try:
            set_def = input("  Set default GP test keys now? [Y/n]: ").strip().lower()
        except EOFError:
            set_def = "y"
        if set_def != "n":
            cmd_set_default_keys()
    else:
        print("  Unexpected response:")
        _print_output(output)
        _session["card_detected"] = False


def cmd_set_default_keys():
    if _session["key_type"] != "factory":
        print("  This command sets default keys on a card that currently uses factory keys.")
        print("  First detect the card with factory keys (option [2]).")
        return
    print("Setting default keys on card...")
    print(f"  From: factory keys")
    print(f"  To:   {DEFAULT_KEY}")
    output, timed_out = _run_gp(["--lock", DEFAULT_KEY], timeout=30)
    if timed_out:
        print("  Timed out while setting keys.")
        return
    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        _print_output(output)
        return
    _print_output(output)
    if "locked with" in output.lower() or "9000" in output:
        _clear_key()
        _set_key("default", key=DEFAULT_KEY)
        print("  SUCCESS: Default keys set. Card now uses 404142...4F")
    else:
        print("  Unexpected response - keys may not have been set.")
        _session["card_detected"] = False


def cmd_list():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    print(f"Listing card contents (key: {_key_label()})...")
    output, timed_out = _run_gp(["-l"], timeout=30)
    if timed_out:
        print("  Timed out. Card may have been removed or keys changed.")
        _session["card_detected"] = False
        return
    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        _print_output(output)
        if err_code in ("AUTH_FAILED", "BRICK_RISK"):
            _session["card_detected"] = False
        return
    entries = parse_list_output(output)
    if not entries:
        print("  No entries found or could not parse output.")
        _print_output(output)
        return
    print(f"  Found {len(entries)} entries:")
    print_entries(entries)


def cmd_delete():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    print(f"Listing card contents (key: {_key_label()})...")
    output, timed_out = _run_gp(["-l"], timeout=30)
    if timed_out:
        print("  Timed out.")
        return
    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        _print_output(output)
        return
    entries = parse_list_output(output)
    if not entries:
        print("  No entries found.")
        return
    print(f"  Found {len(entries)} entries:")
    print_entries(entries)

    card_os_aids = {
        "A0000001515350", "A000000308000010",
        "A00000016443446F634C697465", "A00000016443446F634C69746501",
        "A0000000620202", "A0000000620204",
        "A000000151000000", "A000000151535041",
    }
    deletable = [e for e in entries if e["kind"] != "ISD"
                 and e["aid"] not in card_os_aids
                 and e["props"].get("From", "") not in card_os_aids]

    if not deletable:
        print("  No deletable entries found. Card OS packages cannot be deleted.")
        return

    print("  Deletable entries:")
    for i, e in enumerate(deletable):
        name, _, _ = aid_info(e["aid"])
        ascii_name = aid_to_ascii(e["aid"])
        display = ascii_name if ascii_name != e["aid"] else name
        print(f"    [{i+1}] {e['kind']}: {e['aid']} ({display})")

    try:
        choice = input("\n  Enter number to delete (or 'q' to cancel): ").strip()
    except EOFError:
        return
    if choice.lower() == "q":
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(deletable):
            print("  Invalid selection.")
            return
    except ValueError:
        print("  Invalid input.")
        return

    target = deletable[idx]
    aid = target["aid"]
    name, _, _ = aid_info(aid)
    ascii_name = aid_to_ascii(aid)
    display = ascii_name if ascii_name != aid else name
    try:
        confirm = input(f"  Delete {target['kind']} {aid} ({display})? [y/N]: ").strip().lower()
    except EOFError:
        return
    if confirm != "y":
        print("  Cancelled.")
        return

    print(f"  Deleting {aid}...")
    output, timed_out = _run_gp(["--delete", aid, "-f"], timeout=30)
    if timed_out:
        print("  Timed out during delete.")
        return

    err_code, err_msg = _parse_error(output)
    if "Could not delete" in output or err_code:
        print(f"  Delete failed: {err_msg if err_code else 'unknown reason'}")
        if target["kind"] == "PKG":
            print("  Trying to delete applet instances first, then package...")
            for e2 in entries:
                if e2["props"].get("From", "") == aid:
                    print(f"    Deleting applet {e2['aid']}...")
                    r2, t2 = _run_gp(["--delete", e2["aid"], "-f"], timeout=30)
                    if t2:
                        print(f"    Timed out on {e2['aid']}")
                    elif "Could not delete" not in r2:
                        print(f"    Deleted applet {e2['aid']}")
                    else:
                        print(f"    Failed: {r2.strip()}")
            output, timed_out = _run_gp(["--delete", aid, "-f"], timeout=30)

    _print_output(output)
    if "Could not delete" not in output and not err_code:
        print("  Deleted successfully.")
        cmd_list()
    else:
        print("  Delete failed.")


def cmd_install():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    try:
        cap_path = input("  Path to CAP file: ").strip()
    except EOFError:
        return
    if not cap_path:
        print("  No path provided.")
        return
    if not os.path.exists(cap_path):
        print(f"  File not found: {cap_path}")
        return

    try:
        applet_aid = input("  Applet AID (hex, leave blank for default): ").strip()
    except EOFError:
        applet_aid = ""
    try:
        package_aid = input("  Package AID (hex, leave blank for default): ").strip()
    except EOFError:
        package_aid = ""

    args = ["--install", cap_path]
    if applet_aid:
        args += ["--applet", applet_aid]
    if package_aid:
        args += ["--package", package_aid]

    print(f"  Installing {cap_path}...")
    output, timed_out = _run_gp(args, timeout=120)
    if timed_out:
        print("  Timed out during install.")
        return
    _print_output(output)


def cmd_load():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    try:
        cap_path = input("  Path to CAP file: ").strip()
    except EOFError:
        return
    if not cap_path:
        print("  No path provided.")
        return
    if not os.path.exists(cap_path):
        print(f"  File not found: {cap_path}")
        return
    print(f"  Loading {cap_path}...")
    output, timed_out = _run_gp(["--load", cap_path], timeout=120)
    if timed_out:
        print("  Timed out during load.")
        return
    _print_output(output)


def cmd_send_apdu():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    try:
        apdu = input("  APDU hex (e.g. 00A4040000): ").strip()
    except EOFError:
        return
    if not apdu:
        print("  No APDU provided.")
        return
    print(f"  Sending plaintext APDU: {apdu}")
    output, timed_out = _run_gp(["--apdu", apdu], timeout=30)
    if timed_out:
        print("  Timed out.")
        return
    _print_output(output)


def cmd_send_secure_apdu():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    try:
        apdu = input("  APDU hex (e.g. 00A4040000): ").strip()
    except EOFError:
        return
    if not apdu:
        print("  No APDU provided.")
        return
    print(f"  Sending secure APDU: {apdu}")
    output, timed_out = _run_gp(["--secure-apdu", apdu], timeout=30)
    if timed_out:
        print("  Timed out.")
        return
    _print_output(output)


def cmd_info():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    print(f"  Card info (key: {_key_label()})...")
    output, timed_out = _run_gp(["-i"], timeout=30)
    if timed_out:
        print("  Timed out.")
        return
    _print_output(output)


def cmd_set_custom_key():
    try:
        key = input("  Master key (hex, 32 bytes): ").strip()
    except EOFError:
        return
    if not key:
        print("  No key provided.")
        return
    if len(key) != 32:
        print(f"  WARNING: Key is {len(key)} hex chars, expected 32 (16 bytes).")
        try:
            confirm = input("  Use anyway? [y/N]: ").strip().lower()
        except EOFError:
            return
        if confirm != "y":
            print("  Cancelled.")
            return
    _clear_key()
    _set_key("custom", key=key)
    print(f"  Key set to: {key}")
    print("  This key will be used for ENC, MAC, and DEK.")
    print("  Note: The card must already be configured with this key.")


def cmd_unlock():
    if not _session["card_detected"]:
        print("  No card detected yet. Use option [1] or [2] first.")
        return
    print("  Unlocking card (sets keys to GP default test keys)...")
    print("  WARNING: This requires the current key to authenticate.")
    output, timed_out = _run_gp(["--unlock"], timeout=30)
    if timed_out:
        print("  Timed out.")
        return
    _print_output(output)
    err_code, err_msg = _parse_error(output)
    if err_code:
        print(f"  FAILED: {err_msg}")
        return
    _clear_key()
    _set_key("default", key=DEFAULT_KEY)
    print("  Card unlocked to default keys.")


def main():
    if not os.path.exists(GP_JAR):
        print(f"FATAL: gp.jar not found.")
        print(f"  Searched: {GP_JAR_PATHS}")
        print("  Install GlobalPlatformPro v25.10.20+ from:")
        print("  https://github.com/martinpaljak/GlobalPlatformPro/releases")
        sys.exit(1)

    print(f"  gp.jar: {GP_JAR}")
    _check_gp_version()

    while True:
        print()
        print("=" * 56)
        print("  Java Card Manager")
        print("=" * 56)
        if _session["card_detected"]:
            print(f"  Card: DETECTED  |  Key: {_key_label()}")
        else:
            print(f"  Card: NOT DETECTED  |  Key: {_key_label()}")
        print()
        print("  --- Detection ---")
        print("  [1]  Detect card (default GP keys 404142...4F)")
        print("  [2]  Detect card (Gemalto factory keys) *caution*")
        print()
        print("  --- Card operations (require detected card) ---")
        print("  [3]  List apps/packages on card")
        print("  [4]  Delete app/package from card")
        print("  [5]  Install CAP file on card")
        print("  [6]  Load CAP file to card")
        print("  [7]  Card info (CPLC data)")
        print()
        print("  --- APDU ---")
        print("  [8]  Send plaintext APDU")
        print("  [9]  Send secure APDU")
        print()
        print("  --- Key management ---")
        print("  [10] Set custom key for session")
        print("  [11] Unlock card (reset to default keys)")
        print("  [12] Set default keys on factory-key card")
        print()
        print("  [0]  Quit")
        print()

        try:
            choice = input("  Choice: ").strip()
        except EOFError:
            break

        if choice == "1":
            cmd_detect()
        elif choice == "2":
            cmd_detect_factory()
        elif choice == "3":
            cmd_list()
        elif choice == "4":
            cmd_delete()
        elif choice == "5":
            cmd_install()
        elif choice == "6":
            cmd_load()
        elif choice == "7":
            cmd_info()
        elif choice == "8":
            cmd_send_apdu()
        elif choice == "9":
            cmd_send_secure_apdu()
        elif choice == "10":
            cmd_set_custom_key()
        elif choice == "11":
            cmd_unlock()
        elif choice == "12":
            cmd_set_default_keys()
        elif choice == "0" or choice.lower() == "q":
            print("  Bye.")
            break
        else:
            print("  Invalid choice.")


def _cli_main():
    parser = argparse.ArgumentParser(
        description="Java Card manager using gp.jar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python3 tools/jc_manager.py --detect              Detect card with default keys
  python3 tools/jc_manager.py --detect-factory       Detect card with factory keys
  python3 tools/jc_manager.py --list                 List apps on card
  python3 tools/jc_manager.py --delete 5361746F4368697000  Delete applet
  python3 tools/jc_manager.py --install applet.cap   Install CAP file
  python3 tools/jc_manager.py --info                 Show card CPLC info
  python3 tools/jc_manager.py --apdu 00A4040000      Send plaintext APDU
  python3 tools/jc_manager.py --set-default-keys     Set default keys on factory card
  python3 tools/jc_manager.py --unlock               Unlock card to default keys
  python3 tools/jc_manager.py                        Interactive mode (no args)
""")
    parser.add_argument("--detect", action="store_true", help="Detect card with default GP keys")
    parser.add_argument("--detect-factory", action="store_true", help="Detect card with Gemalto factory keys")
    parser.add_argument("--list", action="store_true", help="List apps/packages on card")
    parser.add_argument("--delete", metavar="AID", help="Delete applet/package by AID (hex)")
    parser.add_argument("--install", metavar="CAP", help="Install CAP file")
    parser.add_argument("--applet-aid", metavar="AID", help="Applet AID for --install")
    parser.add_argument("--package-aid", metavar="AID", help="Package AID for --install")
    parser.add_argument("--load", metavar="CAP", help="Load CAP file to card")
    parser.add_argument("--info", action="store_true", help="Show card CPLC info")
    parser.add_argument("--apdu", metavar="HEX", help="Send plaintext APDU")
    parser.add_argument("--secure-apdu", metavar="HEX", help="Send secure APDU")
    parser.add_argument("--key", metavar="HEX", help="Use custom key (hex, 32 chars)")
    parser.add_argument("--factory", action="store_true", help="Use factory keys")
    parser.add_argument("--set-default-keys", action="store_true", help="Set default keys on factory-key card")
    parser.add_argument("--unlock", action="store_true", help="Unlock card to default keys")
    parser.add_argument("--force", "-f", action="store_true", help="Skip confirmations in CLI mode")

    args = parser.parse_args()

    if not os.path.exists(GP_JAR):
        print(f"FATAL: gp.jar not found at {GP_JAR}")
        sys.exit(1)

    has_action = any([
        args.detect, args.detect_factory, args.list, args.delete,
        args.install, args.load, args.info, args.apdu, args.secure_apdu,
        args.set_default_keys, args.unlock,
    ])

    if not has_action:
        main()
        return

    print(f"  gp.jar: {GP_JAR}")
    _check_gp_version()

    if args.key:
        if len(args.key) != 32:
            print(f"  WARNING: Key is {len(args.key)} chars, expected 32.")
            if not args.force:
                print("  Use --force to proceed anyway.")
                sys.exit(1)
        _set_key("custom", key=args.key)
    elif args.factory:
        _set_key("factory",
                 key_enc=FACTORY_KEYS["enc"],
                 key_mac=FACTORY_KEYS["mac"],
                 key_dek=FACTORY_KEYS["dek"])

    if args.detect:
        cmd_detect()

    if args.detect_factory:
        cmd_detect_factory()

    if args.set_default_keys:
        cmd_set_default_keys()

    if args.unlock:
        cmd_unlock()

    if args.list:
        cmd_list()

    if args.delete:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        aid = args.delete
        name, _, _ = aid_info(aid)
        ascii_name = aid_to_ascii(aid)
        display = ascii_name if ascii_name != aid else name
        print(f"  Deleting {aid} ({display})...")
        output, timed_out = _run_gp(["--delete", aid, "-f"], timeout=30)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        err_code, err_msg = _parse_error(output)
        if err_code:
            print(f"  FAILED: {err_msg}")
            _print_output(output)
            sys.exit(1)
        if "Could not delete" in output:
            print(f"  FAILED: could not delete")
            _print_output(output)
            sys.exit(1)
        print(f"  Deleted {aid} successfully.")

    if args.install:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        cap = args.install
        if not os.path.exists(cap):
            print(f"  File not found: {cap}")
            sys.exit(1)
        install_args = ["--install", cap]
        if args.applet_aid:
            install_args += ["--applet", args.applet_aid]
        if args.package_aid:
            install_args += ["--package", args.package_aid]
        print(f"  Installing {cap}...")
        output, timed_out = _run_gp(install_args, timeout=120)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        _print_output(output)

    if args.load:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        cap = args.load
        if not os.path.exists(cap):
            print(f"  File not found: {cap}")
            sys.exit(1)
        print(f"  Loading {cap}...")
        output, timed_out = _run_gp(["--load", cap], timeout=120)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        _print_output(output)

    if args.info:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        output, timed_out = _run_gp(["-i"], timeout=30)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        _print_output(output)

    if args.apdu:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        output, timed_out = _run_gp(["--apdu", args.apdu], timeout=30)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        _print_output(output)

    if args.secure_apdu:
        if not _session["card_detected"]:
            print("  Card not detected. Run with --detect or --detect-factory first, or use --key/--factory.")
            sys.exit(1)
        output, timed_out = _run_gp(["--secure-apdu", args.secure_apdu], timeout=30)
        if timed_out:
            print("  Timed out.")
            sys.exit(1)
        _print_output(output)


if __name__ == "__main__":
    _cli_main()
