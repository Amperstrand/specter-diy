# SeedKeeper Smart Card Compatibility Analysis for f469-disco

## Background

The [SeedKeeper](https://github.com/Toporin/SeedKeeper-Applet) JavaCard applet provides secure seed storage on a smart card. When used with the STM32F469-Discovery board via the [Specter-DIY](https://github.com/cryptoadvance/specter-diy) firmware and the [f469-disco](https://github.com/diybitcoinhardware/f469-disco) MicroPython port, the smart card interface requires specific USART configuration changes to communicate successfully.

This analysis experimentally determines which of the proposed f469-disco USART fixes are strictly necessary for SeedKeeper communication.

---

## The 3 Fixes Under Test

Three separate USART fixes have been proposed to improve smart card compatibility:

### FIX_T1_RECONFIG (PR #40)

**PR:** [diybitcoinhardware/f469-disco #40](https://github.com/diybitcoinhardware/f469-disco/pull/40)

Reconfigures USART stop bits and guard time after ATR reception for T=1 protocol:

```c
// After ATR reception, when T=1 protocol is selected:
// Note: 'usart' is a pointer to the USART instance used for smartcard
// (USART2 on STM32F469-DISCO with PA2/PA4 pins)
usart->CR2 &= ~USART_CR2_STOP;  // 1 stop bit (was 1.5 for T=0)
usart->GTPR = (1U << 8) | psc;   // Guard time = 1 ETU (was 16)
```

**Note:** On STM32F469-DISCO, the smartcard interface uses **USART2** (PA2=IO, PA4=CLK), not USART1. The code uses a generic `usart` pointer to the active USART instance (`handle->sc_handle.Instance`).

Per ISO 7816-3, the ATR is transmitted using T=0 character framing. When switching to T=1 protocol, the USART must be reconfigured to T=1 timing.

### FIX_HALFDUPLEX (PR #41)

**PR:** [diybitcoinhardware/f469-disco #41](https://github.com/diybitcoinhardware/f469-disco/pull/41)

Uses explicit CR1 RE (Receiver Enable) and TE (Transmitter Enable) bit control instead of a `skip_bytes` counter for half-duplex USART switching. The original implementation counted bytes to delay during TX to RX transitions; this fix uses direct hardware register control for more precise timing.

### FIX_PPS (local, not in any PR)

Smart PPS (Protocol Parameter Selection) negotiation. Skips PPS exchange when TA1 is absent or contains default values. The SeedKeeper ATR includes TA1=0x18 (proposing faster communication), but this fix attempts to handle PPS more gracefully.

---

## Test Methodology

### Experimental Design

Three binary fixes create eight possible combinations (2^3 = 8 firmware variants). Each variant was compiled with conditional `#ifdef SCARD_FIX_*` guards:

| Variant | HALFDUPLEX | T1_RECONFIG | PPS |
|---------|-----------|-------------|-----|
| V0 | OFF | OFF | OFF |
| V1 | OFF | OFF | ON |
| V2 | OFF | ON | OFF |
| V3 | ON | OFF | OFF |
| V4 | OFF | ON | ON |
| V5 | ON | OFF | ON |
| V6 | ON | ON | OFF |
| V7 | ON | ON | ON |

### Build Process

All variants built using the Docker toolchain (specter24d image) with consistent settings:
- `USE_DBOOT=0` (no secure bootloader)
- `DEBUG=0` (release build)
- Build date: 2026-03-11

Each firmware was flashed to the target hardware and USB serial output was captured for 30 seconds per variant.

### Hardware

- **Board:** STM32F469-Discovery + Specter Shield
- **Card:** SeedKeeper JavaCard applet

### Verification

Binary uniqueness verified via MD5 hashes. All eight variants produced different hashes, confirming distinct compiled code:

```
V0: 8c71e03e50d5360d1e46e48912c45a43
V1: 14af0474e73ba6bc7e7d72b3bc20ebcd
V2: c0f3a6fb4291b27f41ef6dc6e41ab2ad
V3: 0f27ad4988e89a6cc3cd45e6c5aa6c14
V4: 0b21f43ef5cf94b3dce0ac75c13ef78a
V5: 6f2bf7eeb5ac8eb24a51ea95136c08a6
V6: 6328f4a025fe92b1ad7e9bb45b3ebea3
V7: 541bf71bb3fbd0e15f8d50868f44f6de
```

### Pass/Fail Criteria

- **PASS:** Serial output contains `[BootTrace][SeedKeeper] ATR:` AND `connected using protocol:`
- **FAIL:** Serial output contains `connect failed` or `protocol not supported`

---

## SeedKeeper ATR Analysis

### Captured ATR

```
3B FA 18 00 00 81 31 FE 45 4A 54 61 78 43 6F 72 65 56 31 B2
```

Captured from all passing variants (V2, V4, V6, V7) during test matrix execution.

### Byte-by-Byte Decode

| Byte | Value | Field | Interpretation |
|------|-------|-------|----------------|
| 0 | 0x3B | TS | Direct convention (LSB first) |
| 1 | 0xFA | T0 | TA1-TD1 present, 10 historical bytes |
| 2 | 0x18 | TA1 | Fi=372, Di=12 (proposes 31x faster speed) |
| 3 | 0x00 | TB1 | No Vpp (deprecated) |
| 4 | 0x00 | TC1 | Minimum guard time (N=0) |
| 5 | 0x81 | TD1 | TD2 present, T=1 protocol offered |
| 6 | 0x31 | TD2 | TA3/TB3 present, T=1 confirmed |
| 7 | 0xFE | TA3 | IFSC = 254 bytes max block size |
| 8 | 0x45 | TB3 | BWI=4, CWI=5 (timing parameters) |
| 9-18 | ... | Historical | "JTaxCoreV1" (applet identifier) |
| 19 | 0xB2 | TCK | XOR checksum |

### Key Findings

1. **TA1=0x18:** Card proposes Fi=372, Di=12, which is 31 times faster than default (Fi=372, Di=1). However, test results show the card tolerates default speed without PPS negotiation.

2. **TC1=0x00:** Minimum guard time (no extra guard time). This is protocol-specific: 12 ETU for T=0, 11 ETU for T=1.

3. **TD1=0x81:** Card offers T=1 protocol first. The USART must switch from T=0 timing (used during ATR) to T=1 timing.

4. **Historical bytes:** "JTaxCoreV1" identifies this as the SeedKeeper application.

---

## Results Table

| Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result | Key Output |
|---------|-----------|-------------|-----|--------|------------|
| V0 | OFF | OFF | OFF | FAIL | connect failed, protocol not supported |
| V1 | OFF | OFF | ON | FAIL | connect failed, protocol not supported |
| V2 | OFF | **ON** | OFF | **PASS** | ATR captured, secure channel established |
| V3 | ON | OFF | OFF | FAIL | connect failed, protocol not supported |
| V4 | OFF | **ON** | ON | **PASS** | ATR captured, secure channel established |
| V5 | ON | OFF | ON | FAIL | connect failed, protocol not supported |
| V6 | ON | **ON** | OFF | **PASS** | ATR captured, secure channel established |
| V7 | ON | **ON** | ON | **PASS** | ATR captured, secure channel established |

### Sample Output (PASS - V2)

```
[SeedKeeper] Applet initialized
[BootTrace][SeedKeeper] ATR: 3B FA 18 00 00 81 31 FE 45 4A 54 61 78 43 6F 72 65 56 31 B2
[BootTrace][SeedKeeper] connected using protocol: 2
[SeedKeeper] Establishing secure channel...
[SeedKeeper] Secure channel established
[BootTrace][SeedKeeper] unlock() called
[BootTrace][SeedKeeper] PIN attempts remaining: 5
```

### Sample Output (FAIL - V0)

```
[SeedKeeper] Applet initialized
[BootTrace][SeedKeeper] connect failed: SmartcardException smart card connection failed
[BootTrace][SeedKeeper] connect failed: SmartcardException protocol not supported
```

---

## Analysis

### Pattern Recognition

```
PASS conditions: V2, V4, V6, V7
Common factor:   T1_RECONFIG = ON

FAIL conditions: V0, V1, V3, V5
Common factor:   T1_RECONFIG = OFF
```

**T1_RECONFIG is the necessary and sufficient fix.** All four variants with T1_RECONFIG enabled pass. All four variants without T1_RECONFIG fail, regardless of HALFDUPLEX or PPS settings.

### Fix Effectiveness

| Fix | Effect on SeedKeeper |
|-----|---------------------|
| **T1_RECONFIG** | **Required** - Without it, all variants fail |
| HALFDUPLEX | No effect - V3 (HALFDUPLEX only) fails same as V0 |
| PPS | No effect - V1 (PPS only) fails same as V0 |

### Why T1_RECONFIG Is Critical

Per ISO 7816-3, the ATR is always transmitted using T=0 character framing (1.5 stop bits, default guard time). After ATR reception, the interface device must switch to the timing parameters of the negotiated protocol.

For SeedKeeper:
- TD1 = 0x81 means the card offers T=1 protocol
- The firmware correctly detects T=1 and attempts to use it
- **But** without T1_RECONFIG, the USART continues using T=0 timing (1.5 stop bits, 16 ETU guard)
- T=1 frames sent/received with T=0 timing cause framing and timing errors
- The smart card controller reports "protocol not supported" because T=1 communication fails at the physical layer

The fix reconfigures the USART after ATR reception:

| Parameter | T=0 (ATR) | T=1 (Post-ATR) |
|-----------|-----------|----------------|
| Stop Bits | 1.5 | 1 |
| Guard Time | 16 ETU | 11 ETU minimum |

### Why HALFDUPLEX Has No Effect

Both approaches (skip_bytes counter vs explicit RE/TE control) provide sufficient switching delay for SeedKeeper. The card's timing parameters (BWI=4, CWI=5 from TB3) are lenient enough that either method works once USART timing is correct for T=1.

This fix may still be useful for other cards with tighter timing requirements.

### Why PPS Has No Effect

Although TA1=0x18 indicates the card proposes faster communication, the card tolerates operating at default speed without explicit PPS negotiation. More importantly, PPS is a protocol-layer exchange that cannot succeed if the underlying USART timing is fundamentally wrong. The T1_RECONFIG fix addresses the root cause; PPS optimization is secondary.

---

## Conclusions and Recommendations

### For Upstream Maintainers

| Fix | PR | Recommendation | Priority |
|-----|-----|---------------|----------|
| **T1_RECONFIG** | [PR #40](https://github.com/diybitcoinhardware/f469-disco/pull/40) | **MERGE** - Required for T=1 smart cards | HIGH |
| HALFDUPLEX | [PR #41](https://github.com/diybitcoinhardware/f469-disco/pull/41) | Consider merging for robustness, but not required for SeedKeeper | LOW |
| PPS | (local) | Not needed - card tolerates default speed | N/A |

### Minimum Change Required

**PR #40 (T1_RECONFIG) alone enables SeedKeeper communication.** The USART must be reconfigured from T=0 timing (1.5 stop bits, default guard time) to T=1 timing (1 stop bit, minimum guard time) after ATR reception.

This is not a SeedKeeper-specific quirk. It is mandated by ISO 7816-3 for any smart card using T=1 protocol.

### Test Scope

These results specifically apply to SeedKeeper communication. Other smart cards may have different timing sensitivities. The HALFDUPLEX fix, while not required for SeedKeeper, may improve compatibility with cards that have stricter timing requirements during TX/RX switching.

---

## References

- ISO/IEC 7816-3: Identification cards - Integrated circuit cards - Part 3: Cards with contacts - Electrical interface and transmission protocols
- SeedKeeper ATR: `3B FA 18 00 00 81 31 FE 45 4A 54 61 78 43 6F 72 65 56 31 B2`
- Test date: 2026-03-11
- Test hardware: STM32F469-Discovery + Specter Shield
- Build toolchain: Docker specter24d
