# T=1 USART reconfiguration — the minimal card-communication primitive

Branch purpose (owner milestone M1): carry **only** the T=1 USART fix that
makes STM32F469-Discovery + Specter Shield talk to T=1 smartcards (SeedKeeper,
Satochip, J3R180-family JavaCards). No keystore features, no HIL, no GP
installer — those live on their own branches so this primitive stays easy to
review and upstream.

## The fix

One function, called once after ATR, before the first T=1 block:

- `f469-disco` submodule pinned to
  [`t1-usart-onto-v1.10.5`](https://github.com/Amperstrand/f469-disco/tree/t1-usart-onto-v1.10.5)
  — commit `6ac214e` on top of the upstream `v1.10.5` pin (`9dd8515`, embit 0.8.2).
- `scard_configure_t1()` in `usermods/scard/ports/stm32/scard_io.c`:
  clears `CR2.STOP` to 00 (1 stop bit, ISO 7816-3 §12 T=1) and sets
  `GTPR[15:8] = 1` (1-ETU guard time), guarded by a one-shot
  `t1_usart_configured` flag; invoked from `usermods/scard/connection.c`
  when T=1 is selected. +55/−1 lines across 3 files, STM32-only.

Without it the USART keeps T=0 timing (1.5 stop bits, guard time 16) and the
first T=1 exchange fails with *"protocol not supported"* — every T=1 card is
unusable on this board.

## Evidence — 8-variant hardware matrix (2026-03-11)

STM32F469-Discovery + Specter Shield + SeedKeeper card, Docker `specter24d`
build, `USE_DBOOT=0 DEBUG=0`. Raw logs: [`results/V0..V7_output.log`](
../results/test_matrix_results.md); analysis: [`results/atr_analysis.md`](
../results/atr_analysis.md).

| Variant | HALFDUPLEX | T1_RECONFIG | PPS | Result |
|---------|-----------|-------------|-----|--------|
| V0 | OFF | OFF | OFF | FAIL — protocol not supported |
| V1 | OFF | OFF | ON  | FAIL — protocol not supported |
| V2 | OFF | ON  | OFF | **PASS** — T=1 connected |
| V3 | ON  | OFF | OFF | FAIL — protocol not supported |
| V4 | OFF | ON  | ON  | **PASS** — T=1 connected |
| V5 | ON  | OFF | ON  | FAIL — protocol not supported |
| V6 | ON  | ON  | OFF | **PASS** — T=1 connected |
| V7 | ON  | ON  | ON  | **PASS** — secure channel established |

**T1_RECONFIG is necessary and sufficient in this matrix**: every variant
with it passes, every variant without it fails regardless of the other
flags. Note the matrix measures *protocol-level* connect/fail, not
byte-level reliability under the half-duplex echo race — that race is what
upstream PR #41 (TE/RE echo control) fixes; the two changes are
complementary, not alternatives. The historical
compile-time matrix flags (`SCARD_FIX_*`) were scaffolding for this
experiment; the landed commit applies the reconfiguration unconditionally on
T=1 selection (T=0 cards are untouched — reconfiguration only triggers for
T=1).

Full protocol-level narrative: [`SEEDKEEPER_BREAKTHROUGH.md`](../SEEDKEEPER_BREAKTHROUGH.md).

## Upstreaming notes

The upstream story is **two PRs on diybitcoinhardware/f469-disco** (owner-filed; external
posting is owner-gated per policy), and the load-bearing one is NOT the timing change
carried here:

- **Upstream PR #41 — half-duplex TE/RE echo control (+90/−38, replaces `skip_bytes`) —
  THE T=1 reliability fix.** STM32 documents smartcard mode as single-wire half-duplex
  where the echo-vs-TC ordering after a direction switch is **unpredictable** (ST forum:
  "completely random"). `skip_bytes` assumed a fixed echo length and loses bytes when the
  assumption breaks; explicit TE/RE direction control eliminates the race. Same approach
  as osmo-ccid-firmware and our ccid-firmware-rs `smartcard.rs`. Lead with this rationale
  in upstream-facing writeups.
- **Upstream PR #40 — `scard_configure_t1()` timing (+55/−0, the commit this branch pins
  as `6ac214e`) — spec-compliance follow-up.** 1 stop bit + 1-ETU guard time per ISO
  7816-3 §12 instead of T=0 timing (1.5 stop bits, guard 16). Its own PR body carries the
  counter-argument ("original T=0 timing works for all known T=1 cards"); the 8-variant
  matrix below is its evidence artifact — T1_RECONFIG is what flipped every failing
  variant to passing, but the reliability race itself is #41's to fix.

Upstream is alive (k9ert active; MicroPython v1.25 WIP in #33) — rebase check before
re-posting. Upstream PR #39 (SDL screenshot function) is the native-simulator counterpart
to our HIL framebuffer dumps (see `feature/hil`, hil-architecture.md §9.2). Direct
register manipulation in #40 is required because the STM32 HAL does not expose
guard-time/stop-bit reconfiguration for smartcard mode post-init.

## Build/verify on this branch

```sh
git submodule update --init --recursive f469-disco
make test          # unix port + frozen-import-smoke + simulator suite
```

STM32 firmware build (`make all`) and on-shield verification are owner-gated
hardware steps — see `HARDWARE-RUNBOOK.md` session (a).
