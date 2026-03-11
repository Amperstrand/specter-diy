# JavaCard Keystore Comparative Analysis

**Document Version:** 1.0  
**Date:** March 11, 2026  
**Author:** Refactoring Analysis

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Keystore Comparison Matrix](#keystore-comparison-matrix)
3. [MemoryCard (Original)](#1-memorycard-original)
4. [SeedKeeper](#2-seedkeeper)
5. [Satochip](#3-satochip)
6. [Secure Channel Comparison](#secure-channel-comparison)
7. [Applet Layer Comparison](#applet-layer-comparison)
8. [Code Duplication Analysis](#code-duplication-analysis)
9. [Implementation Gaps](#implementation-gaps)
10. [Refactoring Recommendations](#refactoring-recommendations)

---

## Executive Summary

This document provides a comprehensive analysis of the three JavaCard-based keystore implementations in specter-diy:

| Keystore | Origin | Status | Primary Use Case |
|----------|--------|--------|------------------|
| **MemoryCard** | Original specter-diy | Stable | PIN-protected smartcard storage |
| **SeedKeeper** | Satochip project | New | BIP39 mnemonic import from SeedKeeper card |
| **Satochip** | Satochip project | New | Hardware wallet with on-card signing |

**Key Findings:**
- ~200 lines of duplicated code between SeedKeeper and Satochip
- Two different secure channel implementations with incompatible protocols
- MemoryCard uses different applet architecture than SeedKeeper/Satochip
- Card detection lacks positive identification (potential security issue)

---

## Keystore Comparison Matrix

### Capabilities

| Feature | MemoryCard | SeedKeeper | Satochip |
|---------|------------|------------|----------|
| **Mnemonic Storage** | ✅ Store on card | ✅ Import from card | ❌ Stays on card |
| **Mnemonic Export** | ✅ Can export | ✅ Can export | ❌ Cannot export |
| **Transaction Signing** | ❌ Not supported | ❌ Not supported | ✅ Full PSBT signing |
| **XPUB Derivation** | ❌ No | ❌ No | ✅ From card |
| **Multi-secret Support** | ❌ Single secret | ✅ Multiple secrets | ❌ Single wallet |
| **Anti-phishing Words** | ✅ Yes (HMAC-based) | ❌ No | ❌ No |
| **Network Awareness** | ❌ No | ❌ No | ✅ Yes |
| **Taproot Support** | ❓ Unknown | ❓ Unknown | ❌ No |

### Implementation Details

| Aspect | MemoryCard | SeedKeeper | Satochip |
|--------|------------|------------|----------|
| **File** | `keystore/memorycard.py` | `keystore/seedkeeper.py` | `keystore/satochip.py` |
| **Lines of Code** | 470 | 428 | 845 |
| **Applet File** | `applets/memorycard.py` | `applets/seedkeeper_applet.py` | `applets/satochip_applet.py` |
| **Applet Lines** | 22 | 434 | 296 |
| **Secure Channel** | `SecureChannel` | `SeedKeeperSecureChannel` | `SeedKeeperSecureChannel` |
| **AID (hex)** | `B0 0B 51 11 CB 01` | `53 65 65 64 4B 65 65 70 65 72` | `53 61 74 6F 43 68 69 70` |
| **AID (ASCII)** | N/A | "SeedKeeper" | "SatoChip" |

### Properties & State

| Property | MemoryCard | SeedKeeper | Satochip |
|----------|------------|------------|----------|
| `is_pin_set` | `applet.is_pin_set` | `True` (always) | `True` (always) |
| `is_locked` | `applet.is_locked` | `not self._pin_unlocked` | `not self._pin_unlocked` |
| `is_ready` | `connected and not is_locked and fingerprint` | `connected and _pin_unlocked and fingerprint` | `connected and _pin_unlocked and fingerprint and idkey` |
| `can_export_seed` | `True` | ✅ Missing (should be True) | `False` |
| `pin_attempts_left` | `applet.pin_attempts_left` | From card status | From card status |
| `hexid` | `tagged_hash(card_pubkey)[:4]` | N/A | `"satochip"` (TODO) |

---

## 1. MemoryCard (Original)

### Overview

The original JavaCard implementation from specter-diy. Uses a custom MemoryCard Java applet that stores encrypted secrets on the card.

### Source Code Locations

| Component | Path | Description |
|-----------|------|-------------|
| Keystore | `src/keystore/memorycard.py` | 470 lines |
| Applet | `src/keystore/javacard/applets/memorycard.py` | 22 lines |
| Secure Channel | `src/keystore/javacard/applets/securechannel.py` | 201 lines |
| Base Applet | `src/keystore/javacard/applets/secureapplet.py` | 119 lines |

### Applet Details

```python
# From memorycard.py
class MemoryCardApplet(SecureApplet):
    AID = b"\xB0\x0B\x51\x11\xCB\x01"
    NAME = "MemoryCard"
    
    # Instructions
    GET_SECRET = b"\x05\x00"
    SET_SECRET = b"\x05\x01"
```

### Key Features

1. **Secret Storage**: Encrypts and stores mnemonic on the card
2. **Anti-phishing Words**: Uses HMAC-based word generation for PIN entry verification
3. **Device Binding**: Optional encryption that ties card to specific device
4. **PIN Management**: Set, change, unlock with attempt tracking

### Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Card detection | ✅ Implemented | Via `is_available()` |
| PIN verification | ✅ Implemented | With attempt tracking |
| Secret storage | ✅ Implemented | Encrypted or plaintext |
| Secret loading | ✅ Implemented | With device binding check |
| Anti-phishing | ✅ Implemented | HMAC-based word generation |
| Card info display | ✅ Implemented | Shows fingerprint, encryption status |
| Multiple cards | ✅ Implemented | Can switch between cards |

### Potential Gaps

| Gap | Description | Priority |
|-----|-------------|----------|
| No signing | Cannot sign transactions | By design |
| No xpub | Cannot derive xpubs | By design |
| Legacy AID | Non-standard AID format | Low |

---

## 2. SeedKeeper

### Overview

SeedKeeper is a dedicated BIP39 secret storage card from the Satochip project. It can store multiple secrets (mnemonics, passwords, etc.) and export them to the device.

### Source Code Locations

| Component | Path | Description |
|-----------|------|-------------|
| Keystore | `src/keystore/seedkeeper.py` | 428 lines |
| Applet | `src/keystore/javacard/applets/seedkeeper_applet.py` | 434 lines |
| Secure Channel | `src/keystore/javacard/applets/seedkeeper_securechannel.py` | ~200 lines |

### External Resources

| Resource | URL |
|----------|-----|
| Official Site | https://satochip.io/seedkeeper/ |
| GitHub (Java) | https://github.com/Toporin/SeedKeeper-java |
| GitHub (Python) | https://github.com/Toporin/SeedKeeper-python |
| Documentation | https://satochip.io/seedkeeper-documentation/ |

### Applet Details

```python
# From seedkeeper_applet.py
class SeedKeeperApplet(Applet):  # Note: NOT SecureApplet!
    AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])  # "SeedKeeper"
    NAME = "SeedKeeper"
    CLA = 0xB0
    
    # Instructions
    INS_VERIFY_PIN = 0x42
    INS_CARD_LABEL = 0x3D
    INS_EXPORT_SECRET = 0xA2
    INS_LIST_SECRETS = 0xA6
    INS_GET_STATUS = 0xA7
    
    # Secret types
    SECRET_TYPE_MASTERSEED = 0x10  # Masterseed with BIP39 subtype
    SECRET_TYPE_BIP39 = 0x30       # Raw BIP39 entropy
    SECRET_TYPE_BIP39_V2 = 0x31    # BIP39 v2 format
```

### Secret Types Supported

| Type | Code | Description | Parse Format |
|------|------|-------------|--------------|
| MASTERSEED | 0x10 | Master seed with BIP39 subtype | `masterseed_size(1) | masterseed(N) | wordlist(1) | entropy_size(1) | entropy(M) | ...` |
| BIP39 | 0x30 | Raw BIP39 entropy | `entropy_len(2) || entropy || [passphrase...]` |
| BIP39_V2 | 0x31 | BIP39 version 2 | Same as BIP39 |
| Password | 0x?? | Generic password storage | N/A |
| Other | Various | Other secret types | N/A |

### Key Features

1. **Multi-secret Storage**: Card can hold multiple secrets of different types
2. **BIP39 Export**: Can export mnemonic entropy to device
3. **Card Labeling**: Supports card-level and secret-level labels
4. **Secret Selection**: User can choose which secret to load
5. **Fingerprint Display**: Shows secret fingerprint for verification

### Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Card detection | ✅ Implemented | Via `is_available()` with SELECT |
| PIN verification | ✅ Implemented | With ISO exception handling |
| Secure channel | ✅ Implemented | ECDH + AES-CBC + HMAC-SHA1 |
| Secret listing | ✅ Implemented | Via `list_secret_headers()` |
| BIP39 export | ✅ Implemented | MASTERSEED and BIP39 types |
| Secret selection | ✅ Implemented | Menu for multiple secrets |
| Card label | ✅ Implemented | Read/set card label |
| Auto-load first secret | ✅ Implemented | After PIN verification |

### Potential Gaps

| Gap | Description | Priority |
|-----|-------------|----------|
| No signing | Cannot sign transactions (by design) | N/A |
| No xpub | Cannot derive xpubs (by design) | N/A |
| No passphrase | BIP39 passphrase not extracted | Medium |
| Dead code | Duplicate `load_mnemonic()` at EOF | Low |
| Missing property | `can_export_seed` not defined | Low |

### Known Issues

1. **Dead Code (lines 361-367)**: Unreachable code after `return True`
   ```python
   # This code is never reached
   """Load mnemonic from SeedKeeper card."""
   await self.check_card(check_pin=True)
   ...
   ```

2. **MASTERSEED Parsing**: Fixed to use dynamic offsets (bytes 67-98, not 0-31)

---

## 3. Satochip

### Overview

Satochip is a full hardware wallet implementation on a JavaCard. Unlike SeedKeeper, the mnemonic never leaves the card - all signing operations happen on-card.

### Source Code Locations

| Component | Path | Description |
|-----------|------|-------------|
| Keystore | `src/keystore/satochip.py` | 845 lines |
| Applet | `src/keystore/javacard/applets/satochip_applet.py` | 296 lines |
| Secure Channel | (uses SeedKeeperSecureChannel) | Shared with SeedKeeper |

### External Resources

| Resource | URL |
|----------|-----|
| Official Site | https://satochip.io/ |
| GitHub (Java) | https://github.com/Toporin/Satochip-java |
| GitHub (Python) | https://github.com/Toporin/Satochip-python |
| Documentation | https://satochip.io/documentation/ |
| BIP32 Spec | BIP-32, BIP-143 |

### Applet Details

```python
# From satochip_applet.py
class SatochipApplet(Applet):  # Note: NOT SecureApplet!
    AID = bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70])  # "SatoChip"
    NAME = "Satochip"
    CLA = 0xB0
    
    # Instructions
    INS_VERIFY_PIN = 0x42
    INS_GET_STATUS = 0x3C
    INS_BIP32_GET_AUTHENTIKEY = 0x73
    INS_BIP32_GET_EXTENDED_KEY = 0x6D
    INS_SIGN_TRANSACTION_HASH = 0x7A
    INS_SIGN_MESSAGE = 0x6E
```

### Key Features

1. **On-card Signing**: Private key never leaves the card
2. **BIP32 Support**: Full hierarchical deterministic wallet support
3. **Authentikey**: Card's public key for fingerprint derivation
4. **PSBT Signing**: Complete PSBT signing workflow
5. **Multiple Address Types**: P2PKH, P2SH-P2WPKH, P2WPKH support
6. **Network Awareness**: Mainnet/testnet/signet/regtest

### Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Card detection | ✅ Implemented | Via `is_available()` with SELECT |
| PIN verification | ✅ Implemented | With ISO exception handling |
| Secure channel | ✅ Implemented | Shared with SeedKeeper |
| Authentikey | ✅ Implemented | For fingerprint/idkey derivation |
| XPUB derivation | ✅ Implemented | Via `get_xpub()` with xtype inference |
| Sign hash | ✅ Implemented | `sign_hash()` for 32-byte hashes |
| Sign PSBT | ✅ Implemented | Full `sign_psbt()` implementation |
| Sign input | ✅ Implemented | `sign_input()` for PSBTView |
| BIP-143 sighash | ✅ Implemented | Segwit sighash computation |
| Legacy sighash | ✅ Implemented | Non-segwit sighash computation |
| Address generation | ✅ Implemented | Native segwit, nested, legacy |
| Key ownership | ✅ Implemented | `owns()` method |
| Network awareness | ✅ Implemented | `set_network()` method |
| Test commands | ✅ Implemented | 15+ TEST_* commands |

### Potential Gaps

| Gap | Description | Priority |
|-----|-------------|----------|
| Taproot | No taproot support (no P2TR) | Medium |
| Recoverable signatures | Not supported | Low (message signing) |
| Multisig | Not explicitly tested | Medium |
| 2FA | 2FA not implemented | Low |
| hexid | Returns "satochip" instead of derived ID | Low |

### Signing Workflow

```
User initiates send
        │
        ▼
PSBT created by wallet app
        │
        ▼
Satochip.sign_psbt(psbt)
        │
        ├── For each input owned by card:
        │       │
        │       ▼
        │   _get_sighash() - compute 32-byte hash
        │       │
        │       ├── witness_utxo? ──► BIP-143 segwit sighash
        │       └── non_witness_utxo? ──► Legacy sighash
        │               │
        │               ▼
        │   sign_hash(derivation, msghash)
        │               │
        │               ▼
        │   Card signs via INS_SIGN_TRANSACTION_HASH
        │               │
        │               ▼
        │   DER signature returned
        │               │
        │               ▼
        │   Add to psbt.partial_sigs
        │
        ▼
Return signed PSBT
```

---

## Secure Channel Comparison

### Overview

Two completely different secure channel implementations exist:

| Aspect | SecureChannel | SeedKeeperSecureChannel |
|--------|---------------|------------------------|
| **Used by** | MemoryCard | SeedKeeper, Satochip |
| **File** | `securechannel.py` | `seedkeeper_securechannel.py` |
| **Lines** | 201 | ~200 |
| **Protocol** | Original specter-diy | Satochip project standard |

### SecureChannel (Original)

**Protocol Flow:**
```
1. GET_PUBKEY (INS 0xB2) → Card returns static public key
2. OPEN_SE or OPEN_EE (INS 0xB4/B5) → ECDH key exchange
   - SE mode: Ephemeral-Static (our ephemeral, card static)
   - EE mode: Ephemeral-Ephemeral (both ephemeral)
3. Card returns: nonce + HMAC + signature
4. Derive keys: host_aes, card_aes, host_mac, card_mac
5. All subsequent messages via SECURE_MSG (INS 0xB6)
```

**Key Derivation:**
```python
host_aes_key = SHA256("host_aes" + shared_secret)
card_aes_key = SHA256("card_aes" + shared_secret)
host_mac_key = SHA256("host_mac" + shared_secret)
card_mac_key = SHA256("card_mac" + shared_secret)
```

**Features:**
- Two modes: ephemeral-static (SE) and ephemeral-ephemeral (EE)
- Full signature verification on card responses
- IV counter with overflow handling (re-establish at 2^16)
- Separate encryption keys for host→card and card→host

### SeedKeeperSecureChannel (Satochip Project)

**Protocol Flow:**
```
1. Generate ephemeral keypair
2. INIT_SC (INS 0x81) → Send our uncompressed pubkey (65 bytes)
3. Card returns: coordx_size(2) + coordx(32) + ...
4. Compute ECDH shared secret (X-coordinate only)
5. Derive keys using HMAC-SHA1
6. All subsequent messages via SECURE_REQUEST (INS 0x82)
```

**Key Derivation:**
```python
aes_key = HMAC-SHA1(shared_secret, "sc_key")[:16]
mac_key = HMAC-SHA1(shared_secret, "sc_mac")
```

**Features:**
- Simpler protocol (no EE/SE modes)
- HMAC-SHA1 for key derivation (vs SHA256)
- 16-byte AES key (vs 32-byte)
- No signature verification (MVP simplification noted in code)
- IV counter starting at 1

### Key Differences

| Difference | SecureChannel | SeedKeeperSecureChannel |
|------------|---------------|------------------------|
| Key derivation | SHA256 | HMAC-SHA1 |
| AES key size | 32 bytes | 16 bytes |
| Ephemeral modes | SE and EE | Single mode |
| Signature verification | Yes | No (MVP) |
| MAC algorithm | HMAC-SHA256 | HMAC-SHA1 |
| Initial IV | 0 | 1 |
| APDU for init | 0xB4/0xB5 | 0x81 |
| APDU for msg | 0xB6 | 0x82 |

### Should They Be Unified?

**Recommendation: NO - Keep Separate**

**Reasons:**
1. **Different Protocols**: The wire protocols are incompatible
2. **Different Cards**: MemoryCard applet uses original protocol; SeedKeeper/Satochip use Satochip protocol
3. **Security Models**: Original has signature verification; Satochip chose simpler MVP model
4. **Maintenance Risk**: Changes to one could break the other

**What CAN be shared:**
- Encryption utilities (AES-CBC, padding)
- MAC computation helpers
- IV counter management pattern

---

## Applet Layer Comparison

### Class Hierarchy

```
Applet (applet.py)
├── SecureApplet (secureapplet.py)
│   └── MemoryCardApplet (memorycard.py)
├── SeedKeeperApplet (seedkeeper_applet.py)
└── SatochipApplet (satochip_applet.py)
```

### Duplicated Code: secure_request()

Both `SeedKeeperApplet` and `SatochipApplet` have identical `secure_request()` implementation:

**SeedKeeperApplet (lines 44-72):**
```python
def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
    if not self.sc.is_initialized:
        raise AppletException("Secure channel not initialized")
    
    encrypted_apdu = self.sc.encrypt_apdu(inner_apdu)
    data = self.conn.transmit(encrypted_apdu)
    resp_data, sw1, sw2 = data[0], data[1], data[2]
    sw = bytes([sw1, sw2])
    
    if sw == b"\x9c\x30" and retry:
        # Re-establish and retry
        ...
    
    if sw != b"\x90\x00":
        raise ISOException(hexlify(sw).decode())
    if len(resp_data) > 0:
        return self.sc.decrypt_response(resp_data)
    return b''
```

**SatochipApplet (lines 41-69):**
```python
def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
    # IDENTICAL IMPLEMENTATION
    ...
```

**Lines duplicated: ~28 lines**

### Recommended: Create SecureAppletBase

```python
# Proposed: secure_applet_base.py
class SecureAppletBase(Applet):
    """Base class for applets using SeedKeeperSecureChannel."""
    
    def __init__(self, connection, aid):
        super().__init__(connection, aid)
        self.sc = SeedKeeperSecureChannel()
    
    def init_secure_channel(self):
        self.sc.initiate(self.conn)
    
    def secure_request(self, inner_apdu: bytes, retry: bool = True) -> bytes:
        # Shared implementation
        ...
```

---

## Code Duplication Analysis

### Summary

| Location | File 1 | File 2 | Lines | Type |
|----------|--------|--------|-------|------|
| Keystore `is_available()` | seedkeeper.py | satochip.py | ~20 | Identical |
| Keystore `is_pin_set` | seedkeeper.py | satochip.py | 3 | Identical |
| Keystore `is_locked` | seedkeeper.py | satochip.py | 3 | Identical |
| Keystore `_unlock()` | seedkeeper.py | satochip.py | ~30 | 95% |
| Keystore `unlock()` | seedkeeper.py | satochip.py | ~40 | 90% |
| Keystore `check_card()` | seedkeeper.py | satochip.py | ~25 | 95% |
| Keystore `wait_for_card()` | seedkeeper.py | satochip.py | 6 | Identical |
| Keystore `get_pin()` | seedkeeper.py | satochip.py | 5 | Identical |
| Applet `secure_request()` | seedkeeper_applet.py | satochip_applet.py | ~28 | Identical |
| Applet `init_secure_channel()` | seedkeeper_applet.py | satochip_applet.py | ~5 | Identical |
| Utility pubkey compression | satochip.py | test_mode.py | ~15 | Similar |
| Utility ISO exception | seedkeeper.py, satochip.py | test_mode.py | ~15 | Similar |
| Utility path conversion | satochip.py | satochip_applet.py | ~15 | Similar |

**Total Estimated Duplication: ~220 lines**

---

## Implementation Gaps

### SeedKeeper

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| `can_export_seed` | Property not defined (defaults to True from RAMKeyStore) | Add explicit `can_export_seed = True` |
| Dead code | Duplicate `load_mnemonic()` at EOF (lines 361-367) | Remove |
| Passphrase | BIP39 passphrase not extracted from secret | Add if needed |
| No signing | Cannot sign (by design) | N/A |

### Satochip

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| `hexid` | Returns "satochip" instead of derived value | Implement proper hexid |
| Taproot | No P2TR support | Add when card supports it |
| Recoverable sigs | Message signing not supported | Document limitation |
| Test mode | Only finds Satochip, not SeedKeeper | Make generic |

### MemoryCard

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| Card detection | No positive AID verification | Add AID check |
| Legacy AID | Non-standard AID format | Document |

### All Keystores

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| Unknown card | No error on unrecognized card | Add detection + error |
| is_available() | Each probes card independently | Centralize detection |

---

## Refactoring Recommendations

### 1. Create JavaCardKeyStore Base Class (HIGH PRIORITY)

**File:** `src/keystore/javacard_base.py`

**Share:**
- `is_pin_set`, `is_locked` properties
- `_unlock()` method with ISO exception handling
- `check_card()` method
- `wait_for_card()` method
- `get_pin()` method

**Estimated savings:** ~130 lines

### 2. Create SecureAppletBase (HIGH PRIORITY)

**File:** `src/keystore/javacard/applets/secure_applet_base.py`

**Share:**
- `init_secure_channel()` method
- `secure_request()` method with retry logic

**Estimated savings:** ~30 lines

### 3. Create Utility Functions (MEDIUM PRIORITY)

**File:** `src/keystore/javacard/util.py` (extend existing)

**Add:**
- `compress_pubkey(pubkey_bytes: bytes) -> bytes`
- `derive_fingerprint(pubkey_bytes: bytes) -> bytes`
- `handle_pin_iso_exception(e: ISOException) -> tuple`
- `path_to_bytes(path: str) -> bytes`

**Estimated savings:** ~50 lines

### 4. Implement Card Detection (HIGH PRIORITY)

**File:** `src/keystore/javacard/card_detector.py`

**Features:**
- Try each known AID in sequence
- Return card type or "unknown"
- Error display for unknown cards
- Integration with specter.py keystore selection

### 5. Do NOT Unify Secure Channels (LOW PRIORITY)

**Reason:** Different protocols, different cards, high risk

---

## Appendix A: AID Reference

| Applet | AID (Hex) | AID (ASCII) | Length |
|--------|-----------|-------------|--------|
| MemoryCard | `B0 0B 51 11 CB 01` | N/A | 6 bytes |
| SeedKeeper | `53 65 65 64 4B 65 65 70 65 72` | "SeedKeeper" | 10 bytes |
| Satochip | `53 61 74 6F 43 68 69 70` | "SatoChip" | 8 bytes |

---

## Appendix B: ISO Exception Codes

| SW | Meaning | Handling |
|----|---------|----------|
| `9000` | Success | Continue |
| `63CX` | Wrong PIN, X attempts left | Raise PinError |
| `6983` | No more PIN attempts | Raise CriticalErrorWipeImmediately |
| `9C0C` | Card bricked | Raise CriticalErrorWipeImmediately |
| `9C12` | No more secrets (SeedKeeper) | End of list |
| `9C30` | Secure channel required | Re-establish SC and retry |

---

## Appendix C: Test Infrastructure

### Existing Tests

| Test File | Type | Target |
|-----------|------|--------|
| `test/tests/test_keystore.py` | Unit | FlashKeyStore |
| `tests/satochip_auto_test.sh` | Integration | Satochip hardware |
| `tests/satochip_signet_e2e.py` | E2E | Satochip + Bitcoin Core |
| `tests/seedkeeper_test.sh` | Integration | SeedKeeper hardware |
| `tests/seedkeeper-test-plan.md` | Documentation | Test cases |

### Test Framework

- **Unit tests:** Python `unittest` via `test/run_tests.py`
- **Integration:** Shell scripts with serial output pattern matching
- **E2E:** Python scripts with Bitcoin Core RPC

### Missing Tests

- Unit tests for JavaCard keystores
- Unit tests for applet layer
- Unit tests for secure channels
- Unit tests for card detection
- Mock-based testing infrastructure

---

## Appendix D: External Dependencies

### Python Libraries

| Library | Usage | Files |
|---------|-------|-------|
| `secp256k1` | EC crypto | securechannel.py, seedkeeper_securechannel.py |
| `ucryptolib.aes` | AES encryption | securechannel.py, seedkeeper_securechannel.py |
| `uscard` | Smartcard interface | util.py |
| `embit` | Bitcoin primitives | satochip.py, seedkeeper_applet.py |
| `hashlib` | SHA256, RIPEMD160 | Multiple |

### Platform Dependencies

| Dependency | Usage |
|------------|-------|
| `pyb.Pin` | GPIO for card reader |
| `rng.get_random_bytes` | Secure random |
| `platform.CriticalErrorWipeImmediately` | Security wipe |

---

*End of Document*
