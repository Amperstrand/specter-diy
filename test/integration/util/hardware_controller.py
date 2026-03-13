"""
HardwareController - Main integration piece for HIL testing.

Combines STLinkManager, UARTChannel, and CommandMapper to provide
a BaseController implementation for real hardware testing.

This controller mirrors SimController's behavior but uses physical
hardware via ST-Link (SWD) and UART3 VCP.
"""

import time
from typing import Union

from util.base_controller import BaseController
from util.stlink_manager import STLinkManager
from util.uart_channel import UARTChannel
from util.protocol import CommandMapper, CommandMapperError


class HardwareController(BaseController):
    """
    Hardware controller for HIL testing via ST-Link and UART.
    
    Composes three components:
    - STLinkManager: Hardware lifecycle (reset, flash, connection check)
    - UARTChannel: Serial communication over UART3 VCP
    - CommandMapper: Protocol translation (USB/GUI → TestMode)
    
    Usage:
        hw = HardwareController()
        hw.start()
        hw.load()
        response = hw.query(b"xpub m/44h/1h/0h")
        hw.shutdown()
    """
    
    def __init__(
        self,
        port: str = '/dev/ttyACM0',
        baudrate: int = 115200,
        stflash_path: str = 'st-flash'
    ):
        """
        Initialize HardwareController with configurable settings.
        
        Args:
            port: Serial port device path (e.g., '/dev/ttyACM0')
            baudrate: UART baud rate (default 115200 for UART3 VCP)
            stflash_path: Path to st-flash binary
        """
        # Call parent constructor
        super().__init__()
        
        # Compose components
        self._stlink = STLinkManager(st_flash_path=stflash_path)
        self._uart = UARTChannel(port=port, baudrate=baudrate)
        self._mapper = CommandMapper()
        
        # State tracking
        self._started = False
        self._loaded = False
    
    def start(self) -> None:
        """
        Start the hardware controller.
        
        1. Verify ST-Link connection via STLinkManager.is_connected()
        2. Reset the device via STLinkManager.reset()
        3. Wait for boot via UARTChannel.wait_for_ready()
        """
        # 1. Verify ST-Link connection
        connected, msg = self._stlink.is_connected()
        if not connected:
            raise RuntimeError(f"ST-Link not connected: {msg}")
        
        # 2. Reset the device
        success, msg = self._stlink.reset()
        if not success:
            raise RuntimeError(f"Failed to reset device: {msg}")
        
        # 3. Wait for boot - open UART temporarily for boot detection
        # UARTChannel.wait_for_ready() handles this internally
        self._uart.open()
        try:
            ready = self._uart.wait_for_ready(timeout=30)
            if not ready:
                raise RuntimeError("Device did not boot within timeout")
        finally:
            # Close after boot detection - load() will reopen
            self._uart.close()
        
        self._started = True
    
    def load(self) -> None:
        """
        Load controller state and prepare for queries.
        
        1. Open UART channel
        2. Drain buffered data
        3. Send TEST_STATUS to verify responsive
        4. Send TEST_PIN to unlock
        5. Setup test state (matching SimController.load())
        """
        if not self._started:
            raise RuntimeError("Controller not started - call start() first")
        
        # 1. Open UART channel
        self._uart.open()
        
        # 2. Drain any buffered data
        self._uart.drain()
        
        # 3. Verify device is responsive
        response = self._uart.query("TEST_STATUS", timeout=5)
        if not response.startswith(b"OK:"):
            self._uart.close()
            raise RuntimeError(f"Device not responsive: {response}")
        
        # 4. Send TEST_PIN to unlock (matching SimController's PIN entry)
        # SimController sends empty string twice for PIN selection/confirmation
        # In TestMode, we use TEST_PIN command
        response = self._uart.query("TEST_PIN:", timeout=5)
        # Don't fail on PIN response - device may be in different state
        
        # 5. Setup test state (matching SimController.load())
        # SimController sends: "", "", 1, "abandon "*11+"about" for recovery
        # In TestMode, we'd need TEST_RESTORE command (if available)
        # For now, assume device is pre-configured or use mnemonic restore
        
        self._loaded = True
    
    def shutdown(self) -> None:
        """
        Shutdown the controller cleanly.
        
        1. Close UART channel
        2. Optionally halt device
        """
        # 1. Close UART channel
        if self._uart is not None:
            try:
                self._uart.close()
            except Exception:
                pass
        
        # 2. Optionally halt device (not required for clean shutdown)
        # Halt is more for debugging - skip for normal operation
        
        self._started = False
        self._loaded = False
    
    def query(
        self,
        data: Union[str, bytes],
        commands: list[Union[str, bytes, bool, int, None]] = []
    ) -> bytes:
        """
        Send data to the hardware and receive response.
        
        Mirrors SimController.query() behavior:
        1. Map data bytes via CommandMapper.map_usb_command()
        2. Send via UARTChannel.send()
        3. Read response via UARTChannel.readline()
        4. For each GUI command, map and send
        5. If commands sent, read final response
        6. Parse response via CommandMapper.parse_response()
        7. Return bytes matching SimController format
        
        Args:
            data: Data to send (str or bytes)
            commands: Optional list of GUI commands (for confirmations)
            
        Returns:
            Response as bytes (matching SimController format)
        """
        if not self._loaded:
            raise RuntimeError("Controller not loaded - call load() first")
        
        # Convert str to bytes if needed (matching SimController)
        if isinstance(data, str):
            data = data.encode()
        
        # Ensure proper line ending (matching SimController)
        if data[-1:] not in b"\r\n":
            data = data + b"\r\n"
        
        try:
            # 1. Map USB command to TestMode command
            testmode_cmd = self._mapper.map_usb_command(data)
            
            # 2. Send via UART
            self._uart.send(testmode_cmd)
            
            # 3. Read response (ACK-like behavior from TestMode)
            response = self._uart.readline(timeout=5)
            
            # 4. For each GUI command, map and send
            for command in commands:
                # Map GUI command to TestMode command
                gui_cmd = self._mapper.map_gui_command(command)
                self._uart.send(gui_cmd)
                time.sleep(0.3)  # Match SimController timing
            
            # 5. If commands sent, read final response
            if commands:
                response = self._uart.readline(timeout=5)
            
            # 6. Parse response and return bytes
            response_str = response.decode('utf-8', errors='replace').strip()
            return self._mapper.parse_response(response_str)
            
        except CommandMapperError as e:
            # Return error in expected format
            return f"error: {e}".encode('utf-8')
        except Exception as e:
            # Handle timeout with soft reset + retry once
            if "timeout" in str(e).lower():
                # Soft reset and retry
                self.reset(hard=False)
                try:
                    # Retry the query
                    testmode_cmd = self._mapper.map_usb_command(data)
                    self._uart.send(testmode_cmd)
                    response = self._uart.readline(timeout=5)
                    
                    for command in commands:
                        gui_cmd = self._mapper.map_gui_command(command)
                        self._uart.send(gui_cmd)
                        time.sleep(0.3)
                    
                    if commands:
                        response = self._uart.readline(timeout=5)
                    
                    response_str = response.decode('utf-8', errors='replace').strip()
                    return self._mapper.parse_response(response_str)
                except Exception:
                    pass
            
            # Return error in expected format
            return f"error: {e}".encode('utf-8')
    
    def reset(self, hard: bool = False) -> None:
        """
        Reset the device.
        
        Args:
            hard: If True, use STLinkManager.reset() (hardware reset)
                  If False, use TEST_RESET UART command (soft reset)
        """
        if hard:
            # Hard reset via ST-Link
            success, msg = self._stlink.reset()
            if not success:
                raise RuntimeError(f"Hard reset failed: {msg}")
            
            # Wait for boot after hard reset
            if self._uart is not None:
                try:
                    self._uart.close()
                except Exception:
                    pass
            
            self._uart.open()
            ready = self._uart.wait_for_ready(timeout=30)
            if not ready:
                raise RuntimeError("Device did not boot after hard reset")
        else:
            # Soft reset via TEST_RESET UART command
            if self._uart is not None:
                try:
                    response = self._uart.query("TEST_RESET", timeout=5)
                    # Wait briefly for reset to complete
                    time.sleep(1)
                    # Wait for device to be ready again
                    ready = self._uart.wait_for_ready(timeout=10)
                    if not ready:
                        raise RuntimeError("Device did not respond after soft reset")
                except Exception as e:
                    raise RuntimeError(f"Soft reset failed: {e}")


# Module-level singleton (matching SimController pattern)
hw = HardwareController()
