# Hardware Validation Guide - SeedKeeper Support

## Overview

This document describes the hardware validation process for SeedKeeper support on STM32F469DISCO devices.

## Prerequisites

- STM32F469DISCO board with ST-Link connected
- SeedKeeper smartcard
- Remote host with st-flash and Docker installed
- Serial console access (optional, for debug trace)

## Fast Iteration Workflow

### One-Time Setup (5-10 min)

```bash
# On remote host (ubuntu@192.168.13.246)
cd ~/specter-diy-fresh

# Mass erase if device was previously protected
st-flash --connect-under-reset erase

# Flash initial firmware bundle
st-flash --connect-under-reset write release/initial_firmware_devboot_unsigned.bin 0x08000000
```

### Iterative Development Cycle (30-60 sec per iteration)

```bash
# 1. Sync code changes
rsync -avz -e "ssh" src/ ubuntu@192.168.13.246:~/specter-diy-fresh/src/

# 2. Incremental build (NO clean!)
ssh ubuntu@192.168.13.246 "cd ~/specter-diy-fresh && sudo docker run --rm -v \$PWD:/app -w /app specter24d make disco USE_DBOOT=1"

# 3. Generate upgrade file
ssh ubuntu@192.168.13.246 "cd ~/specter-diy-fresh && python3 ./bootloader/tools/upgrade-generator.py gen -f ./bin/specter-diy.hex -p stm32f469disco ./release/specter_upgrade_dev_unsigned.bin"

# 4. Copy to SD card as specter_upgrade.bin
# 5. Reboot device → bootloader auto-upgrades
```

## SeedKeeper Validation Steps

### 1. Card Detection

1. Insert SeedKeeper card into smartcard reader
2. Navigate to Settings → Keystore
3. Verify "SeedKeeper" appears as an option
4. Select "Load key from SeedKeeper"

**Expected**: Device prompts for PIN with anti-phishing words

### 2. PIN Verification

1. Note the anti-phishing words displayed
2. Enter SeedKeeper PIN using touchscreen
3. Verify PIN is accepted

**Expected**: 
- Correct PIN: Proceeds to secret selection
- Wrong PIN: Shows "X of 5 attempts remaining"
- 5 failed attempts: Device bricks (permanent)

### 3. Mnemonic Loading

1. If multiple secrets on card, select one from menu
2. Wait for "Loading mnemonic from card..." message
3. Verify success alert appears

**Expected**: "Success! Your key is loaded." alert

### 4. PSBT Signing (Optional)

1. Load a PSBT transaction
2. Navigate to signing menu
3. Verify transaction details
4. Confirm signing

**Expected**: Signed PSBT returned

## Debug Trace Monitoring

The firmware outputs debug traces via:
- USB VCP (Virtual COM Port)
- ST-Link UART (9600 baud by default)

### Start Trace Capture

```bash
# On remote host
nohup cat /dev/ttyACM0 > /tmp/trace.log 2>&1 &
echo $! > /tmp/trace.pid

# View trace
tail -f /tmp/trace.log
```

### Key Trace Messages

```
[SeedKeeper] Checking availability...
[SeedKeeper] Card inserted: True
[SeedKeeper] PIN verified successfully
[SeedKeeper] Found N BIP39 secrets
[SeedKeeper] Selected secret id: X
[SeedKeeper] Mnemonic loaded successfully
```

## Troubleshooting

### Flash Write Protected

```
ERROR common_flash.c: Flash memory is write protected
```

**Solution**: Mass erase first
```bash
st-flash --connect-under-reset erase
```

### No Serial Output

1. Check baud rate (try 9600 and 115200)
2. Verify /dev/ttyACM0 exists
3. Check firmware has debug_trace enabled

### Card Not Detected

1. Verify card is fully inserted
2. Check smartcard reader connection
3. Try reinserting card

## Build Commands Reference

| Command | Purpose | Time |
|---------|---------|------|
| `make clean` | Full clean | 5 sec |
| `make disco USE_DBOOT=1` | Incremental build | 30-60 sec |
| `make disco` | Build without bootloader | 30-60 sec |
| `./build_firmware.sh devboot-init` | Full dev setup | 5-10 min |
| `./build_firmware.sh devboot-upgrade` | Fast upgrade build | 1-2 min |
| `./build_firmware.sh devboot-check` | Validate artifacts | 5 sec |

## Validation Checklist

- [ ] Device boots to main menu
- [ ] SeedKeeper option visible in keystore menu
- [ ] Card detection works
- [ ] PIN prompt with anti-phishing words appears
- [ ] PIN verification succeeds
- [ ] Mnemonic loads from card
- [ ] Success alert displays
- [ ] (Optional) PSBT signing works
- [ ] Trace output visible on serial console
