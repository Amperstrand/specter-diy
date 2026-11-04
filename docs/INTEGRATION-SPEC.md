# Integration Spec — Satochip + SeedKeeper on specter-diy (for tomorrow's session)

This is the implementation plan derived from the 2026-11-04 overnight survey.
All protocol behavior verified on real hardware (F469 + J3R180 CPLC 50942720).

## Current state (what works, proven)

| Family | Working | Evidence |
|---|---|---|
| MemoryCard | full e2e: detect, connect, PIN 1234, unlock, menu | M1 gate CLOSED |
| Satochip v0.14 | SELECT, SC, PIN, seed, authentikey, BIP32 (all paths incl. BIP85), signing (P2=0x00), PIN change | signature VERIFIED against embit |
| SeedKeeper v0.2 | SELECT, SC, PIN, SETUP, list_headers | 9C04 resolved; store accessible |

## What to build (in order)

### 1. Applet detection + chooser (main.py + specter.py)

```python
# in main.py keystores list (already registered on m-branches):
keystores = [MemoryCard, Satochip, SeedKeeper, SDKeyStore]

# in specter.py select_keystore(): detect which applets are SELECTable
# (probe each AID with 00 A4 04 00, ~36ms each, already proven)
# - one hit → autoselect + show "detected: Satochip" banner
# - multiple hits → chooser menu (new screen, simple button list)
# - none → existing SD fallback
```

### 2. Satochip keystore (m2-satochip branch, 3 changes)

a. **P2 fix in `satochip_applet.get_extended_key()`**:
```python
def get_extended_key(self, path, for_signing=False):
    p2 = 0x00 if for_signing else 0x40  # 0x40 = watch-only → breaks signing
    ...
```

b. **`sign_hash()` calls the fix**:
```python
def sign_hash(self, derivation, msghash):
    path_bytes = self.applet._path_to_bytes(derivation)
    self.applet.get_extended_key(path_bytes, for_signing=True)  # P2=0x00
    return self.applet.sign_transaction_hash(0xFF, msghash)
```

c. **Personalization flow** (first-use UI): SETUP with PIN/PUK when `verify_pin("Muscle00")` succeeds (= fresh card), then set user PIN/PUK. ~10 lines in the keystore's `init()`.

### 3. SeedKeeper keystore (m2-seedkeeper branch, 2 changes)

a. **SETUP flow** (first-use): send SETUP via secure channel when `get_status` returns 9C04:
```python
def _ensure_setup(self):
    try:
        self.applet.get_seedkeeper_status()
    except ISOException as e:
        if "9c04" in str(e).lower():
            self._send_setup(pin, puk)  # INS 0x2A via SC
```

b. **Secret import/export round-trip**: the store ops are unblocked; add `import_bip39_secret(mnemonic)` and `get_bip39_secret()` to the keystore (the applet client already has the protocol methods).

### 4. UI flows (specter-diy app layer)

| Flow | Screen | Notes |
|---|---|---|
| Fresh Satochip detected | "Set up your Satochip" (PIN + PUK entry) | Triggered by Muscle00 verify success |
| Fresh SeedKeeper detected | "Set up your SeedKeeper" (PIN + PUK) | Triggered by 9C04 on get_status |
| Multi-applet card | Applet chooser menu | "Detected: MemoryCard, Satochip, SeedKeeper — choose one" |
| Single applet | Banner on existing boot flow | "Satochip card detected" |

### 5. MPY v1.10 API fixes (apply everywhere)

- `bytes.hex()` → `binascii.hexlify(bytes).decode()`
- `os.path.isdir()` → `try: os.stat(x) except OSError`
- Secure channel: all protected ops go through `secure_request()`, never raw

### 6. Y-parity handling (Satochip client)

The card reports even-Y (02 prefix) for some derivation paths. When using the pubkey for ECDH or verification, try both 02+X and 03+X. Already documented in the `secure-channel-parity` branch.

## File map (where changes go)

| Change | Branch | File(s) |
|---|---|---|
| P2 fix + sign fix | m2-satochip | `src/keystore/javacard/applets/satochip_applet.py` |
| Personalization flow | m2-satochip | `src/keystore/satochip.py` |
| SETUP flow | m2-seedkeeper | `src/keystore/seedkeeper.py` |
| Detection/chooser | m1-specter-applet (or new branch) | `src/specter.py` (select_keystore), `src/main.py` |
| UI screens | feature branch off m2 | `src/gui/screens/` (chooser menu, setup prompts) |
| TestMode fixes | feature/hil | `src/test_mode.py` (UART read_buf_len, heartbeat) |

## Verification checklist (per family, per change)

1. Native pytest suite green (no regressions)
2. On-device survey re-run: all ops still work
3. Full app boots + keystore detected + PIN + unlock
4. Satochip: xpub at m/84h + sign + host-verify
5. SeedKeeper: import secret → list → export → verify match
6. MemoryCard: existing M1 gate evidence unchanged
