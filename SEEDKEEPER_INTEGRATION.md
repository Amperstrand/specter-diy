# SeedKeeper Integration — Specter-DIY Fork

This fork integrates [SeedKeeper](https://github.com/Toporin/Seedkeeper-Applet)
and [Satochip](https://github.com/Toporin/SatochipApplet) JavaCard smartcard
wallets into the Specter-DIY airgapped hardware bitcoin wallet firmware.

## Why This Fork Exists

Specter-DIY ships with an SD-card-based keystore. We want to use secure
JavaCard smartcards (SeedKeeper/Satochip) as the keystore instead, so that
private keys never touch the device's filesystem. This requires:

1. Smartcard T=1 protocol support in the STM32's USART smartcard interface
2. A secure channel (SCP02/SCP03) to authenticate with the card
3. A keystore implementation that talks to the card instead of SD card
4. Applet lifecycle management (install, delete, provision) via GlobalPlatform

## Branch Map

All work is preserved as separate branches on the Amperstrand fork:

| Branch | Purpose | Status |
|--------|---------|--------|
| `master` | HIL testing framework (Wave 1-4) + JavaCard keystore refactoring | **Working** — sim tests pass |
| `applet-manager` | Full GP provisioning pipeline (M1-M6) | **Needs hardware test** |
| `gp-repl-tests` | GP provisioning refinements + session leak fixes | **Needs hardware test** |
| `secure-channel-parity` | MAC verify, ECDSA authenticity, SeedKeeper lifecycle | **Needs hardware test** |
| `seedkeeper-sole` | SeedKeeper as sole keystore with working card detection | **Hardware tested** |
| `satochip` | Initial Satochip keystore support | Baseline (shared) |
| `satochip-dev` | HIL integration docs and validation guide | Baseline (shared) |
| `seedkeeper` | SeedKeeper lifecycle tests and card management | Baseline (shared) |
| `seedkeeper-support` | Touchscreen PIN prompt and wallet fingerprint display | Baseline (shared) |

## What Works (Confirmed on Hardware)

### T=1 Protocol Reconfiguration — THE BREAKTHROUGH

**Tested**: 2026-03-11 on STM32F469-Discovery + Specter Shield + SeedKeeper card

The SeedKeeper smartcard requires T=1 protocol with specific USART
reconfiguration. Without this fix, the STM32's smartcard interface cannot
communicbrate with the SeedKeeper at all — every connection attempt fails
with "protocol not supported".

**The fix** (`SCARD_FIX_T1_RECONFIG`):
- Reconfigure stop bits from 1.5 to 1
- Reconfigure guard time from 16 to 1
- Applied in `scard_io.c` after T=1 protocol selection

**Test matrix results** (8 variants, see `results/test_matrix_results.md`):

| Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result |
|---------|-----------|-------------|-----|--------|
| V0 | OFF | OFF | OFF | FAIL — protocol not supported |
| V1 | OFF | OFF | ON | FAIL — protocol not supported |
| V2 | OFF | ON | OFF | **PASS** — T=1 connected |
| V3 | ON | OFF | OFF | FAIL — protocol not supported |
| V4 | OFF | ON | ON | **PASS** — T=1 connected |
| V5 | ON | OFF | ON | FAIL — protocol not supported |
| V6 | ON | ON | OFF | **PASS** — T=1 connected |
| V7 | ON | ON | ON | **PASS** — Secure channel established |

**Conclusion**: T1_RECONFIG is the necessary and sufficient fix. All variants
with it enabled pass. All without it fail, regardless of other settings.

### SeedKeeper as Sole Keystore

**Branch**: `seedkeeper-sole`

Device boots directly to SeedKeeper PIN prompt instead of falling back to
internal SD-card storage. Verified working:
- Card detection (ATR: `3B FA 18...`)
- Boot trace logging for diagnostics
- USB REPL routing fix for VCP+MSC mode
- MemoryCard and SDKeyStore removed from keystore list

### HIL Testing Framework

**Branch**: `master`

Hardware-in-the-loop testing framework, Waves 1-4 complete:
- UART3 VCP listener at 115200 baud
- Host-side serial communication via pyserial
- CommandMapper: SimController to TestMode protocol translation
- HardwareController: main integration piece
- `--hardware` flag for automated test execution
- Makefile `test-hil` and `test-hil-flash` targets

## What Needs Testing (Implemented, Not Yet Hardware-Validated)

### GP Provisioning Pipeline (M1-M6)

**Branches**: `applet-manager`, `gp-repl-tests`

Full GlobalPlatform applet lifecycle management — can install, delete, and
manage JavaCard applets directly from the device firmware:

- **M1**: AES-CMAC and SCP03 secure channel establishment
- **M2**: GET STATUS — query card's applet registry
- **M3**: DELETE — remove applet instances and packages
- **M4**: INSTALL and LOAD — install MemoryCard applet (63KB CAP bundled in firmware)
- **M5**: Non-destructive card probe — detect card kind without side effects
- **M6**: Boot-time provisioning prompt, developer UI, HIL test commands

**What needs testing**: Run the GP provisioning flow on a real blank JavaCard.
HIL commands (TEST_GP_INIT, TEST_GP_STATUS, TEST_GP_DELETE, TEST_GP_INSTALL,
TEST_GP_VERIFY, TEST_GP_PROBE) are implemented and ready.

### Secure Channel MAC Verification + ECDSA Authenticity

**Branch**: `secure-channel-parity`

Brings the secure channel implementation to feature parity with the
Toporin/pysatochip reference implementation:

- **MAC verification**: HMAC-SHA1 integrity check before decryption (previously
  decrypted without verification — security vulnerability)
- **Pubkey Y-parity recovery**: Tries both 0x02 and 0x03 prefixes when parsing
  the card's x-coordinate-only pubkey (previously hardcoded 0x02 — would
  silently produce wrong ECDH shared secret for odd-Y keys)
- **ECDSA card authenticity**: Challenge-response via INS 0x9A. Card signs
  SHA-256("Challenge:" || both_challenges) with its signing key.
- **DER-to-compact signature conversion** for MicroPython

**What needs testing**: Verify MAC verification and ECDSA authenticity work
with a real SeedKeeper card. The V7 test confirmed secure channel
establishment, but MAC verify and ECDSA were added after that test.

### SeedKeeper Lifecycle Operations

**Branch**: `secure-channel-parity`

- `import_secret` (INS 0xA1): Multi-step INIT/PROCESS/FINALIZE protocol for
  BIP39 entropy import
- `delete_secret`, `card_reset` HIL commands
- PIN error handling fix: ISO 7816 0x63cX format (was 0x9c02)
- Blank SeedKeeper handling in firmware unlock flow

**What needs testing**: import_secret with actual BIP39 entropy on a real
SeedKeeper card.

## What Is Good (Infrastructure)

### JavaCard Keystore Refactoring

**Branch**: `master`

- `JavaCardKeyStore` abstract base class for all card types
- Positive card type detection: Satochip vs SeedKeeper vs MemoryCard vs
  GP-installable vs GP-supported vs unknown
- `change_pin` implemented across all JavaCard keystores
- Enhanced card info screens for Satochip and SeedKeeper
- Secret types with descriptor support and authentikey display
- Shared fingerprint utility

### Test Automation

- Conditional compile flags: `SCARD_FIX_HALFDUPLEX`, `SCARD_FIX_T1_RECONFIG`,
  `SCARD_FIX_PPS`
- `tools/run_variant_test.sh` — test a single compile variant
- `tools/run_all_variants.sh` — run all 8 variants with power cycle reminders
- `tests/unified_card_test.py` — unified card test suite
- Test matrix documentation with pass/fail criteria

## Architecture

```
                    Specter-DIY Firmware (STM32F469-Discovery)
                    ┌─────────────────────────────────────┐
                    │            specter.py                │
                    │   (boot, UI, wallet management)      │
                    │                                      │
                    │    ┌─────────────────────────┐       │
                    │    │   JavaCardKeyStore      │       │
                    │    │   (abstract base)       │       │
                    │    └──┬──────┬──────┬───────┘       │
                    │       │      │      │               │
                    │  ┌────▼┐ ┌──▼──┐ ┌─▼────────────┐  │
                    │  │ Sato│ │Seed │ │ GP Applet    │  │
                    │  │ chip│ │Keep │ │ Manager      │  │
                    │  │     │ │ er  │ │ (install/    │  │
                    │  │     │ │     │ │  delete)     │  │
                    │  └──┬──┘ └──┬──┘ └──────┬───────┘  │
                    │     │       │           │          │
                    │  ┌──▼───────▼───────────▼───────┐  │
                    │  │    Secure Channel (SCP02)     │  │
                    │  │  MAC verify + ECDSA auth      │  │
                    │  └──────────────┬───────────────┘  │
                    │                 │                  │
                    │  ┌──────────────▼───────────────┐  │
                    │  │    Smartcard I/O (T=1)        │  │
                    │  │  USART reconfig: 1.5→1 stop   │  │
                    │  │  Guard time: 16→1             │  │
                    │  └──────────────┬───────────────┘  │
                    └─────────────────┼──────────────────┘
                                      │ ISO 7816
                            ┌─────────▼─────────┐
                            │   JavaCard        │
                            │  (SeedKeeper /    │
                            │   Satochip /      │
                            │   MemoryCard)     │
                            └───────────────────┘
```

## How to Test

### Simulator (no hardware)

```bash
# On master branch
make test
```

### Hardware-in-the-loop

```bash
# Requires STM32F469-Discovery + Specter Shield + SeedKeeper card
make test-hil-flash  # Flash firmware with HIL support
make test-hil        # Run HIL tests via UART3
```

### SeedKeeper T=1 Protocol Test Matrix

```bash
# On seedkeeper-sole branch
# Build all 8 variants
./tools/run_all_variants.sh

# Power cycle between variants!
```

### GP Provisioning Test

```bash
# On applet-manager branch
# Flash firmware, then use HIL commands:
# TEST_GP_PROBE — detect card kind
# TEST_GP_INIT — establish SCP03 channel
# TEST_GP_STATUS — query applet registry
# TEST_GP_INSTALL — install MemoryCard CAP
# TEST_GP_VERIFY — verify installation
# TEST_GP_DELETE — delete applet
```

## Hardware Requirements

- STM32F469I-Discovery board
- Specter Shield (with smartcard slot)
- SeedKeeper card (Toporin) or Satochip card or blank JavaCard
- ST-LINK USB cable (flashing + debug)
- User USB cable (VCP serial for HIL)
- Docker with specter24d build environment

## Related Repos

- [cryptoadvance/specter-diy](https://github.com/cryptoadvance/specter-diy) — upstream
- [Toporin/Seedkeeper-Applet](https://github.com/Toporin/Seedkeeper-Applet) — card applet
- [Toporin/pysatochip](https://github.com/Toporin/pysatochip) — reference implementation
- [Amperstrand/f469-disco](https://github.com/Amperstrand/f469-disco) — STM32F469 board support (fork with T=1 USART reconfig)
