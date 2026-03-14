"""
Example HIL test demonstrating the framework.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "test.hil"

from . import controller as controller_module
from .controller import HardwareController


class FakeSerial:
    def __init__(self) -> None:
        self.last_write: bytes = b""

    def write(self, data: bytes) -> int:
        self.last_write = data
        return len(data)

    def readline(self) -> bytes:
        return b"OK\n"

    def close(self) -> None:
        return None


class FakeSerialModule:
    def __init__(self, fake_serial: FakeSerial) -> None:
        self.fake_serial: FakeSerial = fake_serial

    def Serial(self, port: str, baudrate: int, timeout: int = 5) -> FakeSerial:
        _ = (port, baudrate, timeout)
        return self.fake_serial


class ExampleHILTest(unittest.TestCase):
    """Example HIL test case."""

    def test_controller_instantiation(self):
        """Test that controller can be instantiated."""
        controller = HardwareController(port="/dev/ttyACM0")
        self.assertEqual(controller.port, "/dev/ttyACM0")
        self.assertEqual(controller.baudrate, 115200)

    def test_send_command_mock(self):
        """Test send_command with mocked serial."""
        controller = HardwareController()
        fake_serial = FakeSerial()
        fake_module = FakeSerialModule(fake_serial)

        with patch.object(controller_module, "serial", fake_module, create=True):
            controller.connect()
            response = controller.send_command("ping")

        self.assertEqual(response, "OK")
