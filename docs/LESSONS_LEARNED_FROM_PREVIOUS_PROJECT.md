# Lessons Learned from Previous SeedKeeper Integration Project

**Source Location:** `/Users/macbook/src/specter-diy`  
**Target Project:** `/Users/macbook/src/seedkeeperport/specter-diy`  
**Date:** March 9, 2026

---

## Executive Summary

A previous SeedKeeper integration attempt exists in `/Users/macbook/src/specter-diy`. While this project **never successfully implemented the secure channel protocol** required for real SeedKeeper card communication, it contains **invaluable knowledge** about:

1. **Hardware flashing procedures** for STM32F469 Discovery board
2. **Smartcard reader initialization** and pin configurations
3. **Debugging strategies** (LED-only, UART, memory markers, display)
4. **Test firmware patterns** for isolating hardware issues
5. **Build system configuration** for MicroPython firmware

This document consolidates all lessons learned so the `seedkeeperport/specter-diy` project can benefit from this experience.

---

## Table of Contents

1. [What Worked and What Didn't](#1-what-worked-and-what-didnt)
2. [Hardware Configuration](#2-hardware-configuration)
3. [Flashing the Device](#3-flashing-the-device)
4. [Build System](#4-build-system)
5. [Smartcard Communication](#5-smartcard-communication)
6. [Debugging Strategies](#6-debugging-strategies)
7. [Test Firmware Patterns](#7-test-firmware-patterns)
8. [Memory Markers for Debugging](#8-memory-markers-for-debugging)
9. [LED Status Codes](#9-led-status-codes)
10. [UART/Serial Debugging](#10-uartserial-debugging)
11. [Critical Gap: Secure Channel](#11-critical-gap-secure-channel)
12. [Files Worth Salvaging](#12-files-worth-salvaging)
13. [Recommended Testing Workflow](#13-recommended-testing-workflow)

---

## 1. What Worked and What Didn't

### What Worked ✅

| Layer | Status | Evidence |
|-------|--------|----------|
| Card reader initialization | **Working** | `get_reader()` successfully initializes |
| Card presence detection | **Working** | `isCardInserted()` returns correct state |
| T=1 protocol connection | **Working** | `conn.connect(conn.T1_protocol)` succeeds |
| SELECT applet (0xB0 A4 04 00) | **Working** | Returns `0x9000` for SeedKeeper cards |
| LED indicators | **Working** | All 4 LEDs controllable |
| UART output | **Working** | ST-Link VCP at 115200 baud |
| Display output | **Working** | LVGL displays work |
| Memory markers | **Working** | Can write/read at 0x20002000 |

### What Didn't Work ❌

| Operation | Status | Reason |
|-----------|--------|--------|
| VERIFY PIN (plaintext) | **FAILS** | Card requires secure channel |
| LIST_SECRETS (plaintext) | **FAILS** | Card requires secure channel |
| EXPORT_SECRET (plaintext) | **FAILS** | Card requires secure channel |
| Full SeedKeeper workflow | **FAILS** | Missing secure channel implementation |

**Root Cause:** SeedKeeper cards enforce encrypted communication (INS 0x81/0x82) after SELECT. The previous implementation only sent plaintext APDUs, which the card rejects.

---

## 2. Hardware Configuration

### STM32F469 Discovery Board

The Specter DIY uses the STM32F469 Discovery development board with a smartcard reader shield.

### Smartcard Reader Pin Configuration

```python
# From src/keystore/javacard/util.py
import uscard as sc
from pyb import Pin

reader = sc.Reader(
    name="Specter card reader",
    ifaceId=2,           # Smartcard interface 2
    ioPin=Pin.cpu.A2,    # IO pin
    clkPin=Pin.cpu.A4,   # Clock pin
    rstPin=Pin.cpu.G10,  # Reset pin
    presPin=Pin.cpu.C2,  # Card presence detection
    pwrPin=Pin.cpu.C5,   # Power pin
)
```

### LED Assignments (STM32F469 Discovery)

| LED | Color | Pin | Typical Use |
|-----|-------|-----|-------------|
| LED1 | Green | PE3 | Reader initialized |
| LED2 | Orange | PG6 | Card present |
| LED3 | Red | PD4 | T=1 connected |
| LED4 | Blue | PG12 | Applet selected |

### UART Channels

| UART | Pins | Connection |
|------|------|------------|
| UART1 | PA9 (TX), PA10 (RX) | External |
| UART3 | PB10 (TX), PB11 (RX) | **ST-Link VCP** (visible as /dev/ttyACM0) |
| UART6 | PC6 (TX), PC7 (RX) | External |

**Important:** UART3 is internally connected to the ST-Link debugger, so you can see output without additional hardware.

---

## 3. Flashing the Device

### Method 1: Full Build and Flash

```bash
# Build everything (bootloader + firmware)
./build_firmware.sh

# Output files:
#   release/initial_firmware.bin  - Complete firmware with bootloader
#   release/specter_upgrade.bin   - Upgrade package
#   bin/specter-diy.bin           - Just the application firmware
```

### Method 2: Debug Firmware

```bash
# Build debug firmware (uses boot/debug frozen files)
make debug

# Output: bin/debug.bin and bin/debug.hex
```

### Method 3: Standard Firmware

```bash
# Build standard firmware
make disco

# Output: bin/specter-diy.bin and bin/specter-diy.hex
```

### Flashing with ST-Link

```bash
# Using st-flash (Linux/macOS)
st-flash write bin/debug.bin 0x08000000

# Or using OpenOCD
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
    -c "program bin/debug.bin verify reset exit 0x08000000"
```

### Flashing the Full Initial Firmware

```bash
# The initial_firmware.bin includes bootloader
# Flash at address 0x08000000
st-flash write release/initial_firmware.bin 0x08000000
```

---

## 4. Build System

### Makefile Targets

```makefile
make mpy-cross    # Build MicroPython cross-compiler
make disco        # Build main firmware
make debug        # Build debug firmware (uses boot/debug)
make unix         # Build Unix simulator
make simulate     # Run simulator
make clean        # Clean build artifacts
```

### Manifest System

The build uses manifest files to determine which Python files are frozen into the firmware:

```python
# manifests/debug.py
include('../f469-disco/manifests/disco.py')
freeze('../boot/debug')  # Frozen FIRST - contains our main.py
freeze('../src')         # App code frozen AFTER
```

**Key Insight:** Order matters! `boot/debug` is frozen first so its `main.py` takes precedence over `src/main.py`.

### User C Modules

```makefile
USER_C_MODULES ?= ../../../usermods
```

This points to C extensions including:
- `uscard` - Smartcard reader driver
- `secp256k1` - Elliptic curve cryptography
- `ucryptolib` - AES encryption

---

## 5. Smartcard Communication

### Connection Sequence

```python
from keystore.javacard.util import get_reader, get_connection

# Step 1: Get reader (initializes hardware)
reader = get_reader()

# Step 2: Get connection object
conn = get_connection()

# Step 3: Check if card is present
if conn.isCardInserted():
    # Step 4: Connect using T=1 protocol
    conn.connect(conn.T1_protocol)
    
    # Step 5: Send APDUs
    response, sw1, sw2 = conn.sendAPDU(cla, ins, p1, p2, data)
```

### APDU Format

```python
# Standard APDU structure
APDU = [CLA, INS, P1, P2, Lc, Data..., Le]

# For SeedKeeper:
CLA = 0xB0  # SeedKeeper class byte
```

### SeedKeeper AID

```python
SEEDKEEPER_AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
# ASCII: "SeedKeeper"
```

### SELECT Command

```python
# Select the SeedKeeper applet
response, sw1, sw2 = conn.sendAPDU(
    0xB0,           # CLA
    0xA4,           # INS = SELECT
    0x04,           # P1 = select by AID
    0x00,           # P2
    SEEDKEEPER_AID  # Data = AID
)

# Success: sw1=0x90, sw2=0x00
# Not found: sw1=0x6A, sw2=0x82
```

### Status Words

| SW1 | SW2 | Meaning |
|-----|-----|---------|
| 0x90 | 0x00 | Success |
| 0x6A | 0x82 | Applet not found |
| 0x63 | 0x0X | Wrong PIN, X attempts remaining |
| 0x69 | 0x83 | Card locked (no PIN attempts) |
| 0x9C | 0x12 | End of list |
| 0x9C | 0x30 | Lock error |
| 0x9C | 0x08 | Secret not found |
| 0x9C | 0x31 | Export not allowed |

---

## 6. Debugging Strategies

The previous project developed **four complementary debugging approaches**:

### Strategy 1: LED-Only Debugging
- **File:** `boot/debug/led_card_test.py`
- **Use when:** No serial connection available
- **How:** Each LED represents a step; patterns indicate errors

### Strategy 2: UART Debugging
- **File:** `boot/debug/uart_card_test.py`, `boot/debug/uart3_card_test.py`
- **Use when:** ST-Link VCP available
- **How:** Detailed log output to /dev/ttyACM0 at 115200 baud

### Strategy 3: Display Debugging
- **File:** `boot/debug/card_test_display.py`
- **Use when:** Device display is working
- **How:** Status text on screen with LVGL

### Strategy 4: Memory Marker Debugging
- **File:** `boot/debug/proof_card.py`
- **Use when:** Need to debug without any output
- **How:** Write state to RAM address 0x20002000, read with debugger

---

## 7. Test Firmware Patterns

### Minimal Boot Test

```python
# boot/debug/minimal_boot_test.py
# Just blinks LEDs - proves firmware boots

from pyb import LED
import time

leds = [LED(i) for i in range(1, 5)]
for led in leds:
    led.off()

while True:
    for led in leds:
        led.on()
        time.sleep_ms(200)
        led.off()
        time.sleep_ms(100)
```

**Use case:** First test after flashing - confirms firmware boots and LEDs work.

### Card Detection Test

```python
# Pattern from boot/debug/led_card_test.py

# Step 1: Initialize reader
from keystore.javacard.util import get_reader, get_connection
led1.on()  # Green = reader OK

# Step 2: Check card presence
conn = get_connection()
if conn.isCardInserted():
    led2.on()  # Orange = card present

# Step 3: Connect T=1
conn.connect(conn.T1_protocol)
led3.on()  # Red = T=1 connected

# Step 4: Select applet
response, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, AID)
if sw1 == 0x90 and sw2 == 0x00:
    led4.on()  # Blue = applet found
```

### Full Diagnostic Test

```python
# Pattern from boot/debug/seedkeeper_test.py
# GUI-based test with menu system

from gui.specter import SpecterGUI
import asyncio

class SeedKeeperTest:
    def __init__(self):
        self.gui = SpecterGUI()
    
    async def full_diagnostic(self):
        results = []
        
        # Test 1: Reader
        try:
            reader = get_reader()
            results.append(("Reader Init", "PASS"))
        except Exception as e:
            results.append(("Reader Init", "FAIL"))
            return
        
        # Test 2: Card presence
        conn = get_connection()
        if conn.isCardInserted():
            results.append(("Card Present", "PASS"))
        else:
            results.append(("Card Present", "FAIL - No card"))
            return
        
        # Test 3: T=1 connection
        conn.connect(conn.T1_protocol)
        results.append(("T=1 Protocol", "PASS"))
        
        # Test 4: Applet selection
        response, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, AID)
        if sw1 == 0x90 and sw2 == 0x00:
            results.append(("SeedKeeper Applet", "PASS"))
        
        # Show results
        await self.show_results(results)
```

---

## 8. Memory Markers for Debugging

When no output is available, use memory markers to track execution state:

```python
# From boot/debug/proof_card.py

MARK_BASE = 0x20002000
MARK_MAGIC = 0x534B5052  # "SKPR" in ASCII

STATE_BOOT = 0x1001
STATE_OUTPUTS_READY = 0x1002
STATE_UTIL_OK = 0x1010
STATE_CONN_OK = 0x1020
STATE_NO_CARD = 0x1030
STATE_CARD_PRESENT = 0x1040
STATE_T1_OK = 0x1050
STATE_SELECT_DONE = 0x1060
STATE_SUCCESS = 0x9000

ERR_OUTPUT_SETUP = 0xE001
ERR_IMPORT_UTIL = 0xE010
ERR_GET_CONNECTION = 0xE020
ERR_CARD_CHECK = 0xE030
ERR_T1_CONNECT = 0xE040
ERR_SELECT = 0xE050

def write_marker(state, arg0, arg1):
    """Write state to RAM for debugger to read."""
    try:
        import stm
        stm.mem32[MARK_BASE] = MARK_MAGIC
        stm.mem32[MARK_BASE + 4] = state
        stm.mem32[MARK_BASE + 8] = arg0
        stm.mem32[MARK_BASE + 12] = arg1
    except:
        import machine
        machine.mem32[MARK_BASE] = MARK_MAGIC
        machine.mem32[MARK_BASE + 4] = state
        machine.mem32[MARK_BASE + 8] = arg0
        machine.mem32[MARK_BASE + 12] = arg1

# Usage:
write_marker(STATE_BOOT, 0, 0)
# ... do stuff ...
write_marker(STATE_T1_OK, attempt, 1)
```

**Reading with debugger:**
```bash
# Using OpenOCD/GDB
(gdb) x/4wx 0x20002000
0x20002000: 0x534b5052 0x00001050 0x00000001 0x00000001
#            MAGIC       STATE      ARG0       ARG1
```

---

## 9. LED Status Codes

### Success Pattern (All 4 LEDs ON)

| LED | Meaning |
|-----|---------|
| LED1 (Green) | Reader initialized |
| LED2 (Orange) | Card present |
| LED3 (Red) | T=1 connected |
| LED4 (Blue) | Applet selected |

### Error Patterns

| Pattern | Meaning |
|---------|---------|
| LED3 rapid blink | Module import failed |
| LED2 slow pulse | No card detected |
| LED2+LED3 alternating | Card check failed |
| LED3+LED4 alternating | Applet selection failed |
| LED4 slow blink | Applet not found (0x6A82) |
| All LEDs flash | Boot indicator |

### Test Progression

```
Boot → [Flash all 3x]
      ↓
LED1 ON → Reader OK
      ↓
LED2 ON → Card present
      ↓
LED3 ON → T=1 connected
      ↓
LED4 ON → Applet found (SUCCESS!)
```

---

## 10. UART/Serial Debugging

### Connection

```bash
# Connect to ST-Link VCP
screen /dev/ttyACM0 115200

# Or with minicom
minicom -D /dev/ttyACM0 -b 115200

# Or with picocom
picocom /dev/ttyACM0 -b 115200
```

### Python UART Setup

```python
from pyb import UART

# UART3 is connected to ST-Link VCP
uart = UART(3, 115200)
uart.init(115200, bits=8, parity=None, stop=1)

def log(msg):
    uart.write(msg + "\r\n")
    uart.flush()

log("Debug message here")
```

### Log Format

```
==================================================
SeedKeeper Card Detection Test
==================================================

[STEP 1] Loading smartcard module...
         OK - Module loaded
[STEP 2] Getting reader...
         OK - Reader initialized
[STEP 3] Checking card presence...
         *** CARD PRESENT! ***
[STEP 4] Connecting T=1 protocol...
         OK - T=1 connected
[STEP 5] Selecting SeedKeeper applet...
         SW1=0x90 SW2=0x00
         
==================================================
SUCCESS! SEEDKEEPER APPLET FOUND!
==================================================
```

---

## 11. Critical Gap: Secure Channel

### The Problem

The previous implementation could:
- ✅ Detect the card
- ✅ Connect via T=1 protocol
- ✅ SELECT the SeedKeeper applet (returns 0x9000)

But it could NOT:
- ❌ Verify PIN
- ❌ List secrets
- ❌ Export secrets

### Why It Failed

After SELECT, the SeedKeeper card **requires encrypted communication**. All subsequent commands must be sent via the secure channel:

| Command | Plaintext | Encrypted |
|---------|-----------|-----------|
| SELECT (0xA4) | ✅ Works | N/A |
| VERIFY_PIN (0x42) | ❌ Rejected | ✅ Required |
| LIST_SECRETS (0xA6) | ❌ Rejected | ✅ Required |
| EXPORT_SECRET (0xA2) | ❌ Rejected | ✅ Required |

### Secure Channel Protocol

The secure channel uses:
1. **INS 0x81** - Initialize secure channel (ECDH key exchange)
2. **INS 0x82** - Send encrypted command

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURE CHANNEL FLOW                      │
├─────────────────────────────────────────────────────────────┤
│  1. SELECT applet (plaintext)                               │
│     └─ Returns 0x9000                                       │
│                                                             │
│  2. INIT_SECURE_CHANNEL (INS 0x81)                          │
│     ├─ Device generates ephemeral keypair                   │
│     ├─ Sends public key to card                            │
│     ├─ Card returns its public key                         │
│     ├─ Both compute ECDH shared secret                     │
│     ├─ Derive AES key: HMAC-SHA1(secret, "sc_key")[:16]    │
│     └─ Derive MAC key: HMAC-SHA1(secret, "sc_mac")         │
│                                                             │
│  3. All subsequent commands via INS 0x82:                   │
│     ├─ Pad inner APDU with PKCS#7                          │
│     ├─ Encrypt with AES-CBC                                │
│     ├─ Compute HMAC-SHA1(IV || len(ct) || ct)              │
│     └─ Send: IV + ciphertext + MAC                         │
└─────────────────────────────────────────────────────────────┘
```

### Implementation in seedkeeperport

The `seedkeeperport/specter-diy` project HAS implemented the secure channel:

```python
# src/keystore/javacard/applets/seedkeeper_securechannel.py

class SeedKeeperSecureChannel:
    def initiate(self, connection, cla=0xB0):
        # 1. Generate ephemeral keypair
        secret = get_random_bytes(32)
        pubkey = secp256k1.ec_pubkey_create(secret)
        
        # 2. Send INIT_SC APDU (INS 0x81)
        apdu = bytes([cla, 0x81, 0x00, 0x00, 0x41]) + pub_bytes
        data = connection.transmit(apdu)
        
        # 3. Compute ECDH shared secret
        shared_secret = secp256k1.ec_pubkey_tweak_mul(card_pubkey, secret)
        
        # 4. Derive keys
        self.aes_key = hmac_sha1(shared_secret, b'sc_key')[:16]
        self.mac_key = hmac_sha1(shared_secret, b'sc_mac')
        self.is_initialized = True
```

**This is the critical missing piece that specter-diy lacked.**

---

## 12. Files Worth Salvaging

### Copy These to seedkeeperport/specter-diy

| Source File | Destination | Value |
|-------------|-------------|-------|
| `boot/debug/proof_card.py` | `boot/debug/proof_card.py` | Memory marker debugging |
| `boot/debug/led_card_test.py` | `boot/debug/led_card_test.py` | LED-only testing |
| `boot/debug/uart3_card_test.py` | `boot/debug/uart3_card_test.py` | UART debugging |
| `boot/debug/card_test_display.py` | `boot/debug/card_test_display.py` | Display testing |
| `boot/debug/seedkeeper_test.py` | `boot/debug/seedkeeper_test.py` | GUI diagnostic (needs SC update) |
| `manifests/debug.py` | `manifests/debug.py` | Debug build manifest |

### Update Required

The `seedkeeper_test.py` needs to be updated to use the secure channel:

```python
# After selecting applet, add:
from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet

applet = SeedKeeperApplet(conn)
applet.init_secure_channel()  # <-- Add this

# Now can use encrypted commands
status = applet.get_seedkeeper_status()
```

---

## 13. Recommended Testing Workflow

### Phase 1: Hardware Verification (No Card)

1. Flash `minimal_boot_test.py`
2. Verify LEDs blink in sequence (1-2-3-4)
3. Confirms firmware boots and LEDs work

### Phase 2: Card Detection

1. Flash `led_card_test.py`
2. Insert SeedKeeper card
3. Watch LED progression:
   - LED1 ON = Reader OK
   - LED2 ON = Card present
   - LED3 ON = T=1 connected
   - LED4 ON = Applet found

### Phase 3: UART Debugging

1. Flash `uart3_card_test.py`
2. Connect to /dev/ttyACM0 at 115200
3. Watch detailed log output
4. Verify all steps complete

### Phase 4: Secure Channel Testing

1. Flash debug firmware with secure channel code
2. Use `proof_card.py` with memory markers
3. Verify secure channel initialization
4. Test PIN verification
5. Test secret export

### Phase 5: Full Integration

1. Flash main firmware with SeedKeeper keystore
2. Navigate to Settings > KeyStore > SeedKeeper
3. Complete full workflow:
   - Card detection
   - Secure channel establishment
   - PIN entry
   - Secret loading
   - Wallet operations

---

## Appendix A: Quick Reference Commands

```bash
# Build debug firmware
make debug

# Flash to device
st-flash write bin/debug.bin 0x08000000

# Connect to serial
screen /dev/ttyACM0 115200

# Read memory markers (with debugger attached)
# In GDB: x/4wx 0x20002000

# Clean and rebuild
make clean && make debug
```

---

## Appendix B: Common Issues and Solutions

| Issue | Likely Cause | Solution |
|-------|--------------|----------|
| No LEDs light up | Firmware not booting | Check flash address (0x08000000) |
| LED1 never turns on | Smartcard module import failed | Check uscard module is compiled |
| LED2 never turns on | Card not detected | Check card presence pin (C2) |
| LED3 never turns on | T=1 connection fails | Check smartcard interface timing |
| LED4 blinks (not solid) | Applet not found (0x6A82) | Not a SeedKeeper card |
| Commands fail after SELECT | Missing secure channel | Use seedkeeperport implementation |

---

## Appendix C: File Locations

```
specter-diy/
├── boot/
│   └── debug/                    # Test firmware files
│       ├── boot.py               # Debug boot script
│       ├── main.py               # Debug main loop
│       ├── minimal_boot_test.py  # LED-only boot test
│       ├── led_card_test.py      # LED card detection
│       ├── uart_card_test.py     # UART debugging
│       ├── uart3_card_test.py    # UART3 to ST-Link
│       ├── card_test_display.py  # Display + LEDs
│       ├── seedkeeper_test.py    # GUI diagnostic
│       └── proof_card.py         # Memory marker test
├── manifests/
│   └── debug.py                  # Debug manifest
├── src/
│   └── keystore/
│       ├── seedkeeper.py         # Keystore (needs secure channel)
│       └── javacard/
│           ├── util.py           # Reader/connection helpers
│           └── applets/
│               ├── applet.py     # Base applet class
│               └── seedkeeper.py # Applet (needs secure channel)
├── release/
│   └── initial_firmware.bin      # Built firmware
├── bin/
│   ├── debug.bin                 # Debug build output
│   └── specter-diy.bin           # Main build output
├── Makefile                      # Build targets
└── build_firmware.sh             # Full build script
```

---

## Summary

The previous `specter-diy` project made significant progress on **hardware integration and debugging infrastructure**, but failed to implement the **secure channel protocol** required for actual SeedKeeper communication.

The key lessons are:

1. **Hardware works** - Card detection, T=1 connection, and SELECT all succeed
2. **Debugging is solid** - Multiple strategies for different scenarios
3. **Secure channel is essential** - Without it, no meaningful operations are possible
4. **seedkeeperport has the missing piece** - The secure channel implementation there is complete

By combining the hardware knowledge from `specter-diy` with the secure channel from `seedkeeperport/specter-diy`, a fully working SeedKeeper integration is achievable.
