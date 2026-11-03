# Satochip client vs applet v0.16-0.1 — compatibility notes

Applet release: [Toporin/SatochipApplet v0.16-0.1](https://github.com/Toporin/SatochipApplet/releases/tag/v0.16-0.1)
(2026-10-16, protocol 0.16, breaking changes; reference client
pysatochip v0.18.5). This branch verifies our client against those notes;
wire-level conformance is pinned by `test/tests/test_satochip_v016.py`
(mock-based, no hardware).

## Verified compatible (no change needed)

| v0.16 change | Our client |
|---|---|
| `VerifyPIN` P1 must be `0x00` (single PIN/PUK) | we already send P1=0x00 |
| `SignTransactionHash (0x7A)` replaces removed `0x6F`/`0x6E` | we only implement 0x7A |
| Derived keys cleared on deselect/reset | `sign_hash()` derives (`0x6D`) immediately before signing (`0x7A`, keynbr `0xFF`) in the same session |
| Secure channel accepts commands without Lc | we always send Lc — stricter, accepted |
| Authentikey in `INIT_SECURE_CHANNEL` response; `0xAD`/`0x98` PIN-free | optional optimizations, not relied upon |

## Changed on this branch

- **Removed dead `INS_SIGN_MESSAGE = 0x6E`** — the instruction is gone from
  the applet (`SW_INS_DEPRECATED 0x9C26`); the constant was never wired to a
  method and must not tempt anyone to use it.
- **Added `factory_reset()`** — the new v0.16 flow: single APDU
  `CLA 0xFD P1=0xAA P2=0x55` over the secure channel, **no PIN required**
  (v0.15 required a PIN-authorized multiphase reset). Intended for bench /
  HIL provisioning sessions; destructive — wipes keys, seed, label, PIN.

## Known interactions to watch (documented, not changed)

- **PIN logout on secure-channel re-init** (v0.16 hardening): our
  `secure_request` auto-retries once on `9c30` by re-establishing the
  channel. On v0.16 cards that retry silently logs the PIN out; the next
  PIN-protected command will fail. If that becomes a nuisance, the retry
  path should flag the keystore locked again (client-side follow-up, not
  applet-compat).
- **UnblockPIN (0x46) new data format** `[PUK_size|PUK|(opt) PIN_size|PIN]` —
  we do not implement UnblockPIN yet; when added, follow the v0.16 format
  only (legacy is rejected).
- `TaprootTweakPrivateKey` BIP341 fix: tweaks derived on ≤ v0.15-0.1 cannot
  be reproduced on v0.16 — irrelevant to us until taproot signing lands.

## Hardware verification

Code-level conformance only (mock suite). On-card verification is an owner
hardware session — `HARDWARE-RUNBOOK.md` session (b) covers Satochip e2e on
the F469; a v0.16 card or a re-flashed one is needed (existing bench
Satochip card runs an older protocol; factory-reset flow above is the
upgrade path for personalization).
