# SeedKeeper Test Matrix - Status Report

## Summary

**Status**: Firmware builds complete, hardware testing blocked

**Blocker**: The build server (192.168.13.246) has the F469-Discovery board connected but does NOT have the Specter Shield with smart card slot. The SeedKeeper communication requires the physical smart card to be inserted in the shield's card reader.

## Completed Work

### Wave 1: Conditional Compile Guards ✅

Added 3 conditional compile flags to the smart card stack:

| Flag | Purpose | Files Modified |
|------|---------|----------------|
| `SCARD_FIX_HALFDUPLEX` | Half-duplex UART mode, removes echo byte tracking | `scard_io.c`, `scard_io.h` |
| `SCARD_FIX_T1_RECONFIG` | T=1 protocol reconfiguration (stop bits 1.5→1, GT 16→1) | `scard_io.c` |
| `SCARD_FIX_PPS` | Smart PPS negotiation (skip if card in specific mode or default params) | `t1_protocol.c` |

### Wave 2: Build All 8 Variants ✅

All 8 firmware variants built successfully:

| Variant | Flags | Size | Expected |
|---------|-------|------|----------|
| V0_baseline | (none) | 1,507,312 bytes | FAIL (baseline) |
| V1_pps | PPS | 1,507,312 bytes | ? |
| V2_t1reconfig | T1_RECONFIG | 1,507,312 bytes | ? |
| V3_halfduplex | HALFDUPLEX | 1,507,312 bytes | ? |
| V4_t1_pps | T1_RECONFIG + PPS | 1,507,312 bytes | ? |
| V5_hd_pps | HALFDUPLEX + PPS | 1,507,312 bytes | ? |
| V6_hd_t1 | HALFDUPLEX + T1_RECONFIG | 1,507,312 bytes | ? |
| V7_all | ALL | 1,507,312 bytes | PASS (current working) |

Binaries stored at: `/home/ubuntu/seedkeeperonly/bin/variants/`

### Wave 2: Test Scripts ✅

Created test automation scripts:
- `tools/run_variant_test.sh` - Test a single variant
- `tools/run_all_variants.sh` - Run all 8 variants with power cycle reminders

## Blocked Work

### Wave 3: Hardware Testing ⏸️

**Requirement**: Specter Shield with SeedKeeper card inserted

**How to proceed**:
1. Connect Specter Shield to F469-Discovery board via Arduino headers
2. Insert SeedKeeper card into shield's smart card slot
3. Connect both USB cables (ST-LINK for flashing, USB for debug)
4. Run: `./tools/run_all_variants.sh`

**Important**: Power cycle the board between variants (unplug/replug both USB cables) because USART configuration persists across resets.

### Wave 4: Analysis & Gist ⏸️

Blocked until hardware test results are available.

## Files Modified

### Local Repository (specter-diy-seedkeeperonly)

```
f469-disco/usermods/scard/ports/stm32/scard_io.c    - Added HALFDUPLEX and T1_RECONFIG guards
f469-disco/usermods/scard/ports/stm32/scard_io.h    - Added HALFDUPLEX guard for skip_bytes member
f469-disco/usermods/scard/t1_protocol/t1_protocol.c - Added PPS guard in handle_atr()
src/keystore/seedkeeper.py                          - Added ATR logging on connect
tools/run_variant_test.sh                           - New: single variant test script
tools/run_all_variants.sh                           - New: all variants test script
```

### Build Server (192.168.13.246)

```
/home/ubuntu/seedkeeperonly/bin/variants/V0_baseline.bin
/home/ubuntu/seedkeeperonly/bin/variants/V1_pps.bin
/home/ubuntu/seedkeeperonly/bin/variants/V2_t1reconfig.bin
/home/ubuntu/seedkeeperonly/bin/variants/V3_halfduplex.bin
/home/ubuntu/seedkeeperonly/bin/variants/V4_t1_pps.bin
/home/ubuntu/seedkeeperonly/bin/variants/V5_hd_pps.bin
/home/ubuntu/seedkeeperonly/bin/variants/V6_hd_t1.bin
/home/ubuntu/seedkeeperonly/bin/variants/V7_all.bin
```

## Build Commands

```bash
# Build a specific variant
cd /home/ubuntu/seedkeeperonly
sudo docker run --rm -v /home/ubuntu/seedkeeperonly:/app -w /app specter24d bash -c \
  'make disco USE_DBOOT=0 DEBUG=0 EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS"'

# Flash to board
sudo st-flash --reset write bin/specter-diy.bin 0x8000000

# Capture debug output (on ttyACM1 after reset)
sudo stty -F /dev/ttyACM1 115200 raw -echo
timeout 30 sudo cat /dev/ttyACM1
```

## Hardware Requirements

To complete the test matrix, you need:

1. **F469-Discovery board** (STM32F469NI)
2. **Specter Shield** (extension board with smart card slot)
3. **SeedKeeper card** (inserted in the shield's smart card slot)
4. **miniUSB cable** (for ST-LINK flashing)
5. **microUSB cable** (for USB debug output)

The smart card communication uses the STM32's USART in smartcard mode, connected via the shield's Arduino headers to a smart card slot.
