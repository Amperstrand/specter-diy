"""
UARTChannel - Host-side serial communication for HIL testing.

This is the serial/UART equivalent of TCPSocket from controller.py.
Provides communication with the device over USB Virtual COM Port (VCP)
via UART3 (PB10/PB11) on the STM32.

Line protocol:
    - Send: COMMAND\\n
    - Receive: OK:data\\n or ERROR:message\\n
"""

import time
from typing import Any

try:
    import serial
    from serial import SerialException
except ImportError:
    serial = None  # type: ignore[misc,assignment]
    SerialException = Exception  # type: ignore[misc,assignment]


class UARTChannel:
    """Serial communication channel for HIL testing over UART/VCP."""

    _port: str
    _baudrate: int
    _timeout: float
    _serial: Any

    def __init__(self, port: str = '/dev/ttyACM0', baudrate: int = 115200, timeout: float = 5):
        """
        Initialize UART channel configuration.
        
        Args:
            port: Serial port path (e.g., '/dev/ttyACM0', '/dev/ttyUSB0', 'COM3')
            baudrate: Baud rate (default 115200 for UART3 VCP)
            timeout: Default read timeout in seconds
        """
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial = None

    def open(self) -> None:
        """
        Open serial port connection.
        
        Raises:
            SerialException: If port cannot be opened
            ImportError: If pyserial is not installed
        """
        if serial is None:
            raise ImportError("pyserial is required for UART communication. Install with: pip install pyserial")
        
        self._serial = serial.Serial(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout
        )

    def close(self) -> None:
        """Close serial port connection."""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def send(self, data: str) -> None:
        """
        Send command string over UART.
        
        Automatically appends '\\n' terminator.
        
        Args:
            data: Command string to send (without terminator)
            
        Raises:
            SerialException: If write fails or port not open
        """
        if self._serial is None:
            raise SerialException("Serial port not open")
        
        if not data.endswith('\n'):
            data = data + '\n'
        
        self._serial.write(data.encode('utf-8'))

    def readline(self, timeout: float | None = None) -> bytes:
        """
        Read one line response (up to '\\n').
        
        Args:
            timeout: Read timeout in seconds (uses default if None)
            
        Returns:
            Line data including '\\n' terminator, or empty bytes on timeout
        """
        if self._serial is None:
            raise SerialException("Serial port not open")
        
        # Use provided timeout or default
        effective_timeout = timeout if timeout is not None else self._timeout
        
        # Manual timeout handling like TCPSocket
        res = b""
        t0 = time.time()
        
        while b'\n' not in res:
            if time.time() - t0 > effective_timeout:
                break
            
            try:
                # Read available bytes
                if self._serial.in_waiting > 0:
                    chunk = self._serial.read(self._serial.in_waiting)
                    res += chunk
                else:
                    time.sleep(0.01)  # Small sleep to avoid busy-waiting
            except Exception:
                time.sleep(0.01)
        
        return res

    def query(self, command: str, timeout: float = 5) -> bytes:
        """
        Send command and read response (convenience wrapper).
        
        Args:
            command: Command string to send
            timeout: Read timeout in seconds
            
        Returns:
            Response line (should be OK:data or ERROR:message)
        """
        self.send(command)
        return self.readline(timeout=timeout)

    def drain(self) -> None:
        """
        Read and discard any buffered data.
        
        Used for synchronization after device reset to clear
        any stale data in the receive buffer.
        """
        if self._serial is not None and self._serial.is_open:
            self._serial.reset_input_buffer()

    def wait_for_ready(self, timeout: float = 30) -> bool:
        """
        Poll with TEST_STATUS until device responds with OK.
        
        Used after device reset to wait for firmware initialization.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if device responded with OK, False on timeout
        """
        t0 = time.time()
        
        # Drain any stale data first
        self.drain()
        
        while time.time() - t0 < timeout:
            try:
                response = self.query("TEST_STATUS", timeout=1)
                if response.startswith(b"OK:"):
                    return True
            except Exception:
                pass
            
            time.sleep(0.5)
        
        return False

    def __enter__(self) -> 'UARTChannel':
        """Context manager entry - opens the port."""
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - closes the port."""
        self.close()
