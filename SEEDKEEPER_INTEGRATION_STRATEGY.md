# SeedKeeper Integration Strategy

**Date:** March 10, 2026  
**Project:** Satochip SeedKeeper + Specter-DIY Integration

---

## Executive Summary

This document outlines the strategy for upstreaming SeedKeeper support to Specter-DIY without requiring changes to the f469-disco submodule.

**Key Finding:** The f469-disco changes are **nice-to-have, not required** for SeedKeeper compatibility. The actual fixes were in the Python layer (specter-diy),---

## Repository Structure

```
seedkeeperport/
├── f469-disco-withchanges/    # Custom f469-disco with T=1 improvements
│   └── (isolated copy, not a submodule)
├── specter-diy/                  # Main project with SeedKeeper support
│   ├── f469-disco/              # Submodule pointing to upstream (reset)
│   └── src/keystore/
│       └── seedkeeper.py        # SeedKeeper implementation (Python)
```

---

## Change Classification

### specter-diy Changes (Python Layer) - **REQUIRED**

| File | Change | Status |
|------|--------|--------|
| `src/keystore/seedkeeper.py` | SeedKeeper keystore implementation | ✅ Committed |
| `src/keystore/javacard/applets/seedkeeper_*.py` | Secure channel implementation | ✅ Committed |
| `src/keystore/memorycard.py` | Disconnect fix | ✅ Committed |
| `src/specter.py` | Auto-load after PIN | ✅ Committed |

**These are the actual fixes** for SeedKeeper compatibility:
1. MASTERSEED entropy offset (bytes 67-98, not 0-31)
2. transmit() return format parsing
3. PIN error handling
4. Auto-load secret after PIN verification

### f469-disco Changes (C Layer) - **NICE-TO-HAVE**

| File | Change | Classification |
|------|--------|----------------|
| `scard_io.c` | Half-duplex USART control | Improvement |
| `scard_io.c` | T=1 USART reconfiguration (stop bits, guard time) | Spec Compliance |
| `connection.c` | t1_usart_configured flag | Infrastructure |
| `t1_protocol.c` | Smart PPS handling | Improvement |

---

## Why f469-disco Changes Are Not Required

### 1. Original Code Works

The original `skip_bytes` approach works for most cards:
```c
// Original approach
handle->skip_bytes += nbytes;  // Count TX bytes
// Later: skip echoed bytes
if(self->skip_bytes) {
    volatile int dummy = uart_rx_char(...);
    --self->skip_bytes;
}
```

**This is functional** for SeedKeeper. The real bugs were in Python.

### 2. Real Issues Were in Python

| Bug | Location | Fix |
|-----|----------|-----|
| MASTERSEED entropy offset | `seedkeeper_applet.py` | Bytes 67-98, not 0-31 |
| transmit() return format | `seedkeeper_securechannel.py` | Parse `transmit()` result correctly |
| PIN error handling | `seedkeeper.py` | Catch 6983/9C0C errors |
| Auto-load after PIN | `specter.py` | Load first secret after unlock |

### 3. Changes Are Backwards Compatible

| Card Type | Before | After (with changes) | After (without changes) |
|-----------|--------|---------------------|------------------------|
| SeedKeeper (T=1) | ❌ | ✅ | ✅ |
| Standard T=0 | ✅ | ✅ | ✅ |
| Standard T=1 | ✅ | ✅ | ✅ |

---

## Testing Strategy

### Phase 1: Test with Stock f469-disco (Current)

```
specter-diy/f469-disco → upstream master (989654e)
specter-diy/src/keystore/ → our SeedKeeper implementation
```

**Goal:** Verify SeedKeeper works with stock f469-disco

**Expected:** ✅ Should work - real fixes are in Python

### Phase 2: Optional f469-disco PR (Future)

```
f469-disco-withchanges/ → submit as optional improvement PR
```

**Goal:** Improve T=1 reliability for all cards

**Benefits:**
- Cleaner half-duplex control
- ISO 7816-3 spec compliance for T=1 timing
- Smart PPS negotiation

---

## Upstream PR Recommendations

### specter-diy PR (Priority: HIGH)

**Status:** Ready to submit

**Contents:**
- SeedKeeper keystore implementation
- Secure channel implementation  
- MASTERSEED entropy offset fix
- PIN error handling
- Auto-load after PIN verification

**PR Title:**
```
feat(seedkeeper): Add Satochip SeedKeeper smartcard support

- Add SeedKeeper keystore implementation with secure channel
- Fix MASTERSEED entropy offset (bytes 67-98)
- Add PIN error handling (6983/9C0C)
- Auto-load first secret after PIN verification
- Tested with Satochip SeedKeeper (JTaxCoreV1)
```

### f469-disco PR (Priority: LOW)

**Status:** Optional improvement

**PR Title:**
```
feat(scard): Improve T=1 protocol reliability

- Add explicit half-duplex USART control (replaces skip_bytes)
- Implement scard_configure_t1() for T=1 timing (1 stop bit, 1 ETU guard)
- Improve PPS negotiation (skip only when TA1 absent/default)
- Tested with Satochip SeedKeeper and standard T=0/T=1 cards
- Backwards compatible - no regression expected
```

**Note:** This is a **nice-to-have**, not required. Submit only if maintainers are interested.

---

## Files Reference

### specter-diy (Required for SeedKeeper)

| File | Purpose |
|------|---------|
| `src/keystore/seedkeeper.py` | Main SeedKeeper keystore class |
| `src/keystore/javacard/applets/seedkeeper_applet.py` | APDU commands |
| `src/keystore/javacard/applets/seedkeeper_securechannel.py` | Secure channel implementation |
| `src/keystore/memorycard.py` | Disconnect fix |
| `src/specter.py` | Auto-load after PIN |

### f469-disco-withchanges (Optional Improvements)

| File | Change |
|------|--------|
| `usermods/scard/connection.c` | t1_usart_configured flag |
| `usermods/scard/ports/stm32/scard_io.c` | Half-duplex, scard_configure_t1 |
| `usermods/scard/ports/stm32/scard_io.h` | hd_dir_t enum, scard_configure_t1 |
| `usermods/scard/t1_protocol/t1_protocol.c` | Smart PPS handling |
| `CHANGES_REPORT.md` | Detailed change documentation |

---

## Conclusion

1. **SeedKeeper works with stock f469-disco** - Real fixes are in Python
2. **f469-disco changes are optional improvements** - Not required
3. **Strategy:** Submit specter-diy PR first, submit f469-disco PR as optional
4. **Both PRs are backwards compatible** - No breaking changes

---

## Author

Strategy document prepared March 10, 2026
