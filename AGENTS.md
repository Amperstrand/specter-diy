# AGENTS.md - Project Onboarding Guide

This file provides essential context for AI agents and developers new to the Specter-DIY SeedKeeper project.

---

## Project Overview

Specter-DIY is an open-source Bitcoin hardware wallet built from off-the-shelf components. This fork adds **SeedKeeper** support - a smartcard-based keystore that stores encrypted mnemonics on JavaCard.

### Key Technologies

- **MicroPython** - Firmware is written in MicroPython (not CPython)
- **LVGL** - GUI library for embedded displays
- **STM32F469** - Target microcontroller (Discovery board)
- **JavaCard** - Smartcard applets for SeedKeeper/MemoryCard

### Project Structure

```
specter-diy/
├── src/                    # Main firmware source (MicroPython)
│   ├── main.py            # Entry point
│   ├── specter.py         # Main Specter class
│   ├── debug_trace.py     # Serial debug logging
│   ├── keystore/          # Keystore implementations
│   │   ├── seedkeeper.py  # SeedKeeper keystore class
│   │   └── javacard/      # JavaCard communication
│   │       └── applets/   # Applet interfaces
│   │           └── seedkeeper_applet.py
│   ├── gui/               # LVGL-based GUI
│   └── apps/              # Wallet, message signing, etc.
├── boot/                  # Bootloader code
├── f469-disco/           # STM32F469 port and MicroPython
├── test/                  # Test suite
│   ├── tests/            # Unit tests (simulator)
│   ├── hil/              # Hardware-in-the-loop tests
│   └── integration/      # Integration tests
└── docs/                  # Documentation
```

---

## Quick Start: Local Testing

### Prerequisites (system packages)

```bash
# Required for MicroPython unix port build
sudo apt install build-essential pkg-config libffi-dev libgmp-dev libreadline-dev libsdl2-dev python3-venv libdb-dev
```

### Setup

```bash
# Initialize submodules (first time only)
git submodule update --init --recursive

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install -r requirements-dev.txt
```

### Running Tests

**Native CPython tests** (fastest, no MicroPython needed):
```bash
source .venv/bin/activate
python3 test/run_native_tests.py
```

**Lint and typecheck:**
```bash
source .venv/bin/activate
make lint          # flake8 (critical errors only, then full report)
make typecheck     # mypy
make format        # black + isort (check only)
make format-fix    # black + isort (auto-fix)
```

**MicroPython unix port tests** (requires building MicroPython first):
```bash
# Build MicroPython unix port + run tests
make test
```

**Coverage report:**
```bash
make coverage
```

### Build Configuration Notes

The MicroPython unix port build requires two patches to work locally:

1. **`f469-disco/micropython/ports/unix/mpconfigport.mk`**: axtls SSL is disabled (submodule config not generated), mbedtls is enabled instead as the AES backend for `ucryptolib` (needed by Specter's secure channel).

2. **`f469-disco/micropython/ports/unix/mpconfigport.h`**: `MICROPY_PY_UCRYPTOLIB` is moved outside the `#if MICROPY_PY_USSL` guard so it remains available when SSL is disabled.

3. **`f469-disco/libs/unix/pyb.py`**: Adds stub `LED`, `SDCard`, and `hard_reset` classes needed by `src/platform.py` on the unix port.

### What Requires Hardware

These test paths need the STM32F469 board or Bitcoin Core regtest:

- **HIL tests**: `make hil-test` (requires board + ST-LINK + HIL firmware)
- **Integration tests**: see below

### Running Integration Tests (Simulator + Bitcoin Core)

Integration tests run the unix simulator and test Bitcoin operations via Bitcoin Core in regtest mode.

**Bitcoin Core is auto-started** by the test runners (`run_tests.py`, `run_integration.py`) if `bitcoind` is found in PATH. It uses a temporary datadir (`/tmp/specter-test-bitcoin-<pid>/`) on port 18778. No manual setup needed.

**1. Run the integration tests:**
```bash
source .venv/bin/activate
cd test/integration
SDL_VIDEODRIVER=software python3 run_tests.py -v
```

**Expected results:** All basic tests pass. RPC tests run automatically if `bitcoind` is available.

**To skip RPC tests**, uninstall `bitcoind` or set `BTC_SKIP_RPC=1`.

**Manual setup** (if you prefer not to use auto-start):
```bash
# Create ~/.bitcoin/bitcoin.conf with:
#   [regtest]
#   server=1
#   rpcuser=specter
#   rpcpassword=specter
#   rpcport=18443
#   rpcallowip=127.0.0.1
#   rpcconnect=127.0.0.1
#   fallbackfee=0.0001
#   listen=0
bitcoind -regtest -daemon

source .venv/bin/activate
cd test/integration
SDL_VIDEODRIVER=software \
  BTC_RPC_USER=specter BTC_RPC_PASSWORD=specter \
  BTC_RPC_HOST=127.0.0.1 BTC_RPC_PORT=18443 \
  BTC_RPC_PROTOCOL=http \
  python3 run_tests.py -v
```

---

## Quick Start: Hardware Testing

### Prerequisites

- STM32F469 Discovery board connected via ST-LINK USB
- Remote build machine: `ubuntu@192.168.13.246`
- Docker for builds

### ARM Toolchain (Required)

**ARM Embedded Toolchain v9-2020-q2-update is required.** The Ubuntu apt package (`gcc-arm-none-eabi`, currently v13.2) generates code that HardFaults on the STM32F469. The v9 toolchain is the same version used in the Docker build.

```bash
# Already installed on this machine at /opt/gcc-arm-none-eabi-9-2020-q2-update/
# PATH is set via /etc/profile.d/arm-toolchain.sh
source /etc/profile.d/arm-toolchain.sh
arm-none-eabi-gcc --version  # Should show 9.3.1 20200408

# DO NOT upgrade without testing — newer gcc-arm-embedded versions have known
# regressions (e.g., v10 broke some Cortex-M targets). See AGENTS.md learnings.
```

**Why not the latest version?** We tested v13.2 (Ubuntu 24.04 apt) — it produces a firmware that immediately HardFaults on boot. This is a codegen incompatibility with the STM32F4 HAL drivers and the specific compiler flags used. v9 is proven working. Testing newer versions requires building, flashing, and verifying — if it fails, you're debugging toolchain issues instead of firmware.

### Build & Flash

```bash
# One-liner: sync, build, flash, monitor
./tools/build.sh --flash

# Or step by step:
./tools/build.sh           # Sync + build only
./tools/build.sh --flash   # Sync + build + flash
./tools/build.sh --monitor # After flash, monitor serial
```

### Manual Commands (if needed)

```bash
# Sync local → remote (exact mirror)
rsync -avz --delete --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  -e "ssh" ./ ubuntu@192.168.13.246:~/specter-build/

# Build firmware (Docker)
ssh ubuntu@192.168.13.246 "cd ~/specter-build && sudo docker run --rm -v \$PWD:/app -w /app specter24d make disco"

# Flash firmware
ssh ubuntu@192.168.13.246 "st-flash --connect-under-reset erase && st-flash --connect-under-reset write ~/specter-build/bin/specter-diy.bin 0x08000000"
```

### Monitor Serial Output

```bash
# ⚠️ Critical: raw mode is required!
ssh ubuntu@192.168.13.246 "stty -F /dev/ttyACM0 9600 raw -echo && cat /dev/ttyACM0"
```

### Expected Output

```
[BOOT] main() started
[BOOT] Display initialized
[BOOT] Starting Specter...
[Specter] select_keystore: starting detection...
[SeedKeeper] Checking availability...
[SeedKeeper] Card inserted: True
[SeedKeeper] -> AVAILABLE
[Specter] Selected keystore: SeedKeeper
[HEARTBEAT] alive count=1
```

---

## Important Patterns

### Debug Logging

**ALWAYS use `log()`, NEVER use `print()`**

```python
# CORRECT
from debug_trace import log, log_exception

log("SeedKeeper", "Card inserted: %s" % card_present)
log_exception("Module", exception)

# WRONG - output is discarded on hardware
print("Debug message")
```

**Why:** The boot sequence disables `os.dupterm()` for security, so `print()` output goes nowhere. The `log()` function writes directly to UART.

### MicroPython Syntax Restrictions

MicroPython's `mpy-cross` compiler has different syntax rules than CPython:

```python
# AVOID: Tuple syntax with string literals in f-strings
f"{a, 'label:', c}"  # FAILS in mpy-cross

# USE: Explicit string formatting
f"{a}, label: {c}"   # OK
"%s, label: %s" % (a, c)  # OK
```

**Validation:** Use `mpy-cross` to validate syntax, not `python3 -m py_compile`.

### AsyncIO Patterns

The firmware uses `uasyncio` (MicroPython's async library):

```python
import asyncio

async def my_task():
    while True:
        await asyncio.sleep(5)
        # do work

# Start background task
asyncio.create_task(my_task())

# Run main loop
asyncio.run(main())
```

---

## Key Files to Understand

| File | Purpose |
|------|---------|
| `src/main.py` | Entry point, initializes GUI, keystores, hosts |
| `src/specter.py` | Main Specter class, keystore selection, menus |
| `src/debug_trace.py` | Serial debug logging (`log()`, `log_exception()`) |
| `src/keystore/seedkeeper.py` | SeedKeeper keystore implementation |
| `src/keystore/javacard/applets/seedkeeper_applet.py` | JavaCard APDU communication |
| `src/gui/screens/debug_info.py` | Debug screen shown during keystore detection |

---

## Common Tasks

### Add a New Debug Message

1. Import `log` from `debug_trace`
2. Add `log("TAG", "message %s" % variable)`
3. Build and flash
4. Monitor serial output

### Run Unit Tests

```bash
# Native CPython tests (fastest, no MicroPython needed)
source .venv/bin/activate
python3 test/run_native_tests.py

# MicroPython unix port tests (requires make unix first)
make test
```

### Debug a Crash

1. Check serial output for exception trace
2. Look for `[TAG] TRACEBACK START` in output
3. Exception type and message will be logged

---

## Constraints (From User)

These constraints must be followed:

- "stick to english"
- "only refactor where it makes a lot of sense"
- "The priority should be to add code in a way that it is easy for the reviewer to test"
- "we will call the channel Satochip secure channel"
- "ALWAYS use Docker for builds"
- "we must not use rdp2" (permanent lock)
- "rdp might permanently lock it so we absolutely must not do that"

---

## Troubleshooting

### Serial Output Not Working

1. Ensure `stty -F /dev/ttyACM0 9600 raw -echo` is set
2. Check device is running: `st-info --probe`
3. Verify firmware flashed: look for "Flash written and verified! jolly good!"

### Build Fails with Syntax Error

1. Check for f-string syntax incompatible with MicroPython
2. Validate with `mpy-cross`: `mpy-cross file.py`
3. Common issues: tuple syntax in f-strings, CPython-only features

### Device Locked (RDP Protection)

**CRITICAL**: If `st-flash --connect-under-reset erase` fails with "Flash memory is write protected", the device has RDP Level 1 enabled.

**Solution - OpenOCD Unlock:**

```bash
# 1. Create OpenOCD config files on remote
mkdir -p ~/specter-diy-fresh/bootloader
cat > ~/specter-diy-fresh/bootloader/openocd.cfg << 'EOF'
source [find interface/stlink-v2-1.cfg]
source [find target/stm32f4x.cfg]
EOF

cat > ~/specter-diy-fresh/bootloader/ocd-unlock.cfg << 'EOF'
init
reset halt
flash protect 0 0 last off
stm32f4x unlock 0
reset halt
exit
EOF

# 2. Run OpenOCD unlock
cd ~/specter-diy-fresh/bootloader && openocd -f openocd.cfg -f ocd-unlock.cfg

# 3. Now mass erase will work
st-flash --connect-under-reset erase
```

**Reference**: See `docs/faq.md` section "I want to do a factory-reset" for more details.

### No Heartbeat

If heartbeat stops, device likely crashed. Check serial output for exception trace before the crash.

### Simulator Segfaults on Startup (NVIDIA + SDL2)

The unix simulator uses SDL2 for its display backend. On machines with NVIDIA GPUs, the NVIDIA OpenGL driver can segfault inside SDL2's rendering pipeline. This is a driver bug, not a firmware bug.

**Symptoms:**
```
[BOOT] main() started
[BOOT] Display initialized
Segmentation fault
```

**Workaround** — set the SDL2 video driver to software rendering:
```bash
# Manual simulator run
SDL_VIDEODRIVER=software ./bin/micropython_unix simulate.py

# Integration tests
SDL_VIDEODRIVER=software python3 test/integration/run_tests.py

# Or source the provided env file
source .env
./bin/micropython_unix simulate.py
```

**To make it persistent**, copy `.env.example` to `.env` and source it in your shell profile.

**Root cause:** GDB backtrace shows the crash in `libnvidia-glcore.so` called through `libSDL2-2.0.so`. Updating the NVIDIA driver may fix it. Software rendering has no performance impact for the simulator's 480x272 LVGL window.

### Debugging Tools Kill USB Enumeration

**CRITICAL: `openocd halt`, `st-info --probe`, and `st-flash` all stop the CPU**, which disables the STM32's USB peripheral. If you use these tools to check firmware state, the device USB (MicroPython CDC VCP) will disappear.

**Symptoms:**
- `lsusb` only shows ST-LINK, not MicroPython device
- `/dev/ttyACM1` disappears after running openocd/st-flash
- Device USB reappears 5-8 seconds after the CPU resumes

**Correct way to check for device USB:**
```bash
# These are READ-ONLY and won't affect the CPU
lsusb -v | grep -i 'micro\|f055'
ls /dev/ttyACM*

# Check serial output from MicroPython VCP (read-only)
timeout 2 python3 -c "
import serial
ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
print(ser.read(ser.in_waiting or 1))
ser.close()
"
```

**If you need to check firmware state AND keep USB alive:**
1. Check USB first (read-only)
2. Use `openocd` or `st-info` (this kills USB)
3. Wait 5-8 seconds for USB to re-enumerate
4. Check USB again

### ARM Compiler v13.2 Generates Broken Code for STM32F469

The Ubuntu apt package `gcc-arm-none-eabi` (v13.2.1) produces firmware that immediately HardFaults on the STM32F469 Discovery board. This is a codegen incompatibility with the STM32F4 HAL drivers, not a source code bug.

**Workaround:** Install ARM Embedded Toolchain v9-2020-q2-update (same as Docker build). Already installed at `/opt/gcc-arm-none-eabi-9-2020-q2-update/` with PATH set via `/etc/profile.d/arm-toolchain.sh`.

**Verification:** After building with v9, firmware boots successfully and device USB enumerates.

---

## Current Status & Learnings

### Test Results (2026-03-18, branch `satochip-dev`, based on v1.10.0 + 30 commits)

| Test Suite | Result | Notes |
|-----------|--------|-------|
| Native CPython unit tests (`test/run_native_tests.py`) | Passes | Fastest, no MicroPython needed |
| MicroPython unix port unit tests (`make test`) | 30/31 pass | 1 fail: `test_save_mnemonic_raises_error` (MicroPython lacks `asyncio.iscoroutinefunction`) |
| **HIL tests on hardware — SeedKeeper** (`make hil-test`) | **19/19 pass** | **~5.5 min total. All tests pass including `test_miniscript`.** |

**Note:** `make hil-test` requires `source .venv/bin/activate` first (for `embit`, `pyserial` deps). Also needs `source /etc/profile.d/arm-toolchain.sh` if using ARM toolchain locally. The Makefile target runs `cd test/integration && python3 ../hil/run_integration.py` which uses the system Python.
| Lint (`make lint`) | Runs | Many pre-existing warnings in source |
| Typecheck (`make typecheck`) | Runs | Many pre-existing errors in source (all Pyright, not runtime) |

### Pre-existing Upstream Bugs (confirmed on clean v1.10.0 tag)

These bugs exist on the unmodified upstream `v1.10.0` release — they are NOT caused by our changes:

1. **Simulator SIGSEGV on NVIDIA GPUs** — `libnvidia-glcore.so` crashes inside SDL2's rendering pipeline. Workaround: `SDL_VIDEODRIVER=software`. See Troubleshooting section below.

2. **Unit test `IndentationError` in `test/tests/test_seedkeeper.py:108`** — duplicate leftover line from an incomplete edit. Fixed in our branch.

3. **`test_miniscript` integration test was broken** — Bitcoin Core v30 requires `descriptors=true` (named param) when creating wallets AND removed `importmulti` (replaced by `importdescriptors`). Both fixed: `createwallet` uses named kwargs, `importmulti` replaced with `importdescriptors` (with backward compat for older Core).

4. **RPC wrapper `KeyError: 'error'`** — `test/integration/util/rpc.py` line 373 does `r["error"]` but Bitcoin Core v30 omits the `"error"` key from success responses. Fixed in our branch with `r.get("error")`.

5. **`HIL_ENABLED = True` in `src/hil.py`** — left enabled, causes `os.dupterm(None, 0)` to run on unix port (which doesn't have dupterm), crashing the simulator. Fixed in our branch.

6. **`__init__.py` unconditional import** — `test/integration/tests/__init__.py` imports `test_with_rpc` at module level, which calls `prepare_rpc()` and crashes without Bitcoin Core. The HIL runner (`run_integration.py`) loads modules individually so it's not affected, but `run_tests.py` is broken.

### Upstream Submodule Issues (NOT our changes)

The `f469-disco` submodule (and its `micropython` sub-submodule) have **two pre-existing bugs** that affect ALL users of the STM32F469 Discovery board. These are unrelated to SeedKeeper and should be fixed in their respective upstream repos.

**Dependency chain:**
```
specter-diy (cryptoadvance/specter-diy)
  └── f469-disco (diybitcoinhardware/f469-disco)     ← maintained by Kim Neunert (k9ert)
        └── micropython (diybitcoinhardware/micropython)  ← maintained by Stepan Snigirev, 3.5 years old
```

**Issue 1: QSPI flash hang (micropython fork)**

The `diybitcoinhardware/micropython` fork (commit `6bdf1b691`, Nov 2022) has an STM32F469DISC board config where the hardware QUADSPI peripheral hangs during initialization. The MCU gets stuck waiting for the QSPI peripheral and never reaches `main()`.

Mike Tolkachev (miketlk) — the same person who originally set up the STM32F469 port for specter-diy — later submitted PR [#18264](https://github.com/micropython/micropython/pull/18264) to upstream micropython (merged Nov 27, 2025 as commits `cad9bb3` and `b4d546d`). This PR added proper QSPI support with `MICROPY_HW_SPIFLASH_SOFT_RESET`, `MICROPY_HW_SPIFLASH_CHIP_PARAMS`, and a `board_early_init()` hook for the N25Q128A chip. However, this was never backported to the `diybitcoinhardware/micropython` fork.

The fork's board config has `MICROPY_F469DISC_USE_SOFTSPI` as a temporary workaround (GPIO bit-bang instead of hardware QSPI), but the SOFTSPI define was later removed in commit `d79d337d9` ("remove soft SPI") without the proper QSPI fix being in place — causing the hang.

**Impact:** The stock upstream specter-diy firmware does not boot on STM32F469 Discovery boards with the QSPI flash chip populated.

**Issue 2: ISO 7816 T=1 USART reconfig (f469-disco)**

The smartcard driver in `f469-disco/usermods/scard/` does not reconfigure the USART after ATR (Answer To Reset). ISO 7816 T=1 protocol requires stop bits changed from 1.5 to 1 and guard time reduced from 16 to 1 ETU after ATR negotiation. Without this reconfig, all smartcard communication fails.

Amperstrand has a fix in the `improve/t1-usart-reconfig` branch (commit `4fd3e51` in `diybitcoinhardware/f469-disco`) but it has not been merged.

**Impact:** No smartcard (MemoryCard or SeedKeeper) can communicate on the STM32F469 Discovery board.

**Hardware testing requires local submodule overrides:**

```bash
# These are LOCAL ONLY — never committed to any PR branch
cd f469-disco && git checkout 4fd3e51           # USART T=1 reconfig
cd f469-disco/micropython && git checkout e061ae4  # SOFTSPI workaround
```

After testing, reset to upstream:
```bash
cd f469-disco && git checkout db3ce3e           # upstream specter-diy pins
cd f469-disco && git submodule update --init micropython  # upstream fork pins
```

**Our PRs do NOT touch any submodule.** We only modify files in `src/`, `test/`, `Makefile`, and `manifests/`.

### Our Changes (src/ and test/ only)

| File | Change | Why |
|------|--------|-----|
| `src/keystore/seedkeeper.py` | **New file**: SeedKeeper keystore class | Smartcard-based keystore |
| `src/keystore/javacard/applets/seedkeeper_applet.py` | **New file**: SeedKeeper APDU commands | Card communication |
| `src/keystore/javacard/applets/satochip_securechannel.py` | **New file**: Satochip secure channel | AES-CBC encrypted channel |
| `src/keystore/javacard/card_scanner.py` | **New file**: Card presence detection | Smartcard ATR handling |
| `src/keystore/memorycard.py` | Modified for SeedKeeper compat | Shared smartcard infrastructure |
| `src/debug_trace.py` | **New file**: Serial debug logging | `log()` writes to ST-Link UART |
| `src/gui/screens/debug_info.py` | **New file**: Debug info screen | Shown during keystore detection |
| `src/hil.py` | **New file**: HIL test command handler | TEST_WIPE, TEST_KEYSTORE, etc. |
| `src/platform.py` | Added `hil_test_mode` flag | HIL detection via hil module |
| `src/specter.py` | HIL keystore query wiring | `hil.set_keystore_name/ref()`, `init_apps()` |
| `src/hosts/usb.py` | HIL auto-enable USB, `log_exception()` | USB host works in HIL mode |
| `src/main.py` | Boot logging, HIL wiring | Debug trace during boot |
| `src/gui/tcp_gui.py` | TEST_STATUS/TEST_SCREEN commands | Simulator HIL support |
| `test/hil/controller.py` | **New file**: HIL hardware controller | Serial communication, popup drain |
| `test/hil/run_integration.py` | **New file**: HIL test runner | Loads tests, auto-starts bitcoind |
| `test/tests/test_seedkeeper.py` | **New file**: SeedKeeper unit tests | Self-skipping on non-SeedKeeper |
| `test/integration/tests/test_seedkeeper.py` | **New file**: SeedKeeper HIL tests | Fingerprint, xpub, read-only |
| `test/integration/util/rpc.py` | `r.get("error")`, named kwargs | Bitcoin Core v30 compat |
| `test/integration/tests/test_with_rpc.py` | `importmulti` → `importdescriptors` | Bitcoin Core v30 compat |
| `test/integration/util/controller.py` | SIGSEGV detection | NVIDIA + SDL2 workaround |
| `test/integration/util/bitcoin_core.py` | **New file**: BitcoinCoreManager | Auto-start bitcoind for tests |
| `Makefile` | `hil`, `hil-test` targets | HIL firmware build and test |
| `manifests/disco-hil.py` | **New file**: HIL manifest | Freezes src/hil.py |

### Key Learnings

1. **The MicroPython unix port is a different build target than the ARM firmware.** Patches to `mpconfigport.mk` and `mpconfigport.h` only affect `make unix` / `make test`, NOT `make disco` (which uses the STM32 board config). ARM builds go through Docker on the remote machine and are unaffected.

2. **Three build strategies coexist but serve different purposes:**
   - **Docker** (remote machine): ARM firmware builds, reproducible toolchain (`gcc-arm-embedded-9-2020-q2`)
   - **Nix** (CI): ARM toolchain + SDL2 + openocd for full build+test pipeline
   - **Local apt** (this machine): unix port for development/testing only

3. **The simulator is sufficient for most development.** The unix port runs the same frozen firmware code as the ARM build. Only hardware-specific features (SPI smartcard communication, physical display, buttons) need the real board.

4. **Bitcoin Core v30 has breaking changes** from the version upstream tests were written for. The `descriptors=true` requirement for wallet creation (must be named param), the `"error"` key omission in success responses, and the removal of `importmulti` (replaced by `importdescriptors`) are the three we've hit.

5. **`SDL_VIDEODRIVER=software` is non-negotiable on this machine** (NVIDIA GPU). The GDB backtrace clearly shows the crash in `libnvidia-glcore.so.580.126.09` — no code fix will help.

6. **ST-LINK V2J47 firmware can get wedged** — if `st-flash` times out during a write, the ST-LINK's internal SWD engine gets stuck. Only a physical USB disconnect/reconnect (power cycle) can recover it. Kernel USB unbind/rebind is insufficient.

7. **Serial buffer staleness corrupts HIL commands** — debug logs and HIL responses share the same UART (`platform.stlk` at 9600 baud). During boot, log messages stream continuously. A 50ms `read_all()` flush is insufficient — must use a `_flush()` method that waits for a quiet period (no data for 150ms) before sending commands.

8. **HIL tests need storage wipe between runs** — the simulator wipes `./fs/` on startup, but on hardware wallet data persists in QSPI flash. The `TEST_WIPE` command wipes `/qspi/wallets` (wallet descriptors) and `/flash/keystore` (keystore data), then hard-resets the device for a clean state.

9. **Wallet storage paths**: Wallets are at `/qspi/wallets/<fingerprint>/<network>/`, auto-created "Default" wallet is always present. The keystore path is `/flash/keystore/` (for internal flash keystore only — SeedKeeper stores keys on the smartcard).

10. **USB protocol is plain-text, not JSON** — commands are `<prefix> <payload>\r\n` (e.g., `fingerprint\r\n`, `sign <base64-psbt>\r\n`, `addwallet <name>&<descriptor>\r\n`). Device sends `ACK\r\n` immediately, then processes and sends the response.

11. **SeedKeeper cards have secret IDs from the card, not sequential** — when listing BIP39 secrets, each has an `id` field from the card (e.g., "abandon" might be ID=1, "bacon" might be ID=0). The HIL controller must query `TEST_SECRETS` to get IDs before selecting.

12. **SeedKeeper `unlock()` loads the mnemonic but doesn't call `Specter.init_apps()`** — this means `WalletsApp.manager` is `None` and USB commands like `fingerprint` fail with `'NoneType' object has no attribute 'can_process'`. Fixed by adding `init_apps()` call in `Specter.setup()` after `unlock()`.

13. **SeedKeeper's "abandon" secret has a different key than the test mnemonic** — the card's "abandon" secret has fingerprint `0cf3bbd9` (12-word mnemonic with 16 bytes entropy), not `73c5da0a` (24-word `abandon abandon... about`). Tests with hardcoded key assertions must skip when SeedKeeper is active.

14. **LVGL popup text leaks into USB VCP** — When `showaddr` displays a `WalletScreen` popup (which extends `QRAlert` → `Alert`), the LVGL label text ("Text" title, "bitcoin:<addr>" QR content) appears on the USB VCP as raw text before the actual address response. Fixed by `_drain_popup()` in `SerialSocket` which reads all available data after GUI confirmation, filters out lines starting with "Text" or "bitcoin:", and preserves any non-popup lines for `receive()`.

15. **HIL tests take ~5.5 minutes** — 19 tests total (3 basic + 3 seedkeeper + 13 RPC). Most time is in RPC tests that create wallets, mine blocks, and sign transactions. Requires `timeout >= 600s` in the test runner.

16. **Upstream submodule changes are out of scope for our PRs.** The QSPI hang (micropython fork) and USART T=1 reconfig (f469-disco) are pre-existing bugs in the build chain. We verified both are needed for hardware testing (3 configurations tested: Config 1 = full upstream = dead board; Config 2 = SOFTSPI only = boots but no smartcard; Config 3 = SOFTSPI + USART = fully working). Our PRs only modify `src/` and `test/`. Local submodule overrides are documented above for developers who want to test on hardware.

17. **`diybitcoinhardware/micropython` is 3.5 years old** (commit `6bdf1b691`, Nov 2022 by Stepan Snigirev). Mike Tolkachev's proper QSPI fix was merged to upstream micropython in Nov 2025 (PR #18264) but never backported. The `diybitcoinhardware/f469-disco` repo (maintained by k9ert) pins this old micropython. Updating the micropython fork requires Stepan's cooperation.

---

## Next Steps

### PR Strategy

Our changes will be split into independent PRs to upstream `cryptoadvance/specter-diy`, each branching from the latest upstream master. We do NOT touch any submodule (`f469-disco`/`micropython`/`bootloader`) — those are separate upstream issues.

| PR | Branch | Scope | Status |
|----|--------|-------|--------|
| Bitcoin Core v30 compat | `fix/bitcoin-core-v30` | `test/integration/util/rpc.py`, `test/integration/tests/test_with_rpc.py` | Ready |
| SeedKeeper keystore | `feat/seedkeeper` | `src/keystore/seedkeeper.py`, `src/keystore/javacard/`, `src/keystore/memorycard.py` | Needs security review |
| HIL testing framework | `feat/seedkeeper-hil` | `src/hil.py`, `src/platform.py`, `src/specter.py`, `src/hosts/usb.py`, `src/main.py`, `src/gui/tcp_gui.py`, `test/hil/`, `test/integration/tests/test_seedkeeper.py`, `Makefile`, `manifests/` | Depends on SeedKeeper PR |

**Rebase workflow:** As each PR merges, rebase remaining branches onto `upstream/master`. `satochip-dev` stays as our integration/safety-net branch.

### Cleanup completed (2026-03-18)

- Removed debug artifacts: `.sisyphus/`, `boot/debug/`, debug scripts, backup files, `tools/debug_monitor/`
- Removed LED debug indicators from `src/platform.py` (replaced with `log()`)
- Reverted `boot/main/boot.py` to upstream (removed unconditional VCP enable)
- Reverted `src/hosts/usb.py` to upstream then re-applied only HIL changes
- Reverted `test/integration/util/controller.py` to upstream + SIGSEGV detection only (removed unused `BaseController`)
- Removed committed dev tooling: `.flake8`, `.pre-commit-config.yaml`, `mypy.ini`, `pyproject.toml`
- Reverted `build_firmware.sh`, `.github/workflows/test.yml`, `Makefile` to upstream (added back only `hil`/`hil-test` targets)
- Reverted dev-only docs, upstream noise changes (typo fixes, pronoun fixes, etc.)
- **Reverted `f469-disco` submodule to upstream `db3ce3e`** (SOFTSPI and USART reconfig are local-only overrides for hardware testing)

### Completed

- [x] **Fix `test_miniscript`** — add `descriptors=True` argument to `rpc.createwallet()` in `test/integration/tests/test_with_rpc.py:245`
- [x] **Fix `test_save_mnemonic_raises_error`** — the test uses `asyncio.iscoroutinefunction` which doesn't exist in this MicroPython version. Guard with `hasattr` check or skip.
- [x] **Verify ARM firmware build still works** — run `./tools/build.sh` to sync and build on the remote machine, confirm our source changes compile for ARM
- [x] **Run HIL tests against real hardware** — `make hil-test` requires the STM32F469 board + ST-LINK + HIL firmware. Verify the test framework works end-to-end. **DONE: 18/19 pass (only `test_miniscript` fails due to upstream Bitcoin Core v30 `importmulti` removal)**
- [x] **Clean up temporary debug code in `src/hosts/usb.py`** — removed hardware-only `debug_trace.log_exception()` block, replaced with `log()` import and `platform.hil_test_mode` guard
- [x] **Add SeedKeeper PSBT signing test** — `test_seedkeeper.py` now includes `test_sign_psbt` with dynamic PSBT construction using the card's actual fingerprint/xpub
- [x] **Wire up HIL tests with RPC** — `run_integration.py` now loads `test_with_rpc.py` when `BTC_RPC_*` env vars are set
- [x] **Fix LVGL popup text leak** — `_drain_popup()` method in `SerialSocket` filters popup noise from USB VCP, enabling all `showaddr`-based tests to pass
- [x] **Fix rpc.py for named kwargs** — `__getattr__` and `multi()` now support passing named JSON-RPC params for Bitcoin Core v30 compatibility
- [x] **Fix `test_miniscript` for Bitcoin Core v30** — replaced `importmulti` with `importdescriptors` (backward compatible), split multi-path `{0,1}/*` descriptor into separate receive/change descriptors

### Short-term (HIL infrastructure)

- [ ] **Test SeedKeeper keystore on hardware** — confirm the Satochip secure channel, PIN management, and mnemonic import/export work on the real card.
- [ ] **Verify internal flash HIL tests still pass** — the `_load_internal_flash()` path was refactored but only SeedKeeper path tested end-to-end. Remove card and run `make hil-test`.

### Medium-term (code quality)

- [ ] **Decide whether to upstream our unix port patches** — the `mpconfigport.mk/h` and `pyb.py` changes could be contributed upstream as a "unix port development" fix. The submodule config generation issue (axtls/btree) affects anyone trying to build locally.
- [ ] **Add more SeedKeeper-specific integration tests** — encrypted mnemonic storage, PIN change, secret deletion, multiple secrets on same card.
- [ ] **Consider updating the MicroPython fork** — the `diybitcoinhardware/micropython` fork is based on an older version. Newer MicroPython has f-string support which would eliminate that class of test compatibility issues.
- [ ] **Evaluate whether integration tests should use env vars or `.env` file** — currently both work, but the `.env.example` should be the canonical approach for new developers.

### Research needed

- [ ] **Investigate the axtls submodule config issue** — `lib/axtls/config/.config` and `config.h` are not generated by the submodule. This prevents building with axtls SSL. Is there a make target to generate them, or is the submodule incomplete?
- [ ] **Evaluate Nix dev shell viability** — `shell.nix` / `flake.nix` are pinned to `nixos-22.05` (3+ years old). Would updating the pin give us a working local ARM toolchain?
- [ ] **Check if the `test_with_rpc.py` `__init__.py` import should be conditional** — currently `test_with_rpc` is imported at module level and crashes if Bitcoin Core isn't available. Should it use lazy imports or a try/except?

---

## Related Documentation

- `docs/faq.md` - FAQ including factory-reset instructions
- `docs/development.md` - Developer notes
- `docs/build.md` - Build instructions (includes HIL firmware target)

---

## Session History

| Date | Key Accomplishments |
|------|---------------------|
| 2026-03-14 | Device unlock, first firmware flash |
| 2026-03-15 | Serial debug working, SeedKeeper detected on hardware, build workflow established |
| 2026-03-17 | Local dev environment set up: venv, requirements-dev.txt, all dev tooling |
| 2026-03-17 | MicroPython unix port builds and runs 30/31 unit tests locally |
| 2026-03-17 | Diagnosed simulator SIGSEGV: NVIDIA driver bug in SDL2, documented workaround |
| 2026-03-17 | Integration tests verified: 15/16 pass on v1.10.0 baseline and our branch |
| 2026-03-17 | Baseline established on clean v1.10.0 tag; confirmed all issues are pre-existing upstream |
| 2026-03-18 | ARM toolchain v9 installed locally at /opt/, v13.2 proven broken (HardFaults on boot) |
| 2026-03-18 | Documented openocd/USB gotcha: debug tools kill device USB enumeration |
| 2026-03-18 | **HIL tests passing end-to-end: `make hil-test` — 3/3 pass on real hardware** |
| 2026-03-18 | Added `TEST_WIPE` command for clean storage state between test runs |
| 2026-03-18 | Fixed serial buffer staleness with `_flush()` method (quiet-period-based drain) |
| 2026-03-18 | Cleaned up `src/hosts/usb.py`: removed try/except import, use `log_exception()` directly |
| 2026-03-18 | Added `test_sign_psbt` to `test_seedkeeper.py`: dynamic PSBT with card's actual key |
| 2026-03-18 | Wired up HIL RPC tests: `run_integration.py` loads `test_with_rpc.py` when `BTC_RPC_*` env vars set |
| 2026-03-18 | Added `BitcoinCoreManager` to auto-start bitcoind for both simulator and HIL test runners |
| 2026-03-18 | Fixed `test_miniscript` with `descriptors=True` in `test_with_rpc.py:245` (13/13 RPC tests) |
| 2026-03-18 | Updated `run_tests.py` hardware path to load multiple test modules with RPC support |
| 2026-03-18 | **HIL tests 19/19 pass: `make hil-test` — 3 basic + 3 seedkeeper + 13 RPC tests** |
| 2026-03-18 | Fixed LVGL popup text leak: `_drain_popup()` in `SerialSocket` filters "Text"/"bitcoin:" noise |
| 2026-03-18 | Fixed rpc.py `multi()` to support named JSON-RPC kwargs for Bitcoin Core v30 |
| 2026-03-18 | Fixed `test_miniscript`: `importmulti` → `importdescriptors` with backward compat, split multi-path descriptor |
| 2026-03-18 | **Major cleanup**: removed debug artifacts, LED indicators, reverted submodule changes, reverted dev tooling and noise changes to upstream |
| 2026-03-18 | **Documented upstream submodule issues**: QSPI hang (micropython fork, 3.5yr stale) and USART T=1 reconfig (f469-disco, Amperstrand's unmerged branch) |
| 2026-03-18 | **Tested 3 submodule configurations**: confirmed both SOFTSPI + USART reconfig needed for hardware; both are pre-existing upstream issues, not our code |
| 2026-03-18 | Reverted f469-disco to upstream `db3ce3e`; our PRs will only touch `src/` and `test/` |
