# HARDWARE RUNBOOK — javacard program owner sessions

Scripted owner-only hardware sessions for the specter-javacard /
specter-diy revival program (owner directive 2026-11-02 "fast forward
everything", restructured 2026-11-03). Every session: exact command,
expected output, evidence capture. Agents prepare scripts; **all hardware
steps on this page are executed by the owner by hand.**

## Program state (2026-11-03)

| Branch line | Content | PR |
|---|---|---|
| `rebase-upstream-v1.10.5` | fork rebased onto upstream v1.10.5 (dead-TRNG fix #370, embit 0.8.2, reproducible build) | #38 |
| `m1-t1-usart` | T=1 USART reconfig primitive (f469-disco `6ac214e`) + 8-variant matrix | #39 |
| `m1-specter-applet` | slim MemoryCard keystore client | #40 |
| `m2-seedkeeper` | SeedKeeper client + #22 fix | #41 |
| `m2-satochip` | Satochip client vs applet v0.16 | #42 |
| `feature/hil` | HIL revival (flag-gated) + labgrid seat | #43 |

**Upstream rebase recommendation** (coordinator intel 2026-11-03): upstream
cryptoadvance/specter-diy v1.10.5 (2026-09-06) ships SECURITY fix #370
(reject dead-TRNG output), embit 0.8.2 and a reproducible-build fix —
landed on our base via PR #38. Our independent Bitcoin Core v30
compatibility commits replayed cleanly on top (no upstream counterpart
existed).

## BENCH RULES — read before touching the F469

1. **The STM32F469-Discovery is EXCLUSIVE**: it runs EITHER
   ccid-firmware-rs (its CCID-reader bench role — other workers depend on
   it) OR specter-diy firmware. Never both. Before flashing specter-diy:
   check the labgrid place `stm32-f469-diy` is free (or no HIL/CCID job is
   running), and **always re-flash ccid-firmware-rs when done**.
   `test/integration/hil_runner.py` encodes this restore step; do it
   manually for ad-hoc sessions.
2. **Bootloader key rotation**: cryptoadvance/specter-bootloader **1.0.2
   (2026-04-08) rotates the firmware signing keys.** Before ANY firmware
   update on the F469: check the installed bootloader version; a 1.0.0/1.0.1
   bootloader will REJECT 1.0.2-keyed firmware. Verify the signature path
   first (build reproducibly, compare hash, check the release signature);
   update the bootloader only from the official signed artifact.
3. **J3H145 card is LOCKED** (keys unknown, ~3 of 5-15 SCP02 retries burned
   — see specter-javacard AGENTS.md). **Never send INITIALIZE UPDATE to it.**
   SELECT probes are safe.
4. **J3R180 cards**: two units, different key state (factory key-ver 0 vs
   default key-ver 1) — identify via CPLC serial first
   (`java -jar gp.jar -d --info`), per-card keys in specter-javacard
   AGENTS.md.
5. Card swaps are manual; power-cycle between firmware variants.

## Wiring reference

- Board: STM32F469I-Discovery + **Specter Shield** (smartcard slot).
- Fork shield-lite gerbers: ST8034ATDT / ST8034HNQR (docs/shield-lite.md).
- Board-support fork: Amperstrand/f469-disco (T=1 USART reconfig);
  HIL transport = UART3 VCP (PB10/PB11) on the ST-Link USB.
- Reader for GP sessions: Gemalto PC Twin Reader on the host.

---

## Session A — J3R180 CAP install + applet smoke (≤15 min)

Prereqs: host with `pcscd` + `gp.jar` (v25.10.20), Gemalto reader, J3R180
card, CAP from specter-javacard CI (or `LANG=C.UTF-8 nix develop --command
ant all` locally).

```sh
sudo /usr/sbin/pcscd                       # unless already running
java -jar gp.jar -d --info                 # CPLC serial -> WHICH card
```

Expected: `CPLC: ... IC Serial: 50879920` (card #1, factory keys key-ver 0)
or `50920920` (card #2, default keys key-ver 1).

Card #2 (default keys) example — MemoryCard applet:

```sh
java -jar gp.jar --key 404142434445464748494A4B4C4D4E4F --key-ver 1 \
    --delete B00B5111CB --force            # clean reinstall (package AID!)
java -jar gp.jar --key 404142434445464748494A4B4C4D4E4F --key-ver 1 \
    --install build/cap/MemoryCardApplet.cap
```

Expected: LOAD progress then `INSTALL)` OK; then:

```sh
java -jar gp.jar --key 404142434445464748494A4B4C4D4E4F --key-ver 1 -l
# expect: B00B5111CB (package) + B00B5111CB01 applet SELECTABLE
```

Smoke test (sim-grade, host side):

```sh
cd specter-javacard/tests/tests
TEST_MODE=card python3 -m pytest test_specter_diy.py -v   # 15 tests
```
Expected: **15 passed** (historical baseline 2026-03-20: 38/38 across three
files; run test_singleusekey.py + test_blindoracle.py separately).

**Evidence capture**: `gp -l` output + pytest tail → append to
`specter-javacard/artifacts/logs/<ts>-j3r180-smoke.log`.

Teardown: leave the applet installed or `--delete B00B5111CB --force`.

## Session B — Satochip e2e sign on the F469 (≤15 min)

Prereqs: `m1-t1-usart` + `m2-satochip` firmware built (or combined branch),
Satochip card seated in the Shield slot, F469 free (BENCH RULES 1-2).

```sh
# flash specter-diy firmware (record ccid restore image path first!)
make all                                   # docs/build.md; note the .bin path
# owner flashing flow per docs/build.md (ST-Link), then boot with card seated
```

Expected boot: `[BootTrace]` on VCP → card detected (SatoChip AID) → PIN
prompt. **The [TEST] badge must NOT appear** (production build — hil_enabled
defaults off; the badge appearing means wrong firmware).

Flow: enter PIN → main menu → derive xpub (`m/84h/0h/0h`) → sign a regtest
PSBT. Expected: xpub matches previously recorded value; signature verifies.

**v0.16 card notes** (docs/satochip-v016.md): on a v0.16 applet card the
flow is unchanged client-side (verify PIN P1=0, 0x7A signing, derive+sign in
one session). If the card is an older protocol, factory-reset via
`applet.factory_reset()` (0xFD AA 55) re-personalizes it — destructive.

**Evidence capture**: VCP boot log + signed PSBT + `satochip_signet_e2e.py`
output if regtest host available. **Restore**: re-flash ccid-firmware-rs
(BENCH RULE 1).

## Session C — SeedKeeper e2e + PIN/GP provisioning (≤15 min)

Prereqs: `m1-t1-usart` + `m2-seedkeeper` firmware, SeedKeeper card seated.

1. Boot → PIN prompt → PIN `1234` (bench card) → secret list.
2. Import: store the bench mnemonic ONCE (`abandon ... about`) — the import
   guard checks `TEST_SECRETS` first; **do not bulk-reimport** (issue #22:
   ≥25 write-ops in one session corrupts the EEPROM object manager).
3. e2e: mnemonic → wallet → sign PSBT (same as session B flow).
4. Wipe (when re-provisioning): HIL `TEST_WIPE_SECRETS` on a HIL build, or
   physical reinsert + per-secret deletes in the UI.
5. GP provisioning on a blank JavaCard (applet-manager line, separate
   session): follow docs in SEEDKEEPER_INTEGRATION.md §GP Provisioning
   (M1-M6) — still needs-hardware-test status.

**If any operation returns 9c06 with PIN verified**: stop, physically
remove and reinsert the card (issue #22 signature — client now raises
`CardStateError` with this guidance; do NOT retry-storm).

**Evidence capture**: VCP log + secret list + signed PSBT →
`artifacts/hil/` (or manual notes in the ledger). **Restore**:
re-flash ccid-firmware-rs.

## Session D (bonus) — M1 gate: wallet end-to-end on J3R180

The milestone gate for M1: MemoryCard applet on J3R180 (session A) +
`m1-specter-applet` firmware + card in Shield → create wallet, store seed
on card, sign PSBT. Pass = full flow completes; capture VCP log + PSBT.

## Future HIL automation

Once sessions B/C pass manually: register the labgrid place
(`test/integration/labgrid-place-stm32f469-diy.yaml` in conwrt-bench), then
`make test-hil` / `hil_runner.py` automate B/C with the acquire→flash→test
→**restore ccid-firmware-rs**→release discipline. Reference: ccid-firmware-rs
labgrid verbs (issue #529, place_card/remove_card over adb, proven 2026-10-31).
