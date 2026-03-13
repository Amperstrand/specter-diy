#!/usr/bin/env python3
import argparse
import sys
if sys.implementation.name == 'micropython':
    print("This file should run with python3, not micropython!")
    sys.exit(1)
import os
from util.controller import sim, core

# Argument parser
parser = argparse.ArgumentParser(description='Run integration tests against SimController or HardwareController')
parser.add_argument('--hardware', '-H', action='store_true', help='Use HardwareController instead of SimController')
parser.add_argument('--port', '-p', type=str, default='/dev/ttyACM0', help='Serial port for UART3 VCP (required with --hardware)')
parser.add_argument('--flash', '-f', type=str, default=None, help='Optional: flash firmware before testing')
parser.add_argument('--hard-reset', '-r', action='store_true', help='Use ST-Link hard reset between tests instead of software reset')
args = parser.parse_args()

# Hardware controller instance
hw = None

def run_hardware_tests():
    """Run tests against real hardware using HardwareController."""
    from util.hardware_controller import HardwareController
    import subprocess

    # Flash firmware if specified
    if args.flash:
        print(f"Flashing firmware: {args.flash}")
        try:
            result = subprocess.run(['st-flash', 'write', args.flash, '0x8000000'], check=True)
            print("Firmware flashed successfully")
            if not args.hard_reset:
                print("Note: --flash without --hard-reset may not boot properly. Consider using --hard-reset.")
        except subprocess.CalledProcessError as e:
            print(f"Flash failed: {e}")
            return False

    # Create HardwareController instance
    try:
        hw = HardwareController(port=args.port)
    except Exception as e:
        print(f"Failed to create HardwareController: {e}")
        return False

    # Monkey-patch the module-level 'sim' variable
    # This allows tests to import 'sim' and get HardwareController instead
    from util import controller
    controller.sim = hw
    print(f"Running tests against hardware on port {args.port}")

    # Run tests using the patched 'sim'
    try:
        hw.start()
        hw.load()
        unittest.main('tests', exit=False)
        return True
    except Exception as e:
        print(f"Test execution failed: {e}")
        return False
    finally:
        # Cleanup
        try:
            if hw is not None:
                hw.shutdown()
        except Exception:
            pass
        # Restore original sim if needed
        from util import controller
        if 'sim' in dir(controller):
            delattr(controller, 'sim')
        controller.core = None

def main():
    if args.hardware:
        success = run_hardware_tests()
        sys.exit(0 if success else 1)
    else:
        # Original behavior: run tests against simulator
        sim.start()  # start simulator
        try:
            sim.load()  # unlock, load mnemonic etc
            unittest.main('tests')
        finally:
            sim.shutdown()

if __name__ == '__main__':
    main()
