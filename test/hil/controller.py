"""
Hardware controller for HIL testing.

Uses UART3 VCP for control channel and ST-Link for lifecycle operations.
"""
import subprocess
from typing import Protocol, cast

try:
    import serial
except ImportError:
    serial = None  # type: ignore


class SerialLike(Protocol):
    def write(self, data: bytes) -> int:
        ...

    def readline(self) -> bytes:
        ...

    def close(self) -> None:
        ...


class HardwareController:
    """Controls Specter-DIY hardware for HIL testing."""

    def __init__(self, port: str = "/dev/ttyACM0", baudrate: int = 115200):
        self.port: str = port
        self.baudrate: int = baudrate
        self._serial: SerialLike | None = None

    def connect(self) -> None:
        """Connect to hardware via UART3 VCP."""
        if serial is None:
            raise RuntimeError("pyserial is required for hardware connection")
        self._serial = cast(
            SerialLike,
            cast(object, serial.Serial(self.port, self.baudrate, timeout=5)),
        )

    def disconnect(self) -> None:
        """Disconnect from hardware."""
        if self._serial:
            self._serial.close()
            self._serial = None

    def send_command(self, command: str) -> str:
        """Send command and receive response."""
        if not self._serial:
            raise RuntimeError("Not connected to hardware")
        _ = self._serial.write((command + "\n").encode())
        response = self._serial.readline().decode().strip()
        return response

    def reset(self) -> None:
        """Reset device via ST-Link."""
        _ = subprocess.run(["st-info", "--reset"], check=True)

    def flash(self, firmware_path: str) -> None:
        """Flash firmware via ST-Link."""
        _ = subprocess.run(["st-flash", "write", firmware_path, "0x08000000"], check=True)
