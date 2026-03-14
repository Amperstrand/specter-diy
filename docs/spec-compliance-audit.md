# Spec Compliance Audit

## BIP-44: Multi-Account Hierarchy
- **Status**: PARTIAL
- **Implementation**:
  - `src/apps/xpubs/xpubs.py:211` (BIP44 derivation template `m/44'/%d'/%d'` for key export)
  - `src/apps/wallets/manager.py:519` (default wallet path uses BIP84, but manager supports BIP44 via descriptors and `showaddr` parsing)
  - `f469-disco/libs/common/embit/bip32.py:292` (path parsing for `m / purpose' / coin_type' / account' / change / index` structure)
  - `src/apps/wallets/wallet.py:153` (branch/index handling for change and address index)
- **Tests**:
  - `test/integration/tests/test_basic.py:22` (`xpub m/44h/1h/0h` request)
  - `test/integration/tests/test_with_rpc.py:304` (legacy `pkh` flow on `44h/1h/0h`)
  - `f469-disco/tests/tests/` has no BIP44-specific tests.
- **Gaps**:
  - No explicit account discovery test coverage per BIP44 algorithm (discover account N+1 only if account N has history).
  - No enforcement test that account creation is blocked when previous account is unused.
  - No dedicated gap-limit warning test for external chain address generation at limit 20.
- **Recommended Test Vectors**:
  - BIP44 example path checks: `m/44'/0'/0'/0/0` and `m/44'/0'/0'/1/0` (external vs change).
  - BIP44 account increment examples: `m/44'/0'/1'/0/0` and `m/44'/1'/1'/1/1` (coin type + account switching).

## BIP-84: Native SegWit
- **Status**: PARTIAL
- **Implementation**:
  - `src/apps/xpubs/xpubs.py:37` (recommended single-sig path `m/84h/%dh/%dh`)
  - `src/apps/wallets/manager.py:519` (default wallet creation at `m/84h/%dh/0h`)
  - `f469-disco/libs/common/embit/bip32.py:270` (`detect_version` maps `84'` to zpub/zprv family)
  - `f469-disco/libs/common/embit/networks.py:13` and `f469-disco/libs/common/embit/networks.py:17` (zprv/zpub version bytes)
- **Tests**:
  - `test/integration/tests/test_with_rpc.py:103` (`test_wpkh` on `84h/1h/0h`)
  - `test/integration/tests/test_with_rpc.py:343` (`test_sighashes` for BIP84 descriptor flow)
  - `test/tests/test_wallets.py:11` (descriptor parsing with `84h/1h/0h` origin)
  - No tests assert official BIP84 zpub/zprv strings or official addresses.
- **Gaps**:
  - No direct regression tests against official BIP84 test vectors.
  - Host `xpub` command returns canonical xpub (`src/apps/xpubs/xpubs.py:277`), while BIP84-specific zpub is only surfaced in UI/export flows.
- **Recommended Test Vectors**:
  - Official BIP84 vector: mnemonic `abandon ... about`, account `m/84'/0'/0'` expected xpub `zpub6rFR7y4Q2Aij...` and xprv `zprvAdG4iTXWBoAR...`.
  - Official BIP84 addresses: `m/84'/0'/0'/0/0 -> bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu` and `m/84'/0'/0'/1/0 -> bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el`.

## BIP-85: Deterministic Entropy
- **Status**: PARTIAL
- **Implementation**:
  - `src/apps/bip85.py:107` (mnemonic derivation UI flow)
  - `src/apps/bip85.py:146` (WIF derivation)
  - `src/apps/bip85.py:150` (XPRV derivation)
  - `src/apps/bip85.py:167` (HEX derivation)
  - `f469-disco/libs/common/embit/bip85.py:16` (core BIP85 entropy derivation and HMAC with `bip-entropy-from-k`)
- **Tests**:
  - No BIP85 tests in `test/tests/` or `f469-disco/tests/tests/`.
- **Gaps**:
  - No test coverage against official BIP85 vectors.
  - Implementation supports a subset of BIP85 applications (BIP39 12/18/24, WIF, XPRV, HEX) and omits newer applications (e.g., DRNG, Base64/Base85, DICE, RSA).
  - BIP39 language options are not exposed beyond English in current app flow.
- **Recommended Test Vectors**:
  - Official BIP85 test case 1: root xprv `xprv9s21...`, path `m/83696968'/0'/0'`, expected derived key `cca20ccb...` and entropy `efecfbcc...`.
  - Official BIP85 BIP39 vector: path `m/83696968'/39'/0'/12'/0'`, expected mnemonic `girl mad pet galaxy egg matter matrix prison refuse sense ordinary nose`.
  - Official BIP85 WIF vector: path `m/83696968'/2'/0'`, expected WIF `Kzyv4uF39d4Jrw2W7UryTHwZr1zQVNk4dAFyqE6BuMrMh1Za7uhp`.

## SLIP-77: Master Blinding Key
- **Status**: PARTIAL
- **Implementation**:
  - `f469-disco/libs/common/embit/liquid/slip77.py:8` (master blinding key derivation from seed)
  - `f469-disco/libs/common/embit/liquid/slip77.py:14` (per-output blinding private key derivation)
  - `src/keystore/ram.py:69` (stores SLIP-77 master key on mnemonic load)
  - `src/apps/blindingkeys/app.py:32` (UI/host export of SLIP-77 key)
- **Tests**:
  - No SLIP-77 tests in `test/tests/` or `f469-disco/tests/tests/`.
- **Gaps**:
  - No dedicated regression tests for SLIP-77 derivation determinism.
  - No negative-path tests for invalid derived scalar edge cases.
  - SLIP-0077 spec text does not publish canonical test vectors; repository currently has no substitute conformance fixture set.
- **Recommended Test Vectors**:
  - Spec-formula vector (master): seed `000102030405060708090a0b0c0d0e0f` -> master blinding key `eb24d23aad8b9d31eaaf724440da6d7f942cf2c704a9ab79de18a943605e1103`.
  - Spec-formula vector (output key #1): scriptPubKey `0014751e76e8199196d454941c45d1b3a323f1433bd6` -> blinding key `7b9f6031dbc5b3043895dfc2df4f395d7c8dc5ee776329481102563f33d9a11b`.
  - Spec-formula vector (output key #2): scriptPubKey `0014d0c4a3ef09e997b6e99e397e518fe3e41a118ca1` -> blinding key `25338c6386391b7fa7187f1645a1e2f28de3e85a96c9fce54eb0cc47efea2843`.

## Summary
- Verified: 0 specs
- Gaps: 4 specs
- Priority fixes:
  - Add conformance tests for official BIP84 and BIP85 vectors.
  - Add BIP44 behavior tests for account discovery and gap-limit warnings.
  - Add SLIP-77 deterministic vector tests (master + per-script derivation) and invalid-scalar edge tests.
