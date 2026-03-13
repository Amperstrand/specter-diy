"""
STLinkManager - Hardware Lifecycle Control for Specter-DIY

Provides low-level hardware control via ST-Link:
- Flash/reset/erase using st-flash (primary tool)
- Memory access via OpenOCD (for marker system)
- Connection detection via st-info

Usage:
    mgr = STLinkManager()
    mgr.flash('bin/firmware.bin')
    mgr.reset()
    markers = mgr.read_memory('0x20002000', 4)
"""

import subprocess
import time
import re


class STLinkManager:
    """
    Hardware lifecycle control via ST-Link debugger.
    
    Uses st-flash for flash/reset/erase operations (primary).
    Uses OpenOCD for memory reads (halt/resume/memory access).
    """
    
    def __init__(
        self,
        st_flash_path: str = 'st-flash',
        st_info_path: str = 'st-info',
        openocd_path: str = 'openocd',
        openocd_interface: str = 'interface/stlink.cfg',
        openocd_target: str = 'target/stm32f4x.cfg',
        flash_timeout: int = 60,
        boot_timeout: int = 10
    ):
        """
        Initialize STLinkManager with configurable tool paths.
        
        Args:
            st_flash_path: Path to st-flash binary
            st_info_path: Path to st-info binary
            openocd_path: Path to openocd binary
            openocd_interface: OpenOCD interface config file
            openocd_target: OpenOCD target config file
            flash_timeout: Timeout in seconds for flash operations
            boot_timeout: Timeout in seconds for boot detection
        """
        self.st_flash_path = st_flash_path
        self.st_info_path = st_info_path
        self.openocd_path = openocd_path
        self.openocd_interface = openocd_interface
        self.openocd_target = openocd_target
        self.flash_timeout = flash_timeout
        self.boot_timeout = boot_timeout
    
    def flash(
        self, 
        firmware_path: str, 
        address: str = '0x08000000'
    ) -> tuple[bool, str]:
        """
        Flash firmware binary to device using st-flash.
        
        Args:
            firmware_path: Path to firmware binary file
            address: Flash address (default: 0x08000000 for STM32)
            
        Returns:
            Tuple of (success, output_message)
        """
        cmd = [
            self.st_flash_path,
            '--reset',
            'write',
            firmware_path,
            address
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.flash_timeout
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, f"Flash operation timed out after {self.flash_timeout}s"
        except FileNotFoundError:
            return False, f"st-flash not found at {self.st_flash_path}"
        except Exception as e:
            return False, str(e)
    
    def reset(self) -> tuple[bool, str]:
        """
        Reset the device using st-flash.
        
        Returns:
            Tuple of (success, output_message)
        """
        cmd = [self.st_flash_path, 'reset']
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "Reset operation timed out"
        except FileNotFoundError:
            return False, f"st-flash not found at {self.st_flash_path}"
        except Exception as e:
            return False, str(e)
    
    def erase(self) -> tuple[bool, str]:
        """
        Erase entire flash memory using st-flash.
        
        Returns:
            Tuple of (success, output_message)
        """
        cmd = [self.st_flash_path, 'erase']
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "Erase operation timed out"
        except FileNotFoundError:
            return False, f"st-flash not found at {self.st_flash_path}"
        except Exception as e:
            return False, str(e)
    
    def halt(self) -> tuple[bool, str]:
        """
        Halt the CPU using OpenOCD.
        
        Returns:
            Tuple of (success, output_message)
        """
        ocd_script = """
init
halt
shutdown
"""
        cmd = [
            self.openocd_path,
            '-f', self.openocd_interface,
            '-f', self.openocd_target,
            '-c', ocd_script
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "Halt operation timed out"
        except FileNotFoundError:
            return False, f"openocd not found at {self.openocd_path}"
        except Exception as e:
            return False, str(e)
    
    def resume(self) -> tuple[bool, str]:
        """
        Resume the CPU from halt using OpenOCD.
        
        Returns:
            Tuple of (success, output_message)
        """
        ocd_script = """
init
halt
resume
shutdown
"""
        cmd = [
            self.openocd_path,
            '-f', self.openocd_interface,
            '-f', self.openocd_target,
            '-c', ocd_script
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
                
        except subprocess.TimeoutExpired:
            return False, "Resume operation timed out"
        except FileNotFoundError:
            return False, f"openocd not found at {self.openocd_path}"
        except Exception as e:
            return False, str(e)
    
    def is_connected(self) -> tuple[bool, str]:
        """
        Check if ST-Link is connected to a device using st-info.
        
        Returns:
            Tuple of (connected, info_message)
        """
        cmd = [self.st_info_path, '--probe']
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # st-info --probe returns 0 if device found
            if result.returncode == 0 and result.stdout.strip():
                return True, result.stdout
            else:
                return False, result.stderr or "No ST-Link device found"
                
        except subprocess.TimeoutExpired:
            return False, "Probe operation timed out"
        except FileNotFoundError:
            return False, f"st-info not found at {self.st_info_path}"
        except Exception as e:
            return False, str(e)
    
    def read_memory(
        self, 
        address: str, 
        word_count: int = 4
    ) -> tuple[bool, str, list[int] | None]:
        """
        Read memory words using OpenOCD mdw command.
        
        Used for reading firmware memory markers for debugging.
        
        Args:
            address: Memory address to read (hex string like '0x20002000')
            word_count: Number of 32-bit words to read
            
        Returns:
            Tuple of (success, raw_output, list_of_word_values)
        """
        ocd_script = f"""
init
halt
mdw {address} {word_count}
shutdown
"""
        cmd = [
            self.openocd_path,
            '-f', self.openocd_interface,
            '-f', self.openocd_target,
            '-c', ocd_script
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout
            
            if result.returncode != 0:
                return False, result.stderr or output, None
            
            # Parse OpenOCD output like:
            # 0x20002000: 534b5052 00001050 00000001 00000001
            pattern = rf'{address}:\s+([0-9a-fA-F]+)' + r'\s+([0-9a-fA-F]+)' * (word_count - 1)
            match = re.search(pattern, output)
            
            if match:
                words = [int(match.group(i + 1), 16) for i in range(word_count)]
                return True, output, words
            else:
                return False, f"Could not parse memory output: {output}", None
                
        except subprocess.TimeoutExpired:
            return False, "Memory read operation timed out", None
        except FileNotFoundError:
            return False, f"openocd not found at {self.openocd_path}", None
        except Exception as e:
            return False, str(e), None
    
    def wait_for_boot(
        self, 
        port: str, 
        timeout: float | None = None,
        baudrate: int = 115200
    ) -> tuple[bool, str]:
        """
        Wait for device UART to respond after reset.
        
        Minimal serial I/O for boot detection only.
        Full UART communication is handled by VCPReader (Task 5).
        
        Args:
            port: Serial port device path (e.g., '/dev/ttyACM0')
            timeout: Maximum time to wait for boot (default: self.boot_timeout)
            baudrate: Serial baud rate
            
        Returns:
            Tuple of (booted, message)
        """
        if timeout is None:
            timeout = float(self.boot_timeout)
            
        try:
            import serial
        except ImportError:
            return False, "pyserial not installed - required for wait_for_boot"
        
        start_time = time.time()
        
        try:
            # Open serial port
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1.0
            )
            
            # Clear any pending data
            ser.reset_input_buffer()
            
            # Wait for any output from device (indicates boot)
            while time.time() - start_time < timeout:
                if ser.in_waiting > 0:
                    # Read and discard - we just need to know device is alive
                    data = ser.read(ser.in_waiting)
                    ser.close()
                    return True, f"Device booted, received {len(data)} bytes"
                
                time.sleep(0.1)
            
            ser.close()
            return False, f"Timeout waiting for boot after {timeout}s"
            
        except Exception as e:
            return False, f"Serial error: {e}"


# Convenience function for quick flashing
def flash_firmware(firmware_path: str, address: str = '0x08000000') -> tuple[bool, str]:
    """
    Quick flash helper function.
    
    Args:
        firmware_path: Path to firmware binary
        address: Flash address
        
    Returns:
        Tuple of (success, message)
    """
    mgr = STLinkManager()
    return mgr.flash(firmware_path, address)
