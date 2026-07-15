# SeedKeeper ATR Analysis per ISO 7816-3

## Captured ATR

```
3B FA 18 00 00 81 31 FE 45 4A 54 61 78 43 6F 72 65 56 31 B2
```

Captured from all passing variants (V2, V4, V6, V7) during test matrix execution.

---

## Byte-by-Byte Decode

### TS (Byte 0): `0x3B` — Initial Character

| Field | Value | Interpretation |
|-------|-------|----------------|
| Convention | 0x3B | Direct convention (LSB first) |

The ATR is transmitted using **T=0 timing** regardless of which protocol will be used after ATR. This is per ISO 7816-3: the interface device receives ATR using T=0 character framing (1.5 stop bits, default guard time).

---

### T0 (Byte 1): `0xFA` — Format Character

| Nibble | Value | Interpretation |
|--------|-------|----------------|
| Upper (Y1) | 0xF (1111b) | TA1, TB1, TC1, TD1 all present |
| Lower (K) | 0xA (10) | 10 historical bytes follow |

This tells us the ATR contains interface bytes TA1 through TD1, followed by 10 historical bytes.

---

### TA1 (Byte 2): `0x18` — Timing Parameters

| Field | Nibble | Index | Value |
|-------|--------|-------|-------|
| Fi (Clock Rate Factor) | Upper (0x1) | 1 | Fi = 372 |
| Di (Baud Rate Divisor) | Lower (0x8) | 8 | Di = 12 |

**Interpretation:**
- Proposed ETU = (1/Di) × (Fi/f) seconds
- For Fi=372, Di=12: ETU = 372/12 = 31 clock cycles
- Default ETU = 372/1 = 372 clock cycles (Fi=372, Di=1)
- This card proposes a **31× faster** communication speed

**PPS Implication:**
- TA1 ≠ 0x11 (default), so per ISO 7816-3, PPS (Protocol Parameter Selection) negotiation **should** be required to change speed
- However, our test matrix shows: **PPS fix has NO effect on SeedKeeper**
- The card apparently tolerates operation at default speed without explicit PPS negotiation

**Conclusion for PPS:** NOT NECESSARY for SeedKeeper — card operates at default speed regardless.

---

### TB1 (Byte 3): `0x00` — Programming Voltage (Deprecated)

| Field | Value | Interpretation |
|-------|-------|----------------|
| II | 0x0 | Not used (Vpp deprecated) |
| PI1 | 0x0 | No external programming voltage |

Modern smart cards (including SeedKeeper) do not require Vpp. This byte is retained for backward compatibility.

---

### TC1 (Byte 4): `0x00` — Extra Guard Time

| Field | Value | Interpretation |
|-------|-------|----------------|
| N | 0 | Minimum guard time |

**Interpretation:**
- N=0 means the minimum character guard time applies
- For T=0: minimum guard time = 12 ETU
- For T=1: minimum guard time = 11 ETU

**Critical Note:** 
The guard time MUST be observed between consecutive characters. With TC1=0x00, the interface device must use the protocol-specific minimum:
- During ATR reception (T=0 mode): 12 ETU guard
- After protocol switch (T=1 mode): 11 ETU guard

This is **WHY T1_RECONFIG is critical** — the USART must be reconfigured from T=0 guard time to T=1 guard time after ATR.

---

### TD1 (Byte 5): `0x81` — First Protocol Indicator

| Nibble | Value | Interpretation |
|--------|-------|----------------|
| Upper (Y2) | 0x8 (1000b) | TD2 present; TA2, TB2, TC2 absent |
| Lower (T) | 0x1 | Protocol T=1 offered first |

**Interpretation:**
- The card offers T=1 protocol first
- TD2 is present, so more interface bytes follow
- No TA2 means no specific mode is required (negotiable mode)

---

### TD2 (Byte 6): `0x31` — Second Protocol Indicator

| Nibble | Value | Interpretation |
|--------|-------|----------------|
| Upper (Y3) | 0x3 (0011b) | TA3, TB3 present; TC3, TD3 absent |
| Lower (T) | 0x1 | Protocol T=1 (confirmation) |

TD2 confirms T=1 protocol and indicates TA3/TB3 (T=1 specific parameters) are present.

---

### TA3 (Byte 7): `0xFE` — Information Field Size (IFSC)

| Field | Value | Interpretation |
|-------|-------|----------------|
| IFSC | 0xFE (254) | Card accepts up to 254-byte information fields |

This is the maximum block size the card can receive in T=1 protocol. Standard T=1 IFSC ranges from 1-254; 254 is the maximum standard value.

---

### TB3 (Byte 8): `0x45` — Waiting Time Parameters

| Field | Nibble | Value | Interpretation |
|-------|--------|-------|----------------|
| BWI | Upper (0x4) | 4 | Block Waiting Integer |
| CWI | Lower (0x5) | 5 | Character Waiting Integer |

**Derived Timing:**

**Block Waiting Time (BWT):**
```
BWT = 11 ETU + 2^BWI × 960 × (Fi/f) × D/s
    = 11 ETU + 2^4 × 960 × 372/f
    = 11 ETU + 15,360 × 372/f
```

At 4MHz clock: BWT ≈ 1.4 seconds maximum block response time.

**Character Waiting Time (CWT):**
```
CWT = 11 ETU + 2^CWI
    = 11 ETU + 2^5
    = 11 + 32
    = 43 ETU
```

Maximum time between consecutive characters in a block is 43 ETU.

---

### Historical Bytes (Bytes 9-18): `4A 54 61 78 43 6F 72 65 56 31`

| Hex | ASCII |
|-----|-------|
| 4A | J |
| 54 | T |
| 61 | a |
| 78 | x |
| 43 | C |
| 6F | o |
| 72 | r |
| 65 | e |
| 56 | V |
| 31 | 1 |

**String:** `JTaxCoreV1`

This identifies the card applet as "JTaxCoreV1" — the SeedKeeper application.

---

### TCK (Byte 19): `0xB2` — Check Byte

XOR checksum of all bytes from T0 through the last historical byte (bytes 1-18). Used to verify ATR integrity.

---

## Cross-Reference with Test Results

### Test Matrix

| Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result |
|---------|-----------|-------------|-----|--------|
| V0 | OFF | OFF | OFF | FAIL |
| V1 | OFF | OFF | ON | FAIL |
| V2 | OFF | **ON** | OFF | **PASS** |
| V3 | ON | OFF | OFF | FAIL |
| V4 | OFF | **ON** | ON | **PASS** |
| V5 | ON | OFF | ON | FAIL |
| V6 | ON | **ON** | OFF | **PASS** |
| V7 | ON | **ON** | ON | **PASS** |

### Pattern Analysis

```
PASS conditions: V2, V4, V6, V7
Common factor:   T1_RECONFIG = ON

FAIL conditions: V0, V1, V3, V5
Common factor:   T1_RECONFIG = OFF
```

**T1_RECONFIG is necessary AND sufficient.**

---

## ATR-Based Explanation of Each Fix

### FIX_T1_RECONFIG: Why It Is Critical

**What the ATR tells us:**
1. **TD1 = 0x81** → Card offers T=1 protocol
2. **TC1 = 0x00** → Minimum guard time (0 extra guard time)
3. **The ATR itself is transmitted using T=0 timing** per ISO 7816-3

**What T1_RECONFIG does:**
```c
// After ATR reception, when T=1 protocol is selected:
// Note: 'usart' is a pointer to the USART instance used for smartcard
// (USART2 on STM32F469-DISCO with PA2/PA4 pins)
usart->CR2 &= ~USART_CR2_STOP;  // 1 stop bit (was 1.5 for T=0)
usart->GTPR = (1U << 8) | psc;   // Guard time = 1 ETU (was 16)
```

**Note:** On STM32F469-DISCO, the smartcard interface uses **USART2** (PA2=IO, PA4=CLK), not USART1. The code uses a generic `usart` pointer to the active USART instance.

**Why this is necessary:**

| Parameter | T=0 (ATR Reception) | T=1 (Post-ATR) |
|-----------|---------------------|----------------|
| Stop Bits | 1.5 | 1 |
| Guard Time | 16 ETU (default) | 11 ETU minimum |

If the USART is not reconfigured:
- The hardware sends/receives T=1 frames with T=0 timing
- Stop bit mismatch causes framing errors
- Guard time mismatch causes character timing violations
- T=1 block exchanges fail → "protocol not supported"

**Conclusion:** NECESSARY — The USART hardware MUST be reconfigured from T=0 to T=1 timing after ATR reception. This is mandated by ISO 7816-3 when switching protocols.

---

### FIX_HALFDUPLEX: Why It Has No Effect

**What HALFDUPLEX does:**
- Uses explicit CR1 RE (Receiver Enable) and TE (Transmitter Enable) bit control
- Replaces the original `skip_bytes` counter approach for guard time during TX→RX switching

**Why no effect on SeedKeeper:**
- The original `skip_bytes` approach apparently provides sufficient switching delay for SeedKeeper
- The card's timing requirements (BWI=4, CWI=5) are lenient enough
- Both approaches result in successful T=1 communication once USART timing is correct

**Conclusion:** NOT NECESSARY for SeedKeeper — Both skip_bytes and set_half_duplex work. The upstream comment about "missing quick responses" may apply to other cards with tighter timing.

---

### FIX_PPS: Why It Has No Effect

**What the ATR tells us (TA1 = 0x18):**
- Fi = 372, Di = 12 → Card proposes 31× faster than default
- TA1 ≠ 0x11 → PPS negotiation SHOULD be required per ISO 7816-3

**Why PPS fix has no effect:**
1. The PPS fix in the code skips PPS exchange under certain conditions
2. But even when PPS exchange occurs (at default speed), connection still fails without T1_RECONFIG
3. SeedKeeper apparently **tolerates operating at default speed** (Fi=372, Di=1) without PPS negotiation
4. PPS is a higher-layer protocol exchange — it cannot succeed if USART timing is fundamentally wrong

**Conclusion:** NOT NECESSARY for SeedKeeper — The card operates at default speed regardless of TA1 value. The USART timing (T1_RECONFIG) is the blocking issue, not speed negotiation.

---

## Final Conclusions

| Fix | Necessity | Rationale |
|-----|-----------|-----------|
| **SCARD_FIX_T1_RECONFIG** | **NECESSARY** | Reconfigures USART from T=0 to T=1 timing after ATR. Mandated by ISO 7816-3 when protocol is T=1. |
| SCARD_FIX_HALFDUPLEX | NOT NECESSARY | Both skip_bytes and explicit RE/TE control work for SeedKeeper. |
| SCARD_FIX_PPS | NOT NECESSARY | Card tolerates default speed despite TA1=0x18. PPS cannot succeed if USART timing is wrong. |

### Minimum Fix Set

```
SCARD_FIX_T1_RECONFIG alone (PR #40)
```

This single fix enables SeedKeeper communication. Adding HALFDUPLEX and/or PPS does not hurt but provides no additional benefit for this card.

---

## Technical Summary

**The Root Cause:**

ISO 7816-3 specifies that the ATR is always transmitted using T=0 character framing (1.5 stop bits, default guard time). After ATR reception, the interface device must switch to the timing parameters of the negotiated protocol.

For SeedKeeper:
- TD1 = 0x81 → Card offers T=1 protocol
- The firmware correctly detects T=1 and attempts to use it
- **BUT** without T1_RECONFIG, the USART continues using T=0 timing (1.5 stop bits, 16 ETU guard)
- T=1 frames sent/received with T=0 timing result in framing and timing errors
- The smart card controller reports "protocol not supported" because T=1 communication fails

**The Fix:**

After ATR reception, when T=1 is selected, the USART must be reconfigured:
1. Stop bits: 1.5 → 1
2. Guard time: 16 ETU → 1 ETU (results in 11 ETU minimum character spacing for T=1)

This is exactly what `SCARD_FIX_T1_RECONFIG` implements.

---

## References

- ISO/IEC 7816-3: Identification cards — Integrated circuit cards — Part 3: Cards with contacts — Electrical interface and transmission protocols
- SeedKeeper ATR captured: `3B FA 18 00 00 81 31 FE 45 4A 54 61 78 43 6F 72 65 56 31 B2`
- Test date: 2026-03-11
- Test hardware: STM32F469-Discovery + Specter Shield
