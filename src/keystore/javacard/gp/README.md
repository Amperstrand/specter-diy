# GlobalPlatform Card Management

## Card States

The JavaCard can be in one of several states. Specter-DIY's boot and
provisioning behaviour depends on the state.

### State 0: BLANK
- Only ISD (Card Manager) present, no user applets
- Boot: `DebugInfoScreen` polling, "Waiting for keystore..."
- Smartcard storage: "Card detected" / "Install MemoryCard"

### State 1: SATOCHIP_ONLY
- SatoChip applet installed (AID `5361746f4368697000`)
- No MemoryCard
- Boot: `DebugInfoScreen` polling (SatoChip is not a keystore)
- Smartcard storage: "Card detected" / "Install MemoryCard"

### State 2: MEMORYCARD_NO_PIN
- MemoryCard applet installed (AID `B00B5111CB01`)
- No PIN set yet
- Boot: `MemoryCard.is_available()` returns True, boots
  normally, PIN setup flow runs
- Smartcard storage: delegates to `MemoryCard.storage_menu()`
  (save/load/delete/get card info)

### State 3: MEMORYCARD_PIN_SET
- MemoryCard applet installed, PIN configured
- Boot: `MemoryCard.is_available()` returns False (cannot open
  secure channel without PIN), shows `DebugInfoScreen`
- Smartcard storage: "MemoryCard: installed (PIN set)"

### State 4: MEMORYCARD_MNEMONIC_SET
- MemoryCard with PIN + stored entropy
- Boot: same as State 3
- Smartcard storage: same as State 3

### State 5: CONFLICT (both SatoChip + MemoryCard)
- Both applets installed on the same card
- **Refuses to boot.** Shows alert on `DebugInfoScreen`:
  "Both SatoChip and MemoryCard are installed on this card.
   Only one applet per card is supported. Please remove the
   card and use another device to delete one applet."
- Stays on debug screen with "Remove card to continue" hint

## State Transitions

```
BLANK ──(Install MemoryCard)──> MEMORYCARD_NO_PIN
SATOCHIP_ONLY ──(Install MemoryCard)──> MEMORYCARD_NO_PIN
MEMORYCARD_NO_PIN ──(setup_pin at first boot)──> MEMORYCARD_PIN_SET
MEMORYCARD_PIN_SET ──(save_mnemonic)──> MEMORYCARD_MNEMONIC_SET
```

Uninstall (delete) transitions are **not supported from the GUI**.
Use `gp.jar` (GlobalPlatformPro) to delete applets.
See: https://github.com/Amperstrand/specter-diy/issues/29

## Install Flow

```
1. User boots with flash/SD keystore, blank JCOP4 inserted
2. initmenu shows "Smartcard storage" (card detected)
3. Smartcard storage shows "Get card info" + "Install MemoryCard"
4. Install MemoryCard → progress screen → "Installed! Reboot."
5. User reboots
6. Boot detects MemoryCard (no PIN) → PIN setup → initmenu
7. Smartcard storage shows save/load/delete (normal flow)
```

## Smartcard Storage Menu

Accessed from initmenu (button 4) and settingsmenu (button 1).

When MemoryCard is the active keystore:
- Delegates to `MemoryCard.storage_menu()` for save/load/delete

When MemoryCard is NOT the active keystore:
- "Get card info" — shows ATR, detected applets, GP registry
- "Install MemoryCard" — installs applet, prompts reboot (State 0/1 only)
- "MemoryCard: installed (PIN set)" — info only, no actions (State 3/4)

## Connection Management

All smartcard code shares a single connection singleton via
`get_connection()` in `keystore/javacard/util.py`. Every code path
that calls `conn.connect()` must:

1. Call `conn.disconnect()` in a `try/except` first (defensive pattern)
2. Ensure `conn.disconnect()` runs on ALL exit paths (success + exceptions)

The `_safe_connect(conn)` helper in `specter.py` implements this pattern.
