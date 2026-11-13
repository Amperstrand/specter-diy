#!/usr/bin/env python3
"""HIL session runner - labgrid-orchestrated, bench-state-restoring (P6).

Runs a specter-diy HIL session on the STM32F469-Discovery bench seat:

    acquire place -> flash HIL firmware -> run tests -> RESTORE
    ccid-firmware-rs -> release place

CRITICAL BENCH RULE (owner directive 2026-11-03): the F469 runs EITHER
ccid-firmware-rs (its CCID-reader role, used by other workers) OR
specter-diy firmware - never both. The restore step below therefore runs
even when tests fail, and the place acquisition is the exclusivity mutex:
if another worker (e.g. cardbench) holds the place, this runner aborts
without touching the board.

Card swaps are MANUAL (M1 gate = one seated card). Use --pause-for-card
to stop between test groups while the operator swaps cards.

Usage:
    python3 test/integration/hil_runner.py \
        --fw build/f469/firmware-hil.bin \
        --restore-fw /path/to/ccid-firmware-rs.bin \
        [--place f469-specter-film] [--coordinator 192.168.13.208:20408] \
        [--tests test/integration/tests/test_basic.py] [--pause-for-card]

Environment (alternative to flags): LG_COORDINATOR, HIL_PLACE,
HIL_FW, HIL_RESTORE_FW.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

DEFAULT_COORDINATOR = "192.168.13.208:20408"
DEFAULT_PLACE = "f469-specter-film"


class BenchLease:
    """Acquires the labgrid place; releases in all exit paths."""

    def __init__(self, coordinator: str, place_name: str):
        self.coordinator = coordinator
        self.place_name = place_name
        self.place = None

    def __enter__(self):
        from labgrid import Client

        client = Client(self.coordinator)
        place = client.get_place(self.place_name)
        print(f"[hil] acquiring place {self.place_name} (blocks while in use)")
        place.acquire()
        self.place = place
        print(f"[hil] place acquired: {place}")
        return place

    def __exit__(self, exc_type, exc, tb):
        if self.place is not None:
            try:
                self.place.release()
                print("[hil] place released")
            except Exception as e:  # release must never mask the real error
                print(f"[hil] WARNING: place release failed: {e}")
        return False


def flash(place, image: str) -> None:
    """Flash via the ST-Link resource bound to the place."""
    if not os.path.isfile(image):
        raise FileNotFoundError(image)
    driver = place.get_driver("OpenOCDDriver", instance=None)
    print(f"[hil] flashing {image}")
    driver.flash(image)
    print("[hil] flash complete")


def reset(place) -> None:
    driver = place.get_driver("OpenOCDDriver", instance=None)
    driver.reset()


def serial_port(place) -> str:
    """The VCP serial resource on the ST-Link (UART3 routing)."""
    from labgrid.resource import NetworkSerialPort

    resource = place.get_resource(NetworkSerialPort)
    return f"{resource.host}:{resource.port}" if getattr(resource, "port", None) else resource.port


def run_tests(port: str, tests, results_dir: str) -> int:
    """Run the HIL pytest modules over the VCP, JSON-lines captured."""
    os.makedirs(results_dir, exist_ok=True)
    env = dict(os.environ)
    env["HIL_PORT"] = port
    cmd = [
        sys.executable, "-m", "pytest",
        "-v", "--tb=short",
        f"--junitxml={os.path.join(results_dir, 'hil-results.xml')}",
    ] + list(tests)
    print("[hil]", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def restore_bench(place, restore_fw: str) -> None:
    """Re-flash ccid-firmware-rs so the bench returns to its CCID role.

    Failures here are FATAL for the session exit code even if tests
    passed: an un-restored board blocks every other worker.
    """
    print(f"[hil] RESTORING bench state: {restore_fw}")
    flash(place, restore_fw)
    reset(place)
    time.sleep(2)
    print("[hil] bench restored to ccid-firmware-rs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fw", default=os.environ.get("HIL_FW"),
                    help="specter-diy HIL firmware .bin (required)")
    ap.add_argument("--restore-fw", default=os.environ.get("HIL_RESTORE_FW"),
                    help="ccid-firmware-rs image to restore (required)")
    ap.add_argument("--place", default=os.environ.get("HIL_PLACE", DEFAULT_PLACE))
    ap.add_argument("--coordinator", default=os.environ.get("LG_COORDINATOR", DEFAULT_COORDINATOR))
    ap.add_argument("--tests", nargs="+", default=["test/integration/tests/test_basic.py"])
    ap.add_argument("--results-dir", default=os.path.join(ROOT, "artifacts", "hil"))
    ap.add_argument("--pause-for-card", action="store_true",
                    help="pause between test groups for manual card swap")
    args = ap.parse_args()

    if not args.fw or not args.restore_fw:
        ap.error("--fw and --restore-fw (or HIL_FW/HIL_RESTORE_FW) are required")

    exit_code = 1
    with BenchLease(args.coordinator, args.place) as place:
        try:
            flash(place, args.fw)
            reset(place)
            port = serial_port(place)
            print(f"[hil] VCP: {port}")

            from util.uart_channel import UARTChannel

            chan = UARTChannel(port=port)
            if not chan.wait_for_ready(timeout=60):
                raise RuntimeError("device did not become ready after flash")
            chan.close()

            exit_code = 0
            for group in args.tests:
                rc = run_tests(port, [group], args.results_dir)
                exit_code = exit_code or rc
                if args.pause_for_card and group is not args.tests[-1]:
                    input("[hil] swap cards now, then press Enter to continue... ")
        except Exception as e:
            print(f"[hil] session failed: {e}")
            exit_code = 1
        finally:
            try:
                restore_bench(place, args.restore_fw)
            except Exception as e:
                print(f"[hil] FATAL: bench restore failed: {e}")
                exit_code = 2  # distinct code: board left in specter-diy state

    print(f"[hil] done, exit={exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
