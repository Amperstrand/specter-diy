# Hardware Validation State - 2026-03-14

## Session Summary

### What Was Accomplished

1. **Branch Structure Established**
   - Created `satochip-dev` branch from `satochip`
   - Organized uncommitted work into 9 proper commits:
     - feat(debug): Debug tracing infrastructure
     - fix(seedkeeper): Crash handling and multi-secret flow
     - test(seedkeeper): Unit tests
     - feat(devboot): Unsigned bootloader dev workflow
     - test(hil): Hardware-in-loop testing infrastructure
     - chore: Development tooling
     - docs: Development workflow documentation
     - chore: Gitignore and cleanup

2. **Remote Host Setup**
   - Connected to `ubuntu@192.168.13.246`
   - Verified st-flash v1.8.0 available
   - Verified /dev/ttyACM0 present (ST-Link VCP)
   - Docker available (requires sudo)

3. **Firmware Build & Flash**
   - Synced source code to remote
   - Built firmware with `make disco USE_DBOOT=1`
   - Mass erased device (was write-protected from previous bootloader)
   - Successfully flashed `initial_firmware_devboot_unsigned.bin`

4. **Trace Monitoring Setup**
   - Started background capture on /dev/ttyACM0
   - No output captured yet (baud rate or firmware output issue)

### What Was NOT Completed

1. **Hardware Testing**
   - No manual testing performed on device
   - SeedKeeper card flow not validated
   - PIN verification not tested
   - Mnemonic loading not tested

2. **Serial Trace**
   - No debug output captured
   - Possible baud rate mismatch (tried 9600, 115200)
   - May need firmware configuration check

### Key Discoveries

1. **Write Protection Issue**
   - Device had RDP protection from previous bootloader
   - Requires `st-flash --connect-under-reset erase` before flashing
   - This is expected behavior for bootloader-protected devices

2. **Iteration Speed**
   - Full rebuild: 5-10 min
   - Incremental build: 30-60 sec
   - SD card upgrade: 30-60 sec (no st-flash needed)
   - **Recommended**: Use SD upgrade method for iterations

### Files Modified

| File | Change |
|------|--------|
| `src/debug_trace.py` | New debug tracing module |
| `src/keystore/seedkeeper.py` | Crash fixes, multi-secret support |
| `src/keystore/memorycard.py` | Debug trace integration |
| `src/specter.py` | Error handling improvements |
| `bootloader/core/bootloader.c` | ALLOW_UNSIGNED_UPGRADE support |
| `bootloader/keys/dev_unsigned/pubkeys.c` | Dev key profile |
| `build_firmware.sh` | devboot-* actions |
| `docs/build.md` | Dev workflow documentation |

### Branch State

```
master
  └── satochip (clean - SeedKeeper feature work)
       └── satochip-dev (messy - dev infra, testing)
```

### Remote Host State

| Item | State |
|------|-------|
| Connection | ✅ Working |
| st-flash | ✅ v1.8.0 |
| /dev/ttyACM0 | ✅ Present |
| Docker | ✅ Available (sudo) |
| Firmware | ✅ Built |
| Device | ✅ Flashed |
| Trace capture | ⚠️ No output |

### Next Steps

1. **Manual Testing Required**
   - User must test device and describe screen contents
   - Navigate to SeedKeeper option
   - Test PIN entry and mnemonic loading

2. **Trace Investigation**
   - Check boot.py UART configuration
   - Verify firmware outputs to correct UART
   - Try different baud rates

3. **Iteration Testing**
   - Make a code change
   - Use SD upgrade method
   - Verify faster iteration cycle

## Lessons Learned

1. **Always mass erase** when device was previously protected
2. **Use SD upgrade method** for fast iterations (avoid st-flash)
3. **Serial trace may need configuration** - not all firmware builds output to UART
4. **Branch organization** - keeping dev work separate from clean feature work is valuable

## Artifacts

- `release/initial_firmware_devboot_unsigned.bin` - One-time flash bundle
- `release/specter_upgrade_dev_unsigned.bin` - SD card upgrade file
- `bootloader/build/stm32f469disco/bootloader/release/bootloader.hex` - Unsigned bootloader
