# Development Workflow - Quick Iteration

This document describes how to set up a fast development cycle on the STM32F469IDISCOVERY board without read/write protections that would slow down debugging.

## Overview

For development, we use **unlocked firmware** with:
- **RDP Level 0** - no read protection, JTAG/SWD fully accessible
- **No write protection** - flash can be erased/written freely
- **Dev/test keys** - signatures not required for upgrades

## Quick Start

### Option A: Firmware Without Bootloader (Fastest)

Direct flash without secure bootloader - best for rapid iteration:

```sh
# Build
./build_firmware.sh nobootloader

# Flash
st-flash --reset write release/disco-nobootloader.bin 0x08000000
```

### Option B: Bootloader + Unsigned Upgrades

Keeps bootloader layout for testing upgrade flow:

```sh
# One-time setup
./build_firmware.sh devboot-init

# Flash initial firmware
st-flash --reset write release/initial_firmware_devboot_unsigned.bin 0x08000000

# For each code change, rebuild upgrade:
./build_firmware.sh devboot-upgrade

# Copy to SD card and reboot device
cp release/specter_upgrade_dev_unsigned.bin /path/to/sd/specter_upgrade.bin
```

## Build Commands Reference

| Command | Description | Protection |
|---------|-------------|------------|
| `./build_firmware.sh nobootloader` | Plain firmware, no bootloader | None |
| `./build_firmware.sh devboot-init` | Bootloader + firmware | None (RDP=0, WP=0) |
| `./build_firmware.sh devboot-upgrade` | Unsigned upgrade only | N/A |
| `make disco` | Plain firmware (alias) | None |
| `make disco USE_DBOOT=1` | Firmware for bootloader | N/A |

## Flashing Methods

### st-flash (Recommended)

```sh
# Erase and flash
st-flash --reset erase
st-flash --reset write release/disco-nobootloader.bin 0x08000000
```

### OpenOCD

```sh
# From bootloader directory
openocd -f openocd.cfg -c "program release/disco-nobootloader.bin 0x08000000 reset exit"
```

### DFU (Mass Storage)

1. Connect mini USB (ST-LINK port)
2. Copy `.bin` file to `F469NI_DISCO` volume
3. Wait for disconnect

## Debugging

### Serial Console

The firmware outputs debug messages via USB CDC:

```sh
# Connect to ST-LINK VCP or MicroPython USB
screen /dev/ttyACM0 115200

# Or with minicom
minicom -D /dev/ttyACM0
```

### OpenOCD Debug

```sh
# Start OpenOCD
cd bootloader && openocd -f openocd.cfg

# In another terminal, start GDB
arm-none-eabi-gdb
(gdb) target remote :3333
(gdb) monitor reset halt
(gdb) continue
```

## Unlocking a Locked Device

If the device has RDP Level 1 or write protection enabled:

### Method 1: st-flash (Simplest)

```sh
st-flash --reset erase
```

This performs a mass erase which removes RDP and write protections.

### Method 2: OpenOCD

```sh
cd bootloader
openocd -f openocd.cfg -f ocd-unlock.cfg
```

### Method 3: STM32CubeProgrammer (GUI)

1. Connect via ST-LINK
2. Click "OB" (Option Bytes)
3. Set "Read Out Protection" to "AA"
4. Check ALL boxes in "Write Protection"
5. Click Apply

**Warning:** RDP Level 2 is irreversible. Never use `READ_PROTECTION=2` for development.

## Troubleshooting

### USB Not Enumerating

If firmware runs but no USB CDC device appears:

1. **Check QSPI flash** - firmware may be stuck in QSPI initialization
2. **SOFTSPI mode enabled** - `MICROPY_F469DISC_USE_SOFTSPI` is now enabled in `mpconfigboard.h` to bypass QSPI
3. **Check USB pins** - ensure PA9/PA10/PA11/PA12 are not conflicting

To disable SOFTSPI and use QSPI again, comment out the define in:
`f469-disco/micropython/ports/stm32/boards/STM32F469DISC/mpconfigboard.h`

### Device Stuck After Flash

1. Verify flash was written correctly:
   ```sh
   st-flash read dump.bin 0x08000000 0x10000
   hexdump -C dump.bin | head
   ```

2. Check if firmware is running:
   ```sh
   openocd -f openocd.cfg -c "halt; reg pc; resume; exit"
   ```

### Cannot Connect to Device

1. Try under-reset: hold RESET button, start OpenOCD, release RESET
2. Check ST-LINK connection (LED should be on)
3. Try different USB cable

## Protection State Reference

| OPTCR Value | Meaning |
|-------------|---------|
| `0x0FFFFF...` | No protection (all bits set) |
| `0x4FFEAAED` | PCROP enabled, some sectors write-protected |
| RDP byte `0xAA` | Level 0 (unprotected) |
| RDP byte `0xFE` | Level 1 (protected, recoverable) |
| RDP byte `0xFC` | Level 2 (permanent, irreversible) |

## Related Documentation

- [Build instructions](./build.md)
- [Removing protections](../bootloader/doc/remove_protection.md)
- [Self-signed firmware](../bootloader/doc/selfsigned.md)
