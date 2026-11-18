# SeedKeeper Fix Test Matrix Results

## Test Environment
- Board: STM32F469-Discovery + Specter Shield
- Card: SeedKeeper (bacon*24 seed, PIN 1234)
- Build: Docker specter24d, USE_DBOOT=0, DEBUG=0
- Date: 2026-03-11

## Results

| Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result | Key Output |
|---------|-----------|-------------|-----|--------|------------|
| V0      | OFF       | OFF         | OFF | FAIL   | connect failed, protocol not supported |
| V1      | OFF       | OFF         | ON  | FAIL   | connect failed, protocol not supported |
| V2      | OFF       | ON          | OFF | PASS   | ATR: 3B FA 18..., connected using protocol: 2 |
| V3      | ON        | OFF         | OFF | FAIL   | connect failed, protocol not supported |
| V4      | OFF       | ON          | ON  | PASS   | ATR: 3B FA 18..., connected using protocol: 2 |
| V5      | ON        | OFF         | ON  | FAIL   | connect failed, protocol not supported |
| V6      | ON        | ON          | OFF | PASS   | ATR: 3B FA 18..., connected using protocol: 2 |
| V7      | ON        | ON          | ON  | PASS   | ATR: 3B FA 18..., Secure channel established |

## Pass/Fail Criteria
- PASS: Serial output contains `[BootTrace][SeedKeeper] ATR:` AND `connected using protocol:`
- FAIL: Serial output contains `connect failed` or `protocol not supported`

## Analysis

### Critical Finding: T1_RECONFIG is the essential fix

| Fix Combination | Works? |
|-----------------|--------|
| T1_RECONFIG only (V2) | YES |
| T1_RECONFIG + PPS (V4) | YES |
| HALFDUPLEX + T1_RECONFIG (V6) | YES |
| All three (V7) | YES |
| No fixes (V0) | NO |
| PPS only (V1) | NO |
| HALFDUPLEX only (V3) | NO |
| HALFDUPLEX + PPS (V5) | NO |

### Conclusion
**T1_RECONFIG is the necessary and sufficient fix.** All variants with T1_RECONFIG enabled (V2, V4, V6, V7) pass. All variants without T1_RECONFIG (V0, V1, V3, V5) fail, regardless of HALFDUPLEX or PPS settings.

The minimum required fix is `SCARD_FIX_T1_RECONFIG` alone. Adding HALFDUPLEX and/or PPS does not hurt but is not required.
