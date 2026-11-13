
## Final client formalization (2026-11-08)

### Satochip P2 signing fix (hardware-proven, now in client code)
`get_extended_key(path, for_signing=True)` sends P2=0x00 (full private-key
derivation) instead of P2=0x40 (watch-only optimization). The card stores
a watch-only key with P2=0x40 — signing with keynbr=0xFF after it produces
unverifiable signatures (~50% wrong keys, proven on m/84h/0h/0h).
`sign_hash()` now calls `get_extended_key(path_bytes, for_signing=True)`
before `sign_transaction_hash(0xFF, hash)`.
Commit: aa8daf5 on m2-satochip (39/39 tests).

### SeedKeeper SETUP flow (hardware-proven, now in client code)
`is_setup()` checks for 9C04 (SW_SETUP_NOT_DONE); `setup(pin, puk)` sends
INS 0x2A via secure channel with the v0.2 format. One-time provisioning
unblocks all data operations (list/export/import).
Proven: hardware SETUP succeeded 2026-11-04, list_secret_headers returned
empty list after SETUP.
Commit: 1f6cb9a on m2-seedkeeper (41/41 tests).

### Console mechanism (v2.2.x diagnostic arc)
Root cause chain: pyb.usb_mode("VCP") enables the UART3 output path on the
ST-Link VCP (D8); platform.py's eager stlk=pyb.UART("YB",9600) was claiming
the UART3 peripheral (D6, replaced with _NullUART); MicroPython GC reaps
unheld create_task returns (task anchor); select_keystore's tight loop needs
a yield (sleep_ms(50)); the wedged card blocks the event loop beyond the
yield's windows (card SC request is synchronous).
