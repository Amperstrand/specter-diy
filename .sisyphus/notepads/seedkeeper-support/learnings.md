
## 2026-03-13 F3 import and hierarchy verification
- `src/keystore/seedkeeper.py` declares `class SeedKeeper(RAMKeyStore)` and `src/keystore/javacard/applets/seedkeeper_applet.py` declares `class SeedKeeperApplet(Applet)`; `src/keystore/javacard/applets/satochip_securechannel.py` keeps `SatochipSecureChannel` standalone.
- `test/tests/test_seedkeeper.py` contains 6 `TestCase` classes and 24 `test_` methods, exceeding the plan minimum of 12 tests.
- `src/main.py` imports `SeedKeeper` and registers it in the keystore list.
