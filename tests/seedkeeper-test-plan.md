# SeedKeeper Integration Test Plan

## Test Environment
- Hardware: STM32F469 Discovery board running Specter-DIY firmware
- Serial Port: `/dev/ttyACM1`
- Card: SeedKeeper smartcard with PIN=1234, 24× "bacon" words mnemonic, 1 secret (type 0x10 = MASTERSEED/BIP39)

---

## TC-01: Correct PIN → mnemonic loads → main menu

### Preconditions
- Card inserted in SeedKeeper reader
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Enter PIN: 1234
3. Observe boot sequence

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace][SeedKeeper] PIN verified successfully
[BootTrace][SeedKeeper] Mnemonic loaded successfully
[BootTrace] keystore.unlock() done
[BootTrace] Keystore is ready, initializing apps and skipping to main menu
```

### Serial Patterns to REJECT (absent)
- `[BootTrace][SeedKeeper] unlock() called` appearing more than once
- Any error messages or PIN failure messages
- Card detection failure messages

### Visual Checks
- Confirm subtitle on PIN screen shows "SeedKeeper card detected"
- Wait for PIN screen before entering PIN

### Timing Notes
- Wait for `[BootTrace][SeedKeeper] is_available = True` before proceeding
- Observe 5 attempts remaining on first PIN screen

---

## TC-02: Wrong PIN once → error alert → retry with correct PIN → success

### Preconditions
- Card inserted with correct PIN: 1234
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Enter wrong PIN: 9999
3. Wait for error alert
4. Enter correct PIN: 1234
5. Observe boot sequence

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace] Incorrect PIN
[BootTrace] PIN attempts remaining: 4
[BootTrace][SeedKeeper] PIN verified successfully
[BootTrace][SeedKeeper] Mnemonic loaded successfully
[BootTrace] keystore.unlock() done
[BootTrace] Keystore is ready, initializing apps and skipping to main menu
```

### Serial Patterns to REJECT (absent)
- `[BootTrace] Incorrect PIN` appearing more than once
- Any multiple wrong PIN entries without correct PIN in between
- Any error messages beyond "Incorrect PIN"

### Visual Checks
- Error alert displayed after wrong PIN
- Retry prompt visible

### Timing Notes
- Wait for error alert before retrying
- Verify PIN attempts decrease from 5 to 4

---

## TC-03: Wrong PIN twice → both errors handled → retry with correct PIN → success

### Preconditions
- Card inserted with correct PIN: 1234
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Enter wrong PIN: 9999
3. Wait for first error alert
4. Enter wrong PIN: 8888
5. Wait for second error alert
6. Enter correct PIN: 1234
7. Observe boot sequence

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace] Incorrect PIN
[BootTrace] PIN attempts remaining: 4
[BootTrace] Incorrect PIN
[BootTrace] PIN attempts remaining: 3
[BootTrace][SeedKeeper] PIN verified successfully
[BootTrace][SeedKeeper] Mnemonic loaded successfully
[BootTrace] keystore.unlock() done
[BootTrace] Keystore is ready, initializing apps and skipping to main menu
```

### Serial Patterns to REJECT (absent)
- Any error messages beyond two "Incorrect PIN" entries
- Any attempt to retry after three wrong PINs without correct PIN
- Failure messages before correct PIN

### Visual Checks
- Two error alerts displayed
- PIN attempts decrease from 5 → 4 → 3

### Timing Notes
- Wait for each error alert before next wrong PIN
- Verify PIN attempts decrease correctly

---

## TC-04: Card identity "SeedKeeper card detected" visible on PIN screen (subtitle)

### Preconditions
- Card inserted in SeedKeeper reader
- Serial port open to `/dev/ttyACM1`
- Device at PIN entry screen

### Steps
1. Power on device
2. Observe PIN screen subtitle
3. Verify card identity text

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
```

### Serial Patterns to REJECT (absent)
- Card detection failure messages
- No card detected messages

### Visual Checks
- Subtitle on PIN screen shows "SeedKeeper card detected"
- No generic "No card" or "Card not detected" text

### Timing Notes
- Wait for PIN screen subtitle before verifying

---

## TC-05: PIN attempts remaining visible on first PIN screen (note)

### Preconditions
- Card inserted with 5 attempts remaining
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Observe first PIN screen note
3. Verify attempts count

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
```

### Serial Patterns to REJECT (absent)
- Wrong attempts count (e.g., 4, 6)
- No attempts display message

### Visual Checks
- Note on first PIN screen shows "PIN attempts remaining: 5"
- Attempts count clearly visible and legible

### Timing Notes
- Wait for first PIN screen to render before checking note

---

## TC-06: PIN attempts count decreases after wrong PIN

### Preconditions
- Card inserted with PIN=1234
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Enter wrong PIN: 9999
3. Observe PIN attempts count
4. Enter wrong PIN: 8888
5. Observe PIN attempts count

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace] Incorrect PIN
[BootTrace] PIN attempts remaining: 4
[BootTrace] Incorrect PIN
[BootTrace] PIN attempts remaining: 3
```

### Serial Patterns to REJECT (absent)
- PIN attempts count increasing
- Attempts count staying the same
- Attempts count decreasing by more than 1

### Visual Checks
- First note shows 5 attempts remaining
- After first wrong PIN, note shows 4 attempts remaining
- After second wrong PIN, note shows 3 attempts remaining

### Timing Notes
- Wait for PIN attempts note to update after each wrong PIN
- Verify count decreases by exactly 1 each time

---

## TC-07: Wallet fingerprint displayed in main menu / storage menu

### Preconditions
- Card successfully unlocked with correct PIN
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device
2. Enter correct PIN: 1234
3. Navigate to main menu
4. Observe wallet fingerprint display

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace][SeedKeeper] PIN verified successfully
[BootTrace][SeedKeeper] Mnemonic loaded successfully
[BootTrace] keystore.unlock() done
[BootTrace] Keystore is ready, initializing apps and skipping to main menu
```

### Serial Patterns to REJECT (absent)
- Mnemonic load failure messages
- Any errors accessing wallet secrets

### Visual Checks
- Wallet fingerprint displayed in main menu
- Fingerprint appears on storage menu when accessed
- Fingerprint icon/text clearly visible

### Timing Notes
- Wait for main menu to render before checking fingerprint
- Check fingerprint in both main menu and storage menu

---

## TC-08: No card inserted → "Please insert" screen → insert card → continues

### Preconditions
- Card removed from SeedKeeper reader
- Serial port open to `/dev/ttyACM1`

### Steps
1. Power on device with no card
2. Observe "Please insert" screen
3. Insert card
4. Wait for card detection
5. Continue with normal flow

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = False
[BootTrace] Default keystore selected (fallback)
```

### Serial Patterns to REJECT (absent)
- Card detection error messages
- "Please insert" screen not appearing

### Visual Checks
- "Please insert" screen displayed
- Card inserted prompt visible
- No system errors or crashes

### Timing Notes
- Wait for "Please insert" screen to appear
- Observe no errors during card removal

---

## TC-09: Empty card (no secrets) → graceful error alert after PIN

### Preconditions
- Card inserted with no secrets (empty)
- Serial port open to `/dev/ttyACM1`
- Correct PIN known: 1234

### Steps
1. Power on device
2. Enter correct PIN: 1234
3. Wait for error alert
4. Observe system response

### Serial Patterns to ASSERT (present)
```
[BootTrace][SeedKeeper] is_available() called
[BootTrace][SeedKeeper] is_available = True
[BootTrace] Selected keystore: SeedKeeper
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
[BootTrace][SeedKeeper] PIN verified successfully
[BootTrace] Mnemonic load failed: No secrets found
[BootTrace] unlock() failed
```

### Serial Patterns to REJECT (absent)
- System crash or freeze
- Unhandled exceptions
- Generic error messages unrelated to empty card

### Visual Checks
- Graceful error alert displayed
- Clear message about no secrets found
- System remains stable

### Timing Notes
- Wait for error alert to appear
- Verify no crash or reboot after error

---

## Test Runner Notes

### Serial Pattern Matching
- Use grep to search for `[BootTrace][SeedKeeper]` prefix
- Case-sensitive matching
- All serial patterns must appear in correct order

### Test Case Execution Flow
1. Read test case from plan
2. Execute steps on device
3. Capture serial output
4. Verify ASSERT patterns present
5. Verify REJECT patterns absent
6. Perform visual checks
7. Mark test case complete

### Failure Handling
- Any missing ASSERT pattern → FAIL
- Any REJECT pattern present → FAIL
- Visual check failure → FAIL
- System crash → FAIL

### Success Criteria
- All 9 test cases pass
- Serial pattern validation successful
- Visual checks confirmed
- No system errors or crashes
