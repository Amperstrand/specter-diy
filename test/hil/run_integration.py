#!/usr/bin/env python3
import sys
import os
import importlib.util
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'integration'))

from controller import sim as hw_sim

import util.controller
util.controller.sim = hw_sim

from util.bitcoin_core import BitcoinCoreManager

TEST_DIR = os.path.join(os.path.dirname(__file__), '..', 'integration', 'tests')


def load_test_module(name, filename):
    path = os.path.join(TEST_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    hw_sim.start()
    btc = None
    try:
        hw_sim.load()

        if BitcoinCoreManager.is_available():
            btc = BitcoinCoreManager()
            btc.start()

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        test_files = [
            ("test_basic", "test_basic.py"),
            ("test_seedkeeper", "test_seedkeeper.py"),
        ]

        if btc is not None:
            test_files.append(("test_with_rpc", "test_with_rpc.py"))

        for name, filename in test_files:
            try:
                mod = load_test_module(name, filename)
                suite.addTests(loader.loadTestsFromModule(mod))
            except Exception as e:
                print("Failed to load %s: %s" % (filename, e))

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    finally:
        if btc is not None:
            btc.stop()
        hw_sim.shutdown()


if __name__ == '__main__':
    main()
