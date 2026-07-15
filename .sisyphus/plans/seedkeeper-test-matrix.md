# SeedKeeper Fix Necessity Test Matrix

## TL;DR

> **Quick Summary**: Implement conditional compile flags for each of the 3 f469-disco fixes,
> build all 8 firmware variants (every combination of fixes), flash each to real hardware,
> capture USB debug output, and publish results as a GitHub Gist that definitively shows
> which fix(es) are strictly necessary for SeedKeeper to work.
>
> **Deliverables**:
> - Modified f469-disco C files with `#ifdef SCARD_FIX_*` guards (and `#else` fallback to original code)
> - `results/` directory with raw USB logs per variant
> - Published GitHub Gist with methodology, ATR analysis, results table, and conclusions
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Task 5 (Makefile fix) → Task 6 (validate) → Task 7 (rebuild) → Task 8 (V0/V7) → Task 9 (V1-V6) → Task 10 (analysis) → Task 11 (gist)

---

## Context

### Original Request
Design experiments to show whether each of the 3 f469-disco fixes is necessary or unnecessary
for SeedKeeper. Publish as a Gist that upstream maintainers (diybitcoinhardware/f469-disco) can
reference when deciding whether to merge PR #40 and PR #41.

### The 3 Fixes Under Test

| ID | PR | Files Changed | What It Does |
|----|-----|---------------|--------------|
| **FIX_HALFDUPLEX** | PR #41 | scard_io.c | Explicit CR1 RE/TE bit control instead of skip_bytes counter |
| **FIX_T1_RECONFIG** | PR #40 | scard_io.c, connection.c | Reconfigure USART after ATR: stop bits 1.5→1, guard time 16→1 ETU |
| **FIX_PPS** | (local) | t1_protocol.c | Smart PPS skip (if TA1 absent or =0x11) + always return true from handle_atr |

### The 8-Variant Test Matrix

| Variant | FIX_HALFDUPLEX | FIX_T1_RECONFIG | FIX_PPS | Expected |
|---------|---------------|-----------------|---------|----------|
| V0 | 0 | 0 | 0 | FAIL (baseline, upstream state) |
| V1 | 0 | 0 | 1 | ? |
| V2 | 0 | 1 | 0 | ? |
| V3 | 1 | 0 | 0 | ? |
| V4 | 0 | 1 | 1 | ? |
| V5 | 1 | 0 | 1 | ? |
| V6 | 1 | 1 | 0 | ? |
| V7 | 1 | 1 | 1 | PASS (current working state) |

### Research Findings

- **ISO 7816-3**: T=1 USART reconfig IS required by spec. "Works with T=0 timing" is empirical
  card tolerance, not compliance. Cards specifying TC1=0xFF require strict T=1 timing.
- **Architecture**: All fixes are USART register manipulation — no Python workaround possible.
  uscard module exposes only `connect()`, `transmit()`, `getATR()` to Python.
- **Original skip_bytes comment** in upstream: "Using set_usart_mode() instead causes missing of
  quick responses like PPS exchange responses." — authors tried half-duplex and reverted it.
- **ba058fc commit** in specter-diy: "PPS was never the problem for SeedKeeper — actual issues
  were Python transmit() return format and MASTERSEED entropy offset." This suggests FIX_PPS
  may not be necessary for SeedKeeper at the C level.

### Metis Review (Round 1 — Original Plan)
**Identified Gaps** (addressed):
- Conditional compile flags don't exist yet — must be built before any test variant
- Both code paths must be preserved (#ifdef NEW #else ORIGINAL #endif)
- Must power cycle board between variants (USART config persists across soft reset)
- Docker cache may serve stale builds — use unique output filenames per variant
- SeedKeeper may require PIN entry before "Applet initialized" — must verify PIN is pre-entered
- USB enumeration takes ~3s after flash — need sleep before capturing

### CRITICAL DISCOVERY: Makefile Bug (Round 2)

> **All 8 variant binaries built in Wave 2 were IDENTICAL** (same MD5: `3f6417e9252ce7208ec4ea202f492c7f`).
> The `EXTRA_CFLAGS` parameter passed on the `make disco` command line was **silently ignored**.
>
> **Root Cause**: The top-level Makefile passes `CFLAGS_EXTRA="$(MPY_CFLAGS)"` to micropython's
> STM32 port, but `MPY_CFLAGS` is hardcoded to warning flags only (`-Wno-dangling-pointer
> -Wno-enum-int-mismatch`). The `EXTRA_CFLAGS` variable from the command line was never
> incorporated into any Makefile variable.
>
> **Flag propagation chain** (after fix):
> ```
> Command line: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX"
>     ↓ (new: appended to MPY_CFLAGS)
> MPY_CFLAGS = -Wno-dangling-pointer -Wno-enum-int-mismatch -DSCARD_FIX_HALFDUPLEX
>     ↓ (existing: passed as CFLAGS_EXTRA to sub-make)
> micropython/ports/stm32 Makefile: CFLAGS = ... $(CFLAGS_EXTRA)
>     ↓ (existing: CFLAGS_USERMOD flows into CFLAGS_MOD into CFLAGS)
> scard C files compiled with -DSCARD_FIX_HALFDUPLEX
> ```

### Metis Review (Round 2 — Makefile Fix)
**Identified Gaps** (addressed in updated plan):
- Use `?=` correctly: `EXTRA_CFLAGS ?=` at top, then include in both ifeq branches
- Validate fix with single-variant test build BEFORE rebuilding all 8 (GATE condition)
- Check that flags appear in gcc compiler commands in build log
- Verify all 8 MD5 hashes are UNIQUE (not just "different from old")
- Build variants SEQUENTIALLY (shared build directory prevents parallel builds)
- Do `make clean` between EVERY variant (stale .o files will be reused)

---

## Work Objectives

### Core Objective
Experimentally determine the minimum set of f469-disco fixes required for SeedKeeper,
and publish a reproducible Gist that justifies which PRs upstream should merge.

### Concrete Deliverables
- `f469-disco/usermods/scard/ports/stm32/scard_io.c` — with FIX_HALFDUPLEX and FIX_T1_RECONFIG guards
- `f469-disco/usermods/scard/connection.c` — with FIX_T1_RECONFIG guard
- `f469-disco/usermods/scard/t1_protocol/t1_protocol.c` — with FIX_PPS guard
- `f469-disco/usermods/scard/ports/stm32/scard_io.h` — struct member guard for skip_bytes
- `src/keystore/seedkeeper.py` — ATR logging added to check_card()
- `Makefile` — EXTRA_CFLAGS propagation fix
- `results/V{0-7}_output.log` — raw USB debug output per variant
- `results/test_matrix_results.md` — filled results table
- `results/atr_analysis.md` — ATR decode and conclusions
- GitHub Gist URL — public, shareable

### Definition of Done
- [ ] All 8 variants build without error AND produce UNIQUE binaries
- [ ] V7 (all fixes) passes: `grep "[SeedKeeper] Applet initialized" results/V7_output.log`
- [ ] V0 (no fixes) fails as expected
- [ ] ATR bytes captured for at least one passing variant
- [ ] Gist published with results table filled in

### Must Have
- Both code paths (fixed AND original) preserved in every #ifdef block
- ATR bytes captured and analyzed for TA1/TC1 values
- Raw USB logs attached to or referenced from Gist
- V0 (baseline = no fixes) tested first to confirm test methodology works
- V7 (all fixes) tested immediately after V0 as a sanity check
- Power cycle board between each variant test
- `make clean` between each variant build
- Verification that all 8 binaries have UNIQUE MD5 hashes

### Must NOT Have (Guardrails)
- No changes beyond adding `#ifdef` guards — do NOT refactor or clean up surrounding code
- No testing of non-SeedKeeper cards — scope is SeedKeeper only
- No oscilloscope or hardware timing analysis — USB logs are sufficient
- No debugging of failure modes — record result, move on
- No new features or behavior changes — this is observation-only
- No modification of Python keystore code (except adding ATR logging)
- Do NOT change timeout values in connection.c
- Do NOT test with DEBUG=1 builds (changes timing characteristics)
- Do NOT modify `f469-disco/usermods/scard/micropython.mk`
- Do NOT modify the `disco:` target or the `CFLAGS_EXTRA="$(MPY_CFLAGS)"` line in the Makefile

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (automated unit tests), YES (SSH + USB capture)
- **Automated tests**: Manual hardware tests via SSH
- **Framework**: bash + SSH + USB serial capture

### Pass/Fail Criteria (BINARY)

```bash
# PASS: SeedKeeper applet initialized and PIN prompt shown
grep -q "\[SeedKeeper\] Applet initialized" results/V${N}_output.log && echo "PASS" || echo "FAIL"

# ATR capture (extract from log)
grep "ATR:" results/V${N}_output.log | head -1

# Failure indicator
grep "connect failed" results/V${N}_output.log && echo "FAILED AT CONNECTION"
```

### QA Policy
Every task has agent-executed QA scenarios. Evidence saved to `results/`.

---

## Execution Strategy

### Task Status

- **Tasks 1-4 (Wave 1): ✅ COMPLETE** — Conditional compile guards + ATR logging in place
- **Tasks 5-11 (Waves 2-4): PENDING** — Makefile fix, rebuild, test, analyze, publish

### Execution Waves

```
Wave 2a (Fix — sequential, GATE before proceeding):
├── Task 5: Fix Makefile to pass EXTRA_CFLAGS to scard module [quick]
└── Task 6: Validate fix with single-variant test build [unspecified-high]
    └── GATE: Binary must differ from old build AND flags must appear in build log

Wave 2b (After Gate — rebuild all 8 variants, sequential with make clean):
└── Task 7: Clean-rebuild all 8 variants with verified flag propagation [unspecified-high]

Wave 3 (After Wave 2b — hardware tests, sequential with power cycle):
├── Task 8: Run V0 and V7 sanity check (baseline fail + all-fixes pass) [unspecified-high]
└── Task 9: Run V1-V6 (the 6 unknown variants) [unspecified-high]

Wave 4 (After Wave 3 — analyze + publish):
├── Task 10: Analyze ATR bytes + determine conclusions [deep]
└── Task 11: Write and publish GitHub Gist [writing]

Wave FINAL (After all tasks — independent review):
└── Task F1: Gist Completeness Check [deep]
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 5 | (none — Tasks 1-4 complete) | 6 | 2a |
| 6 | 5 | 7 (GATE) | 2a |
| 7 | 6 (gate passed) | 8 | 2b |
| 8 | 7 | 9 | 3 |
| 9 | 8 | 10, 11 | 3 |
| 10 | 9 | 11 | 4 |
| 11 | 9, 10 | F1 | 4 |
| F1 | 11 | (done) | FINAL |

### Agent Dispatch Summary

- **Wave 2a**: T5 → `quick`, T6 → `unspecified-high`
- **Wave 2b**: T7 → `unspecified-high`
- **Wave 3**: T8, T9 → `unspecified-high`
- **Wave 4**: T10 → `deep`, T11 → `writing`
- **FINAL**: F1 → `deep`

---

## TODOs

---

- [x] 1. Add ATR logging to seedkeeper.py ✅ COMPLETE

- [x] 2. Add #ifdef SCARD_FIX_HALFDUPLEX guards to scard_io.c and scard_io.h ✅ COMPLETE

- [x] 3. Add #ifdef SCARD_FIX_T1_RECONFIG guard to scard_io.c ✅ COMPLETE

- [x] 4. Add #ifdef SCARD_FIX_PPS guard to t1_protocol.c ✅ COMPLETE

---

- [x] 5. Fix Makefile to pass EXTRA_CFLAGS through build chain ✅ COMPLETE

  **What to do**:
  - SSH to build server: `ubuntu@192.168.13.246`
  - Edit `/home/ubuntu/seedkeeperonly/Makefile`
  - Add `EXTRA_CFLAGS ?=` before the `ifeq ($(shell uname),Linux)` block (after line 4, before line 5)
  - Modify the Linux branch:
    ```makefile
    # BEFORE (broken):
    MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch
    # AFTER (fixed):
    MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch $(EXTRA_CFLAGS)
    ```
  - Modify the else branch:
    ```makefile
    # BEFORE:
    MPY_CFLAGS ?=
    # AFTER:
    MPY_CFLAGS ?= $(EXTRA_CFLAGS)
    ```
  - The chain then becomes: command-line `EXTRA_CFLAGS` → `MPY_CFLAGS` → `CFLAGS_EXTRA` →
    micropython `CFLAGS` → applies to all C files including scard module (via `CFLAGS_MOD` ← `CFLAGS_USERMOD`)
  - Also apply the same change to the LOCAL Makefile at `/Users/macbook/src/seedkeeperport/specter-diy-seedkeeperonly/Makefile`

  **Must NOT do**:
  - Do NOT modify any other lines in the Makefile
  - Do NOT modify the `disco:` target or the `CFLAGS_EXTRA="$(MPY_CFLAGS)"` line
  - Do NOT modify `f469-disco/usermods/scard/micropython.mk`
  - Do NOT change any C source files — the guards from Tasks 1-4 are correct

  **Recommended Agent Profile**:
  - **Category**: `quick`  **Skills**: []
  - Reason: Single file edit, 3 lines changed

  **Parallelization**:
  - **Can Run In Parallel**: NO — must be first
  - **Blocks**: Task 6 (validation)
  - **Blocked By**: None (Tasks 1-4 already complete)

  **References**:
  - Build server Makefile: `ssh ubuntu@192.168.13.246 'cat /home/ubuntu/seedkeeperonly/Makefile'`
  - Current content (lines 5-10):
    ```makefile
    MPY_DIR ?= f469-disco/micropython
    ifeq ($(shell uname),Linux)
        MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch
    else
        MPY_CFLAGS ?=
    endif
    ```
  - How flags propagate: Makefile line 48 passes `CFLAGS_EXTRA="$(MPY_CFLAGS)"` to micropython/ports/stm32,
    which sets `CFLAGS = ... $(CFLAGS_EXTRA)` (line 93 of micropython STM32 Makefile),
    and scard's `CFLAGS_USERMOD` flows into `CFLAGS_MOD` (py/py.mk line 38), which is part of `CFLAGS`.

  **Acceptance Criteria**:
  - [ ] `ssh ubuntu@192.168.13.246 'grep EXTRA_CFLAGS /home/ubuntu/seedkeeperonly/Makefile'` shows 3 lines:
    1. `EXTRA_CFLAGS ?=`
    2. `MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch $(EXTRA_CFLAGS)`
    3. `MPY_CFLAGS ?= $(EXTRA_CFLAGS)`
  - [ ] Local Makefile has the same changes

  **QA Scenarios**:
  ```
  Scenario: Makefile correctly references EXTRA_CFLAGS
    Tool: Bash (SSH)
    Steps:
      1. ssh ubuntu@192.168.13.246 'grep -c EXTRA_CFLAGS /home/ubuntu/seedkeeperonly/Makefile'
         → assert output is 3
      2. ssh ubuntu@192.168.13.246 'grep "MPY_CFLAGS.*EXTRA_CFLAGS" /home/ubuntu/seedkeeperonly/Makefile'
         → assert 2 lines returned (Linux branch and else branch)
    Expected Result: EXTRA_CFLAGS referenced in both MPY_CFLAGS definitions
    Failure Indicators: grep returns 0 matches, or EXTRA_CFLAGS only in one branch
    Evidence: results/makefile_fix_verify.log
  ```

  **Commit**: YES
  - Message: `fix(build): pass EXTRA_CFLAGS through Makefile to scard module compilation`
  - Files: `Makefile`

---

- [x] 6. Validate Makefile fix with single-variant test build (GATE) ✅ COMPLETE - MD5=ce96c59173a1b705b305dc27b058b6fb

  **What to do**:
  - On build server, do a clean build of ONE variant (V7 = all flags) to validate:
    ```bash
    ssh ubuntu@192.168.13.246 'cd /home/ubuntu/seedkeeperonly && sudo docker run --rm \
      -v /home/ubuntu/seedkeeperonly:/app -w /app specter24d bash -c \
      "make clean && make disco USE_DBOOT=0 DEBUG=0 EXTRA_CFLAGS=\"-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS\"" \
      2>&1 | tee /home/ubuntu/seedkeeperonly/results/build_validation.log'
    ```
  - Verify flags appear in compiler commands:
    ```bash
    ssh ubuntu@192.168.13.246 'grep -c "SCARD_FIX" /home/ubuntu/seedkeeperonly/results/build_validation.log'
    ```
    Must be > 0 (flags are passed to gcc)
  - Verify binary differs from the old (broken) identical builds:
    ```bash
    ssh ubuntu@192.168.13.246 'md5sum /home/ubuntu/seedkeeperonly/bin/specter-diy.bin'
    ```
    Must NOT be `3f6417e9252ce7208ec4ea202f492c7f` (the old identical hash)
  - **GATE CONDITION**: If flags don't appear in build log OR binary matches old hash → STOP.
    Debug the Makefile further. Do NOT proceed to Task 7.

  **Must NOT do**:
  - Do NOT proceed to Task 7 if this validation fails
  - Do NOT use DEBUG=1
  - Do NOT skip `make clean`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`  **Skills**: []
  - Reason: Needs careful verification and potential debugging if gate fails

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential after Task 5
  - **Blocks**: Task 7 (GATE — must pass before proceeding)
  - **Blocked By**: Task 5

  **References**:
  - Old (broken) hash for ALL 8 variants: `3f6417e9252ce7208ec4ea202f492c7f`
  - Docker image: `specter24d`
  - Build directory: `/home/ubuntu/seedkeeperonly`
  - Build command: `sudo docker run --rm -v /home/ubuntu/seedkeeperonly:/app -w /app specter24d bash -c 'make clean && make disco USE_DBOOT=0 DEBUG=0 EXTRA_CFLAGS="..."'`

  **Acceptance Criteria**:
  - [ ] `grep -c 'SCARD_FIX' results/build_validation.log` > 0 (flags in compiler commands)
  - [ ] `md5sum bin/specter-diy.bin` ≠ `3f6417e9252ce7208ec4ea202f492c7f` (binary differs)
  - [ ] Build exits with code 0 (no compilation errors)

  **QA Scenarios**:
  ```
  Scenario: GATE — Flag propagation validated
    Tool: Bash (SSH)
    Preconditions: Task 5 Makefile fix applied
    Steps:
      1. Run clean build with all 3 flags (command above)
         → assert exit code 0
      2. grep -c 'DSCARD_FIX' results/build_validation.log
         → assert > 0 (flags passed to gcc)
      3. md5sum bin/specter-diy.bin
         → assert NOT 3f6417e9252ce7208ec4ea202f492c7f
    Expected Result: Build succeeds, flags visible in log, binary is different
    Failure Indicators: exit code != 0, grep returns 0, MD5 matches old hash
    Evidence: results/build_validation.log, results/gate_check.log

  Scenario: GATE FAILURE — Stop and debug
    Tool: Bash (SSH)
    Preconditions: Scenario 1 failed
    Steps:
      1. If flags not in log: check Makefile with 'cat /home/ubuntu/seedkeeperonly/Makefile'
      2. Add debug print: insert '$(info CFLAGS_EXTRA=$(CFLAGS_EXTRA))' in micropython STM32 Makefile
      3. Rebuild and check debug output for flag values
    Expected Result: Identify where flags are being dropped
    Evidence: results/gate_debug.log
  ```

  **Commit**: NO (validation only)

---

- [ ] 7. Clean-rebuild all 8 variants with verified flag propagation

  **What to do**:
  - Delete old (identical) variant binaries first:
    ```bash
    ssh ubuntu@192.168.13.246 'rm -f /home/ubuntu/seedkeeperonly/bin/variants/V*.bin'
    ```
  - For each variant V0-V7, run `make clean` then build with the correct flags:
    ```
    V0: EXTRA_CFLAGS=""                                                                    → V0_baseline.bin
    V1: EXTRA_CFLAGS="-DSCARD_FIX_PPS"                                                     → V1_pps.bin
    V2: EXTRA_CFLAGS="-DSCARD_FIX_T1_RECONFIG"                                             → V2_t1reconfig.bin
    V3: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX"                                              → V3_halfduplex.bin
    V4: EXTRA_CFLAGS="-DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS"                              → V4_t1_pps.bin
    V5: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_PPS"                               → V5_hd_pps.bin
    V6: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG"                       → V6_hd_t1.bin
    V7: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX -DSCARD_FIX_T1_RECONFIG -DSCARD_FIX_PPS"       → V7_all.bin
    ```
  - Build command for each variant:
    ```bash
    ssh ubuntu@192.168.13.246 "cd /home/ubuntu/seedkeeperonly && sudo docker run --rm \
      -v /home/ubuntu/seedkeeperonly:/app -w /app specter24d bash -c \
      'make clean && make disco USE_DBOOT=0 DEBUG=0 EXTRA_CFLAGS=\"${FLAGS}\"' \
      2>&1 | tee results/build_V${N}.log \
      && cp bin/specter-diy.bin bin/variants/${NAME}"
    ```
  - Build variants SEQUENTIALLY (not parallel) — shared build directory
  - After ALL 8 are built, verify all MD5 hashes are unique:
    ```bash
    ssh ubuntu@192.168.13.246 'md5sum /home/ubuntu/seedkeeperonly/bin/variants/*.bin | sort'
    ```
    All 8 hashes MUST be different. If any match, the flags are not working for that combination.
  - Also verify V0 build log does NOT contain `DSCARD_FIX` and V7 build log contains all 3.

  **Must NOT do**:
  - Do NOT build in parallel (shared build directory)
  - Do NOT skip `make clean` between variants (stale .o files will be reused)
  - Do NOT use DEBUG=1
  - Do NOT proceed if any variant fails to build or if any two MD5s match

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`  **Skills**: []
  - Reason: Repetitive but needs careful verification at each step; long-running (8 builds)

  **Parallelization**:
  - **Can Run In Parallel**: NO — must be sequential (shared build dir, make clean between)
  - **Blocks**: Tasks 8, 9
  - **Blocked By**: Task 6 (gate must pass)

  **References**:
  - Docker: `specter24d`
  - Build dir: `/home/ubuntu/seedkeeperonly`
  - Old (broken) variant dir: `/home/ubuntu/seedkeeperonly/bin/variants/` — delete old binaries first
  - Flag names: `SCARD_FIX_HALFDUPLEX`, `SCARD_FIX_T1_RECONFIG`, `SCARD_FIX_PPS`
  - The 8 combinations follow a 3-bit binary pattern (bit 0=PPS, bit 1=T1_RECONFIG, bit 2=HALFDUPLEX)

  **Acceptance Criteria**:
  - [ ] All 8 .bin files exist: `ls /home/ubuntu/seedkeeperonly/bin/variants/V*.bin | wc -l` = 8
  - [ ] All 8 MD5 hashes are UNIQUE: `md5sum bin/variants/*.bin | awk '{print $1}' | sort -u | wc -l` = 8
  - [ ] V0 build log does NOT contain `DSCARD_FIX`: `grep -c 'DSCARD_FIX' results/build_V0.log` = 0
  - [ ] V7 build log contains all 3 flags: `grep 'DSCARD_FIX_HALFDUPLEX\|DSCARD_FIX_T1_RECONFIG\|DSCARD_FIX_PPS' results/build_V7.log`
  - [ ] All builds exit code 0

  **QA Scenarios**:
  ```
  Scenario: All 8 variants are distinct binaries
    Tool: Bash (SSH)
    Preconditions: Task 6 gate passed
    Steps:
      1. Delete old variants: rm -f /home/ubuntu/seedkeeperonly/bin/variants/V*.bin
      2. Build each V0-V7 sequentially with make clean between each
      3. md5sum /home/ubuntu/seedkeeperonly/bin/variants/*.bin | sort
         → assert 8 UNIQUE hashes
      4. For V0: grep -c 'DSCARD_FIX' results/build_V0.log → assert 0
      5. For V7: grep 'DSCARD_FIX' results/build_V7.log → assert all 3 flags present
    Expected Result: 8 distinct binaries, correct flags per variant
    Failure Indicators: Any two MD5s match, missing flags in build log, build error
    Evidence: results/build_V0.log through results/build_V7.log, results/md5_all_variants.txt

  Scenario: V0 and V7 binaries are meaningfully different
    Tool: Bash (SSH)
    Steps:
      1. ls -la bin/variants/V0_baseline.bin bin/variants/V7_all.bin → both exist, both > 100KB
      2. cmp bin/variants/V0_baseline.bin bin/variants/V7_all.bin → assert files differ (exit code 1)
    Expected Result: Files are different
    Evidence: results/binary_diff_check.log
  ```

  **Commit**: NO (build artifacts on remote server, not committed)

---

- [ ] 8. Run V0 and V7 sanity check (baseline fail + all-fixes pass)

  **What to do**:
  - **V0 test** (no fixes — upstream baseline, expected FAIL):
    1. Reset board: `ssh ubuntu@192.168.13.246 'sudo st-flash reset'`
    2. Wait 3 seconds
    3. Flash V0: `ssh ubuntu@192.168.13.246 'sudo st-flash --reset write /home/ubuntu/seedkeeperonly/bin/variants/V0_baseline.bin 0x8000000'`
    4. Wait 5 seconds for USB enumeration
    5. Configure and capture serial:
       ```bash
       ssh ubuntu@192.168.13.246 'sudo stty -F /dev/ttyACM1 115200 raw -echo; timeout 30 sudo cat /dev/ttyACM1' > results/V0_output.log
       ```
    6. Check result: `grep -q 'connect failed\|protocol not supported' results/V0_output.log`
  - **V7 test** (all fixes — expected PASS):
    1. Reset board: `ssh ubuntu@192.168.13.246 'sudo st-flash reset'`
    2. Wait 3 seconds
    3. Flash V7: same command but V7_all.bin
    4. Wait 5 seconds, capture 30 seconds of serial output → results/V7_output.log
    5. Check result: `grep -q 'Applet initialized' results/V7_output.log`
    6. Extract ATR: `grep 'ATR:' results/V7_output.log`
  - **STOP CONDITIONS**:
    - If V7 FAILS: The Makefile fix or conditional guards broke something. Debug before continuing.
    - If V0 PASSES: The original code works without fixes — test methodology may be invalid, or the
      #else branches don't match original code. Investigate.
  - **IMPORTANT**: If serial capture is empty or inconclusive, try:
    - Longer timeout (60s instead of 30s)
    - Physical power cycle (ask user via agent message)
    - Verify ttyACM1 is the correct port: `ls -la /dev/ttyACM*`

  **Must NOT do**:
  - Do NOT proceed to V1-V6 if V0 or V7 behaves unexpectedly
  - Do NOT enter PIN on the SeedKeeper (tests observe connection behavior only)
  - Do NOT use DEBUG=1 firmware

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`  **Skills**: []
  - Reason: Hardware interaction via SSH, needs judgment on pass/fail

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential (hardware shared resource)
  - **Blocks**: Task 9
  - **Blocked By**: Task 7

  **References**:
  - Flash: `sudo st-flash --reset write <bin> 0x8000000`
  - Reset: `sudo st-flash reset`
  - Serial config: `sudo stty -F /dev/ttyACM1 115200 raw -echo`
  - Serial capture: `timeout 30 sudo cat /dev/ttyACM1`
  - Pass indicator: `[SeedKeeper] Applet initialized`
  - Fail indicators: `connect failed`, `protocol not supported`, `PIN for internal storage`
  - USB devices: ttyACM0 = ST-LINK debug, ttyACM1 = MicroPython Virtual Comm Port

  **Acceptance Criteria**:
  - [ ] V0 output contains `connect failed` or `protocol not supported` (expected failure)
  - [ ] V7 output contains `Applet initialized` (expected pass)
  - [ ] V7 output contains `ATR:` line with hex bytes
  - [ ] V0 and V7 outputs are DIFFERENT (confirming firmware difference matters)

  **QA Scenarios**:
  ```
  Scenario: Sanity check — V0 fails, V7 passes
    Tool: Bash (SSH)
    Preconditions: V0_baseline.bin and V7_all.bin are distinct binaries (Task 7 verified)
    Steps:
      1. Reset + flash V0 + wait 5s + capture 30s → results/V0_output.log
      2. grep -q 'connect failed\|protocol not supported' results/V0_output.log
         → assert true (V0 should fail)
      3. Reset + flash V7 + wait 5s + capture 30s → results/V7_output.log
      4. grep -q 'Applet initialized' results/V7_output.log
         → assert true (V7 should pass)
      5. grep 'ATR:' results/V7_output.log | head -1
         → assert contains hex bytes starting with '3B' or '3F'
      6. diff results/V0_output.log results/V7_output.log
         → assert files differ
    Expected Result: V0 fails, V7 passes, ATR captured, outputs differ
    Failure Indicators: V7 fails (guards broke something), V0 passes (original code works), identical output
    Evidence: results/V0_output.log, results/V7_output.log

  Scenario: V7 failure — debug stop
    Tool: Bash (SSH)
    Preconditions: V7 did NOT show 'Applet initialized'
    Steps:
      1. Check if capture was empty: wc -c results/V7_output.log
         → if 0 bytes, serial capture failed (wrong port or baud rate)
      2. Check full output: cat results/V7_output.log
         → look for error messages, stack traces
      3. Try longer capture: timeout 60 sudo cat /dev/ttyACM1
         → maybe initialization takes longer than 30s
    Expected Result: Identify whether failure is test-methodology or firmware
    Evidence: results/V7_debug.log
  ```

  **Commit**: NO (test results saved locally)

---

- [ ] 9. Run V1-V6 (the 6 unknown single and double-fix variants)

  **What to do**:
  - For each variant V1 through V6 in order:
    1. Reset board: `sudo st-flash reset`
    2. Wait 3 seconds
    3. Flash the variant: `sudo st-flash --reset write bin/variants/V${N}_${NAME}.bin 0x8000000`
    4. Wait 5 seconds for USB enumeration
    5. Capture 30 seconds of serial:
       `sudo stty -F /dev/ttyACM1 115200 raw -echo; timeout 30 sudo cat /dev/ttyACM1` → results/V${N}_output.log
    6. Determine PASS/FAIL:
       - PASS: `grep -q 'Applet initialized' results/V${N}_output.log`
       - FAIL: `grep -q 'connect failed\|protocol not supported' results/V${N}_output.log`
       - INCONCLUSIVE: neither string found → retry with 60-second timeout
    7. If INCONCLUSIVE after 2 retries: record as INCONCLUSIVE with notes
  - Fill in the results table and save to `results/test_matrix_results.md`:
    ```
    | Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result |
    |---------|-----------|-------------|-----|--------|
    | V0      | OFF       | OFF         | OFF | FAIL   |  ← from Task 8
    | V1      | OFF       | OFF         | ON  | ?      |
    | V2      | OFF       | ON          | OFF | ?      |
    | V3      | ON        | OFF         | OFF | ?      |
    | V4      | OFF       | ON          | ON  | ?      |
    | V5      | ON        | OFF         | ON  | ?      |
    | V6      | ON        | ON          | OFF | ?      |
    | V7      | ON        | ON          | ON  | PASS   |  ← from Task 8
    ```

  **Must NOT do**:
  - Do NOT skip any variant
  - Do NOT test out of order
  - Do NOT forget to reset between variants (USART config persists)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`  **Skills**: []
  - Reason: Repetitive hardware testing, needs judgment on inconclusive results

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential (single board)
  - **Blocks**: Tasks 10, 11
  - **Blocked By**: Task 8 (V0/V7 sanity must pass)

  **References**:
  - Variant files on build server: `/home/ubuntu/seedkeeperonly/bin/variants/V{1..6}_*.bin`
  - Flash: `sudo st-flash --reset write <bin> 0x8000000`
  - Serial: `sudo stty -F /dev/ttyACM1 115200 raw -echo; timeout 30 sudo cat /dev/ttyACM1`
  - Pass: `Applet initialized`
  - Fail: `connect failed`, `protocol not supported`

  **Acceptance Criteria**:
  - [ ] All 6 log files exist: `ls results/V{1..6}_output.log | wc -l` = 6
  - [ ] Each log is non-empty: `wc -c results/V{1..6}_output.log` — all > 0 bytes
  - [ ] Each variant has a definitive result (PASS, FAIL, or documented INCONCLUSIVE)
  - [ ] Results table saved to `results/test_matrix_results.md`

  **QA Scenarios**:
  ```
  Scenario: All 6 variants produce definitive results
    Tool: Bash (SSH)
    Steps:
      1. For each V1-V6: reset + flash + wait + capture → results/V${N}_output.log
      2. For each: grep -q 'Applet initialized\|connect failed\|protocol not supported' results/V${N}_output.log
         → assert at least one match per file
      3. Verify no empty files:
         for n in 1 2 3 4 5 6; do test -s results/V${n}_output.log && echo "V${n}: OK" || echo "V${n}: EMPTY"; done
    Expected Result: 6 non-empty logs, each with definitive PASS or FAIL
    Failure Indicators: Empty log (serial capture failed), no pass/fail string (INCONCLUSIVE)
    Evidence: results/V1_output.log through results/V6_output.log, results/test_matrix_results.md
  ```

  **Commit**: NO (test results saved locally)

---

- [ ] 10. Analyze ATR bytes and determine conclusions

  **What to do**:
  - Parse the captured ATR from `results/V7_output.log` (or first passing variant)
  - Decode the ATR structure per ISO 7816-3:
    - TS (byte 0): 0x3B = direct convention, 0x3F = inverse
    - T0 (byte 1): upper nibble = indicator bits for TA1/TB1/TC1/TD1 presence
    - TAi/TBi/TCi/TDi: interface bytes based on TD indicator bits
  - Specifically determine:
    - **TA1**: Baud rate negotiation parameter
      - If absent or 0x11 → PPS is unnecessary (card uses default speed)
      - If other value → PPS needed to negotiate baud rate
    - **TC1**: Extra guard time
      - If 0xFF → minimum guard time, T=1 timing critical → T1_RECONFIG likely necessary
      - If absent → default guard time (12 ETU), less critical
    - **TD1**: Protocol indicator (T=0 or T=1)
  - Cross-reference with experimental results:
    ```
    If V3 (HALFDUPLEX only) PASSES → HALFDUPLEX alone is sufficient for connection
    If V3 FAILS but V6 (HD+T1) PASSES → both HD and T1 needed together
    If V1 (PPS only) PASSES → PPS is the key fix
    Single-fix variants that PASS identify individually sufficient fixes
    Single-fix variants that FAIL identify individually insufficient fixes
    ```
  - Write conclusions:
    ```
    FIX_HALFDUPLEX: NECESSARY / NOT NECESSARY / INSUFFICIENT ALONE (evidence: V3 result)
    FIX_T1_RECONFIG: NECESSARY / NOT NECESSARY / INSUFFICIENT ALONE (evidence: V2 result)
    FIX_PPS: NECESSARY / NOT NECESSARY / INSUFFICIENT ALONE (evidence: V1 result)
    MINIMUM FIX SET: [smallest combination of fixes that produces PASS]
    ```
  - Save analysis to `results/atr_analysis.md`

  **Recommended Agent Profile**:
  - **Category**: `deep`  **Skills**: []
  - Reason: Requires ISO 7816-3 knowledge and logical analysis of test matrix

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 4 (but Task 11 needs its output)
  - **Blocked By**: Task 9

  **References**:
  - ISO 7816-3 ATR structure: TS, T0, TA1, TB1, TC1, TD1 byte positions
  - `results/V7_output.log` — ATR bytes to parse
  - `results/V{0..6}_output.log` — test results to cross-reference
  - `results/test_matrix_results.md` — summary table from Task 9

  **Acceptance Criteria**:
  - [ ] ATR hex bytes listed in `results/atr_analysis.md`
  - [ ] TA1 value (or absence) documented with interpretation
  - [ ] TC1 value (or absence) documented with interpretation
  - [ ] Each fix has a conclusion: NECESSARY / NOT NECESSARY / INSUFFICIENT ALONE
  - [ ] Minimum fix set identified

  **QA Scenarios**:
  ```
  Scenario: ATR decoded and all conclusions stated
    Tool: Bash (local)
    Steps:
      1. grep 'ATR:' results/V7_output.log | head -1 → assert non-empty
      2. cat results/atr_analysis.md | grep -c 'NECESSARY\|NOT NECESSARY\|INSUFFICIENT'
         → assert >= 3 (one conclusion per fix)
      3. grep 'MINIMUM FIX SET' results/atr_analysis.md → assert present
    Expected Result: Complete analysis with all conclusions
    Evidence: results/atr_analysis.md
  ```

  **Commit**: NO

---

- [ ] 11. Write and publish GitHub Gist

  **What to do**:
  - Write `seedkeeper-f469-disco-fix-analysis.md` with these sections:
    1. **Background**: SeedKeeper smart card, STM32F469-Discovery + Specter Shield, f469-disco scard module
    2. **The 3 Fixes Under Test**: FIX_HALFDUPLEX (PR #41), FIX_T1_RECONFIG (PR #40), FIX_PPS (local)
    3. **Test Methodology**: 8-variant matrix, conditional compile flags, Docker build, st-flash + serial capture
    4. **SeedKeeper ATR Analysis**: Raw bytes, decoded structure, TA1/TC1 interpretation
    5. **Results Table**: All 8 variants with PASS/FAIL
    6. **Analysis**: Which fixes are individually sufficient, necessary, minimum set
    7. **Conclusions & Recommendations**: Which PRs upstream should merge, in what priority
  - Publish:
    ```bash
    gh gist create --public \
      --desc 'SeedKeeper smart card compatibility analysis: which f469-disco USART fixes are necessary? (PR #40, PR #41)' \
      seedkeeper-f469-disco-fix-analysis.md
    ```
  - Post the Gist URL as a comment on PR #40 and PR #41:
    ```bash
    gh pr comment 40 --repo diybitcoinhardware/f469-disco --body "SeedKeeper compatibility analysis: <GIST_URL>"
    gh pr comment 41 --repo diybitcoinhardware/f469-disco --body "SeedKeeper compatibility analysis: <GIST_URL>"
    ```

  **Must NOT do**:
  - Do NOT claim results apply to cards other than SeedKeeper
  - Do NOT recommend closing PRs — only recommend merging or further testing
  - Do NOT include proprietary or sensitive information (PIN, seed words)

  **Recommended Agent Profile**:
  - **Category**: `writing`  **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — needs Task 10 conclusions
  - **Blocked By**: Tasks 9, 10

  **References**:
  - `results/test_matrix_results.md` — filled results table
  - `results/atr_analysis.md` — ATR analysis and conclusions
  - `results/V{0..7}_output.log` — raw evidence
  - PR #40: https://github.com/diybitcoinhardware/f469-disco/pull/40
  - PR #41: https://github.com/diybitcoinhardware/f469-disco/pull/41

  **Acceptance Criteria**:
  - [ ] Gist published and URL obtained
  - [ ] Gist contains all 7 sections listed above
  - [ ] Results table has all 8 variants with PASS/FAIL
  - [ ] Recommendations section present
  - [ ] Comments posted on both PR #40 and PR #41

  **QA Scenarios**:
  ```
  Scenario: Gist is publicly accessible and complete
    Tool: Bash (gh CLI)
    Steps:
      1. gh gist list --limit 1 → find the new gist
      2. gh gist view <GIST_ID> | grep -q 'Results' → assert present
      3. gh gist view <GIST_ID> | grep -q 'Recommendations' → assert present
      4. gh gist view <GIST_ID> | grep -c '| V[0-7]' → assert 8 (all variants in table)
    Expected Result: Public gist with complete content
    Evidence: results/gist_url.txt

  Scenario: PR comments posted
    Tool: Bash (gh CLI)
    Steps:
      1. gh pr view 40 --repo diybitcoinhardware/f469-disco --comments | grep -q 'SeedKeeper'
         → assert present
      2. gh pr view 41 --repo diybitcoinhardware/f469-disco --comments | grep -q 'SeedKeeper'
         → assert present
    Expected Result: Both PRs have the analysis link
    Evidence: (visible in PR comment threads)
  ```

  **Commit**: YES
  - Message: `docs: add SeedKeeper fix analysis results and gist`
  - Files: `results/test_matrix_results.md`, `results/atr_analysis.md`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

- [ ] F1. **Gist Completeness Check** — `deep`
  Read the published Gist end-to-end. Verify:
  - Test matrix has all 8 variants filled in (no '?' remaining)
  - ATR bytes are present and decoded
  - Conclusions clearly state which fixes are necessary vs optional
  - Minimum fix set is identified
  - Recommendations are actionable for upstream maintainers
  - Gist is publicly accessible (curl the URL)
  - Comments exist on both PR #40 and PR #41
  Output: `APPROVE` or `REJECT with specific missing items`

---

## Commit Strategy

- **Task 5**: `fix(build): pass EXTRA_CFLAGS through Makefile to scard module compilation` — Makefile
- **Task 11**: `docs: add SeedKeeper fix analysis results and gist` — results/

## Success Criteria

### Verification Commands
```bash
# All 8 builds are DIFFERENT (the critical fix!)
ssh ubuntu@192.168.13.246 'md5sum /home/ubuntu/seedkeeperonly/bin/variants/*.bin | awk "{print \$1}" | sort -u | wc -l'
# Expected: 8

# V0 fails, V7 passes
grep -q 'connect failed\|protocol not supported' results/V0_output.log && echo 'V0 FAIL (expected)'
grep -q 'Applet initialized' results/V7_output.log && echo 'V7 PASS (expected)'

# ATR captured
grep 'ATR:' results/V7_output.log

# Results complete
grep -c '| V[0-7]' results/test_matrix_results.md  # Expected: 8

# Gist published
cat results/gist_url.txt  # Expected: https://gist.github.com/...
```

### Final Checklist
- [ ] Makefile fix applied and verified (EXTRA_CFLAGS propagates to scard C files)
- [ ] All 8 variants built with UNIQUE binaries (8 different MD5 hashes)
- [ ] All 8 variants tested on hardware with definitive results
- [ ] ATR bytes captured and analyzed
- [ ] Minimum fix set identified
- [ ] Gist published with complete results
- [ ] Comments posted on PR #40 and PR #41
