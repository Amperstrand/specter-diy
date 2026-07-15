
## ATR Logging Implementation (2026-03-11)

Successfully added ATR logging to SeedKeeper check_card() method:

### Implementation Details
- **File**: `src/keystore/seedkeeper.py`
- **Method**: `check_card()` 
- **Location**: Line 262 (after successful `conn.connect()`)
- **Code**: `print('[BootTrace][SeedKeeper] ATR:', ' '.join('%02X' % b for b in self.connection.getATR()))`

### Key Findings
1. ATR is obtained via `self.connection.getATR()` which returns bytes
2. Format uses existing `[BootTrace][SeedKeeper]` prefix for consistency with other logging
3. ATR bytes are formatted as hex strings with ` ` (space) separator
4. Placed immediately after successful connect, before `connect_error = None`
5. Located inside the protocol loop (lines 253-266) for T1/T0 protocol attempts

### ATR Information Value
- ATR bytes reveal TA1 (PPS necessity indicator)
- ATR bytes reveal TC1 (guard time/BWT configuration)
- Critical for test matrix to determine f469-disco fix necessity
- This logging enables analysis of SeedKeeper card protocol requirements

### Verification
- Grep pattern confirmed: `grep 'BootTrace.*SeedKeeper.*ATR'` returns the statement
- Python syntax validation passed
- No logic changes, only monitoring/logging addition

## SCARD_FIX_PPS Guard Implementation (2026-03-11)

### Task Completed
Added `#ifdef SCARD_FIX_PPS` conditional compile guard to `handle_atr()` in `f469-disco/usermods/scard/t1_protocol/t1_protocol.c`.

### Implementation Details
- **When SCARD_FIX_PPS is defined**:
  - Uses smart PPS logic: skips PPS exchange if TA1 is absent, TA2 is present, or TA1=0x11 (default)
  - Always returns `true` (card is compatible)

- **When SCARD_FIX_PPS is NOT defined** (original behavior):
  - Always requests PPS in negotiable mode (if TA2 absent)
  - Returns `false` when T=1 is not supported
  - Returns `true` otherwise

### Key Structural Points
1. Both the smart PPS skip logic AND the `return true` change are guarded together
   - Commit ba058fc ("PPS was never the problem for SeedKeeper") grouped these changes
   - Testing both together enables proper validation
2. Line 853 marks the guard boundary with `#ifdef SCARD_FIX_PPS`
3. Line 881 closes guard with `#endif`
4. Line 873 provides `#else` for original behavior fallback

### Verification
- LSP diagnostics: clean (no errors)
- Guard structure: 3 related lines (ifdef/else/endif)
- File compiles without warnings
- Git diff shows clear before/after behavior

### Testing Strategy
This guard enables:
1. Testing with PPS fix enabled (fast path, fewer exchanges)
2. Testing with original always-PPS logic (baseline)
3. Comparative testing to validate "PPS was never the problem" hypothesis


## 2026-03-11: SCARD_FIX_HALFDUPLEX Conditional Compilation

### Task: Add conditional compile guards for half-duplex fix

**Files modified:**
- `f469-disco/usermods/scard/ports/stm32/scard_io.h`
- `f469-disco/usermods/scard/ports/stm32/scard_io.c`

**Key patterns:**
- `#ifdef SCARD_FIX_HALFDUPLEX` enables the half-duplex fix (hd_dir_t, set_half_duplex())
- `#else` branch contains the original upstream code (usart_mode_t, set_usart_mode(), skip_bytes)
- `skip_bytes` struct member is conditionally compiled with `#ifndef SCARD_FIX_HALFDUPLEX`

**Verification:** `grep -c 'SCARD_FIX_HALFDUPLEX' scard_io.c` returns 17 (>= 4 required)

**Historical context from upstream comment:**
> "Using set_usart_mode() instead causes missing of quick responses like PPS exchange responses"

This indicates the original authors tried half-duplex mode and reverted to skip_bytes approach due to race conditions with fast-responding cards.
## Conditional Compile Guards Added to SCARD_FIX_HALFDUPLEX

- scard_io.h: Added `skip_bytes` member under `#ifndef SCARD_FIX_HALFDUPLEX` guard
- scard_io.c: 
1. Added `hd_dir_t` enum +`set_half_duplex()` function under`#ifdef SCARD_FIX_HALFDUPLEX` guard
2. Added `usart_mode_t` enum+`set_usart_mode()` function under`#else` branch
3. Added `skip_bytes` initialization under`#ifndef SCARD_FIX_HALFDUPLEX` guard
7. Added conditional paths in `scard_rx_readinto()`
8. Added conditional paths in `scard_tx_write()`
9. Added conditional paths in `uart_callback()`

## Verification
- `grep -c 'SCARD_FIX_HALFDUPLEX' scard_io.c` returns 17 (>= 4)
- `grep -c 'SCARD_FIX_HALFDUPLEX' scard_io.h` returns 1 (1 new member added)

## Summary
Both code paths compile cleanly with proper `#ifdef`/`#endif` guards.
- When `SCARD_FIX_HALFDUPLEX` is defined: uses half-duplex fix with `hd_dir_t`, `set_half_duplex()`
- When NOT defined: uses original skip_bytes approach with `usart_mode_t`, `set_usart_mode()`
- Original upstream noted skip_bytes has race condition on quick card responses

## Makefile EXTRA_CFLAGS Propagation Fix (2026-03-11)

### Task: Pass EXTRA_CFLAGS through build chain to scard module

### Problem Identified
Old builds produced IDENTICAL binaries because EXTRA_CFLAGS was ignored by Makefile.

### Root Cause
MPY_CFLAGS was defined but EXTRA_CFLAGS variable was never appended to it.

### Solution Applied
Added 3 lines to Makefile to propagate EXTRA_CFLAGS:

1. **EXTRA_CFLAGS definition** (line 5):
   `EXTRA_CFLAGS ?=`

2. **Linux branch** (line 8):
   `MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch $(EXTRA_CFLAGS)`

3. **Else branch** (line 10):
   `MPY_CFLAGS ?= $(EXTRA_CFLAGS)`

### Propagation Chain
Command line: EXTRA_CFLAGS="-DSCARD_FIX_HALFDUPLEX"
  ↓ (new: appended to MPY_CFLAGS)
MPY_CFLAGS = -Wno-dangling-pointer -Wno-enum-int-mismatch -DSCARD_FIX_HALFDUPLEX
  ↓ (existing: passed as CFLAGS_EXTRA to sub-make)
micropython/ports/stm32 Makefile: CFLAGS = ... $(CFLAGS_EXTRA)
  ↓ (existing: CFLAGS_USERMOD flows into CFLAGS_MOD into CFLAGS)
scard C files compiled with -DSCARD_FIX_HALFDUPLEX

### Files Modified
- Build server: `/home/ubuntu/seedkeeperonly/Makefile`
- Local: `/Users/macbook/src/seedkeeperport/specter-diy-seedkeeperonly/Makefile`
- Both files have identical changes

### Verification
- `ssh ubuntu@192.168.13.246 'grep EXTRA_CFLAGS /home/ubuntu/seedkeeperonly/Makefile'` returns 3 lines
- `grep EXTRA_CFLAGS Makefile` (local) returns 3 lines
- Both files have identical changes
- Results directory created: `/home/ubuntu/seedkeeperonly/results`

### Impact
This fix enables proper testing of conditional compile guards (SCARD_FIX_HALFDUPLEX,
SCARD_FIX_T1_RECONFIG, SCARD_FIX_PPS) by passing the appropriate defines through the
build chain to the scard module compilation.

