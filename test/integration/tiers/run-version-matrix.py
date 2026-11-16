#!/usr/bin/env python3
"""Version matrix runner — test the tiered harness against every deployed
Satochip version and produce a compatibility matrix.

Usage:
    python3 test/integration/tiers/run-version-matrix.py [--quick]
    python3 test/integration/tiers/run-version-matrix.py --versions sato-v0.14-0.2,sato-v0.16-0.1

Produces: a markdown table with pass/fail/skip per version per test,
plus a summary of breaking-change boundaries.
"""
import os
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# Versions to test (must have readers deployed in pcscd)
ALL_VERSIONS = [
    "sato-v0.11",
    "sato-v0.12",
    "sato-v0.14-0.2",
    "sato-v0.15-0.0",
    "sato-v0.15-0.1",
    "sato-v0.16-0.1",
]

TESTS = [
    "test_satochip_versions.py::TestSatochipVersion::test_get_status_reports_version",
    "test_satochip_versions.py::TestSatochipVersion::test_secure_channel_opens",
    "test_satochip_versions.py::TestSatochipVersion::test_satochip_pin_via_sc",
]


def check_reader_available(version):
    """Check if the version's reader is deployed in pcscd."""
    try:
        from smartcard.System import readers
        for r in readers():
            if version.replace("sato-", "Farm sato-") in str(r) and "00 00" in str(r):
                return True
            # also check jCardSim variants
            if version == "sato-v0.16-0.1" and "v016" in str(r) and "00 00" in str(r):
                return True
    except Exception:
        pass
    return False


def run_test(version, test):
    """Run a single test against a specific version. Returns pass/fail/skip."""
    cmd = [
        sys.executable, "-m", "pytest",
        os.path.join(HERE, test),
        "--backend=vpcd",
        f"--applet-version={version}",
        "-q", "--tb=line", "-p", "no:cacheprovider",
    ]
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                            cwd=repo_root)
    output = result.stdout + result.stderr
    if "passed" in output and "failed" not in output:
        return "PASS"
    elif "skipped" in output and "passed" not in output:
        return "SKIP"
    elif "failed" in output or "error" in output.lower():
        return "FAIL"
    return "SKIP"


def main():
    versions = sys.argv[sys.argv.index("--versions") + 1].split(",") if "--versions" in sys.argv else ALL_VERSIONS
    quick = "--quick" in sys.argv
    if quick:
        tests = TESTS[:1]  # just GET_STATUS
    else:
        tests = TESTS

    # Filter to available readers
    available = [v for v in versions if check_reader_available(v)]
    unavailable = [v for v in versions if v not in available]

    print(f"Testing {len(available)} versions × {len(tests)} tests\n")

    results = {}
    for version in available:
        results[version] = {}
        for test in tests:
            test_name = test.split("::")[-1]
            outcome = run_test(version, test)
            results[version][test_name] = outcome
            symbol = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[outcome]
            print(f"  {symbol} {version:20s} {test_name}")

    # Produce markdown matrix
    print("\n## Satochip Version Compatibility Matrix\n")
    header = "| Version | " + " | ".join(t.split("::")[-1] for t in tests) + " |"
    separator = "|---" * (len(tests) + 1) + "|"
    print(header)
    print(separator)
    for version in available:
        row = f"| {version} "
        for test in tests:
            test_name = test.split("::")[-1]
            symbol = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[results[version][test_name]]
            row += f"| {symbol} "
        row += "|"
        print(row)

    if unavailable:
        print(f"\n⚠️  Not deployed: {', '.join(unavailable)} (deploy with farm scripts)")

    # Breaking-change boundaries
    fails = [v for v in available if any(results[v][t.split("::")[-1]] == "FAIL" for t in tests)]
    if fails:
        print(f"\n❌ Breaking changes detected at: {', '.join(fails)}")
    else:
        print(f"\n✅ All {len(available)} versions pass the compatibility suite")

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
