
## 2026-03-13 F3 import and hierarchy verification
- Direct host-side `python3 -c "from keystore.seedkeeper import SeedKeeper"` fails before reaching SeedKeeper code because `keystore.__init__` imports `flash`, which imports `platform.py`, which requires MicroPython's `pyb`. Per task guidance, treated as expected environment-specific behavior rather than an implementation failure.
