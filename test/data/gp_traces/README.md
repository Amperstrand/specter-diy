# GP Reference Traces

APDU traces captured from GlobalPlatformPro (GPPro) v25.10.20 interacting with a
JCOP4 JavaCard via SCP02. These traces serve as the ground truth for testing
our SCP02 implementation and GP command formatting.

## Hardware

- Card: JCOP4 (NXP J3H145)
- Reader: Gemalto PC Twin Reader (08e6:3437)
- ATR: `3B:D5:18:FF:81:91:FE:1F:C3:80:73:C8:21:10:0A`

## Session 001 — TeapotApplet Install/Verify/Delete

| File | Description |
|------|-------------|
| `session_001_environment.txt` | Test environment, tool versions, ATR |
| `session_001_card_atr.txt` | Raw card ATR bytes |
| `session_001_install_teapot.txt` | Full TeapotApplet install trace (INIT UPDATE, LOAD 4 blocks, INSTALL) |
| `session_001_verify_teapot.txt` | Registry verification after install |
| `session_001_uninstall_teapot.txt` | DELETE command trace |
| `session_001_verify_removed.txt` | Registry verification after removal |
| `session_001_delete_memorycard.txt` | Orphaned MemoryCard package deletion |
| `session_001_result_summary.md` | Protocol reference: key derivation, APDU formats, notes |

## Trace Format

Traces contain `[TRACE]` lines from GPPro with MAC inputs and `A>>`/`A<<` lines
showing raw T=0 APDUs. Key patterns:

- `[TRACE] SCP02Wrapper - MAC input: <hex>` — the data used for MAC computation
- `A>> T=1 (4+NNNN) <CLA INS P1 P2 Lc> <data> <MAC> 00` — command APDU
- `A<< (NNNN+2) <data> <SW1><SW2>` — response APDU

## Usage in Tests

See `test/tests_native/test_scp02_crypto.py` for how traces are parsed and used
to verify our SCP02 session key derivation, cryptogram computation, and MAC.
