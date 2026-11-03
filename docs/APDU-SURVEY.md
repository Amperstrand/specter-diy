# APDU Survey — bench F469 + seated J3R180 (CPLC 50942720) — 2026-11-04 00:05 run

First full on-device battery (evidence: `artifacts/hil/survey-run1.log`, 49 lines).
Environment: m1-gate-firmware build (nix, gcc-9) on m1-gate-board (#40+#41), single
T=1 session, SELECT-switched, UART3/if02 console.

## Card state (THE headline finding)

Cross-referenced with cardbench ledger: **this card's applets are installed but NEVER
personalized** ("no Satochip lock, no PIN/setup, ISDs OP_READY"). Therefore:

- Satochip v0.14: `verify_pin(1234)` → **63C2 (2 tries left — DO NOT retry blindly)**;
  all PIN-protected ops → **9C04 = SW_SETUP_NOT_DONE (literal)**. The applet needs
  `INS_SETUP (0x2A)` + `INS_CREATE_PIN`/PIN-set flow first. Personalization = step 1
  of tomorrow's integration logic.
- SeedKeeper v0.2: SC-init ✓, `verify_pin(1234)` → **9000 OK** (SK PIN default works),
  but GET_STATUS/label/list/export via secure channel → 9C04. Interpretation: SK also
  reports setup-pending for secret-store ops (needs its setup/first-secret flow), or a
  secure-channel sequence nuance in our client — **unresolved, top debug item**.
- MemoryCard: fully functional (see below) — it self-personalizes on first PIN set.

## MemoryCard (specter applet) — COMPLETE, protocol truth confirmed on-device

| Op | Result | Timing |
|---|---|---|
| SELECT | 9000 | 36.5 ms |
| SC open (lazy, in first request) | implicit ✓ | — |
| GET_RANDOM | OK | 604 ms (TRNG + SC) |
| pin_status | reaches applet (client parse bug ours — note) | 6.7 ms |
| STORAGE_PUT/GET 0 B | OK | — |
| STORAGE_PUT/GET 1 B | OK | — |
| STORAGE_PUT/GET 220 B | OK | — |
| STORAGE_PUT/GET 221 B | **rejected** (boundary = 220 exactly, as documented) | 7.0 ms |
| client API notes | `mc.sc.request()` = the flow; no open_channel/get_pubkey/close_channel attrs (survey script bugs, not card) | |

## Session & transport truth

- Cross-family SELECT switching (MC→SK→SC→MC→SC): all 9000 — one session, family
  switching at will ✓.
- Reader connection cap: **2 per power cycle** (1 disconnect doesn't free a slot);
  survey design (single session) is the correct pattern; app must cache one connection.
- ATR not exposed via uscard conn attribute (documented gap; SELECT-probing is the
  detection path — as our card_detector already does).
- SC init timing ~480 ms both families (card-side ECDH) — budget for UI feedback.

## Integration spec inputs (for tomorrow)

1. **App detection**: SELECT-probe all three AIDs (36-48 ms each) — cheap enough to
   run in the keystore picker; multi-hit → chooser dialog; single → autoselect+banner.
2. **Personalization logic needed**: Satochip SETUP+PIN (fresh applet!), SK setup/first
   secret (verify 9C04 semantics), MemoryCard PIN-set flow exists (pin_status+set).
3. **PIN doctrine**: Satochip PIN attempts FINITE — never brute; setup flow sets PIN
   first time. SK default 1234 verified working.
4. BIP32/BIP85: card-side commands = INS_BIP32_GET_EXTENDED_KEY (0x6D) at any path
   incl. m/83696968h/* (BIP85 is host-side derivation over card xpubs — no card BIP85
   INS exists in v0.14). Blocked on Satochip personalization for live capture.
5. Signing: INS_SIGN_TRANSACTION_HASH (0x7A) blocked on PIN; spec verified from
   CardEdge v0.14-0.2 source (checked out at /tmp/opencode/ref-satochip).

## Survey harness (reusable)

`boot/debug/apdu_survey.py` on m1-gate-firmware — pyb.main rung, phase batteries,
timed ops, `[tag.OK/ERR]` lines to UART3. Dev loop: nix build (1-3 min incremental) →
`/tmp/m1-gate/flash.sh` (8 s) → persistent logger `/tmp/m1-gate/console.log`.
Run-2 TODO: after Satochip SETUP, rerun for xpub/signature captures; fix client API
calls flagged above; add deliberate typed-secret round-trip once SK store is live.
