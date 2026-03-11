# Prompt: Create Clean SeedKeeper Branch for Upstream PR

**Context:** This is a copy of the seedkeeperport project. Your task is to isolate ONLY the SeedKeeper-related changes into a clean git branch called `seedkeeper` with logical, reviewable commits for upstream specter-diy.

---

## Step 1: Understand the File Categories

### Files to INCLUDE (SeedKeeper + Shared Infrastructure)

**New SeedKeeper files:**
```
src/keystore/seedkeeper.py
src/keystore/javacard/applets/seedkeeper_applet.py
src/keystore/javacard/applets/seedkeeper_securechannel.py
```

**Modified files with SeedKeeper changes (extract only SeedKeeper parts):**
```
src/apps/wallets/manager.py    — SeedKeeper label rename logic
src/apps/wallets/wallet.py     — SeedKeeper label persistence skip
src/specter.py                 — Auto-load after unlock
src/main.py                    — Add SeedKeeper to keystore probe
src/keystore/memorycard.py     — Disconnect fix (shared infrastructure)
```

**Test files:**
```
tests/seedkeeper-test-plan.md
tests/seedkeeper_interactive_test.sh
tests/seedkeeper_test.sh
```

### Files to EXCLUDE (Satochip-only)

**Do NOT include these in the seedkeeper branch:**
```
src/keystore/satochip.py
src/keystore/javacard/applets/satochip_applet.py
```

### Files to EXCLUDE (Debug/Test artifacts)

**Do NOT commit these:**
```
boot/debug/card_test_display.py
boot/debug/led_card_test.py
boot/debug/minimal_boot_test.py
boot/debug/proof_card.py
boot/debug/uart3_card_test.py
boot/main/boot.py (debug modifications)
```

### Files to EXCLUDE (Internal documentation)

```
SEEDKEEPER_INTEGRATION_STRATEGY.md (internal strategy, not for upstream)
docs/LESSONS_LEARNED_FROM_PREVIOUS_PROJECT.md
```

---

## Step 2: Create the Branch

```bash
# Start from upstream master (commit 8131bc9 is the upstream point)
git checkout 8131bc9

# Create clean branch
git checkout -b seedkeeper
```

---

## Step 3: Create Commits in This Order

### Commit 1: feat(keystore): Add JavaCard infrastructure for smartcard support

**Purpose:** Shared infrastructure that both SeedKeeper and future smartcard keystore implementations need.

**Files:**
- `src/keystore/javacard/applets/seedkeeper_securechannel.py` — Rename to `securechannel.py` (remove "seedkeeper" prefix since it's shared)
- `src/keystore/javacard/applets/applet.py` — Base applet class (if modified)
- `src/keystore/memorycard.py` — Disconnect fix only

**Refactoring before commit:**
- Rename `seedkeeper_securechannel.py` → `securechannel.py`
- Update imports in other files accordingly

**Commit message:**
```
feat(keystore): Add JavaCard secure channel infrastructure

- Add ECDH key exchange with AES-CBC encryption
- Implement HMAC-SHA1 authentication for secure channel
- Add PKCS#7 padding utilities
- Fix memorycard disconnect to avoid corrupting subsequent connections

This infrastructure enables smartcard-based keystore implementations
like SeedKeeper to communicate securely with JavaCard applets.
```

---

### Commit 2: feat(seedkeeper): Add Satochip SeedKeeper keystore implementation

**Purpose:** The main SeedKeeper keystore implementation.

**Files:**
- `src/keystore/seedkeeper.py` — Main keystore class
- `src/keystore/javacard/applets/seedkeeper_applet.py` — APDU commands (rename to use `securechannel` import)
- `src/keystore/javacard/applets/__init__.py` — Update if needed

**Refactoring before commit:**
- Update `seedkeeper_applet.py` to import from `securechannel` (not `seedkeeper_securechannel`)
- Remove any debug print statements that are not production-ready
- Ensure `seedkeeper.py` follows existing keystore patterns (check `sdcard.py`, `memorycard.py` for style)

**Commit message:**
```
feat(seedkeeper): Add Satochip SeedKeeper keystore implementation

- Add SeedKeeper keystore class extending RAMKeyStore
- Implement secure PIN verification with attempt tracking
- Add multi-secret enumeration and selection
- Implement BIP39 mnemonic export from card
- Add card-level label management (INS 0x3D)
- Support wallet names from card label (not persisted locally)

The SeedKeeper is a JavaCard-based hardware wallet that stores
BIP39 mnemonics securely on the card. This implementation allows
Specter-DIY to export secrets from the card and use them for signing.

Tested with Satochip SeedKeeper (JTaxCoreV1) hardware.
```

---

### Commit 3: feat(wallets): Integrate SeedKeeper with wallet management

**Purpose:** Wallet manager changes to support SeedKeeper-specific label handling.

**Files:**
- `src/apps/wallets/manager.py` — Add SeedKeeper label rename logic
- `src/apps/wallets/wallet.py` — Skip local name persistence for SeedKeeper

**Changes to extract (SeedKeeper-specific only):**

In `manager.py`, the rename flow should route to card label update:
```python
# Around line 134-142
if getattr(self.keystore, "NAME", "") == "SeedKeeper":
    try:
        self.keystore.set_wallet_label_on_card(name)
        w.name = self.keystore.wallet_label
    except Exception as e:
        await show_screen(Alert("Error", "Failed to update SeedKeeper label:\n%s" % str(e)))
else:
    w.name = name
    w.save(self.keystore)
```

In `wallet.py`, skip name persistence for SeedKeeper:
```python
# In save() method
obj = {"gaps": self.gaps, "unused_recv": self.unused_recv}
if getattr(keystore, "NAME", "") != "SeedKeeper":
    obj["name"] = self.name
```

**Commit message:**
```
feat(wallets): Add SeedKeeper-specific label handling

- Route wallet rename to card label update for SeedKeeper
- Skip local name persistence for SeedKeeper wallets
- Wallet names come from card-level label (INS 0x3D)

This ensures SeedKeeper wallet names are stored on the card,
not in local flash storage, providing consistency across devices.
```

---

### Commit 4: feat(boot): Add SeedKeeper to keystore detection

**Purpose:** Enable SeedKeeper detection at boot.

**Files:**
- `src/main.py` — Add SeedKeeper to keystore probe order
- `src/specter.py` — Auto-load logic after PIN unlock

**Changes in `main.py`:**
```python
# Keystore probe order should include SeedKeeper
KEYSTORES = ["MemoryCard", "SeedKeeper", "SDKeyStore"]
```

**Changes in `specter.py`:**
- Any auto-load logic after PIN verification for SeedKeeper

**Commit message:**
```
feat(boot): Add SeedKeeper to keystore detection

- Add SeedKeeper to keystore probe order
- Auto-load secret after PIN verification for seamless UX
- Display secret selection menu for multi-secret cards

SeedKeeper cards are now detected at boot alongside existing
keystore types.
```

---

### Commit 5 (Optional): test(seedkeeper): Add test plan and scripts

**Files:**
```
tests/seedkeeper-test-plan.md
tests/seedkeeper_interactive_test.sh
tests/seedkeeper_test.sh
```

**Commit message:**
```
test(seedkeeper): Add test plan and scripts

- Add comprehensive test plan for M4 milestone
- Add interactive test script for manual verification
- Document expected behavior for multi-secret cards
```

---

## Step 4: Refactoring Checklist

Before each commit, verify:

### Code Quality
- [ ] No debug `print()` statements (use only BootTrace-prefixed logs if needed)
- [ ] No hardcoded PINs or test values
- [ ] All imports are correct after file renames
- [ ] Follows existing code style (check similar files for patterns)

### File Naming
- [ ] `seedkeeper_securechannel.py` → `securechannel.py` (shared infrastructure)
- [ ] Update imports in `seedkeeper_applet.py` and `satochip_applet.py`

### Upstream Compatibility
- [ ] No changes to base classes (KeyStore, RAMKeyStore) unless absolutely necessary
- [ ] No changes to PinScreen widget
- [ ] No changes to f469-disco submodule (reset it to upstream)

### What NOT to Include
- [ ] Satochip implementation (separate PR)
- [ ] Debug files in `boot/debug/`
- [ ] Internal strategy documents
- [ ] Build artifacts (`.mpy` files, `bin/` changes)

---

## Step 5: Verification

After creating the branch:

```bash
# Check that only expected files are changed
git diff 8131bc9..HEAD --name-only

# Expected output:
# src/keystore/javacard/applets/securechannel.py (renamed)
# src/keystore/javacard/applets/seedkeeper_applet.py
# src/keystore/seedkeeper.py
# src/keystore/memorycard.py
# src/apps/wallets/manager.py
# src/apps/wallets/wallet.py
# src/main.py
# src/specter.py
# tests/seedkeeper-test-plan.md (optional)
# tests/seedkeeper_interactive_test.sh (optional)
# tests/seedkeeper_test.sh (optional)

# Verify build works
sudo docker run --rm -v $(pwd):/app -w /app specter24d bash -lc \
  'export PATH=/opt/gcc-arm-none-eabi-9-2020-q2-update/bin:$PATH && make disco USE_DBOOT=0 DEBUG=0'

# Verify no Satochip files included
git diff 8131bc9..HEAD --name-only | grep -i satochip && echo "ERROR: Satochip files found!" || echo "OK: No Satochip files"
```

---

## Step 6: Final Branch Structure

```
seedkeeper
├── Commit 1: JavaCard infrastructure (shared)
├── Commit 2: SeedKeeper keystore implementation
├── Commit 3: Wallet integration (label handling)
├── Commit 4: Boot detection
└── Commit 5 (optional): Tests

Total: 4-5 clean commits, easy to review
```

---

## Notes for Prometheus

1. **Start fresh** — Checkout upstream commit 8131bc9 and create a new branch. Don't try to cherry-pick from the messy history.

2. **Copy files manually** — Use `git show HEAD:src/keystore/seedkeeper.py > src/keystore/seedkeeper.py` to extract specific file versions.

3. **Rename securechannel** — This is important for future Satochip support. The secure channel is shared infrastructure.

4. **Test build** — After each commit, verify the Docker build succeeds.

5. **Clean imports** — After renaming `seedkeeper_securechannel.py` to `securechannel.py`, update all imports:
   - `seedkeeper_applet.py`
   - `satochip_applet.py` (but don't include this file in the branch)

6. **Keep it minimal** — Only include what's needed for SeedKeeper. Satochip comes later in a separate PR.

---

## Success Criteria

- [ ] Branch `seedkeeper` created from upstream master
- [ ] 4-5 logical commits with clear messages
- [ ] No Satochip files included
- [ ] No debug files included
- [ ] Build succeeds
- [ ] Ready for upstream review
