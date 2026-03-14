# SeedKeeper Hardware Wallet Support (Milestone 1)

## TL;DR

> **Quick Summary**: Add SeedKeeper smartcard support to Specter-DIY as a new keystore, following the existing MemoryCard code pattern exactly. Clean branch from upstream `8131bc9` for easy PR review.
> 
> **Deliverables**:
> - `src/keystore/javacard/applets/satochip_securechannel.py` — Satochip secure channel (ECDH + AES-CBC + HMAC-SHA1)
> - `src/keystore/javacard/applets/seedkeeper_applet.py` — SeedKeeper applet interface (card commands)
> - `src/keystore/seedkeeper.py` — SeedKeeper keystore (inherits RAMKeyStore, like MemoryCard)
> - `test/tests/test_seedkeeper.py` — Unit tests with mocked card communication
> - Modified `src/main.py` — Register SeedKeeper in keystores list
> - Modified `test/tests/__init__.py` — Register test module
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 3 waves + final verification
> **Critical Path**: Branch creation → Secure Channel → Applet → Keystore → Integration → Tests → Final Verification

---

## Context

### Original Request
Add SeedKeeper (and later Satochip) hardware wallet support to Specter-DIY. Create a clean `satochip` branch from upstream commit `8131bc9` that's easy to review as a PR. Start with SeedKeeper only (Milestone 1). Follow the existing MemoryCard code pattern — prefer duplicating code over refactoring shared base classes. Priority is reviewer comprehension.

### Interview Summary
**Key Discussions**:
- **Branch strategy**: New `satochip` branch from upstream `8131bc93099332e3a421519c4463be6fe5ac8446` (not from current master)
- **Inheritance**: `SeedKeeper(RAMKeyStore)` — copying MemoryCard's exact pattern at the base commit
- **No refactoring**: Do NOT create shared base classes (`JavaCardKeyStore`, `SecureAppletBase`). Inline everything.
- **Naming**: Secure channel file = `satochip_securechannel.py` (Satochip is the company name)
- **Scope**: SeedKeeper only. No Satochip card support in this milestone.
- **Tests**: Match or exceed MemoryCard's testing level. Mock card communication since no hardware in CI.
- **Commits**: Optimize for reviewer understanding — logical grouping preferred.

**Research Findings**:
- MemoryCard at `8131bc9` inherits from `RAMKeyStore` directly (CONFIRMED)
- MemoryCardApplet inherits from `SecureApplet` (which inherits from `Applet`)
- SeedKeeper's secure channel uses a completely different protocol from MemoryCard's (HMAC-SHA1 vs HMAC-SHA256, different MAC lengths, different wrapping)
- SeedKeeper is read-only (exports secrets) vs MemoryCard (stores/retrieves single blob)
- SeedKeeper has multi-secret listing/selection vs MemoryCard single secret
- Existing SeedKeeper code (~1142 lines) is functional on real hardware but needs adaptation for clean branch (remove JavaCardKeyStore/SecureAppletBase dependencies)
- Test infrastructure uses `unittest`, `make test`, `python3 test/run_tests.py`. No MemoryCard-specific unit tests exist — only FlashKeyStore tests.

### Metis Review
**Identified Gaps** (addressed):
- **Base commit verification**: Confirmed — `MemoryCard(RAMKeyStore)` at `8131bc9` ✓
- **Test infrastructure reality**: No hardware mocking exists — tests must create mock infrastructure for card communication
- **File modification boundary**: Must also modify `test/tests/__init__.py` to register test module (was missing)
- **Error code mapping**: SeedKeeper uses different error codes — need explicit handling in applet
- **MASTERSEED parsing duplication**: Existing `get_bip39_secret()` has duplicated code for MASTERSEED vs BIP39 — should deduplicate
- **Card removal edge cases**: Need graceful handling for mid-operation card removal
- **Scope creep risk areas locked down**: No PIN change, no card label editing UI, no descriptor parsing, no Satochip support

---

## Work Objectives

### Core Objective
Add a `SeedKeeper` keystore to Specter-DIY that allows users to load BIP39 mnemonics from a SeedKeeper smartcard, following the identical code pattern used by the existing `MemoryCard` keystore at commit `8131bc9`.

### Concrete Deliverables
- 4 new files: secure channel, applet, keystore, tests
- 2 modified files: `main.py` (import + register), `test/tests/__init__.py` (register test)
- All existing tests still pass (`make test`)
- SeedKeeper tests pass with mocked card communication

### Definition of Done
- [ ] `make test` passes (including new SeedKeeper tests)
- [ ] `python3 -c "from keystore.seedkeeper import SeedKeeper"` succeeds
- [ ] `SeedKeeper` appears in the keystores list in `main.py`
- [ ] `SeedKeeper` inherits from `RAMKeyStore` (not JavaCardKeyStore)
- [ ] `SeedKeeperApplet` inherits from `Applet` (not SecureAppletBase)
- [ ] No new shared base classes created
- [ ] No existing files modified (except main.py and test/__init__.py)

### Must Have
- Card detection via `is_available()` (SELECT AID + get_card_status)
- Satochip secure channel establishment (ECDH + AES-CBC + HMAC-SHA1)
- PIN verification with attempt tracking and lockout detection
- Multi-secret listing with header parsing (id, label, type)
- BIP39 mnemonic export (BIP39 and MASTERSEED secret types)
- Card-wait UI flow (Progress screen while waiting for card insertion)
- Storage menu with "Load key from card" and "Show card info" options
- Error recovery: secure channel re-establishment on 0x9C30 error
- Graceful error messages for: no card, wrong PIN, bricked card, no BIP39 secrets found

### Must NOT Have (Guardrails)
- **NO shared base classes**: Do not create `JavaCardKeyStore`, `SecureAppletBase`, `CardDetector`, or any other shared infrastructure
- **NO existing file modifications**: Do not touch `memorycard.py`, `secureapplet.py`, `securechannel.py`, `applet.py`, `ram.py`, `core.py`, or any other existing file (except `main.py` and `test/tests/__init__.py`)
- **NO Satochip card support**: This is SeedKeeper only (Milestone 1)
- **NO PIN change functionality**: Read-only interaction with card
- **NO card label editing UI**: Backend label reading only, no UI for editing
- **NO descriptor parsing**: Show descriptor secrets as raw text only
- **NO Electrum mnemonic support**: BIP39 only
- **NO Shamir secret support**: Not needed for Milestone 1
- **NO save_mnemonic to card**: SeedKeeper is read-only from Specter's perspective
- **NO over-engineering tests**: Match MemoryCard parity. Unit tests with mocks. No integration tests requiring hardware.
- **AI slop patterns to avoid**: No excessive comments, no over-abstraction, no generic variable names, no JSDoc-style docstrings that don't add value

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (unittest framework, `make test`)
- **Automated tests**: YES (tests-after — write implementation first, then tests)
- **Framework**: `unittest` (matches existing project convention)
- **Test approach**: Mock the smartcard connection object. Test applet command construction, secure channel crypto, keystore state management, and error handling.

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash — `python3 -c "..."` for import/class verification
- **Tests**: Use Bash — `make test` or `python3 -m unittest test.tests.test_seedkeeper`
- **Code quality**: Use Bash — `python3 -m py_compile src/keystore/seedkeeper.py`
- **Git verification**: Use Bash — `git log`, `git diff`, `git branch`

---

## Execution Strategy

### Parallel Execution Waves

> Each wave completes before the next begins.
> Working directory for ALL tasks is the `satochip` branch (created in Task 1).

```
Wave 1 (Foundation — branch + standalone modules):
├── Task 1: Create satochip branch from 8131bc9 [quick]
├── Task 2: Write SatochipSecureChannel (standalone crypto, no deps) [deep]
└── (Task 2 can start once Task 1 creates the branch)

Wave 2 (Core — applet + keystore, sequential dependency):
├── Task 3: Write SeedKeeperApplet (depends: 2) [deep]
├── Task 4: Write SeedKeeper keystore (depends: 3) [deep]
└── Task 5: Integrate into main.py + test/__init__.py (depends: 4) [quick]

Wave 3 (Verification — tests + commit):
├── Task 6: Write SeedKeeper tests (depends: 4, 5) [deep]
├── Task 7: Run full test suite + fix issues (depends: 6) [quick]
└── Task 8: Create git commit(s) (depends: 7) [quick]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Syntax + import verification (unspecified-high)
└── Task F4: Scope fidelity check (deep)

Critical Path: T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → F1-F4
Max Concurrent: 4 (Final wave)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T2, T3, T4, T5, T6, T7, T8 | 1 |
| T2 | T1 | T3 | 1 |
| T3 | T2 | T4 | 2 |
| T4 | T3 | T5, T6 | 2 |
| T5 | T4 | T6, T7 | 2 |
| T6 | T4, T5 | T7 | 3 |
| T7 | T6 | T8 | 3 |
| T8 | T7 | F1-F4 | 3 |
| F1-F4 | T8 | — | FINAL |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|-----------|
| 1 | 2 | T1 → `quick`, T2 → `deep` |
| 2 | 3 | T3 → `deep`, T4 → `deep`, T5 → `quick` |
| 3 | 3 | T6 → `deep`, T7 → `quick`, T8 → `quick` |
| FINAL | 4 | F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

- [x] 1. Create `satochip` branch from upstream commit `8131bc9`

  **What to do**:
  - Run `git checkout -b satochip 8131bc93099332e3a421519c4463be6fe5ac8446` to create the branch
  - Verify the branch is at the correct commit: `git log --oneline -1` should show `8131bc9 Fix: minor comment cleanups (#343)`
  - Verify the clean state: `git status` should show nothing to commit
  - Verify MemoryCard pattern is intact: `grep "class MemoryCard(RAMKeyStore)" src/keystore/memorycard.py` should match
  - Verify no SeedKeeper files exist: `ls src/keystore/seedkeeper.py` should fail (file not found)

  **Must NOT do**:
  - Do NOT merge or cherry-pick any commits from master or seedkeeper-support branches
  - Do NOT run `git checkout master` after creating the branch
  - Do NOT modify any existing files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`git-master`]
    - `git-master`: Branch creation and git state verification

  **Parallelization**:
  - **Can Run In Parallel**: NO (must be first)
  - **Parallel Group**: Wave 1 (alone — prerequisite for all)
  - **Blocks**: T2, T3, T4, T5, T6, T7, T8
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - Current `master` branch — do NOT use this, only use the base commit `8131bc9`

  **WHY Each Reference Matters**:
  - The entire plan depends on starting from the correct commit. Every subsequent task assumes the branch state at `8131bc9`.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Branch created at correct commit
    Tool: Bash
    Preconditions: Repository is at /Users/macbook/src/seedkeeperport/specter-diy
    Steps:
      1. Run: git branch --show-current
      2. Assert output equals: satochip
      3. Run: git log --oneline -1
      4. Assert output starts with: 8131bc9
      5. Run: git status --porcelain
      6. Assert output is empty
    Expected Result: Branch "satochip" exists at commit 8131bc9, clean working tree
    Failure Indicators: Wrong branch name, wrong commit hash, uncommitted files
    Evidence: .sisyphus/evidence/task-1-branch-created.txt

  Scenario: Base commit state is correct (no SeedKeeper files)
    Tool: Bash
    Preconditions: On satochip branch
    Steps:
      1. Run: ls src/keystore/seedkeeper.py 2>&1
      2. Assert output contains: No such file
      3. Run: grep "class MemoryCard(RAMKeyStore)" src/keystore/memorycard.py
      4. Assert match found
      5. Run: ls src/keystore/javacard_keystore.py 2>&1
      6. Assert output contains: No such file (this file should NOT exist at base)
    Expected Result: Clean base state — only original MemoryCard files present
    Failure Indicators: SeedKeeper files exist, MemoryCard has wrong inheritance
    Evidence: .sisyphus/evidence/task-1-base-state.txt
  ```

  **Commit**: NO (no changes to commit — just branch creation)

- [x] 2. Write `satochip_securechannel.py` — Satochip secure channel implementation

  **What to do**:
  - Create `src/keystore/javacard/applets/satochip_securechannel.py`
  - Adapt from the existing `src/keystore/javacard/applets/seedkeeper_securechannel.py` (at current HEAD on master) — this file contains ~233 lines of working, hardware-tested code
  - The class should be named `SatochipSecureChannel` (not `SeedKeeperSecureChannel`) since Satochip is the company name
  - This is a **standalone module** with no internal project dependencies (only uses `secp256k1`, `ucryptolib`, `hashlib` from MicroPython)
  - Include these components:
    - `hmac_sha1(key, msg)` helper function — HMAC-SHA1 using hashlib.sha1
    - `pkcs7_pad(data, block_size=16)` — PKCS#7 padding for AES-CBC
    - `pkcs7_unpad(data)` — PKCS#7 unpadding with validation
    - `SatochipSecureChannel` class with:
      - `__init__()` — initialize state (iv_counter, secret keys to None)
      - `initiate(connection, cla=0xB0)` — ECDH key exchange: generate ephemeral keypair, send INS 0x81 APDU with compressed pubkey, derive shared secret via ECDH, split into `secret_key` (AES key) and `mac_key` (HMAC key), initialize `iv_counter` to 1
      - `encrypt_apdu(inner_apdu, cla=0xB0)` — Encrypt outgoing command: build IV from counter, AES-CBC encrypt padded APDU, compute HMAC-SHA1 over (IV + encrypted), wrap in INS 0x82 APDU, increment counter
      - `decrypt_response(encrypted_response)` — Decrypt incoming response: extract IV + ciphertext + MAC from response, verify HMAC-SHA1, AES-CBC decrypt, unpad, return plaintext
  - **Key protocol details** (from existing working code):
    - IV construction: 16 bytes, first 12 are zero, last 4 are big-endian counter
    - HMAC covers: IV bytes + encrypted data
    - MAC is 20 bytes (SHA1), appended to encrypted data in the APDU
    - INS 0x82 wraps: `[cla, 0x82, 0x00, 0x00, len, IV(16) + encrypted + MAC(20)]`
    - Response format: `IV(16) + encrypted_data + MAC(20) + SW1SW2(2)`

  **Must NOT do**:
  - Do NOT import from any other project files (this is standalone crypto)
  - Do NOT change the cryptographic protocol — it must match the SeedKeeper card's expectations exactly
  - Do NOT add unnecessary abstractions or factory patterns
  - Do NOT use SHA256 — SeedKeeper uses SHA1 for HMAC (different from MemoryCard's SecureChannel)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Cryptographic protocol implementation requires careful attention to byte-level details. Getting any byte offset wrong breaks the entire secure channel.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `git-master`: Not needed — this is file creation, not git operations

  **Parallelization**:
  - **Can Run In Parallel**: NO (must wait for T1 branch creation)
  - **Parallel Group**: Wave 1 (after T1)
  - **Blocks**: T3 (applet needs the secure channel)
  - **Blocked By**: T1

  **References**:

  **Pattern References** (CRITICAL — adapt from these):
  - `src/keystore/javacard/applets/seedkeeper_securechannel.py` (at current HEAD on `master`) — This is the **existing working implementation** with the correct protocol. Adapt this file, renaming class from `SeedKeeperSecureChannel` to `SatochipSecureChannel`. The code is hardware-tested and functional.
    - Lines 22-56: `hmac_sha1()` function — copy as-is
    - Lines 59-75: `pkcs7_pad()` function — copy as-is  
    - Lines 77-103: `pkcs7_unpad()` function — copy as-is
    - Lines 105-118: `SeedKeeperSecureChannel.__init__()` — rename class to `SatochipSecureChannel`
    - Lines 119-165: `initiate()` — ECDH key exchange with card. Key method. Copy and verify.
    - Lines 166-209: `encrypt_apdu()` — command encryption. Copy and verify byte offsets.
    - Lines 210-233: `decrypt_response()` — response decryption. Copy and verify.

  **External References**:
  - MicroPython `secp256k1` module — used for ECDH keypair generation and shared secret derivation
  - MicroPython `ucryptolib` — used for AES-CBC encryption/decryption
  - MicroPython `hashlib` — used for SHA1 in HMAC implementation

  **WHY Each Reference Matters**:
  - The existing `seedkeeper_securechannel.py` IS the reference implementation — it's been tested on real hardware. The task is primarily a rename + adaptation, not a from-scratch implementation. But the agent must understand the byte-level protocol to verify correctness.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Module imports successfully
    Tool: Bash
    Preconditions: On satochip branch, file created
    Steps:
      1. Run: cd src && python3 -c "from keystore.javacard.applets.satochip_securechannel import SatochipSecureChannel; print('OK')"
      2. Assert output: OK
      3. Run: cd src && python3 -c "from keystore.javacard.applets.satochip_securechannel import hmac_sha1, pkcs7_pad, pkcs7_unpad; print('OK')"
      4. Assert output: OK
    Expected Result: All public symbols importable
    Failure Indicators: ImportError, ModuleNotFoundError
    Evidence: .sisyphus/evidence/task-2-import.txt

  Scenario: Class has correct name and methods
    Tool: Bash
    Preconditions: Module importable
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.javacard.applets.satochip_securechannel import SatochipSecureChannel
         sc = SatochipSecureChannel()
         assert hasattr(sc, 'initiate'), 'missing initiate'
         assert hasattr(sc, 'encrypt_apdu'), 'missing encrypt_apdu'
         assert hasattr(sc, 'decrypt_response'), 'missing decrypt_response'
         assert hasattr(sc, 'iv_counter'), 'missing iv_counter'
         assert hasattr(sc, 'secret_key'), 'missing secret_key'
         assert hasattr(sc, 'mac_key'), 'missing mac_key'
         print('ALL METHODS PRESENT')
         "
      2. Assert output contains: ALL METHODS PRESENT
    Expected Result: SatochipSecureChannel has all required attributes
    Failure Indicators: AssertionError for any missing attribute
    Evidence: .sisyphus/evidence/task-2-methods.txt

  Scenario: PKCS7 padding/unpadding roundtrip
    Tool: Bash
    Preconditions: Module importable
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.javacard.applets.satochip_securechannel import pkcs7_pad, pkcs7_unpad
         # Test various data lengths
         for length in [0, 1, 15, 16, 17, 31, 32]:
             data = bytes(range(length))
             padded = pkcs7_pad(data)
             assert len(padded) % 16 == 0, f'padding failed for length {length}'
             unpadded = pkcs7_unpad(padded)
             assert unpadded == data, f'roundtrip failed for length {length}'
         print('PADDING OK')
         "
      2. Assert output: PADDING OK
    Expected Result: PKCS7 pad/unpad works for all edge case lengths
    Failure Indicators: AssertionError for any test case
    Evidence: .sisyphus/evidence/task-2-padding.txt

  Scenario: File does not import from project modules
    Tool: Bash
    Preconditions: File exists
    Steps:
      1. Run: grep -n "from \." src/keystore/javacard/applets/satochip_securechannel.py || echo "NO_RELATIVE_IMPORTS"
      2. Assert output: NO_RELATIVE_IMPORTS
      3. Run: grep -n "from keystore" src/keystore/javacard/applets/satochip_securechannel.py || echo "NO_PROJECT_IMPORTS"
      4. Assert output: NO_PROJECT_IMPORTS
    Expected Result: No internal project imports — standalone module
    Failure Indicators: Any relative or project imports found
    Evidence: .sisyphus/evidence/task-2-standalone.txt
  ```

  **Commit**: YES (groups with T3, T4, T5 — all committed together after T7)
  - Files: `src/keystore/javacard/applets/satochip_securechannel.py`

- [x] 3. Write `seedkeeper_applet.py` — SeedKeeper card command interface

  **What to do**:
  - Create `src/keystore/javacard/applets/seedkeeper_applet.py`
  - Adapt from existing `src/keystore/javacard/applets/seedkeeper_applet.py` (at current HEAD on master) — 482 lines of working, hardware-tested code
  - Class `SeedKeeperApplet` must inherit from `Applet` directly (NOT from `SecureAppletBase` which won't exist on the clean branch)
  - Inline the secure channel management that was previously in `SecureAppletBase`:
    - Create `SatochipSecureChannel` instance in `__init__`
    - Add `init_secure_channel()` method that calls `self.sc.initiate(self.conn)`
    - Add `secure_request(inner_apdu)` method that encrypts via secure channel, transmits, decrypts response. Handle 0x9C30 error (stale secure channel) by re-establishing channel and retrying once.
  - Include all SeedKeeper-specific APDU constants at class level:
    - `AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])` — "SeedKeeper" in ASCII
    - `INS_VERIFY_PIN = 0x42`
    - `INS_GET_STATUS = 0x3C`
    - `INS_LIST_SECRET_HEADERS = 0x73`
    - `INS_EXPORT_SECRET = 0x6C`
    - `INS_GET_LABEL = 0x3D`
    - `INS_SET_LABEL = 0x3E`
    - Other INS constants as defined in existing code
  - Include these methods (adapt from existing code):
    - `get_card_status()` — returns (protocol_version, applet_version, ...) via plain (unencrypted) APDU
    - `get_seedkeeper_status()` — returns detailed status via secure channel
    - `verify_pin(pin)` — send PIN via secure channel, return remaining attempts, raise on wrong PIN
    - `get_card_label()` — read card label string via secure channel
    - `set_card_label(label)` — set card label string via secure channel
    - `list_secret_headers()` — list all secrets on card, return list of dicts with {id, label, type, subtype, origin, ...}
    - `_parse_header(data)` — parse raw header bytes into dict
    - `export_secret(sid, include_header=False)` — export a secret by ID via secure channel
    - `get_bip39_secret(secret_id=None, secret_type=None)` — export and convert a BIP39 or MASTERSEED secret to mnemonic string. **IMPORTANT**: Deduplicate the MASTERSEED parsing logic that currently appears twice in the existing code (once for direct ID, once for search).
    - `get_descriptor_secrets()` — list descriptor-type secrets (for display only)
  - **Key protocol details**:
    - All commands except `get_card_status()` go through the secure channel (`secure_request`)
    - PIN verification: `INS 0x42`, P1=0x00, P2=0x00, data=PIN bytes. Response SW=0x9000 on success, SW=0x63CX on failure (X = remaining attempts)
    - Secret header format: 1-byte id + variable header data parsed by `_parse_header`
    - Export: returns raw secret bytes, interpretation depends on type (BIP39 = UTF-8 mnemonic, MASTERSEED = raw entropy bytes)
    - MASTERSEED to mnemonic conversion: use `embit.bip39.mnemonic_from_bytes(entropy)`

  **Must NOT do**:
  - Do NOT create a `SecureAppletBase` class — inline the secure channel management directly
  - Do NOT inherit from `SecureApplet` — that's MemoryCard's pattern with a different protocol
  - Do NOT modify `applet.py` — inherit from it as-is
  - Do NOT add methods not present in the existing working code (no new features)
  - Do NOT leave the MASTERSEED parsing duplicated — deduplicate it

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex APDU protocol implementation with byte-level parsing, multiple methods, and error handling. Requires careful attention to SeedKeeper-specific protocol details.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T2 — needs secure channel)
  - **Parallel Group**: Wave 2 (sequential after T2)
  - **Blocks**: T4 (keystore needs applet)
  - **Blocked By**: T1, T2

  **References**:

  **Pattern References** (CRITICAL — adapt from these):
  - `src/keystore/javacard/applets/seedkeeper_applet.py` (at current HEAD on `master`) — **The existing working implementation**. Adapt this, changing inheritance from `SecureAppletBase` to `Applet` and inlining secure channel management.
    - Lines 5-81: Class definition with all APDU constants — copy constants as-is
    - Lines 83-88: `__init__` — change `super().__init__(connection, self.AID)` (Applet), add `self.sc = SatochipSecureChannel()`
    - Lines 89-111: `get_seedkeeper_status()` — copy, uses `secure_request`
    - Lines 112-127: `verify_pin(pin)` — copy, uses `secure_request`
    - Lines 128-167: `get_card_label()` / `set_card_label()` — copy, uses `secure_request`
    - Lines 168-235: `list_secret_headers()` / `_parse_header()` — copy, header parsing logic
    - Lines 236-314: `export_secret()` — copy, secret export via secure channel
    - Lines 315-321: `get_card_status()` — copy, this is the ONLY method that doesn't use secure channel
    - Lines 322-450: `get_bip39_secret()` — **ADAPT**: deduplicate the MASTERSEED parsing that appears twice
    - Lines 451-482: `get_descriptor_secrets()` — copy
  
  - `src/keystore/javacard/applets/secure_applet_base.py` (at current HEAD on `master`, 167 lines) — **Source for inlining**. This contains the `init_secure_channel()` and `secure_request()` methods that need to be moved into SeedKeeperApplet directly.
    - Lines 28-35: `init_secure_channel()` — inline into SeedKeeperApplet
    - Lines 37-80: `secure_request()` — inline into SeedKeeperApplet (includes 0x9C30 retry logic)

  - `src/keystore/javacard/applets/applet.py` (at base commit `8131bc9`) — **Parent class**. Understand the `Applet` API: `__init__(connection, aid)`, `select()`, `request(apdu)`, `ping()`.

  - `src/keystore/javacard/applets/memorycard.py` (at base commit `8131bc9`, ~20 lines) — **Peer pattern**. See how MemoryCardApplet inherits from SecureApplet. SeedKeeperApplet follows a similar structure but inherits from Applet and manages its own secure channel.

  **WHY Each Reference Matters**:
  - `seedkeeper_applet.py` at HEAD: This IS the implementation to adapt. It's hardware-tested and correct. The agent's job is to change inheritance and inline secure channel management, not rewrite business logic.
  - `secure_applet_base.py` at HEAD: Contains the two methods (`init_secure_channel`, `secure_request`) that must be inlined into the applet since we're not creating a shared base class.
  - `applet.py` at base: The parent class contract. Agent needs to know what methods `Applet` provides (select, request, ping, conn).
  - `memorycard.py` at base: Peer pattern for how applets are structured in this codebase.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Module imports successfully with correct inheritance
    Tool: Bash
    Preconditions: On satochip branch, T2 complete (satochip_securechannel.py exists)
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
         from keystore.javacard.applets.applet import Applet
         assert issubclass(SeedKeeperApplet, Applet), 'Wrong parent class'
         print('INHERITANCE OK')
         "
      2. Assert output contains: INHERITANCE OK
    Expected Result: SeedKeeperApplet inherits from Applet
    Failure Indicators: ImportError, AssertionError (wrong parent class)
    Evidence: .sisyphus/evidence/task-3-inheritance.txt

  Scenario: All required methods present
    Tool: Bash
    Preconditions: Module importable
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
         required = ['get_card_status', 'get_seedkeeper_status', 'verify_pin',
                     'get_card_label', 'set_card_label', 'list_secret_headers',
                     'export_secret', 'get_bip39_secret', 'get_descriptor_secrets',
                     'init_secure_channel', 'secure_request', '_parse_header']
         for method in required:
             assert hasattr(SeedKeeperApplet, method), f'missing {method}'
         print('ALL METHODS PRESENT')
         "
      2. Assert output: ALL METHODS PRESENT
    Expected Result: All required methods exist on the class
    Failure Indicators: AssertionError listing missing method
    Evidence: .sisyphus/evidence/task-3-methods.txt

  Scenario: No SecureAppletBase dependency
    Tool: Bash
    Preconditions: File exists
    Steps:
      1. Run: grep -n "SecureAppletBase\|secure_applet_base" src/keystore/javacard/applets/seedkeeper_applet.py || echo "NO_BASE_DEPENDENCY"
      2. Assert output: NO_BASE_DEPENDENCY
      3. Run: grep "class SeedKeeperApplet" src/keystore/javacard/applets/seedkeeper_applet.py
      4. Assert output contains: (Applet)
      5. Assert output does NOT contain: SecureAppletBase
    Expected Result: No reference to SecureAppletBase anywhere in the file
    Failure Indicators: Any match for SecureAppletBase
    Evidence: .sisyphus/evidence/task-3-no-base.txt

  Scenario: AID constant is correct
    Tool: Bash
    Preconditions: Module importable
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
         expected = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
         assert SeedKeeperApplet.AID == expected, f'AID mismatch: {SeedKeeperApplet.AID.hex()}'
         assert expected == b'SeedKeeper', 'AID is not ASCII SeedKeeper'
         print('AID CORRECT')
         "
      2. Assert output: AID CORRECT
    Expected Result: AID matches SeedKeeper ASCII bytes
    Failure Indicators: AID bytes don't match
    Evidence: .sisyphus/evidence/task-3-aid.txt
  ```

  **Commit**: YES (groups with T2, T4, T5)
  - Files: `src/keystore/javacard/applets/seedkeeper_applet.py`

- [x] 4. Write `seedkeeper.py` — SeedKeeper keystore (main user-facing module)

  **What to do**:
  - Create `src/keystore/seedkeeper.py`
  - Adapt from existing `src/keystore/seedkeeper.py` (at current HEAD on master) — 427 lines of working code
  - Class `SeedKeeper` must inherit from `RAMKeyStore` directly (same pattern as MemoryCard at base commit)
  - Inline all connection management and card interaction that was previously in `JavaCardKeyStore`:
    - Class-level `connection = get_connection()` (shared connection object, same as MemoryCard)
    - Card detection (`is_available`) — try SELECT AID + get_card_status, return True/False
    - Card waiting (`check_card`) — wait for card insertion with Progress screen, connect, select, init secure channel
    - `wait_for_card(scr)` — async polling loop (copy from MemoryCard pattern)
    - `init(show_fn, show_loader)` — same structure as MemoryCard: load secret, check card, call super().init()
  - Include SeedKeeper-specific behavior:
    - `NAME = "SeedKeeper"`, `COLOR = "FF8C00"` (or appropriate color)
    - `NOTE` = description string explaining SeedKeeper functionality
    - `unlock()` — Custom override: prompt for PIN, verify via applet, then present secret selection menu. Load BIP39 mnemonic. **This replaces the standard RAMKeyStore unlock flow** because SeedKeeper needs PIN → list secrets → select → export → convert to mnemonic.
    - `load_mnemonic()` — Export selected secret from card, convert to mnemonic words, call `set_mnemonic(mnemonic, "")` to load into RAM
    - `save_mnemonic()` — Raise error or show alert: "SeedKeeper is read-only" 
    - `is_key_saved` property — Return True if card has BIP39 secrets (after listing headers)
    - `storage_menu()` — Menu with options: "Load key from card", "Show card info". Follow MemoryCard's menu pattern.
    - `show_card_info()` — Display card label, firmware version, number of secrets, card status info
  - **Key implementation details** (from existing working code):
    - `is_available()` is a `@classmethod` — it must work without an instance. Pattern: create temp connection, try SELECT + get_card_status, catch exceptions, return bool.
    - `_unlock(pin)` is called by `RAMKeyStore.unlock()` — but for SeedKeeper we override `unlock()` entirely because we need the multi-step flow (PIN → list → select → export)
    - After unlocking, the mnemonic is held in RAM only (same security model as MemoryCard)
    - `is_locked` and `is_ready` properties need to reflect SeedKeeper state
    - The `hexid` property should use the card's public key (from get_card_status) for device identification

  **Must NOT do**:
  - Do NOT create `JavaCardKeyStore` base class — inline everything
  - Do NOT modify `ram.py` or `core.py`
  - Do NOT add save/write functionality to card (SeedKeeper is read-only from Specter's perspective)
  - Do NOT add PIN change UI (Milestone 2)
  - Do NOT add card label editing UI (backend method in applet is fine, no UI)
  - Do NOT add Electrum mnemonic support
  - Do NOT over-engineer the storage_menu — keep it simple like MemoryCard's

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: This is the most complex file — integrates applet, UI flows, PIN management, secret selection, and error handling. Must correctly implement the RAMKeyStore contract while adding SeedKeeper-specific flows.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T3 — needs applet)
  - **Parallel Group**: Wave 2 (sequential after T3)
  - **Blocks**: T5, T6
  - **Blocked By**: T1, T2, T3

  **References**:

  **Pattern References** (CRITICAL — the TWO source files to adapt from):
  - `src/keystore/seedkeeper.py` (at current HEAD on `master`, 427 lines) — **Existing working implementation**. Adapt this, changing inheritance from `JavaCardKeyStore` to `RAMKeyStore` and inlining connection management.
    - Lines 1-8: Imports — adapt for RAMKeyStore instead of JavaCardKeyStore
    - Lines 9-22: Class definition, NAME, COLOR, NOTE — keep, adjust NOTE text
    - Lines 23-30: `__init__` — adapt: add `self.connection = get_connection()`, create `SeedKeeperApplet(self.connection)`, add connection state tracking
    - Lines 31-66: `_sanitize_wallet_label`, `set_wallet_label_on_card`, `is_available` — key methods, adapt is_available for standalone use
    - Lines 67-70: `is_ready` property — adapt
    - Lines 71-181: `unlock()` — **CRITICAL METHOD**: PIN prompt → verify → list secrets → select → export → convert. This is SeedKeeper's unique flow. Adapt, removing JavaCardKeyStore references.
    - Lines 182-223: `check_card()` — **INLINE from MemoryCard pattern**: wait for card, connect, select, init secure channel
    - Lines 224-297: `load_mnemonic()` — export from card, convert to mnemonic string
    - Lines 289-327: `save_mnemonic`, `is_key_saved`, `storage_menu` — adapt
    - Lines 328-427: `show_card_info()` — display card metadata

  - `src/keystore/memorycard.py` (at base commit `8131bc9`, 469 lines) — **THE pattern to copy for RAMKeyStore integration**:
    - Line 17: `class MemoryCard(RAMKeyStore)` — same inheritance pattern
    - Lines 42-50: `__init__` — how MemoryCard sets up connection and applet
    - Lines 51-65: `is_available()` classmethod — how MemoryCard detects card
    - Lines 89-110: Properties: `is_pin_set`, `pin_attempts_left`, `pin_attempts_max`, `is_locked`, `is_ready` — adapt for SeedKeeper
    - Lines 112-131: `_unlock(pin)` — how MemoryCard unlocks (SeedKeeper overrides `unlock()` instead)
    - Lines 300-340: `check_card()` and `wait_for_card()` — **COPY THIS PATTERN** for card detection/connection
    - Lines 341-355: `init()` — **COPY THIS PATTERN** for initialization flow
    - Lines 359-427: `storage_menu()` — menu structure pattern to follow

  - `src/keystore/javacard_keystore.py` (at current HEAD on `master`, 256 lines) — **Source for inlining**. This contains connection management logic that was extracted from MemoryCard. Some of it needs to be inlined back into SeedKeeper:
    - Lines 55-95: `check_card()` — card waiting + connection logic (already adapted in existing seedkeeper.py, use that version)
    - Lines 97-130: `wait_for_card()` — async card polling
    - Lines 132-170: PIN prompt and verification loop

  - `src/keystore/ram.py` (at base commit `8131bc9`, 427 lines) — **Parent class contract**. Understand what RAMKeyStore provides:
    - `unlock()` async method — calls `get_pin()` then `_unlock(pin)`. SeedKeeper overrides this entirely.
    - `_unlock(pin)` — abstract, must be implemented
    - `is_locked` property — must be implemented
    - `set_mnemonic(mnemonic, password)` — call this after exporting secret from card
    - `save_mnemonic()` — SeedKeeper overrides to say "read-only"
    - `get_keypath(...)`, `sign_transaction(...)`, etc. — inherited from RAMKeyStore, work after mnemonic is loaded

  **WHY Each Reference Matters**:
  - `seedkeeper.py` at HEAD: The working implementation with all SeedKeeper-specific logic. Agent adapts this.
  - `memorycard.py` at base: THE canonical pattern for how a keystore integrates with RAMKeyStore. Copy structure exactly.
  - `javacard_keystore.py` at HEAD: Contains inlined logic for card management — but prefer the MemoryCard base-commit pattern for structure.
  - `ram.py` at base: Parent class contract — must know what methods to implement/override.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Module imports with correct inheritance
    Tool: Bash
    Preconditions: On satochip branch, T2+T3 complete
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.seedkeeper import SeedKeeper
         from keystore.ram import RAMKeyStore
         assert issubclass(SeedKeeper, RAMKeyStore), 'Wrong parent'
         print('INHERITANCE OK')
         "
      2. Assert output: INHERITANCE OK
    Expected Result: SeedKeeper inherits from RAMKeyStore
    Failure Indicators: ImportError, AssertionError
    Evidence: .sisyphus/evidence/task-4-inheritance.txt

  Scenario: No JavaCardKeyStore dependency
    Tool: Bash
    Preconditions: File exists
    Steps:
      1. Run: grep -n "JavaCardKeyStore\|javacard_keystore" src/keystore/seedkeeper.py || echo "NO_JCK_DEPENDENCY"
      2. Assert output: NO_JCK_DEPENDENCY
      3. Run: grep "class SeedKeeper" src/keystore/seedkeeper.py
      4. Assert output contains: (RAMKeyStore)
    Expected Result: No reference to JavaCardKeyStore
    Failure Indicators: Any match found
    Evidence: .sisyphus/evidence/task-4-no-jck.txt

  Scenario: Required class attributes and methods exist
    Tool: Bash
    Preconditions: Module importable
    Steps:
      1. Run: cd src && python3 -c "
         from keystore.seedkeeper import SeedKeeper
         # Class attributes
         assert hasattr(SeedKeeper, 'NAME'), 'missing NAME'
         assert SeedKeeper.NAME == 'SeedKeeper', f'NAME wrong: {SeedKeeper.NAME}'
         assert hasattr(SeedKeeper, 'COLOR'), 'missing COLOR'
         # Required methods
         required = ['is_available', 'unlock', 'check_card', 'wait_for_card',
                     'init', 'load_mnemonic', 'save_mnemonic', 'storage_menu',
                     'show_card_info']
         for m in required:
             assert hasattr(SeedKeeper, m), f'missing {m}'
         # Properties
         sk = SeedKeeper.__new__(SeedKeeper)  # don't call __init__
         # Verify is_available is classmethod
         assert isinstance(SeedKeeper.__dict__['is_available'], classmethod), 'is_available not classmethod'
         print('ALL ATTRS OK')
         "
      2. Assert output: ALL ATTRS OK
    Expected Result: All required class attributes and methods present
    Failure Indicators: AssertionError for any missing attribute
    Evidence: .sisyphus/evidence/task-4-attrs.txt

  Scenario: SeedKeeper uses shared connection (like MemoryCard)
    Tool: Bash
    Preconditions: File exists
    Steps:
      1. Run: grep -n "get_connection" src/keystore/seedkeeper.py
      2. Assert at least one match found (connection = get_connection() at class level or in __init__)
      3. Run: grep -n "from.*javacard.util import\|from.*javacard import" src/keystore/seedkeeper.py
      4. Assert import of get_connection found
    Expected Result: Uses get_connection() utility like MemoryCard does
    Failure Indicators: No get_connection import/usage
    Evidence: .sisyphus/evidence/task-4-connection.txt
  ```

  **Commit**: YES (groups with T2, T3, T5)
  - Files: `src/keystore/seedkeeper.py`

- [x] 5. Integrate SeedKeeper into `main.py` and `test/tests/__init__.py`

  **What to do**:
  - Modify `src/main.py`:
    - Add import: `from keystore.seedkeeper import SeedKeeper` (after the MemoryCard import on line 7)
    - Add `SeedKeeper` to the keystores list (after `MemoryCard`, before `SDKeyStore`):
      ```python
      keystores = [
          MemoryCard,
          SeedKeeper,
          SDKeyStore,
      ]
      ```
  - Modify `test/tests/__init__.py`:
    - Add line: `from .test_seedkeeper import *` (after existing imports)
  - These are minimal, surgical changes — 2-3 lines per file

  **Must NOT do**:
  - Do NOT modify any other lines in main.py
  - Do NOT change the order of existing keystores
  - Do NOT add conditional imports or try/except around the import
  - Do NOT modify any other files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Two small surgical edits — 2-3 lines each
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T4)
  - **Parallel Group**: Wave 2 (final step)
  - **Blocks**: T6, T7
  - **Blocked By**: T4

  **References**:

  **Pattern References**:
  - `src/main.py` (at base commit `8131bc9`) — Lines 1-7: imports section. Line 7 is `from keystore.memorycard import MemoryCard`. Add SeedKeeper import right after. Lines ~55-58: keystores list where `MemoryCard` and `SDKeyStore` are listed.
  - `test/tests/__init__.py` (at base commit `8131bc9`) — Contains `from .test_xxx import *` lines for each test module. Add the SeedKeeper test module here.

  **WHY Each Reference Matters**:
  - `main.py`: Exact insertion points matter — import must be near other keystore imports, keystores list must include SeedKeeper
  - `test/__init__.py`: Test discovery depends on this file importing the test module

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: main.py imports and registers SeedKeeper
    Tool: Bash
    Preconditions: T4 complete (seedkeeper.py exists)
    Steps:
      1. Run: grep "from keystore.seedkeeper import SeedKeeper" src/main.py
      2. Assert match found
      3. Run: grep "SeedKeeper" src/main.py | grep -v "^#\|^from"
      4. Assert SeedKeeper appears in keystores list context
    Expected Result: SeedKeeper imported and in keystores list
    Failure Indicators: Import missing or not in keystores
    Evidence: .sisyphus/evidence/task-5-main.txt

  Scenario: test/__init__.py registers seedkeeper tests
    Tool: Bash
    Preconditions: File modified
    Steps:
      1. Run: grep "from .test_seedkeeper import" test/tests/__init__.py
      2. Assert match found
    Expected Result: Test module registered for discovery
    Failure Indicators: Import line missing
    Evidence: .sisyphus/evidence/task-5-test-init.txt

  Scenario: Only expected lines changed in main.py
    Tool: Bash
    Preconditions: On satochip branch
    Steps:
      1. Run: git diff 8131bc9 -- src/main.py | grep "^[+-]" | grep -v "^[+-][+-][+-]"
      2. Assert only 2-3 lines added (import + keystores list entry)
      3. Assert no lines removed (except possibly blank line adjustments)
    Expected Result: Minimal, surgical change to main.py
    Failure Indicators: More than 3-4 changed lines, any removed lines of substance
    Evidence: .sisyphus/evidence/task-5-diff.txt
  ```

  **Commit**: YES (groups with T2, T3, T4)
  - Files: `src/main.py`, `test/tests/__init__.py`

- [x] 6. Write `test_seedkeeper.py` — SeedKeeper unit tests with mocked card

  **What to do**:
  - Create `test/tests/test_seedkeeper.py`
  - Use `unittest` framework (matching project convention from `test_keystore.py`)
  - Mock the smartcard connection to test without hardware
  - Test structure should match existing `test_keystore.py` style:
    - `TestCase` subclass with `setUp` / helper methods
    - Descriptive docstrings on each test method
    - Clear assertions with meaningful failure messages
  - **Test categories to cover** (functional parity with MemoryCard + SeedKeeper-specific):

  **Category 1: Import and Class Structure Tests**
  - Test that `SeedKeeper` imports correctly
  - Test that `SeedKeeper` inherits from `RAMKeyStore`
  - Test that `SeedKeeperApplet` inherits from `Applet`
  - Test that `SatochipSecureChannel` class exists and has required methods
  - Test that `SeedKeeper.NAME == "SeedKeeper"`

  **Category 2: Secure Channel Crypto Tests**
  - Test `pkcs7_pad` with various input sizes (0, 1, 15, 16, 17, 31, 32 bytes)
  - Test `pkcs7_unpad` with valid padded data
  - Test `pkcs7_unpad` with invalid padding (should raise ValueError)
  - Test `hmac_sha1` produces correct output (compare with known test vector)
  - Test `SatochipSecureChannel` initialization (attributes set to None/defaults)

  **Category 3: Applet Command Construction Tests** (with mocked connection)
  - Test `get_card_status()` sends correct APDU bytes and parses response
  - Test `verify_pin()` constructs correct APDU with PIN bytes
  - Test `verify_pin()` handles wrong PIN response (0x63CX → extract remaining attempts)
  - Test `list_secret_headers()` parses multi-secret response into list of dicts
  - Test `_parse_header()` with known header bytes → correct dict fields
  - Test `export_secret()` sends correct ID in APDU

  **Category 4: Keystore State Tests**
  - Test `SeedKeeper` construction (attributes initialized correctly)
  - Test `is_available()` returns False when no card (mock connection)
  - Test `save_mnemonic()` raises or shows read-only error
  
  **Category 5: BIP39 Conversion Tests**
  - Test BIP39 secret type → mnemonic string conversion (known test vector)
  - Test MASTERSEED secret type → entropy → mnemonic conversion (known test vector)
  - Test handling of missing/empty secret data

  **Implementation approach**:
  - Use `unittest.mock.MagicMock` or simple mock classes for the card connection
  - For crypto tests (Category 2), use known test vectors — no card needed
  - For applet tests (Category 3), mock `self.conn.request()` to return predefined APDU responses
  - For keystore tests (Category 4), mock the applet methods
  - Keep tests focused and fast — no async testing needed for unit tests (test sync methods directly)
  - **NOTE**: Some methods are `async` — if the test framework doesn't support async easily, test the underlying sync logic (applet commands, crypto) and skip async UI flow testing

  **Must NOT do**:
  - Do NOT require real hardware to run tests
  - Do NOT test async UI flows that require `lvgl` or display infrastructure (those need the simulator)
  - Do NOT over-engineer test infrastructure — simple mocks, no test fixtures framework
  - Do NOT add tests for features that don't exist (no Satochip, no PIN change)
  - Do NOT use pytest — project uses unittest

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Writing comprehensive tests requires understanding the entire SeedKeeper stack (crypto → applet → keystore) and creating appropriate mocks for each layer
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T4+T5)
  - **Parallel Group**: Wave 3
  - **Blocks**: T7
  - **Blocked By**: T4, T5

  **References**:

  **Pattern References**:
  - `test/tests/test_keystore.py` (at base commit `8131bc9`, 80 lines) — **THE test pattern to follow**. Shows unittest TestCase structure, setUp pattern, assertion style, how to instantiate keystores for testing. Copy this style exactly.
  - `src/keystore/javacard/applets/satochip_securechannel.py` (created in T2) — Test the crypto functions directly (pkcs7_pad, pkcs7_unpad, hmac_sha1)
  - `src/keystore/javacard/applets/seedkeeper_applet.py` (created in T3) — Test applet command construction and response parsing
  - `src/keystore/seedkeeper.py` (created in T4) — Test keystore class structure and state management

  **External References**:
  - Python `unittest.mock` docs — for MagicMock usage in mocking card connection
  - Known HMAC-SHA1 test vectors (RFC 2202) — for verifying hmac_sha1 implementation

  **WHY Each Reference Matters**:
  - `test_keystore.py`: THE style guide. Tests must look and feel like this file.
  - Created files (T2-T4): The actual code being tested. Agent needs to understand the public API of each module.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass
    Tool: Bash
    Preconditions: All implementation files created (T2-T5)
    Steps:
      1. Run: cd test && python3 -m pytest tests/test_seedkeeper.py -v 2>&1 || python3 -m unittest tests.test_seedkeeper -v 2>&1
      2. Assert output contains: OK or passed
      3. Assert output does NOT contain: FAIL or ERROR
    Expected Result: All SeedKeeper tests pass
    Failure Indicators: Any FAIL or ERROR in output
    Evidence: .sisyphus/evidence/task-6-tests.txt

  Scenario: Tests cover all 5 categories
    Tool: Bash
    Preconditions: Test file exists
    Steps:
      1. Run: grep -c "def test_" test/tests/test_seedkeeper.py
      2. Assert count >= 12 (minimum: 2-3 tests per category × 5 categories)
      3. Run: grep "def test_" test/tests/test_seedkeeper.py
      4. Verify tests span: import/structure, crypto, applet, keystore state, bip39
    Expected Result: At least 12 test methods covering all categories
    Failure Indicators: Fewer than 12 tests or missing categories
    Evidence: .sisyphus/evidence/task-6-coverage.txt

  Scenario: Existing tests still pass
    Tool: Bash
    Preconditions: test/__init__.py updated (T5)
    Steps:
      1. Run: cd test && make test 2>&1
      2. Assert output contains: OK
      3. Assert output does NOT contain: FAIL or ERROR (except expected skips)
    Expected Result: Full test suite passes including new tests
    Failure Indicators: Any regression in existing tests
    Evidence: .sisyphus/evidence/task-6-full-suite.txt

  Scenario: No hardware required
    Tool: Bash
    Preconditions: Test file exists
    Steps:
      1. Run: grep -n "mock\|Mock\|MagicMock\|patch" test/tests/test_seedkeeper.py
      2. Assert at least 3 matches (mocking is used for card communication)
      3. Run: grep -n "isCardInserted\|SmartcardConnection\|connect" test/tests/test_seedkeeper.py | grep -iv "mock\|fake\|stub" || echo "ALL_MOCKED"
      4. Assert: No real hardware calls (all mocked)
    Expected Result: Tests use mocks for all card communication
    Failure Indicators: Direct hardware calls without mocking
    Evidence: .sisyphus/evidence/task-6-mocked.txt
  ```

  **Commit**: YES (groups with T2, T3, T4, T5 — all in one commit)
  - Files: `test/tests/test_seedkeeper.py`

- [x] 7. Run full test suite and fix any issues

  **What to do**:
  - Run `make test` from the `test/` directory
  - If any tests fail, diagnose and fix:
    - Import errors → fix imports in the affected file
    - Test failures → fix the test or the implementation (prefer fixing implementation if test exposes a real bug)
    - MicroPython-specific import issues → add conditional imports or skip logic for test environment
  - Run syntax check on all new files: `python3 -m py_compile src/keystore/seedkeeper.py` etc.
  - Verify all QA scenarios from Tasks 2-6 pass
  - **Common issues to anticipate**:
    - MicroPython modules (`ucryptolib`, `secp256k1`, `lvgl`) won't be available in CPython test environment. Ensure these are handled (mocked or conditionally imported).
    - `platform` module conflicts — MicroPython has custom `platform` module with `CriticalErrorWipeImmediately`. Tests may need to mock this.
    - `asyncio.sleep_ms` doesn't exist in CPython — may need `asyncio.sleep(0.03)` equivalent or mock

  **Must NOT do**:
  - Do NOT skip failing tests — fix them
  - Do NOT modify existing test files to accommodate SeedKeeper
  - Do NOT add try/except to hide import errors in production code

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Running tests and fixing minor issues — not designing new code
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T6)
  - **Parallel Group**: Wave 3 (after T6)
  - **Blocks**: T8
  - **Blocked By**: T6

  **References**:

  **Pattern References**:
  - `Makefile` — `test` target for how tests are invoked
  - `test/run_tests.py` — test runner configuration, sys.path setup
  - All files created in T2-T6 — the code being tested

  **WHY Each Reference Matters**:
  - Need to understand how the test runner works to diagnose failures
  - Need to know sys.path setup to fix import issues

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full test suite passes
    Tool: Bash
    Preconditions: All tasks T1-T6 complete
    Steps:
      1. Run: cd test && make test 2>&1
      2. Assert output contains: OK
      3. Assert exit code is 0
      4. Count total tests run — assert > 0
    Expected Result: All tests pass with exit code 0
    Failure Indicators: Any FAIL, ERROR, or non-zero exit code
    Evidence: .sisyphus/evidence/task-7-full-suite.txt

  Scenario: All new files compile cleanly
    Tool: Bash
    Preconditions: Files exist
    Steps:
      1. Run: python3 -m py_compile src/keystore/javacard/applets/satochip_securechannel.py && echo "SC OK"
      2. Run: python3 -m py_compile src/keystore/javacard/applets/seedkeeper_applet.py && echo "APPLET OK"
      3. Run: python3 -m py_compile src/keystore/seedkeeper.py && echo "KS OK"
      4. Run: python3 -m py_compile test/tests/test_seedkeeper.py && echo "TEST OK"
      5. Assert all 4 output: OK
    Expected Result: No syntax errors in any new file
    Failure Indicators: SyntaxError or compilation failure
    Evidence: .sisyphus/evidence/task-7-compile.txt
  ```

  **Commit**: NO (this is verification, not implementation)

- [x] 8. Create git commit(s) on the `satochip` branch

  **What to do**:
  - Stage all new and modified files:
    - `git add src/keystore/javacard/applets/satochip_securechannel.py`
    - `git add src/keystore/javacard/applets/seedkeeper_applet.py`
    - `git add src/keystore/seedkeeper.py`
    - `git add test/tests/test_seedkeeper.py`
    - `git add src/main.py`
    - `git add test/tests/__init__.py`
  - Create commit with message:
    ```
    feat(keystore): add SeedKeeper smartcard support
    
    Add SeedKeeper hardware wallet as a new keystore option, enabling
    users to load BIP39 mnemonics from Satochip SeedKeeper smartcards.
    
    Follows existing MemoryCard pattern:
    - SeedKeeper(RAMKeyStore) keystore with card detection, PIN flow,
      and multi-secret selection
    - SeedKeeperApplet(Applet) with Satochip secure channel protocol
      (ECDH + AES-CBC + HMAC-SHA1)
    - Unit tests with mocked card communication
    
    New files:
    - src/keystore/seedkeeper.py
    - src/keystore/javacard/applets/seedkeeper_applet.py
    - src/keystore/javacard/applets/satochip_securechannel.py
    - test/tests/test_seedkeeper.py
    ```
  - Verify commit: `git log --oneline -2` should show the new commit on top of `8131bc9`
  - Verify only expected files in commit: `git diff --name-only 8131bc9..HEAD`
  - **Alternative**: If the agent finds a natural logical split (e.g., crypto layer separate from keystore), 2-3 commits is fine. But single commit is preferred for simplicity.

  **Must NOT do**:
  - Do NOT commit any files outside the expected set
  - Do NOT use `git add .` (only stage specific files)
  - Do NOT amend upstream commits
  - Do NOT push to remote

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple git operations
  - **Skills**: [`git-master`]
    - `git-master`: Commit creation and verification

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T7)
  - **Parallel Group**: Wave 3 (final step)
  - **Blocks**: F1-F4
  - **Blocked By**: T7

  **References**:

  **Pattern References**:
  - Existing commit history — `git log --oneline -5 8131bc9` for commit message style in this repo

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Commit created with correct files
    Tool: Bash
    Preconditions: T7 passed (all tests pass)
    Steps:
      1. Run: git log --oneline -2
      2. Assert top commit message starts with "feat(keystore): add SeedKeeper"
      3. Run: git diff --name-only 8131bc9..HEAD
      4. Assert exactly 6 files listed:
         - src/keystore/javacard/applets/satochip_securechannel.py
         - src/keystore/javacard/applets/seedkeeper_applet.py
         - src/keystore/seedkeeper.py
         - src/main.py
         - test/tests/__init__.py
         - test/tests/test_seedkeeper.py
      5. Run: git status --porcelain
      6. Assert output is empty (clean working tree)
    Expected Result: Single clean commit with exactly the expected files
    Failure Indicators: Wrong files, dirty working tree, wrong commit message
    Evidence: .sisyphus/evidence/task-8-commit.txt

  Scenario: Branch is on correct base
    Tool: Bash
    Preconditions: Commit created
    Steps:
      1. Run: git log --oneline 8131bc9..HEAD
      2. Assert exactly 1 commit (or 2-3 if split)
      3. Run: git merge-base HEAD 8131bc9
      4. Assert output equals: 8131bc93099332e3a421519c4463be6fe5ac8446
    Expected Result: Branch has clean history from base commit
    Failure Indicators: Extra commits, wrong base
    Evidence: .sisyphus/evidence/task-8-base.txt
  ```

  **Commit**: This IS the commit task.

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run import check). For each "Must NOT Have": search codebase for forbidden patterns (shared base classes, modifications to existing files). Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python3 -m py_compile` on all new files. Review all new files for: bare except clauses, unused imports, inconsistent naming, print statements that should be removed. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify code style matches existing MemoryCard patterns.
  Output: `Compile [PASS/FAIL] | Style [N clean/N issues] | VERDICT`

- [x] F3. **Test + Import Verification** — `unspecified-high`
  Run `make test` from `test/` directory. Verify ALL tests pass (existing + new). Run individual imports: `python3 -c "from keystore.seedkeeper import SeedKeeper"`, `python3 -c "from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet"`, `python3 -c "from keystore.javacard.applets.satochip_securechannel import SatochipSecureChannel"`. Verify class hierarchy with `issubclass()` checks.
  Output: `Tests [N pass/N fail] | Imports [N/N] | Hierarchy [CORRECT/WRONG] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Run `git diff 8131bc9..HEAD --stat` to see all changed files. Verify ONLY expected files changed: `main.py`, `test/tests/__init__.py` (modified), plus 4 new files. Flag ANY unexpected modifications. Check "Must NOT do" compliance — search for `JavaCardKeyStore`, `SecureAppletBase`, `CardDetector` class definitions. Verify no existing file was modified beyond main.py and test/__init__.py.
  Output: `Files [N expected/N unexpected] | Scope [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

The implementation should be committed as **one logical commit** (or 2-3 if the agent finds a natural split). Suggested single commit:

```
feat(keystore): add SeedKeeper smartcard support

Add SeedKeeper hardware wallet as a new keystore option, enabling
users to load BIP39 mnemonics from Satochip SeedKeeper smartcards.

Follows existing MemoryCard pattern:
- SeedKeeper(RAMKeyStore) keystore with card detection, PIN flow,
  and multi-secret selection
- SeedKeeperApplet(Applet) with Satochip secure channel protocol
  (ECDH + AES-CBC + HMAC-SHA1)
- Unit tests with mocked card communication

New files:
- src/keystore/seedkeeper.py
- src/keystore/javacard/applets/seedkeeper_applet.py
- src/keystore/javacard/applets/satochip_securechannel.py
- test/tests/test_seedkeeper.py
```

Pre-commit check: `make test` from `test/` directory.

---

## Success Criteria

### Verification Commands
```bash
# Branch verification
git branch --show-current  # Expected: satochip
git log --oneline -1 HEAD~1  # Expected: starts from 8131bc9 or its child

# Import verification (run from src/ directory)
cd src && python3 -c "from keystore.seedkeeper import SeedKeeper; from keystore.ram import RAMKeyStore; assert issubclass(SeedKeeper, RAMKeyStore); print('OK')"
cd src && python3 -c "from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet; from keystore.javacard.applets.applet import Applet; assert issubclass(SeedKeeperApplet, Applet); print('OK')"
cd src && python3 -c "from keystore.javacard.applets.satochip_securechannel import SatochipSecureChannel; print('OK')"

# Test execution
cd test && make test  # Expected: all tests pass

# Scope check
git diff 8131bc9..HEAD --name-only
# Expected ONLY:
#   src/keystore/seedkeeper.py (new)
#   src/keystore/javacard/applets/seedkeeper_applet.py (new)
#   src/keystore/javacard/applets/satochip_securechannel.py (new)
#   test/tests/test_seedkeeper.py (new)
#   src/main.py (modified)
#   test/tests/__init__.py (modified)
```

### Final Checklist
- [ ] All "Must Have" features present and working
- [ ] All "Must NOT Have" constraints respected
- [ ] All existing tests still pass
- [ ] New SeedKeeper tests pass
- [ ] Branch is clean (no stray files, no merge artifacts)
- [ ] Commit message is clear and descriptive
