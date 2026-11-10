# Integration tests

These tests should run against Bitcoin Core (regtest mode).

To run launch with python3 from this folder (you should have `micropython_unix` built in the `../../bin/` folder):

```
python3 run_tests.py
```

## Hardware-in-the-Loop (HIL) tests

Tests run against real STM32F469 hardware via the debug UART (ST-Link VCP).

Prerequisites:
- Device flashed with HIL firmware: `make hardwareintheloop`
- ST-Link connected (debug UART on `/dev/ttyACM0`)
- Bitcoin Core running in regtest mode (for RPC tests)

```
make hardwareintheloop-test
```

The full suite (16 tests) takes approximately **6 minutes** to complete.
