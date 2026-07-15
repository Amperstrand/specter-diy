#!/usr/bin/env python3
"""
Unified Smart Card Test Runner with Auto-Detection

Detects card type from structured [TEST] output and runs appropriate tests.
Works with SeedKeeper and MemoryCard/Satochip cards.

Usage:
    python3 unified_card_test.py [--build] [--flash] [--serial /dev/ttyACM1]

Output format:
    [TEST] events are parsed as JSON for structured reporting
    [BootTrace] events are logged for debugging
"""

import sys
import json
import time
import argparse
import subprocess
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import serial


class CardType(Enum):
    SEEDKEEPER = "seedkeeper"
    MEMORYCARD = "memorycard"
    SATOCHIP = "satochip"
    UNKNOWN = "unknown"


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CardInfo:
    card_type: CardType = CardType.UNKNOWN
    atr: Optional[str] = None
    applet: Optional[str] = None
    aid: Optional[str] = None
    pin_attempts_remaining: Optional[int] = None
    pin_attempts_max: Optional[int] = None
    fingerprint: Optional[str] = None
    secure_channel_established: bool = False


class TestRunner:
    def __init__(self, serial_port: str, baudrate: int = 115200):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.card_info = CardInfo()
        self.results: List[TestResult] = []
        self.test_events: List[Dict[str, Any]] = []
        self.boot_trace: List[str] = []
        
    def connect(self):
        """Connect to serial port"""
        print(f"Connecting to {self.serial_port}...")
        self.serial = serial.Serial(self.serial_port, self.baudrate, timeout=1)
        time.sleep(0.5)  # Wait for connection to stabilize
        
    def disconnect(self):
        """Disconnect from serial port"""
        if self.serial:
            self.serial.close()
            self.serial = None
            
    def read_output(self, duration: float = 30.0) -> List[str]:
        """Read serial output for specified duration"""
        lines = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if self.serial and self.serial.in_waiting > 0:
                try:
                    line = self.serial.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        lines.append(line)
                        print(f"  {line}")  # Echo to console
                except Exception as e:
                    print(f"Error reading serial: {e}")
            else:
                time.sleep(0.01)
                
        return lines
    
    def parse_test_event(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse [TEST] JSON event from line"""
        if line.startswith('[TEST] '):
            try:
                json_str = line[7:]  # Remove '[TEST] ' prefix
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"Failed to parse test event: {e}")
                return None
        return None
    
    def parse_boot_trace(self, line: str) -> Optional[str]:
        """Extract BootTrace message"""
        if '[BootTrace]' in line:
            return line
        return None
    
    def process_lines(self, lines: List[str]):
        """Process all lines, extracting test events and boot traces"""
        for line in lines:
            event = self.parse_test_event(line)
            if event:
                self.test_events.append(event)
                self._process_event(event)
            else:
                trace = self.parse_boot_trace(line)
                if trace:
                    self.boot_trace.append(trace)
    
    def _process_event(self, event: Dict[str, Any]):
        """Process a structured test event"""
        event_type = event.get('event')
        
        if event_type == 'atr':
            self.card_info.atr = event.get('atr_hex')
            # Detect SeedKeeper by ATR
            if '4A 54 61 78 43 6F 72 65' in (self.card_info.atr or ''):
                self.card_info.card_type = CardType.SEEDKEEPER
                print(f"Detected SeedKeeper by ATR")
                
        elif event_type == 'card_detected':
            card_type_str = event.get('card_type', '').lower()
            if 'seedkeeper' in card_type_str:
                self.card_info.card_type = CardType.SEEDKEEPER
            elif 'memorycard' in card_type_str:
                self.card_info.card_type = CardType.MEMORYCARD
            elif 'satochip' in card_type_str:
                self.card_info.card_type = CardType.SATOCHIP
            self.card_info.applet = event.get('applet')
            self.card_info.aid = event.get('aid')
            print(f"Card detected: {self.card_info.card_type.value}")
            
        elif event_type == 'keystore_selected':
            keystore_name = event.get('keystore', '').lower()
            if 'seedkeeper' in keystore_name:
                self.card_info.card_type = CardType.SEEDKEEPER
            elif 'memorycard' in keystore_name or 'smartcard' in keystore_name:
                self.card_info.card_type = CardType.MEMORYCARD
            print(f"Keystore selected: {keystore_name}")
            
        elif event_type == 'pin_state':
            self.card_info.pin_attempts_remaining = event.get('attempts_remaining')
            self.card_info.pin_attempts_max = event.get('attempts_max')
            print(f"PIN state: {self.card_info.pin_attempts_remaining}/{self.card_info.pin_attempts_max}")
            
        elif event_type == 'pin_result':
            success = event.get('success', False)
            error = event.get('error')
            if success:
                self.results.append(TestResult("pin_verify", True, "PIN verified successfully"))
            else:
                self.results.append(TestResult("pin_verify", False, error or "PIN verification failed"))
                
        elif event_type == 'secure_channel':
            self.card_info.secure_channel_established = event.get('established', False)
            if self.card_info.secure_channel_established:
                self.results.append(TestResult("secure_channel", True, "Secure channel established"))
            else:
                error = event.get('error', 'Unknown error')
                self.results.append(TestResult("secure_channel", False, f"Failed: {error}"))
                
        elif event_type == 'mnemonic_loaded':
            self.card_info.fingerprint = event.get('fingerprint')
            label = event.get('label', 'Unknown')
            self.results.append(TestResult("mnemonic_load", True, f"Loaded: {label}"))
            
        elif event_type == 'error':
            stage = event.get('stage', 'unknown')
            message = event.get('message', 'Unknown error')
            self.results.append(TestResult(f"error_{stage}", False, message))
    
    def run_tests(self, duration: float = 60.0) -> bool:
        """Run tests and return True if all passed"""
        print(f"\n{'='*60}")
        print("Starting test capture...")
        print(f"{'='*60}\n")
        
        lines = self.read_output(duration)
        self.process_lines(lines)
        
        return self.report()
    
    def report(self) -> bool:
        """Generate test report and return True if all passed"""
        print(f"\n{'='*60}")
        print("TEST REPORT")
        print(f"{'='*60}")
        
        print(f"\nCard Information:")
        print(f"  Type: {self.card_info.card_type.value}")
        print(f"  ATR: {self.card_info.atr or 'N/A'}")
        print(f"  Applet: {self.card_info.applet or 'N/A'}")
        print(f"  Secure Channel: {'Yes' if self.card_info.secure_channel_established else 'No'}")
        print(f"  PIN Attempts: {self.card_info.pin_attempts_remaining}/{self.card_info.pin_attempts_max}")
        print(f"  Fingerprint: {self.card_info.fingerprint or 'N/A'}")
        
        print(f"\nTest Results:")
        passed = 0
        failed = 0
        
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            symbol = "✓" if result.passed else "✗"
            print(f"  {symbol} [{status}] {result.name}: {result.message}")
            if result.passed:
                passed += 1
            else:
                failed += 1
        
        print(f"\n{'='*60}")
        print(f"Summary: {passed} passed, {failed} failed")
        print(f"{'='*60}")
        
        return failed == 0


def flash_firmware(remote: str, firmware_path: str):
    """Flash firmware using st-flash on remote machine"""
    print(f"Flashing firmware from {firmware_path}...")
    cmd = f"ssh {remote} 'st-flash --connect-under-reset --reset write {firmware_path} 0x08000000'"
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Flash failed with code {result.returncode}")
        return False
    print("Flash successful")
    return True


def reset_board(remote: str):
    """Reset the board using st-flash"""
    print("Resetting board...")
    cmd = f"ssh {remote} 'st-flash reset'"
    subprocess.run(cmd, shell=True)


def main():
    parser = argparse.ArgumentParser(description="Unified Smart Card Test Runner")
    parser.add_argument('--serial', default='/dev/ttyACM1', help='Serial port device')
    parser.add_argument('--duration', type=float, default=60.0, help='Test duration in seconds')
    parser.add_argument('--remote', default='ubuntu@192.168.13.246', help='Remote host for flashing')
    parser.add_argument('--flash', help='Flash firmware from path before testing')
    parser.add_argument('--reset', action='store_true', help='Reset board before testing')
    parser.add_argument('--build', action='store_true', help='Build firmware before flashing')
    args = parser.parse_args()
    
    # Build if requested
    if args.build:
        print("Building firmware...")
        # Add build command here
        pass
    
    # Flash if requested
    if args.flash:
        if not flash_firmware(args.remote, args.flash):
            sys.exit(1)
    
    # Reset if requested
    if args.reset:
        reset_board(args.remote)
    
    # Run tests
    runner = TestRunner(args.serial)
    try:
        runner.connect()
        success = runner.run_tests(args.duration)
        sys.exit(0 if success else 1)
    finally:
        runner.disconnect()


if __name__ == "__main__":
    main()
