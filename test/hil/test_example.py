"""
HIL tests matching SimController interface.
"""
import sys
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "test.hil"

from controller import HardwareController


class MockSerial:
    def __init__(self):
        self.written = []
        self.responses = []
        
    def write(self, data):
        self.written.append(data)
        return len(data)
        
    def read(self, n=1):
        if self.responses:
            return self.responses.pop(0)
        return b""
        
    def readline(self):
        if self.responses:
            return self.responses.pop(0)
        return b""
        
    def in_waiting(self):
        return len(self.responses)
        
    def close(self):
        pass


class HardwareControllerTest(unittest.TestCase):
    
    def test_controller_instantiation(self):
        ctrl = HardwareController()
        self.assertIsNone(ctrl.gui)
        self.assertIsNone(ctrl.usb)
        self.assertFalse(ctrl.started)
        
    def test_start_method_exists(self):
        ctrl = HardwareController()
        self.assertTrue(hasattr(ctrl, 'start'))
        self.assertTrue(callable(ctrl.start))
        
    def test_load_method_exists(self):
        ctrl = HardwareController()
        self.assertTrue(hasattr(ctrl, 'load'))
        self.assertTrue(callable(ctrl.load))
        
    def test_query_method_exists(self):
        ctrl = HardwareController()
        self.assertTrue(hasattr(ctrl, 'query'))
        self.assertTrue(callable(ctrl.query))
        
    def test_shutdown_method_exists(self):
        ctrl = HardwareController()
        self.assertTrue(hasattr(ctrl, 'shutdown'))
        self.assertTrue(callable(ctrl.shutdown))
        
    def test_query_signature(self):
        import inspect
        sig = inspect.signature(HardwareController.query)
        params = list(sig.parameters.keys())
        self.assertIn('self', params)
        self.assertIn('data', params)
        self.assertIn('commands', params)


if __name__ == '__main__':
    unittest.main()
