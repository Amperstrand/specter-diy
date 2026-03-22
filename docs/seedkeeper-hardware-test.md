# SeedKeeper Hardware Installation Test

## Prerequisites

- STM32F469-Discovery board with Specter-DIY firmware (gp-repl-tests branch)
- JCOP4 JavaCard with GP default keys (404142...4F)
- USB cable for device connection
- mpremote installed (`pip install mpremote`)

## Step 1: Build and Flash Firmware

```bash
cd /Users/macbook/src/seedkeeperport/specter-diy
git checkout gp-repl-tests
make clean
make
# Flash with st-link or copy to device
```

## Step 2: Copy SeedKeeper DGP to Device

```bash
# DGP file was generated at /tmp/SeedKeeper.dgp
# Or regenerate:
python3 tools/cap_to_dgp.py ~/src/seedkeeperport/Seedkeeper-Applet/SeedKeeper-v0.2-0.1.cap /tmp/SeedKeeper.dgp

# Copy to device
mpremote cp /tmp/SeedKeeper.dgp :/flash/gp/

# Also copy TeapotApplet.dgp if not already present (for basic GP test)
```

## Step 3: Run Hardware Test via REPL

```bash
# Connect to device REPL
mpremote connect /dev/ttyACM1

# Run the GP test
>>> exec(open("/flash/gp/test_gp_flow.py").read())
```

Expected output:
```
==================================================
GP Card Management Hardware Test
==================================================

--- Test 1: SCP02 Session ---
[PASS] Card present          ATR: 3bd518ff8191fe1fc38073c821100a
[PASS] SCP02 session

--- Test 2: GET STATUS ---
[PASS] GET STATUS parsed
[PASS] ISD lifecycle         LC=07
[PASS] ISD privileges        9e
[PASS] Apps found            1 entries
[PASS] Load files found      1 entries
[PASS] Packages found        1 entries

--- Test 3: AID Lookup ---
[PASS] SatoChip found
[PASS] MemoryCard absent
[PASS] TeapotApplet pre-check  installed=False

--- Test 4: INSTALL FOR LOAD ---
[PASS] INSTALL for load

--- Test 5: LOAD CAP ---
[PASS] CAP file loaded       7644 bytes from /flash/gp/TeapotApplet.dgp
[PASS] LOAD CAP              7644 bytes in 30 blocks, 7829 ms

--- Test 6: INSTALL FOR INSTALL ---
[PASS] INSTALL for install

--- Test 7: Verify Installation ---
[PASS] TeapotApplet installed

--- Test 8: DELETE ---
[PASS] DELETE instance       SW=9000
[PASS] DELETE package        SW=9000

--- Test 9: Verify Deletion ---
[PASS] TeapotApplet removed

--- Test 10: SeedKeeper Install ---
[PASS] SeedKeeper DGP loaded  18641 bytes
[PASS] SeedKeeper install     18641 bytes in 74 blocks, XXXXX ms
[PASS] SeedKeeper verified
       SeedKeeper left installed for keystore use

==================================================
Results: XX/XX passed, 0 failed
ALL TESTS PASSED
==================================================
```

## Step 4: Test via GUI

1. Boot device normally
2. Go to: Settings → Developer → JavaCard Provisioning
3. Select "Install SeedKeeper"
4. Confirm the installation prompt
5. Wait for "Done!" message

## Step 5: Verify SeedKeeper Keystore

After installation, the SeedKeeper keystore should be usable:

1. Reboot device
2. Insert the card
3. Device should detect SeedKeeper and offer to use it as keystore
4. Follow PIN setup and secret import flows

## Troubleshooting

### "SeedKeeper.dgp not found"
Copy the DGP file to the correct location:
```bash
mpremote cp /tmp/SeedKeeper.dgp :/flash/gp/
```

### "Install failed: SW=6985"
Card conditions not satisfied. Ensure:
- Card has sufficient EEPROM space
- Card is not locked
- No existing SeedKeeper with same AID

### "Install failed: SW=6A80"
Invalid data. Check:
- DGP file is valid (SHA256 matches)
- Package AID is correct (536565644b6565706572)

### SeedKeeper not detected after install
1. Reboot the device
2. Remove and reinsert the card
3. Check card registry via "Card info" in provisioning menu

## Files Changed

| File | Purpose |
|------|---------|
| `tools/cap_to_dgp.py` | CAP to DGP converter |
| `src/keystore/javacard/gp/profiles.py` | Applet AID registry |
| `src/keystore/javacard/gp/test_gp_flow.py` | Hardware test with Test 10 |
| `src/specter.py` | GUI provisioning menu |

## SeedKeeper AIDs

| Name | AID (hex) | Notes |
|------|-----------|-------|
| Package | `536565644b6565706572` | "SeedKeeper" |
| Applet/Instance | `536565644b656570657201` | Package + 0x01 |

## DGP File Details

- Size: 18,641 bytes
- SHA256: `e447e45f37cafeb751fff1fdd71002c4e5cf0e837a9586ed6cea51369c841128`
- Source: `SeedKeeper-v0.2-0.1.cap` from Seedkeeper-Applet repo
