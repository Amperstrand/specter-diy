# Clean SeedKeeper Branch for Upstream PR

## TL;DR

> **Quick Summary**: Create a clean `seedkeeper` git branch from upstream commit `8131bc9` containing ONLY SeedKeeper-related changes in 4-5 logical commits, ready for an upstream specter-diy PR.
> 
> **Deliverables**:
> - Clean `seedkeeper` branch with 4-5 atomic commits
> - New files: seedkeeper.py, seedkeeper_applet.py, seedkeeper_securechannel.py
> - Surgical patches to 6 existing files (memorycard, ram, main, specter, manager, wallet)
> - Zero Satochip/debug/test_mode contamination
> - Optional: test files in final commit
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: NO — sequential commits (each builds on the previous)
> **Critical Path**: Branch creation → Commit 1 → Commit 2 → Commit 3 → Commit 4 → Commit 5 → Verification

---

## Context

### Original Request
Create a clean git branch isolating ONLY SeedKeeper-related changes from the messy development history. The branch should start from upstream commit `8131bc9` and contain 4-5 logical commits suitable for an upstream PR to specter-diy.

### Interview Summary
**Key Discussions**:
- **Secure channel naming**: DO NOT rename `seedkeeper_securechannel.py` → `securechannel.py`. Upstream already has a different `securechannel.py` for BlindOracle protocol.
- **can_export_seed**: INCLUDE as infrastructure — defined in ram.py, used in specter.py to hide buttons for non-exportable keystores.
- **specter.py bug**: Working copy accidentally deleted the entire settingsmenu processing block. Must restore from upstream.
- **Debug print statements**: The `print('[SeedKeeper]...')` statements in seedkeeper files appear to be intentional trace logging. Include them unless user says otherwise.
- **wallet_label safety**: `manager.py` uses `getattr(self.keystore, "wallet_label", "Default")` — safe for non-SeedKeeper keystores via getattr default.

**Research Findings**:
- Upstream `securechannel.py` (201 lines) = BlindOracle protocol (HMAC-SHA256, `\x80` padding)
- `seedkeeper_securechannel.py` (233 lines) = SeedKeeper protocol (HMAC-SHA1, PKCS#7, different INS codes)
- Both `satochip_applet.py` AND `seedkeeper_applet.py` import from `seedkeeper_securechannel` — shared between Satochip-family applets
- `seedkeeper.py` has dead code at lines 361-367 (duplicated `load_mnemonic` docstring) — clean up when copying
- f469-disco submodule changed in working copy — must NOT include in clean branch

### Metis Review
**Identified Gaps** (addressed):
- **wallet_label attribute**: Uses `getattr` with default fallback — safe for non-SeedKeeper keystores. No base class change needed.
- **settingsmenu restoration**: Must use `git show 8131bc9:src/specter.py` to get exact upstream content, then apply only SeedKeeper additions.
- **Scope creep risk**: Locked down — only SeedKeeper-gated changes pass through. Any change not behind `if isinstance(keystore, SeedKeeper)` or `if hasattr(keystore, 'can_export_seed')` must be justified.

---

## Work Objectives

### Core Objective
Produce a clean, reviewable `seedkeeper` branch containing only SeedKeeper hardware wallet support, ready for upstream PR submission.

### Concrete Deliverables
- Git branch `seedkeeper` based on `8131bc9`
- Commit 1: Infrastructure (memorycard.py + ram.py)
- Commit 2: Applet layer (seedkeeper_securechannel.py + seedkeeper_applet.py)
- Commit 3: Keystore (seedkeeper.py)
- Commit 4: Integration (main.py + specter.py + manager.py + wallet.py)
- Commit 5 (optional): Test files

### Definition of Done
- [ ] `git log --oneline seedkeeper` shows 4-5 clean commits on top of `8131bc9`
- [ ] `git diff 8131bc9..seedkeeper --name-only` shows ONLY expected files (no satochip, no debug, no docs)
- [ ] `grep -r "satochip" src/` on the branch returns NO hits (except comments explaining SeedKeeper context)
- [ ] `grep -r "test_mode" src/` returns NO hits
- [ ] Each commit builds without syntax errors
- [ ] Import chain is complete: seedkeeper.py → seedkeeper_applet.py → seedkeeper_securechannel.py
- [ ] f469-disco submodule is at upstream state (`db3ce3e`)

### Must Have
- Clean commit history (no squash of unrelated changes)
- All SeedKeeper functionality preserved
- Upstream compatibility (no changes to base classes)
- settingsmenu processing block fully intact in specter.py
- can_export_seed infrastructure in ram.py + specter.py

### Must NOT Have (Guardrails)
- Satochip files (`satochip.py`, `satochip_applet.py`)
- `test_mode.py` or any test_mode imports/references
- Debug boot files (`boot/debug/*`, modified `boot/main/boot.py`)
- Internal documentation (`SEEDKEEPER_INTEGRATION_STRATEGY.md`, `docs/LESSONS_LEARNED*.md`)
- Changes to base classes (`KeyStore`, `RAMKeyStore` class definition) unless can_export_seed property
- Changes to `PinScreen` widget
- f469-disco submodule changes
- Changes to upstream `securechannel.py` (BlindOracle)
- Changes to `applet.py` base class

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (Makefile has `make test` target)
- **Automated tests**: NO (this is a git branch creation task, not feature development)
- **Framework**: N/A
- **Primary verification**: Git diff analysis + grep exclusion checks + import chain verification

### QA Policy
Every task includes agent-executed QA scenarios verifying:
1. Correct files are included/excluded via `git diff --name-only`
2. No contamination via grep checks
3. Import chains resolve correctly
4. Upstream settingsmenu block is intact

Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Sequential Execution (Git Commits Are Order-Dependent)

> This plan is SEQUENTIAL — each commit builds on the previous one.
> Parallelism is not applicable because git commits are ordered.
> However, within each task, file operations CAN be parallelized.

```
Wave 1 (Branch Setup):
└── Task 1: Create clean branch from upstream 8131bc9

Wave 2 (Commit 1 — Infrastructure):
└── Task 2: memorycard.py disconnect fix + ram.py can_export_seed

Wave 3 (Commit 2 — Applet Layer):
└── Task 3: Add seedkeeper_securechannel.py + seedkeeper_applet.py

Wave 4 (Commit 3 — Keystore):
└── Task 4: Add seedkeeper.py keystore

Wave 5 (Commit 4 — Integration):
└── Task 5: Patch main.py + specter.py + manager.py + wallet.py

Wave 6 (Commit 5 — Optional Tests):
└── Task 6: Add test files

Wave FINAL (Verification):
├── Task F1: Plan compliance audit
├── Task F2: Contamination check (grep for excluded content)
├── Task F3: Import chain + syntax verification
└── Task F4: Diff review (every changed line is SeedKeeper-related)
```

### Dependency Matrix
- **T1**: None → T2, T3, T4, T5, T6
- **T2**: T1 → T3
- **T3**: T2 → T4
- **T4**: T3 → T5
- **T5**: T4 → T6
- **T6**: T5 → F1-F4
- **F1-F4**: T6 (parallel final verification)

### Agent Dispatch Summary
- **Wave 1**: T1 → `quick`
- **Wave 2**: T2 → `quick`
- **Wave 3**: T3 → `quick`
- **Wave 4**: T4 → `quick`
- **Wave 5**: T5 → `deep` (most complex — 4 files with surgical patches)
- **Wave 6**: T6 → `quick`
- **FINAL**: F1-F4 → `deep`, `quick`, `quick`, `deep` (parallel)

---

## TODOs

- [x] 1. Create clean branch from upstream commit 8131bc9

  **What to do**:
  - Run `git checkout 8131bc9` to move to the upstream base commit
  - Run `git checkout -b seedkeeper` to create the new branch
  - Verify with `git log --oneline -1` that HEAD is at `8131bc9`
  - Verify with `git submodule status` that f469-disco is at `db3ce3e`
  - If submodule is different, run `git submodule update --init`

  **Must NOT do**:
  - Do NOT cherry-pick from existing history
  - Do NOT bring any working copy changes

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple git commands, no code changes
  - **Skills**: [`git-master`]
    - `git-master`: Git branch operations

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (solo)
  - **Blocks**: Tasks 2, 3, 4, 5, 6
  - **Blocked By**: None (first task)

  **References**:
  - Upstream commit: `8131bc9` ("Fix: minor comment cleanups (#343)")
  - Current HEAD: `eacc06f` ("checkpoint")
  - f469-disco expected: `db3ce3e`

  **Acceptance Criteria**:
  - [ ] `git rev-parse HEAD` returns hash starting with `8131bc9`
  - [ ] `git branch --show-current` returns `seedkeeper`
  - [ ] `git submodule status` shows f469-disco at `db3ce3e`

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Branch created at correct upstream commit
    Tool: Bash
    Preconditions: Repository at any state
    Steps:
      1. Run `git checkout 8131bc9 && git checkout -b seedkeeper`
      2. Run `git rev-parse HEAD`
      3. Run `git branch --show-current`
      4. Run `git submodule status`
    Expected Result: HEAD starts with `8131bc9`, branch is `seedkeeper`, f469-disco at `db3ce3e`
    Failure Indicators: Different commit hash, wrong branch name, submodule at `ba058fc`
    Evidence: .sisyphus/evidence/task-1-branch-created.txt
  ```

  **Commit**: NO (no code changes, just branch creation)

---

- [x] 2. Commit 1 — Infrastructure: memorycard disconnect fix + can_export_seed

  **What to do**:
  - **memorycard.py**: Apply 1-line fix to `is_available()` exception handler
    - In the `except Exception as e:` block of `is_available()`, add `cls.connection.disconnect()` before `cls.connection = None`
    - Extract the exact upstream file first: `git show 8131bc9:src/keystore/memorycard.py > /tmp/memorycard_upstream.py`
    - Extract the HEAD version: `git show eacc06f:src/keystore/memorycard.py > /tmp/memorycard_head.py`
    - Apply ONLY the disconnect line (the single line addition in the except block)
  - **ram.py**: Add `can_export_seed` property after `save_mnemonic` method (~line 206)
    - Extract upstream: `git show 8131bc9:src/keystore/ram.py > /tmp/ram_upstream.py`
    - Add the following property after the existing `save_mnemonic` method:
    ```python
    @property
    def can_export_seed(self):
        """Whether this keystore can export the seed/mnemonic."""
        return True
    ```
    - This is ~8 lines including the decorator, docstring, and return

  **Must NOT do**:
  - Do NOT change RAMKeyStore class definition or __init__
  - Do NOT change any other methods in ram.py
  - Do NOT change memorycard.py beyond the single disconnect line

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Two small surgical patches, no complex logic
  - **Skills**: [`git-master`]
    - `git-master`: Staging specific changes for clean commit

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential)
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References (CRITICAL — Be Exhaustive)**:

  **Pattern References**:
  - `src/keystore/memorycard.py` — Current upstream version at `8131bc9`. The `is_available()` classmethod has a try/except block. The fix adds `cls.connection.disconnect()` in the except handler before `cls.connection = None`.
  - `src/keystore/ram.py` — Current upstream at `8131bc9`. The `save_mnemonic` method ends around line 206. Add `can_export_seed` property directly after it.

  **Diff References**:
  - `git diff 8131bc9..eacc06f -- src/keystore/memorycard.py` — Shows the exact 1-line addition needed
  - `git diff 8131bc9..eacc06f -- src/keystore/ram.py` — Shows the exact `can_export_seed` property to add (filter out any other changes)

  **Acceptance Criteria**:
  - [ ] `git diff HEAD~1..HEAD --name-only` shows exactly: `src/keystore/memorycard.py`, `src/keystore/ram.py`
  - [ ] `git diff HEAD~1..HEAD -- src/keystore/memorycard.py` shows only the disconnect line
  - [ ] `git diff HEAD~1..HEAD -- src/keystore/ram.py` shows only the can_export_seed property
  - [ ] `python3 -c "import ast; ast.parse(open('src/keystore/memorycard.py').read())"` — no syntax errors
  - [ ] `python3 -c "import ast; ast.parse(open('src/keystore/ram.py').read())"` — no syntax errors

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: memorycard.py has exactly one new line (disconnect)
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 1
    Steps:
      1. Run `git diff 8131bc9..HEAD -- src/keystore/memorycard.py`
      2. Count added lines (lines starting with `+` excluding `+++`)
      3. Verify the added line contains `cls.connection.disconnect()`
    Expected Result: Exactly 1 added line containing `cls.connection.disconnect()`
    Failure Indicators: More than 1 added line, missing disconnect call, other changes
    Evidence: .sisyphus/evidence/task-2-memorycard-diff.txt

  Scenario: ram.py has can_export_seed property and nothing else
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 1
    Steps:
      1. Run `git diff 8131bc9..HEAD -- src/keystore/ram.py`
      2. Verify diff contains `can_export_seed` property definition
      3. Verify diff does NOT contain any other changes
      4. Run `python3 -c "import ast; ast.parse(open('src/keystore/ram.py').read())"`
    Expected Result: Only can_export_seed property added, syntax valid
    Failure Indicators: Additional changes, syntax error, missing property
    Evidence: .sisyphus/evidence/task-2-ram-diff.txt

  Scenario: Commit is clean with correct message
    Tool: Bash
    Preconditions: Both files patched
    Steps:
      1. Run `git log --oneline -1`
      2. Verify commit message matches expected pattern
      3. Run `git diff HEAD~1..HEAD --name-only`
      4. Verify exactly 2 files
    Expected Result: Commit message starts with `feat(keystore):`, exactly 2 files changed
    Failure Indicators: Wrong message format, wrong file count, unexpected files
    Evidence: .sisyphus/evidence/task-2-commit-clean.txt
  ```

  **Commit**: YES
  - Message: `feat(keystore): add memorycard disconnect fix and can_export_seed property`
  - Files: `src/keystore/memorycard.py`, `src/keystore/ram.py`
  - Pre-commit: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/keystore/memorycard.py', 'src/keystore/ram.py']]"`

---

- [x] 3. Commit 2 — Applet Layer: SeedKeeper secure channel + applet

  **What to do**:
  - **seedkeeper_securechannel.py**: Copy from HEAD into clean branch
    - Run `git show eacc06f:src/keystore/javacard/applets/seedkeeper_securechannel.py > src/keystore/javacard/applets/seedkeeper_securechannel.py`
    - Verify the file exists and parses correctly
    - DO NOT rename this file (upstream has different `securechannel.py` for BlindOracle)
  - **seedkeeper_applet.py**: Copy from HEAD into clean branch
    - Run `git show eacc06f:src/keystore/javacard/applets/seedkeeper_applet.py > src/keystore/javacard/applets/seedkeeper_applet.py`
    - Verify import chain: `seedkeeper_applet.py` imports from `seedkeeper_securechannel`, `applet`, and `embit.bip39`
  - Both files are NEW (don't exist in upstream), so just `git add` them

  **Must NOT do**:
  - Do NOT modify upstream `securechannel.py` (BlindOracle protocol)
  - Do NOT modify `applet.py` base class
  - Do NOT add `satochip_applet.py`
  - Do NOT modify `__init__.py` files (they're empty and should stay empty)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Copy 2 files from HEAD, verify, commit
  - **Skills**: [`git-master`]
    - `git-master`: Extracting files from specific commits

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential)
  - **Blocks**: Task 4
  - **Blocked By**: Task 2

  **References (CRITICAL — Be Exhaustive):**

  **Source Files (copy from HEAD):**
  - `git show eacc06f:src/keystore/javacard/applets/seedkeeper_securechannel.py` — 233 lines, implements SeedKeeper-specific secure channel protocol: ECDH key exchange, AES-CBC encryption, HMAC-SHA1 MAC. Key classes: `SeedKeeperSecureChannel`. Uses PKCS#7 padding, IV with odd last byte, counter increments by 2.
  - `git show eacc06f:src/keystore/javacard/applets/seedkeeper_applet.py` — SeedKeeper APDU command layer. Key class: `SeedKeeperApplet`. Imports `SeedKeeperSecureChannel` from `.seedkeeper_securechannel`. Methods: `card_init_connect`, `card_verify_PIN`, `card_generate_masterseed`, `card_generate_2FA_secret`, `card_import_secret`, `card_export_secret`, `card_bip32_get_extendedkey`, etc.

  **Architecture Context:**
  - `src/keystore/javacard/applets/securechannel.py` — UPSTREAM file (201 lines). BlindOracle protocol. Uses HMAC-SHA256, `\x80` padding, GET_PUBKEY/OPEN_EE/OPEN_SE. DO NOT TOUCH OR CONFUSE WITH seedkeeper_securechannel.py.
  - `src/keystore/javacard/applets/applet.py` — UPSTREAM base class. Unchanged. `seedkeeper_applet.py` inherits from `Applet` defined here.
  - `src/keystore/javacard/applets/__init__.py` — Empty file. Must remain empty.
  - `src/keystore/javacard/__init__.py` — Empty file. Must remain empty.

  **Import Chain to Verify:**
  ```
  seedkeeper_applet.py
  ├── from .applet import Applet, ISOException, AppletException  (UPSTREAM — exists)
  ├── from .seedkeeper_securechannel import SeedKeeperSecureChannel  (NEW — just added)
  └── from embit import bip39  (UPSTREAM dep — exists)
  ```

  **Acceptance Criteria**:
  - [ ] `git diff HEAD~1..HEAD --name-only` shows exactly 2 new files in `src/keystore/javacard/applets/`
  - [ ] `python3 -c "import ast; ast.parse(open('src/keystore/javacard/applets/seedkeeper_securechannel.py').read())"` — no errors
  - [ ] `python3 -c "import ast; ast.parse(open('src/keystore/javacard/applets/seedkeeper_applet.py').read())"` — no errors
  - [ ] `grep -c 'class SeedKeeperSecureChannel' src/keystore/javacard/applets/seedkeeper_securechannel.py` returns 1
  - [ ] `grep -c 'class SeedKeeperApplet' src/keystore/javacard/applets/seedkeeper_applet.py` returns 1
  - [ ] `grep 'from .seedkeeper_securechannel import' src/keystore/javacard/applets/seedkeeper_applet.py` shows the import exists

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Both applet files exist and parse correctly
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 2
    Steps:
      1. Run `ls -la src/keystore/javacard/applets/seedkeeper_*.py`
      2. Run `python3 -c "import ast; ast.parse(open('src/keystore/javacard/applets/seedkeeper_securechannel.py').read())"` 
      3. Run `python3 -c "import ast; ast.parse(open('src/keystore/javacard/applets/seedkeeper_applet.py').read())"`
      4. Run `wc -l src/keystore/javacard/applets/seedkeeper_securechannel.py` (expect ~233 lines)
      5. Run `wc -l src/keystore/javacard/applets/seedkeeper_applet.py` (expect ~400+ lines)
    Expected Result: Both files exist, parse without errors, have expected line counts
    Failure Indicators: File not found, syntax error, truncated file
    Evidence: .sisyphus/evidence/task-3-applet-files.txt

  Scenario: Upstream securechannel.py is untouched
    Tool: Bash
    Preconditions: On seedkeeper branch after adding new files
    Steps:
      1. Run `git diff 8131bc9..HEAD -- src/keystore/javacard/applets/securechannel.py`
      2. Verify diff is empty (no changes)
    Expected Result: Zero diff — upstream securechannel.py is completely unchanged
    Failure Indicators: Any diff output at all
    Evidence: .sisyphus/evidence/task-3-upstream-securechannel-untouched.txt

  Scenario: No Satochip applet included
    Tool: Bash
    Preconditions: After commit
    Steps:
      1. Run `ls src/keystore/javacard/applets/satochip_applet.py 2>&1`
      2. Run `git diff HEAD~1..HEAD --name-only`
    Expected Result: satochip_applet.py does NOT exist, only seedkeeper files in diff
    Failure Indicators: satochip_applet.py exists or appears in diff
    Evidence: .sisyphus/evidence/task-3-no-satochip.txt
  ```

  **Commit**: YES
  - Message: `feat(javacard): add SeedKeeper secure channel and applet`
  - Files: `src/keystore/javacard/applets/seedkeeper_securechannel.py`, `src/keystore/javacard/applets/seedkeeper_applet.py`
  - Pre-commit: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/keystore/javacard/applets/seedkeeper_securechannel.py', 'src/keystore/javacard/applets/seedkeeper_applet.py']]"`

---

- [x] 4. Commit 3 — Keystore: SeedKeeper keystore implementation

  **What to do**:
  - **seedkeeper.py**: Copy from HEAD into clean branch
    - Run `git show eacc06f:src/keystore/seedkeeper.py > src/keystore/seedkeeper.py`
    - **Clean up dead code**: Remove duplicated `load_mnemonic` docstring and stub at lines 361-367 of the HEAD version (a duplicated, incomplete `load_mnemonic` method after the real implementation)
    - Verify imports resolve: `from .ram import RAMKeyStore`, `from .javacard.applets.seedkeeper_applet import SeedKeeperApplet`, etc.
  - The file is NEW (doesn't exist in upstream)

  **Must NOT do**:
  - Do NOT modify RAMKeyStore base class
  - Do NOT modify KeyStore base class
  - Do NOT add satochip.py
  - Do NOT strip `print('[SeedKeeper]...')` trace statements (these are intentional trace logging)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Copy 1 file, minor dead code cleanup, commit
  - **Skills**: [`git-master`]
    - `git-master`: Extracting files from specific commits

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (sequential)
  - **Blocks**: Task 5
  - **Blocked By**: Task 3

  **References (CRITICAL — Be Exhaustive):**

  **Source File (copy from HEAD):**
  - `git show eacc06f:src/keystore/seedkeeper.py` — ~370 lines. Key class: `SeedKeeper(RAMKeyStore)`. NAME = "SeedKeeper". Methods: `init()` (card connection + secure channel + PIN + master seed + 2FA), `load_mnemonic()` (export from card + BIP39 decode), `save_mnemonic()` (import to card + optional BIP85). Inherits `can_export_seed = True` from RAMKeyStore (added in Task 2).

  **Dead Code to Remove (lines 361-367 of HEAD version):**
  - After the real `load_mnemonic()` implementation, there's a duplicated docstring and basic stub:
    ```python
    async def load_mnemonic(self):
        """Load mnemonic from the SeedKeeper card."""
        mnemonic = await self.applet.card_export_secret(0)
        return mnemonic
    ```
  - This is dead code because the REAL `load_mnemonic()` above it (~lines 280-360) is the complete implementation. Remove the duplicate.

  **Import Chain to Verify:**
  ```
  seedkeeper.py
  ├── from .ram import RAMKeyStore  (UPSTREAM + Task 2 additions)
  ├── from .javacard.applets.seedkeeper_applet import SeedKeeperApplet  (Task 3)
  ├── from .javacard.applets.applet import ISOException, AppletException  (UPSTREAM)
  ├── from .javacard.util import get_connection  (UPSTREAM)
  └── from .core import KeyStoreError, PinError  (UPSTREAM)
  ```

  **Architecture Context:**
  - `src/keystore/ram.py` — RAMKeyStore base class (modified in Task 2 with `can_export_seed`). SeedKeeper inherits from this. MUST exist before this task.
  - `src/keystore/core.py` — UPSTREAM. Defines `KeyStoreError`, `PinError`. No changes.
  - `src/keystore/javacard/util.py` — UPSTREAM. Provides `get_connection()` for smart card communication. No changes.

  **Acceptance Criteria**:
  - [ ] `git diff HEAD~1..HEAD --name-only` shows exactly 1 new file: `src/keystore/seedkeeper.py`
  - [ ] `python3 -c "import ast; ast.parse(open('src/keystore/seedkeeper.py').read())"` — no errors
  - [ ] `grep -c 'class SeedKeeper' src/keystore/seedkeeper.py` returns 1
  - [ ] `grep 'NAME = ' src/keystore/seedkeeper.py` shows `NAME = "SeedKeeper"`
  - [ ] Dead code (duplicated load_mnemonic stub) is NOT present
  - [ ] `grep -c 'async def load_mnemonic' src/keystore/seedkeeper.py` returns exactly 1 (not 2)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: seedkeeper.py exists, parses, and has correct class
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 3
    Steps:
      1. Run `python3 -c "import ast; ast.parse(open('src/keystore/seedkeeper.py').read())"`
      2. Run `grep 'class SeedKeeper' src/keystore/seedkeeper.py`
      3. Run `grep 'NAME = ' src/keystore/seedkeeper.py`
      4. Run `grep -c 'async def load_mnemonic' src/keystore/seedkeeper.py`
    Expected Result: Parses OK, has `class SeedKeeper(RAMKeyStore)`, NAME="SeedKeeper", exactly 1 load_mnemonic
    Failure Indicators: Syntax error, wrong class name, NAME mismatch, 2 load_mnemonic methods
    Evidence: .sisyphus/evidence/task-4-seedkeeper-class.txt

  Scenario: Dead code removed
    Tool: Bash
    Preconditions: After dead code cleanup
    Steps:
      1. Run `grep -n 'async def load_mnemonic' src/keystore/seedkeeper.py`
      2. Verify only ONE occurrence exists
      3. Run `tail -20 src/keystore/seedkeeper.py` to verify no trailing duplicate
    Expected Result: Single load_mnemonic definition, no trailing stub
    Failure Indicators: Two load_mnemonic definitions, stub still present at end of file
    Evidence: .sisyphus/evidence/task-4-dead-code-removed.txt

  Scenario: No satochip.py added
    Tool: Bash
    Preconditions: After commit
    Steps:
      1. Run `ls src/keystore/satochip.py 2>&1`
      2. Run `git diff HEAD~1..HEAD --name-only`
    Expected Result: satochip.py does NOT exist, only seedkeeper.py in diff
    Failure Indicators: satochip.py exists or appears in diff
    Evidence: .sisyphus/evidence/task-4-no-satochip.txt
  ```

  **Commit**: YES
  - Message: `feat(keystore): add SeedKeeper keystore implementation`
  - Files: `src/keystore/seedkeeper.py`
  - Pre-commit: `python3 -c "import ast; ast.parse(open('src/keystore/seedkeeper.py').read())"`

---

- [ ] 5. Commit 4 — Integration: Wire SeedKeeper into boot, UI, and wallet management

  **What to do**:
  This is the most complex task — 4 files need surgical patches on top of the upstream base. For EACH file:
  1. Extract the upstream version: `git show 8131bc9:src/{path} > src/{path}` (start from clean upstream)
  2. Extract the HEAD version to a temp file: `git show eacc06f:src/{path} > /tmp/{filename}_head.py`
  3. Compare and apply ONLY SeedKeeper-related hunks

  **File-by-file instructions:**

  **A. `src/main.py`** — Add SeedKeeper to keystores list
  - Start from upstream `git show 8131bc9:src/main.py`
  - Add import: `from keystore.seedkeeper import SeedKeeper` (after existing keystore imports)
  - Add `SeedKeeper` to the `keystores` list (probe order: after MemoryCard, before Flash/RAMKeyStore)
  - DO NOT add `from keystore.satochip import Satochip`
  - DO NOT add `from test_mode import maybe_enter_test_mode` or any test_mode code
  - DO NOT change the USB/QR communication setup
  - The upstream `keystores` list is: `[MemoryCard, SDKeyStore, Flash, RAMKeyStore]`
  - New list should be: `[MemoryCard, SeedKeeper, SDKeyStore, Flash, RAMKeyStore]`

  **B. `src/specter.py`** — 3 surgical additions + KEEP all upstream code intact
  - Start from upstream `git show 8131bc9:src/specter.py` — this is the BASELINE (has the settingsmenu processing block intact)
  - **Change 1 (~line 193)**: After `await self.unlock()`, add auto-load skip block:
    ```python
    # If the keystore is already ready after unlock (e.g., SeedKeeper loads during init),
    # skip the load_mnemonic step
    if self.keystore.is_ready:
        return True
    ```
    This goes AFTER `await self.unlock()` and BEFORE the `if await self.load_mnemonic():` block.
  - **Change 2 (~line 248)**: In `initmenu()`, wrap key generation/recovery buttons in `can_export_seed` check:
    ```python
    if self.keystore.can_export_seed:
        buttons += [
            (lv.SYMBOL.EDIT, "Generate new key"),
            (lv.SYMBOL.DOWNLOAD, "Enter recovery phrase"),
        ]
    ```
    The upstream version has these buttons unconditionally. Wrap them.
  - **Change 3 (~line 399)**: In `settingsmenu()`, wrap Show recovery phrase / Enter passphrase in `can_export_seed` check:
    ```python
    if self.keystore.can_export_seed:
        buttons += [
            (lv.SYMBOL.DOWNLOAD, "Show recovery phrase"),
            (None, "Enter BIP-39 passphrase"),
        ]
    ```
  - **CRITICAL**: The `settingsmenu()` function's menu item processing block (the if/elif chain that handles button selections, ~lines 410-436 in upstream) MUST remain INTACT. The working copy HEAD accidentally deleted this block. Since we start from upstream, it will be there — just don't delete it.
  - DO NOT add any test_mode imports or test_mode handling
  - DO NOT add `from test_mode import maybe_enter_test_mode`

  **C. `src/apps/wallets/manager.py`** — SeedKeeper wallet label + creation
  - Start from upstream `git show 8131bc9:src/apps/wallets/manager.py`
  - **Change 1 (~line 131-142)**: In the wallet rename/label section, add SeedKeeper label routing:
    When renaming, if the keystore has `wallet_label` attribute, set it on the keystore:
    ```python
    if hasattr(self.keystore, 'wallet_label'):
        self.keystore.wallet_label = new_name
    ```
  - **Change 2 (~line 523-540)**: In wallet creation, use SeedKeeper label for wallet name:
    ```python
    name = getattr(self.keystore, 'wallet_label', 'Default')
    ```
  - Add `from gui.components.alert import Alert` if needed for any SeedKeeper-specific alerts
  - Use `git diff 8131bc9..eacc06f -- src/apps/wallets/manager.py` to see exact hunks and apply only SeedKeeper-related ones

  **D. `src/apps/wallets/wallet.py`** — SeedKeeper name handling in save/load
  - Start from upstream `git show 8131bc9:src/apps/wallets/wallet.py`
  - **Change 1 (~line 116-120)**: In `save()`, skip name persistence for SeedKeeper:
    If the keystore has `wallet_label`, don't save the name to the descriptor (it comes from the card)
  - **Change 2 (~line 325-330)**: In `load()`, read wallet_label from keystore:
    Use the keystore's `wallet_label` as the wallet display name if available
  - Use `git diff 8131bc9..eacc06f -- src/apps/wallets/wallet.py` to see exact hunks

  **Must NOT do**:
  - Do NOT delete the settingsmenu processing block in specter.py
  - Do NOT add test_mode imports or handling in any file
  - Do NOT add Satochip import in main.py
  - Do NOT change base classes or PinScreen widget
  - Do NOT change USB/QR communication setup
  - Do NOT change f469-disco submodule

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Most complex task — 4 files with surgical patches requiring careful diff analysis
  - **Skills**: [`git-master`]
    - `git-master`: Extracting upstream versions, analyzing diffs for cherry-picking hunks

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (sequential)
  - **Blocks**: Task 6
  - **Blocked By**: Task 4

  **References (CRITICAL — Be Exhaustive):**

  **Diff References (THE PRIMARY GUIDE for each file):**
  - `git diff 8131bc9..eacc06f -- src/main.py` — Shows ALL changes. Include ONLY: `from keystore.seedkeeper import SeedKeeper` import and adding `SeedKeeper` to keystores list. EXCLUDE: `from keystore.satochip import Satochip`, `from test_mode import maybe_enter_test_mode`, any test_mode handling blocks.
  - `git diff 8131bc9..eacc06f -- src/specter.py` — Shows ALL changes. Include ONLY: (1) is_ready check after unlock ~line 193, (2) can_export_seed button wrapping in initmenu ~line 248, (3) can_export_seed button wrapping in settingsmenu ~line 399. EXCLUDE: test_mode imports, test_mode handling. WARNING: HEAD version has deleted settingsmenu processing block — since we start from upstream this block will already be present.
  - `git diff 8131bc9..eacc06f -- src/apps/wallets/manager.py` — Shows ALL changes. Include ONLY SeedKeeper-gated hunks (wallet_label routing, SeedKeeper name in wallet creation, Alert import if used).
  - `git diff 8131bc9..eacc06f -- src/apps/wallets/wallet.py` — Shows ALL changes. Include ONLY SeedKeeper-gated hunks (name skip in save, wallet_label in load).

  **Upstream Baseline Files (start from these, NOT from HEAD):**
  - `git show 8131bc9:src/main.py` — Clean upstream. Has `keystores = [MemoryCard, SDKeyStore, Flash, RAMKeyStore]`.
  - `git show 8131bc9:src/specter.py` — Clean upstream. HAS the settingsmenu processing block intact (lines ~410-436). This is the safe baseline.
  - `git show 8131bc9:src/apps/wallets/manager.py` — Clean upstream.
  - `git show 8131bc9:src/apps/wallets/wallet.py` — Clean upstream.

  **Architecture Context:**
  - `src/keystore/seedkeeper.py` — Task 4 already added this. Has `NAME = "SeedKeeper"`, class `SeedKeeper(RAMKeyStore)`, `wallet_label` attribute.
  - The `can_export_seed` property was added to RAMKeyStore in Task 2. All keystores inheriting from RAMKeyStore now have it (returns True).
  - `getattr(self.keystore, 'wallet_label', 'Default')` is safe — uses getattr with default for non-SeedKeeper keystores.
  - `hasattr(self.keystore, 'wallet_label')` is safe — returns False for non-SeedKeeper keystores.

  **WHY Each Reference Matters:**
  - The diffs show EVERYTHING that changed, but we must cherry-pick ONLY SeedKeeper hunks. The diff is your map.
  - The upstream baselines are the STARTING POINT. Apply patches onto these, never start from HEAD versions.
  - specter.py is the highest-risk file because the HEAD version has a bug (deleted settingsmenu block). Starting from upstream avoids this.

  **Acceptance Criteria**:
  - [ ] `git diff HEAD~1..HEAD --name-only` shows exactly: `src/main.py`, `src/specter.py`, `src/apps/wallets/manager.py`, `src/apps/wallets/wallet.py`
  - [ ] `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/main.py', 'src/specter.py', 'src/apps/wallets/manager.py', 'src/apps/wallets/wallet.py']]"` — no syntax errors
  - [ ] `grep 'from keystore.seedkeeper import SeedKeeper' src/main.py` — exists
  - [ ] `grep 'SeedKeeper' src/main.py | grep -v import | grep 'keystores'` — SeedKeeper in keystores list
  - [ ] `grep -c 'satochip' src/main.py` returns 0
  - [ ] `grep -c 'test_mode' src/main.py` returns 0
  - [ ] `grep -c 'test_mode' src/specter.py` returns 0
  - [ ] `grep 'can_export_seed' src/specter.py` — shows usage in initmenu and settingsmenu
  - [ ] `grep 'is_ready' src/specter.py` — shows the auto-load skip check
  - [ ] `grep 'wallet_label' src/apps/wallets/manager.py` — shows SeedKeeper label routing
  - [ ] `grep 'wallet_label' src/apps/wallets/wallet.py` — shows SeedKeeper name handling
  - [ ] specter.py settingsmenu processing block is intact (verify the if/elif chain exists after the button definitions)

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: main.py has SeedKeeper import and keystores entry, no contamination
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 4
    Steps:
      1. Run `grep 'from keystore.seedkeeper import SeedKeeper' src/main.py`
      2. Run `grep 'SeedKeeper' src/main.py` to verify it's in keystores list
      3. Run `grep -c 'satochip' src/main.py`
      4. Run `grep -c 'test_mode' src/main.py`
    Expected Result: SeedKeeper import present, in keystores, 0 satochip refs, 0 test_mode refs
    Failure Indicators: Missing import, missing from keystores, satochip or test_mode present
    Evidence: .sisyphus/evidence/task-5-main-py.txt

  Scenario: specter.py has all 3 SeedKeeper additions and settingsmenu processing intact
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 4
    Steps:
      1. Run `grep -n 'is_ready' src/specter.py` to verify auto-load skip
      2. Run `grep -n 'can_export_seed' src/specter.py` to verify both usages
      3. Run `grep -c 'test_mode' src/specter.py` to verify no test_mode
      4. Run `grep -A5 'scr.get_value()' src/specter.py | head -30` to verify settingsmenu processing block exists (the if/elif chain that handles menu selections)
      5. Run `python3 -c "import ast; ast.parse(open('src/specter.py').read())"`
    Expected Result: is_ready check exists, 2+ can_export_seed usages, 0 test_mode, settingsmenu if/elif chain present, syntax valid
    Failure Indicators: Missing is_ready, missing can_export_seed, test_mode present, missing settingsmenu processing, syntax error
    Evidence: .sisyphus/evidence/task-5-specter-py.txt

  Scenario: manager.py and wallet.py have SeedKeeper-gated changes only
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 4
    Steps:
      1. Run `grep -n 'wallet_label' src/apps/wallets/manager.py`
      2. Run `grep -n 'wallet_label' src/apps/wallets/wallet.py`
      3. Run `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/apps/wallets/manager.py', 'src/apps/wallets/wallet.py']]"`
    Expected Result: wallet_label references in both files, syntax valid
    Failure Indicators: Missing wallet_label, syntax errors
    Evidence: .sisyphus/evidence/task-5-wallet-files.txt

  Scenario: Full integration diff is clean (no extra files)
    Tool: Bash
    Preconditions: After commit
    Steps:
      1. Run `git diff HEAD~1..HEAD --name-only | sort`
      2. Compare against expected: main.py, specter.py, manager.py, wallet.py (exactly 4 files)
    Expected Result: Exactly 4 files, all in expected list
    Failure Indicators: More or fewer files, unexpected file paths
    Evidence: .sisyphus/evidence/task-5-integration-diff.txt
  ```

  **Commit**: YES
  - Message: `feat(integration): wire SeedKeeper into boot, UI, and wallet management`
  - Files: `src/main.py`, `src/specter.py`, `src/apps/wallets/manager.py`, `src/apps/wallets/wallet.py`
  - Pre-commit: `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/main.py', 'src/specter.py', 'src/apps/wallets/manager.py', 'src/apps/wallets/wallet.py']]"`

---

- [ ] 6. Commit 5 (Optional) — Test files

  **What to do**:
  - Copy test files from HEAD into the branch:
    - `git show eacc06f:tests/seedkeeper-test-plan.md > tests/seedkeeper-test-plan.md`
    - `git show eacc06f:tests/seedkeeper_interactive_test.sh > tests/seedkeeper_interactive_test.sh`
    - `git show eacc06f:tests/seedkeeper_test.sh > tests/seedkeeper_test.sh`
  - Create `tests/` directory if it doesn't exist on this branch
  - `git add tests/` and commit

  **Must NOT do**:
  - Do NOT add any files outside the tests/ directory
  - Do NOT modify any source files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Copy 3 files, commit
  - **Skills**: [`git-master`]
    - `git-master`: File extraction from commits

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 6 (sequential)
  - **Blocks**: F1-F4 (final verification)
  - **Blocked By**: Task 5

  **References:**
  - `git show eacc06f:tests/seedkeeper-test-plan.md` — Test plan documentation for SeedKeeper
  - `git show eacc06f:tests/seedkeeper_interactive_test.sh` — Interactive test script
  - `git show eacc06f:tests/seedkeeper_test.sh` — Automated test script

  **Acceptance Criteria**:
  - [ ] `git diff HEAD~1..HEAD --name-only` shows exactly 3 test files
  - [ ] All 3 files exist in `tests/` directory
  - [ ] No source files modified

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Test files copied correctly
    Tool: Bash
    Preconditions: On seedkeeper branch after Task 5
    Steps:
      1. Run `ls tests/seedkeeper*`
      2. Run `wc -l tests/seedkeeper-test-plan.md`
      3. Run `wc -l tests/seedkeeper_interactive_test.sh`
      4. Run `wc -l tests/seedkeeper_test.sh`
      5. Run `git diff HEAD~1..HEAD --name-only`
    Expected Result: All 3 files exist, non-empty, only test files in commit
    Failure Indicators: Missing files, empty files, source files in commit
    Evidence: .sisyphus/evidence/task-6-test-files.txt
  ```

  **Commit**: YES
  - Message: `test: add SeedKeeper test files`
  - Files: `tests/seedkeeper-test-plan.md`, `tests/seedkeeper_interactive_test.sh`, `tests/seedkeeper_test.sh`
  - Pre-commit: N/A (non-code files)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run git commands). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Contamination Check** — `quick`
  On the `seedkeeper` branch, run: `grep -r "satochip" src/`, `grep -r "test_mode" src/`, `grep -r "debug" boot/`. Verify `git diff 8131bc9..seedkeeper --name-only` contains ONLY the expected files. Check f469-disco submodule is at upstream commit `db3ce3e`. Reject if ANY unexpected file or content found.
  Output: `Satochip refs [CLEAN/N found] | test_mode refs [CLEAN/N found] | Debug refs [CLEAN/N found] | File list [EXACT/N extra] | Submodule [OK/CHANGED] | VERDICT`

- [ ] F3. **Import Chain + Syntax Verification** — `quick`
  Verify all imports resolve: `python3 -c "import ast; ast.parse(open('src/keystore/seedkeeper.py').read())"` for each new/modified file. Trace import chain: seedkeeper.py → seedkeeper_applet.py → seedkeeper_securechannel.py. Verify no circular imports. Check that `from keystore.seedkeeper import SeedKeeper` in main.py would resolve.
  Output: `Syntax [N/N pass] | Imports [N/N resolve] | Circular [CLEAN/N found] | VERDICT`

- [ ] F4. **Diff Review — Every Line Is SeedKeeper-Related** — `deep`
  Run `git diff 8131bc9..seedkeeper` and review EVERY changed line. For each hunk, verify it is SeedKeeper-related. Flag any line that appears to be: unrelated refactoring, Satochip-specific, debug-only, or scope creep. Special attention to specter.py — verify settingsmenu processing block matches upstream exactly (no deletions, no additions beyond can_export_seed wrapping).
  Output: `Hunks reviewed [N] | SeedKeeper-related [N/N] | Flagged [N lines] | VERDICT`

---

## Commit Strategy

- **Commit 1**: `feat(keystore): add memorycard disconnect fix and can_export_seed property` — memorycard.py, ram.py
- **Commit 2**: `feat(javacard): add SeedKeeper secure channel and applet` — seedkeeper_securechannel.py, seedkeeper_applet.py
- **Commit 3**: `feat(keystore): add SeedKeeper keystore implementation` — seedkeeper.py
- **Commit 4**: `feat(integration): wire SeedKeeper into boot, UI, and wallet management` — main.py, specter.py, manager.py, wallet.py
- **Commit 5**: `test: add SeedKeeper test files` — tests/*

---

## Success Criteria

### Verification Commands
```bash
git log --oneline seedkeeper  # Expected: 4-5 commits on top of 8131bc9
git diff 8131bc9..seedkeeper --name-only  # Expected: only SeedKeeper files
git diff 8131bc9..seedkeeper --stat  # Expected: reasonable line counts
grep -r "satochip" src/  # Expected: no hits (on seedkeeper branch)
grep -r "test_mode" src/  # Expected: no hits
git submodule status  # Expected: f469-disco at db3ce3e
python3 -c "import ast; ast.parse(open('src/keystore/seedkeeper.py').read())"  # Expected: no errors
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] 4-5 clean, logical commits
- [ ] Each commit is self-contained and reviewable
- [ ] Import chain complete and resolvable
- [ ] settingsmenu processing block intact in specter.py
- [ ] No debug/Satochip/test_mode contamination
- [ ] f469-disco submodule unchanged from upstream
