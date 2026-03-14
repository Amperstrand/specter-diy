"""
Host communication module tests using mocks for hardware dependencies.
"""
import asyncio
import importlib
import io
import os
import sys
import types
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

# Mock hardware modules before importing
_ = sys.modules.setdefault("pyb", MagicMock())
_ = sys.modules.setdefault("machine", MagicMock())
_ = sys.modules.setdefault("usb", MagicMock())
_ = sys.modules.setdefault("lvgl", MagicMock())
_ = sys.modules.setdefault("ucryptolib", MagicMock())
_ = sys.modules.setdefault("uhashlib", MagicMock())
_ = sys.modules.setdefault("microur", MagicMock())
_ = sys.modules.setdefault("microur.decoder", MagicMock())
_ = sys.modules.setdefault("microur.util", MagicMock())
_ = sys.modules.setdefault("qrencoder", MagicMock())

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")

# Add src directory to path for imports
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

def _clear_hosts_modules():
    """Clear any previously imported hosts modules."""
    for key in list(sys.modules.keys()):
        if key == "hosts" or key.startswith("hosts."):
            _ = sys.modules.pop(key)


def _create_mock_platform():
    """Create a mock platform module."""
    platform = types.ModuleType("platform")
    setattr(platform, "simulator", False)
    setattr(platform, "usb_connected", MagicMock(return_value=True))
    setattr(platform, "enable_usb", MagicMock())
    setattr(platform, "disable_usb", MagicMock())
    setattr(platform, "delete_recursively", MagicMock())
    setattr(platform, "fpath", lambda x: x)
    setattr(platform, "file_exists", MagicMock(return_value=False))
    setattr(platform, "maybe_mkdir", MagicMock())
    setattr(platform, "sync", MagicMock())
    
    # Mock sdcard
    sdcard = MagicMock()
    sdcard.is_present = True
    sdcard.mount = MagicMock()
    sdcard.unmount = MagicMock()
    setattr(platform, "sdcard", sdcard)
    
    return platform


def _create_mock_pyb():
    """Create a mock pyb module with USB_VCP and UART."""
    pyb = types.ModuleType("pyb")
    
    # USB_VCP mock
    class MockUSB_VCP:
        RTS = 1
        CTS = 2
        
        def __init__(self):
            self._buffer = b""
            self._write_buffer = b""
        
        def init(self, flow=0):
            pass
        
        def read(self, n=64):
            result = self._buffer[:n]
            self._buffer = self._buffer[n:]
            return result if result else None
        
        def write(self, data):
            if isinstance(data, str):
                data = data.encode()
            self._write_buffer += data
            return len(data)
        
        def set_rx_data(self, data):
            """Helper to set data to be read."""
            if isinstance(data, str):
                data = data.encode()
            self._buffer = data
    
    setattr(pyb, "USB_VCP", MockUSB_VCP)
    
    # UART mock
    class MockUART:
        def __init__(self, port, baudrate, read_buf_len=256):
            self.port = port
            self.baudrate = baudrate
            self._buffer = b""
            self._read_buf_len = read_buf_len
        
        def init(self, baudrate=None, read_buf_len=None):
            if baudrate:
                self.baudrate = baudrate
            if read_buf_len:
                self._read_buf_len = read_buf_len
        
        def deinit(self):
            pass
        
        def any(self):
            return len(self._buffer)
        
        def read(self):
            result = self._buffer
            self._buffer = b""
            return result
        
        def write(self, data):
            if isinstance(data, str):
                data = data.encode()
            return len(data)
        
        def set_rx_data(self, data):
            if isinstance(data, str):
                data = data.encode()
            self._buffer = data
    
    setattr(pyb, "UART", MockUART)
    
    # Pin mock
    class MockPin:
        OUT = 1
        IN = 0
        
        def __init__(self, pin, mode=0):
            self.pin = pin
            self.mode = mode
            self._state = False
        
        def on(self):
            self._state = True
        
        def off(self):
            self._state = False
        
        def value(self, v=None):
            if v is not None:
                self._state = bool(v)
            return self._state
    
    setattr(pyb, "Pin", MockPin)
    
    # LED mock
    class MockLED:
        def __init__(self, n):
            self.n = n
            self._state = False
        
        def on(self):
            self._state = True
        
        def off(self):
            self._state = False
    
    setattr(pyb, "LED", MockLED)
    
    return pyb


def _create_mock_errors():
    """Create a mock errors module."""
    errors = types.ModuleType("errors")
    
    class BaseError(Exception):
        NAME = "Base error"
    
    setattr(errors, "BaseError", BaseError)
    return errors


def _create_mock_helpers():
    """Create a mock helpers module."""
    helpers = types.ModuleType("helpers")
    
    def read_until(f, delimiter, max_len=None, return_on_max_len=False):
        """Mock read_until function."""
        data = b""
        while True:
            char = f.read(1)
            if not char:
                if return_on_max_len:
                    return data, None
                return data, None
            data += char
            if char == delimiter:
                return data[:-1], char
            if max_len and len(data) >= max_len:
                if return_on_max_len:
                    return data, None
                raise ValueError("Max length exceeded")
    
    def read_write(fin, fout):
        """Mock read_write function."""
        while True:
            chunk = fin.read(100)
            if not chunk:
                break
            fout.write(chunk)
    
    def a2b_base64_stream(fin, fout):
        """Mock base64 decode function."""
        data = fin.read()
        # Simple mock - just pass through
        fout.write(data)
    
    setattr(helpers, "read_until", read_until)
    setattr(helpers, "read_write", read_write)
    setattr(helpers, "a2b_base64_stream", a2b_base64_stream)
    
    return helpers


def _create_mock_gui():
    """Create a mock gui module structure."""
    gui = types.ModuleType("gui")
    gui.__path__ = [os.path.join(SRC_DIR, "gui")]
    
    common = types.ModuleType("gui.common")
    setattr(common, "HOR_RES", 480)
    setattr(common, "add_button", MagicMock())
    setattr(common, "add_label", MagicMock())
    
    decorators = types.ModuleType("gui.decorators")
    setattr(decorators, "on_release", MagicMock())
    setattr(decorators, "feed_touch", MagicMock())
    
    screens = types.ModuleType("gui.screens")
    setattr(screens, "Alert", MagicMock())
    setattr(screens, "Menu", MagicMock())
    
    settings = types.ModuleType("gui.screens.settings")
    setattr(settings, "HostSettings", MagicMock())
    
    return {
        "gui": gui,
        "gui.common": common,
        "gui.decorators": decorators,
        "gui.screens": screens,
        "gui.screens.settings": settings,
    }


def _import_usb_host():
    """Import USBHost with all mocks in place."""
    _clear_hosts_modules()
    
    pyb = _create_mock_pyb()
    platform = _create_mock_platform()
    errors = _create_mock_errors()
    helpers = _create_mock_helpers()
    gui_modules = _create_mock_gui()
    
    mock_modules = {
        "pyb": pyb,
        "platform": platform,
        "errors": errors,
        "helpers": helpers,
        "lvgl": MagicMock(),
        **gui_modules,
    }
    
    with patch.dict(sys.modules, mock_modules):
        from hosts.usb import USBHost
        return USBHost, pyb, platform


def _import_sd_host():
    """Import SDHost with all mocks in place."""
    _clear_hosts_modules()
    
    pyb = _create_mock_pyb()
    platform = _create_mock_platform()
    errors = _create_mock_errors()
    helpers = _create_mock_helpers()
    gui_modules = _create_mock_gui()
    
    mock_modules = {
        "pyb": pyb,
        "platform": platform,
        "errors": errors,
        "helpers": helpers,
        "os": os,
        "lvgl": MagicMock(),
        **gui_modules,
    }
    
    with patch.dict(sys.modules, mock_modules):
        from hosts.sd import SDHost
        return SDHost, platform


def _import_qr_host():
    """Import QRHost with all mocks in place."""
    _clear_hosts_modules()
    
    pyb = _create_mock_pyb()
    platform = _create_mock_platform()
    errors = _create_mock_errors()
    helpers = _create_mock_helpers()
    gui_modules = _create_mock_gui()
    
    # Mock time module
    time = types.ModuleType("time")
    setattr(time, "time", MagicMock(return_value=0))
    setattr(time, "sleep_ms", MagicMock())
    
    # Mock gc module
    gc = types.ModuleType("gc")
    setattr(gc, "collect", MagicMock())
    
    # Mock microur modules
    microur = types.ModuleType("microur")
    decoder = types.ModuleType("microur.decoder")
    setattr(decoder, "FileURDecoder", MagicMock())
    util = types.ModuleType("microur.util")
    setattr(util, "cbor", MagicMock())
    
    # Mock qrencoder
    qrencoder = types.ModuleType("qrencoder")
    setattr(qrencoder, "Base64QREncoder", MagicMock())
    setattr(qrencoder, "CryptoPSBTEncoder", MagicMock())
    setattr(qrencoder, "LegacyBCUREncoder", MagicMock())
    
    # Mock config
    config = types.ModuleType("config")
    setattr(config, "QRSCANNER_TRIGGER", "Y5")
    
    # Update platform with needed functions
    setattr(platform, "simulator", False)
    setattr(platform, "config", config)
    
    mock_modules = {
        "pyb": pyb,
        "platform": platform,
        "errors": errors,
        "helpers": helpers,
        "time": time,
        "gc": gc,
        "microur": microur,
        "microur.decoder": decoder,
        "microur.util": util,
        "qrencoder": qrencoder,
        "lvgl": MagicMock(),
        **gui_modules,
    }
    
    with patch.dict(sys.modules, mock_modules):
        from hosts.qr import QRHost
        return QRHost, pyb, platform


class USBHostTest(TestCase):
    """Tests for USB host communication."""
    
    def test_usb_mock_setup(self):
        """Verify USB mocking works."""
        USBHost, pyb, platform = _import_usb_host()
        
        # Create USBHost instance
        with patch("builtins.open", mock_open()):
            host = USBHost("/tmp/usb_test")
        
        self.assertIsNotNone(host)
        self.assertEqual(host.path, "/tmp/usb_test")
        self.assertFalse(host.is_enabled)
        self.assertEqual(host.ACK, b"ACK\r\n")
    
    def test_usb_init(self):
        """Test USB initialization."""
        USBHost, pyb, platform = _import_usb_host()
        
        with patch("builtins.open", mock_open()):
            host = USBHost("/tmp/usb_test")
        
        host.init()
        
        self.assertIsNotNone(host.usb)
    
    def test_usb_respond(self):
        """Test USB send/receive with mocked pyb.USB_VCP."""
        USBHost, pyb, platform = _import_usb_host()
        
        with patch("builtins.open", mock_open()):
            host = USBHost("/tmp/usb_test")
        
        host.init()
        
        # Test respond method
        host.respond(b"test response")
        
        self.assertIn(b"test response", host.usb._write_buffer)
        self.assertIn(b"\r\n", host.usb._write_buffer)
    
    def test_usb_read_to_file_no_data(self):
        """Test read_to_file when no data available."""
        USBHost, pyb, platform = _import_usb_host()
        
        with patch("builtins.open", mock_open()):
            host = USBHost("/tmp/usb_test")
        
        host.init()
        # No data in buffer
        result = host.read_to_file()
        self.assertIsNone(result)
    
    def test_usb_cleanup(self):
        """Test USB cleanup functionality."""
        USBHost, pyb, platform = _import_usb_host()
        
        with patch("builtins.open", mock_open()) as mock_file:
            host = USBHost("/tmp/usb_test")
            host.init()
            
            # Simulate an open file
            host.f = mock_file.return_value
            host.cleanup()
            
            # File should be closed and set to None
            self.assertIsNone(host.f)


class SDHostTest(TestCase):
    """Tests for SD card communication."""
    
    def test_sd_mock_setup(self):
        """Verify SD mocking works."""
        SDHost, platform = _import_sd_host()
        
        with patch("builtins.open", mock_open()):
            host = SDHost("/tmp/sd_test")
        
        self.assertIsNotNone(host)
        self.assertEqual(host.path, "/tmp/sd_test")
        self.assertEqual(host.sdpath, "/sd")
    
    def test_sd_truncate_filename(self):
        """Test SD filename truncation."""
        SDHost, platform = _import_sd_host()
        
        with patch("builtins.open", mock_open()):
            host = SDHost("/tmp/sd_test")
        
        # Short filename should remain unchanged
        short = "short.psbt"
        self.assertEqual(host.truncate(short), short)
        
        # Long filename should be truncated
        long_name = "a_very_long_filename_that_exceeds_limit.psbt"
        truncated = host.truncate(long_name)
        self.assertLessEqual(len(truncated), 36)  # 18 + 3 + 12 + 3 (...)
        self.assertIn("...", truncated)
    
    def test_sd_completed_filename(self):
        """Test SD completed filename generation."""
        SDHost, platform = _import_sd_host()
        
        with patch("builtins.open", mock_open()):
            host = SDHost("/tmp/sd_test")
        
        # PSBT file
        result = host.completed_filename("/sd/unsigned.psbt")
        self.assertEqual(result, "/sd/unsigned.signed.psbt")
        
        # With parent fingerprint
        host.parent = MagicMock()
        host.parent.fingerprint = b"\x12\x34\x56\x78"
        result = host.completed_filename("/sd/unsigned.psbt")
        self.assertIn(".signed", result)
        self.assertTrue(result.endswith(".psbt"))
    
    def test_sd_copy(self):
        """Test SD file copy operation."""
        SDHost, platform = _import_sd_host()
        
        with patch("builtins.open", mock_open()):
            host = SDHost("/tmp/sd_test")
        
        # Create mock file objects
        fin = io.BytesIO(b"test data for copy")
        fout = io.BytesIO()
        
        host.copy(fin, fout)
        
        fout.seek(0)
        self.assertEqual(fout.read(), b"test data for copy")


class QRHostTest(TestCase):
    """Tests for QR code communication."""
    
    def test_qr_mock_setup(self):
        """Verify QR mocking works."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        self.assertIsNotNone(host)
        self.assertEqual(host.path, "/tmp/qr_test")
        self.assertTrue(host.settings.get("enabled", True))
    
    def test_qr_mask_property(self):
        """Test QR MASK property based on settings."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        # Default settings: sound=True, aim=True, light=False
        mask = host.MASK
        # bit 7 should be set, bit 6 (sound) set, bit 4 (aim) set, bit 2 (light) not set
        self.assertTrue(mask & (1 << 7))  # default bit
        self.assertTrue(mask & (1 << 6))  # sound
        self.assertTrue(mask & (1 << 4))  # aim
        self.assertFalse(mask & (1 << 2))  # light
    
    def test_qr_cmd_mode_property(self):
        """Test QR CMD_MODE property."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        cmd_mode = host.CMD_MODE
        # Should be MASK | 1
        self.assertEqual(cmd_mode, host.MASK | 1)
    
    def test_qr_parse_prefix(self):
        """Test QR prefix parsing."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        # Valid prefix
        m, n = host.parse_prefix(b"p2of3")
        self.assertEqual(m, 2)
        self.assertEqual(n, 3)
        
        # Another valid prefix
        m, n = host.parse_prefix(b"p1of5")
        self.assertEqual(m, 1)
        self.assertEqual(n, 5)
    
    def test_qr_parse_prefix_invalid(self):
        """Test QR prefix parsing with invalid input."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        from hosts.core import HostError
        
        # Missing 'p' prefix
        with self.assertRaises(HostError):
            host.parse_prefix(b"2of3")
        
        # Missing 'of'
        with self.assertRaises(HostError):
            host.parse_prefix(b"p23")
    
    def test_qr_check_animated(self):
        """Test QR animated detection."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        # UR:BYTES prefix should be animated
        self.assertTrue(host.check_animated(b"UR:BYTES/1of3/abc/data"))
        
        # pMofN prefix should be animated
        self.assertTrue(host.check_animated(b"p1of3 data here"))
        
        # Plain data should not be animated
        self.assertFalse(host.check_animated(b"plain data without prefix"))
    
    def test_qr_bcc_computation(self):
        """Test QR BCC (Block Check Character) computation."""
        QRHost, pyb, platform = _import_qr_host()
        
        with patch("builtins.open", mock_open()):
            host = QRHost("/tmp/qr_test")
        
        # Test BCC computation
        data = b"\x00\x01\x02"
        bcc = host._compute_bcc(data)
        self.assertIsInstance(bcc, bytes)
        self.assertEqual(len(bcc), 1)
        
        # XOR of 0x00 ^ 0x01 ^ 0x02 = 0x03
        self.assertEqual(bcc, b"\x03")


class CoreHostTest(TestCase):
    """Tests for the base Host class."""
    
    def test_host_is_enabled_property(self):
        """Test Host is_enabled property."""
        _clear_hosts_modules()
        
        platform = _create_mock_platform()
        errors = _create_mock_errors()
        
        mock_modules = {
            "platform": platform,
            "errors": errors,
            "asyncio": asyncio,
            "json": types.ModuleType("json"),
            "gui.screens.settings": MagicMock(),
            "gui.screens": MagicMock(),
            "lvgl": MagicMock(),
        }
        
        with patch.dict(sys.modules, mock_modules):
            from hosts.core import Host
            
            class ConcreteHost(Host):
                pass
            
            with patch("builtins.open", mock_open()):
                host = ConcreteHost("/tmp/test")
            
            # Default is enabled
            self.assertTrue(host.is_enabled)
            
            # Change settings
            host.settings["enabled"] = False
            self.assertFalse(host.is_enabled)
    
    def test_host_enable_disable(self):
        """Test Host enable/disable functionality."""
        _clear_hosts_modules()
        
        platform = _create_mock_platform()
        errors = _create_mock_errors()
        
        mock_modules = {
            "platform": platform,
            "errors": errors,
            "asyncio": asyncio,
            "json": types.ModuleType("json"),
            "gui.screens.settings": MagicMock(),
            "gui.screens": MagicMock(),
            "lvgl": MagicMock(),
        }
        
        with patch.dict(sys.modules, mock_modules):
            from hosts.core import Host
            
            class ConcreteHost(Host):
                def init(self):
                    self.init_called = True
            
            with patch("builtins.open", mock_open()):
                host = ConcreteHost("/tmp/test")
            
            # Enable should call init and set enabled
            asyncio.run(host.enable())
            self.assertTrue(host.init_called)
            self.assertTrue(host.enabled)
            
            # Disable should set enabled to False
            asyncio.run(host.disable())
            self.assertFalse(host.enabled)


if __name__ == "__main__":
    import unittest
    unittest.main()
