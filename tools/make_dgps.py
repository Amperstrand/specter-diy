#!/usr/bin/env python3
"""Download CAP files, convert to DGP, and verify checksums.

Reads applets.yaml and for each entry:
  1. Downloads CAP file (if not cached)
  2. Verifies CAP SHA256
  3. Converts CAP to DGP via tools/cap_to_dgp.py
  4. Verifies DGP SHA256

Usage:
    python3 tools/make_dgps.py              # process all applets
    python3 tools/make_dgps.py seedkeeper   # process specific applet
    python3 tools/make_dgps.py --verify     # only verify existing DGP files
"""

import sys
import os
import hashlib
import urllib.request
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
APPLETS_YAML = os.path.join(ROOT_DIR, "applets.yaml")
CACHE_DIR = os.path.join(ROOT_DIR, "bin", "applets")
CAP_TO_DGP = os.path.join(SCRIPT_DIR, "cap_to_dgp.py")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    print("  Downloading %s ..." % os.path.basename(dest))
    urllib.request.urlretrieve(url, dest)


def convert_cap_to_dgp(cap_path, dgp_path):
    import subprocess
    result = subprocess.run(
        [sys.executable, CAP_TO_DGP, cap_path, dgp_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("  ERROR: cap_to_dgp.py failed:")
        print(result.stderr)
        return False
    print(result.stdout.rstrip())
    return True


def process_applet(name, entry, verify_only=False):
    print()
    print("=== %s (%s) ===" % (entry.get("name", name), entry.get("version", "?")))

    if entry.get("cap_url", "TBD") == "TBD":
        print("  SKIPPED: no download URL configured")
        return True

    cap_sha = entry.get("cap_sha256")
    dgp_sha = entry.get("dgp_sha256")
    if not cap_sha or cap_sha == "TBD" or not dgp_sha or dgp_sha == "TBD":
        print("  SKIPPED: checksums not configured")
        return True

    os.makedirs(CACHE_DIR, exist_ok=True)
    cap_path = os.path.join(CACHE_DIR, "%s.cap" % name)
    dgp_path = os.path.join(CACHE_DIR, "%s.dgp" % name)

    if verify_only:
        if not os.path.isfile(dgp_path):
            print("  FAIL: %s not found" % dgp_path)
            return False
        actual = sha256_file(dgp_path)
        if actual == dgp_sha:
            print("  OK: %s SHA256 verified" % os.path.basename(dgp_path))
            return True
        else:
            print("  FAIL: %s SHA256 mismatch" % os.path.basename(dgp_path))
            print("    expected: %s" % dgp_sha)
            print("    actual:   %s" % actual)
            return False

    if not os.path.isfile(cap_path):
        download(entry["cap_url"], cap_path)

    actual_cap = sha256_file(cap_path)
    if actual_cap != cap_sha:
        print("  FAIL: CAP SHA256 mismatch")
        print("    expected: %s" % cap_sha)
        print("    actual:   %s" % actual_cap)
        return False
    print("  OK: CAP SHA256 verified (%d bytes)" % os.path.getsize(cap_path))

    if not convert_cap_to_dgp(cap_path, dgp_path):
        return False

    actual_dgp = sha256_file(dgp_path)
    if actual_dgp != dgp_sha:
        print("  FAIL: DGP SHA256 mismatch")
        print("    expected: %s" % dgp_sha)
        print("    actual:   %s" % actual_dgp)
        return False
    print("  OK: DGP SHA256 verified (%d bytes)" % os.path.getsize(dgp_path))

    print("  Ready: mpremote cp %s :%s" % (dgp_path, entry.get("dgp_path", "/flash/gp/")))
    return True


def main():
    if not os.path.isfile(APPLETS_YAML):
        print("ERROR: %s not found" % APPLETS_YAML)
        sys.exit(1)

    with open(APPLETS_YAML) as f:
        applets = yaml.safe_load(f)

    verify_only = "--verify" in sys.argv
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]

    if targets:
        entries = {k: v for k, v in applets.items() if k in targets}
    else:
        entries = applets

    if not entries:
        print("No applets found")
        sys.exit(1)

    all_ok = True
    for name, entry in entries.items():
        if not process_applet(name, entry, verify_only):
            all_ok = False

    print()
    if all_ok:
        print("All applets OK")
    else:
        print("Some applets FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
