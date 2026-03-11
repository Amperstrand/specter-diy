# JavaCard Keystore Refactoring Plan

**Date:** March 11, 2026  
**Status:** Phase 1 In Progress  
**Branch:** master (clean state after commit 05a494a)

**Related Documents:**
- [JavaCard Comparative Analysis](./JAVACARD_COMPARATIVE_ANALYSIS.md) - Full analysis of all 3 keystores
- [SeedKeeper Integration Strategy](./SEEDKEEPER_INTEGRATION_STRATEGY.md) - Original integration notes

---

## Executive Summary

This document outlines a systematic refactoring of the JavaCard keystore implementations in specter-diy to:
1. Eliminate ~220 lines of duplicated code
2. Create a unified base class for all JavaCard keystores
3. Implement proper card type detection with positive identification
4. Add comprehensive unit tests before each refactoring step

---

## Current Architecture Analysis

### Keystore Hierarchy (Before Refactoring)

```
KeyStore (core.py)
└── RAMKeyStore (ram.py)
    ├── FlashKeyStore (flash.py)
    │   └── SDKeyStore (sdcard.py)
    ├── MemoryCard (memorycard.py)      ← Original JavaCard
    ├── SeedKeeper (seedkeeper.py)      ← New
    └── Satochip (satochip.py)          ← New
```

### Applet Hierarchy (Before Refactoring)

```
Applet (applet.py)
├── SecureApplet (secureapplet.py)
│   └── MemoryCardApplet (memorycard.py)  ← Uses SecureChannel
├── SeedKeeperApplet (seedkeeper_applet.py)  ← Uses SeedKeeperSecureChannel
└── SatochipApplet (satochip_applet.py)      ← Uses SeedKeeperSecureChannel
```

### Known Applet AIDs

| Applet | AID (hex) | AID (ASCII) | Keystore |
|--------|-----------|-------------|----------|
| MemoryCard | `B0 0B 51 11 CB 01` | N/A | `MemoryCard` |
| SeedKeeper | `53 65 65 64 4B 65 65 70 65 72` | "SeedKeeper" | `SeedKeeper` |
| Satochip | `53 61 74 6F 43 68 69 70` | "SatoChip" | `Satochip` |

---

## Identified Code Duplication

### 1. Keystore Level (seedkeeper.py vs satochip.py)

| Method | Lines | Identical? |
|--------|-------|------------|
| `is_available()` | ~20 | 95% |
| `is_pin_set` | 3 | 100% |
| `is_locked` | 3 | 100% |
| `_unlock(pin)` | ~30 | 95% |
| `unlock()` PIN loop | ~40 | 90% |
| `check_card()` | ~25 | 95% |
| `wait_for_card()` | 6 | 100% |
| `get_pin()` | 5 | 100% |

**Total: ~130 lines duplicated**

### 2. Applet Level (seedkeeper_applet.py vs satochip_applet.py)

| Method | Lines | Identical? |
|--------|-------|------------|
| `init_secure_channel()` | ~5 | 100% |
| `secure_request()` | ~25 | 100% |
| `verify_pin()` | ~10 | 90% |

**Total: ~40 lines duplicated**

### 3. Utility Functions (scattered)

| Function | Locations | Lines |
|----------|-----------|-------|
| Pubkey compression | satochip.py, test_mode.py | ~20 |
| PIN ISO exception handling | seedkeeper.py, satochip.py, test_mode.py | ~15 |
| Path to bytes conversion | satochip.py, satochip_applet.py | ~15 |

**Total: ~50 lines duplicated**

---

## Refactoring Plan

### Phase 1: Foundation (Tests & Utilities)

#### Task 1.1: Create Unit Test Infrastructure
- [ ] Create `test/tests/test_javacard_util.py`
- [ ] Add tests for `compress_pubkey()` function
- [ ] Add tests for `derive_fingerprint()` function
- [ ] Add tests for `handle_pin_iso_exception()` function
- [ ] Add tests for `path_to_bytes()` function
- [ ] Verify tests pass

**Commit:** `test: add unit tests for JavaCard utility functions`

#### Task 1.2: Add Utility Functions
- [ ] Add `compress_pubkey()` to `javacard/util.py`
- [ ] Add `derive_fingerprint()` to `javacard/util.py`
- [ ] Add `handle_pin_iso_exception()` to `javacard/util.py`
- [ ] Add `path_to_bytes()` to `javacard/util.py`
- [ ] Verify tests pass

**Commit:** `refactor: add shared JavaCard utility functions`

---

### Phase 2: Applet Layer Refactoring

#### Task 2.1: Create Unit Tests for SecureAppletBase
- [ ] Create `test/tests/test_secure_applet_base.py`
- [ ] Mock connection and test `secure_request()` logic
- [ ] Test retry on 9c30 error
- [ ] Verify tests pass

**Commit:** `test: add unit tests for SecureAppletBase`

#### Task 2.2: Create SecureAppletBase Class
- [ ] Create `javacard/applets/secure_applet_base.py`
- [ ] Move `secure_request()` from SeedKeeperApplet/SatochipApplet
- [ ] Move `init_secure_channel()` from SeedKeeperApplet/SatochipApplet
- [ ] Update SeedKeeperApplet to inherit from SecureAppletBase
- [ ] Update SatochipApplet to inherit from SecureAppletBase
- [ ] Verify existing hardware tests still pass

**Commit:** `refactor(applet): create SecureAppletBase to eliminate duplication`

---

### Phase 3: Keystore Layer Refactoring

#### Task 3.1: Create Unit Tests for JavaCardKeyStore
- [ ] Create `test/tests/test_javacard_keystore.py`
- [ ] Mock applet and connection
- [ ] Test `is_available()` with various card types
- [ ] Test `_unlock()` with PIN errors
- [ ] Test `check_card()` flow
- [ ] Verify tests pass

**Commit:** `test: add unit tests for JavaCardKeyStore base class`

#### Task 3.2: Create JavaCardKeyStore Base Class
- [ ] Create `keystore/javacard_base.py`
- [ ] Move shared properties: `is_pin_set`, `is_locked`
- [ ] Move shared methods: `is_available()`, `check_card()`, `wait_for_card()`, `get_pin()`
- [ ] Move `_unlock()` with exception handling
- [ ] Create abstract method `get_applet_class()` or similar

**Commit:** `refactor(keystore): create JavaCardKeyStore base class`

#### Task 3.3: Refactor SeedKeeper to Use Base Class
- [ ] Update `SeedKeeper` to inherit from `JavaCardKeyStore`
- [ ] Remove duplicated code
- [ ] Keep SeedKeeper-specific: multi-secret selection, mnemonic loading
- [ ] Verify tests pass

**Commit:** `refactor(seedkeeper): use JavaCardKeyStore base class`

#### Task 3.4: Refactor Satochip to Use Base Class
- [ ] Update `Satochip` to inherit from `JavaCardKeyStore`
- [ ] Remove duplicated code
- [ ] Keep Satochip-specific: signing, xpub derivation, authentikey
- [ ] Verify tests pass

**Commit:** `refactor(satochip): use JavaCardKeyStore base class`

#### Task 3.5: Refactor MemoryCard to Use Base Class (Optional)
- [ ] Evaluate if MemoryCard can benefit from JavaCardKeyStore
- [ ] Note: MemoryCard uses different SecureChannel (SecureApplet vs SeedKeeperSecureChannel)
- [ ] May require additional abstraction

**Commit:** (if applicable) `refactor(memorycard): use JavaCardKeyStore base class`

---

### Phase 4: Card Detection Enhancement

#### Task 4.1: Create Unit Tests for Card Detection
- [ ] Create `test/tests/test_card_detection.py`
- [ ] Test detection of MemoryCard
- [ ] Test detection of SeedKeeper
- [ ] Test detection of Satochip
- [ ] Test unknown card rejection
- [ ] Test no card scenario
- [ ] Verify tests pass

**Commit:** `test: add unit tests for card type detection`

#### Task 4.2: Implement Positive Card Type Detection
- [ ] Create `keystore/javacard/card_detector.py`
- [ ] Implement `detect_card_type()` that tries each AID
- [ ] Return: "memorycard", "seedkeeper", "satochip", "unknown", or None
- [ ] Update `specter.py` to use new detection
- [ ] Show error if unknown card detected
- [ ] Verify tests pass

**Commit:** `feat: implement positive card type detection with unknown card rejection`

#### Task 4.3: Update Keystore is_available() Methods
- [ ] Update MemoryCard.is_available() to use positive detection
- [ ] Update SeedKeeper.is_available() to use positive detection
- [ ] Update Satochip.is_available() to use positive detection
- [ ] Verify tests pass

**Commit:** `refactor: use positive card detection in is_available()`

---

### Phase 5: Test Mode Enhancement

#### Task 5.1: Make Test Mode Generic
- [ ] Update `test_mode.py` to support all JavaCard keystores
- [ ] Rename `find_satochip()` to `find_javacard_keystore()`
- [ ] Add keystore type to TEST_STATUS output
- [ ] Verify tests pass

**Commit:** `refactor(test_mode): make test commands generic for all JavaCard keystores`

---

### Phase 6: Cleanup & Documentation

#### Task 6.1: Remove Dead Code
- [ ] Remove duplicate `load_mnemonic()` in seedkeeper.py (lines 361-367)
- [ ] Add `can_export_seed = True` to SeedKeeper
- [ ] Verify tests pass

**Commit:** `chore: remove dead code and add missing properties`

#### Task 6.2: Update Architecture Documentation
- [ ] Update this document with final architecture
- [ ] Document new class hierarchy
- [ ] Add migration guide if needed

**Commit:** `docs: update JavaCard architecture documentation`

---

## Target Architecture (After Refactoring)

### Keystore Hierarchy

```
KeyStore (core.py)
└── RAMKeyStore (ram.py)
    ├── FlashKeyStore (flash.py)
    │   └── SDKeyStore (sdcard.py)
    └── JavaCardKeyStore (javacard_base.py)  ← NEW
        ├── MemoryCard (memorycard.py)
        ├── SeedKeeper (seedkeeper.py)
        └── Satochip (satochip.py)
```

### Applet Hierarchy

```
Applet (applet.py)
├── SecureApplet (secureapplet.py)         ← Original, uses SecureChannel
│   └── MemoryCardApplet (memorycard.py)
└── SecureAppletBase (secure_applet_base.py)  ← NEW, uses SeedKeeperSecureChannel
    ├── SeedKeeperApplet (seedkeeper_applet.py)
    └── SatochipApplet (satochip_applet.py)
```

### Card Detection Flow

```
specter.py:select_keystore()
    │
    ▼
CardDetector.detect_card_type()
    │
    ├─► Try SELECT MemoryCard AID → success? → return "memorycard"
    ├─► Try SELECT SeedKeeper AID → success? → return "seedkeeper"  
    ├─► Try SELECT Satochip AID → success? → return "satochip"
    ├─► All failed but card present → return "unknown" → ERROR
    └─► No card → return None
    │
    ▼
Instantiate appropriate keystore class
```

---

## Testing Strategy

### Unit Tests (run before and after each change)

```bash
cd /Users/macbook/src/seedkeeperport/specter-diy
python3 test/run_tests.py
```

### Integration Tests (require hardware)

```bash
# SeedKeeper tests
./tests/seedkeeper_test.sh

# Satochip tests  
./tests/satochip_auto_test.sh
```

### Test Coverage Requirements

| Component | Test Type | Requirement |
|-----------|-----------|-------------|
| Utility functions | Unit | 100% coverage |
| SecureAppletBase | Unit (mocked) | All code paths |
| JavaCardKeyStore | Unit (mocked) | All code paths |
| Card detection | Unit (mocked) | All card types + unknown |
| SeedKeeper | Integration | Hardware test |
| Satochip | Integration | Hardware test |
| MemoryCard | Integration | Hardware test |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing functionality | Medium | High | Unit tests before each change |
| Hardware incompatibility | Low | High | Integration tests on real hardware |
| Memory constraints on device | Low | Medium | Profile memory usage |
| Import cycles | Medium | Low | Careful dependency management |

---

## Progress Tracking

| Phase | Task | Status | Commit |
|-------|------|--------|--------|
| 1.1 | Unit test infrastructure | ✅ Complete | b0dc63a |
| 1.2 | Utility functions | ✅ Complete | c5d66a7 |
**Status Legend:** ⬜ Not Started | 🔄 In Progress | ✅ Complete | ❌ Blocked

---

## Estimated Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total lines (keystores) | ~1,750 | ~1,550 | -200 |
| Duplicated code | ~200 lines | ~0 | -200 |
| Test coverage | ~20% | ~80% | +60% |
| Card detection reliability | Unknown card silent | Unknown card error | Improved |

---

## Next Steps

1. Review and approve this plan
2. Start with Task 1.1: Create unit test infrastructure
3. Follow the plan sequentially
4. Commit after each completed task
5. Run full test suite after each phase

---

## Author
Last updated: Phase 1.1 and 1.2 complete
