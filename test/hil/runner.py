"""
HIL test runner.

Discovers and runs HIL tests with hardware setup/teardown.
"""
import unittest
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "test.hil"

from .controller import HardwareController


class HILTestRunner:
    """Runs HIL tests with hardware control."""

    def __init__(self, controller: HardwareController):
        self.controller: HardwareController = controller

    def run_tests(self, test_dir: str = "test/hil") -> bool:
        """Discover and run HIL tests."""
        loader = unittest.TestLoader()
        suite = loader.discover(test_dir, pattern="test_*.py")

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        return result.wasSuccessful()
