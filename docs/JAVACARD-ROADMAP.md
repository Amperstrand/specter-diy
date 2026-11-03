# Javacard program roadmap & testing strategy (M0–M3)

> **Mirror of [Amperstrand/specter-diy issue #45](https://github.com/Amperstrand/specter-diy/issues/45)**
> — the issue is the single source of truth; this doc is the in-repo mirror plus
> pointers to the artifacts that implement each track. Maintained by worker `javacard`
> (status table updated as milestones progress).

## Status snapshot (2026-11-03)
| Milestone | State | Evidence |
|---|---|---|
| M0 foundations | ✅ mostly done | master = upstream mirror bec1ab10 (PR #38 superseded/closed, archive `javacard-experiments`); T=1 primitive PR #39; MemoryCard PR #40; SeedKeeper client PR #41; Satochip client PR #42; PR#4 (specter-javacard J3H145 fix) rebased; Toporin CAPs = release downloads (no builds); card bench seat 1 (OmniKey+J3R180) proven w/ ATR; seat 2 (F469) in re-diagnosis (owner asserts connected; labgrid exporter fix authorized) |
| M1 J3R180 + specter applet | 🔨 in flight | gate: card in shield → wallet e2e on J3R180 → HIL green + framebuffer screenshots. **Runbook sessions A + D** ([HARDWARE-RUNBOOK.md](../HARDWARE-RUNBOOK.md), PR #44) are the M1 gate procedure; card-side ops guide [specter-javacard docs/J3R180.md](https://github.com/Amperstrand/specter-javacard/blob/docs-j3r180/docs/J3R180.md) (PR#5) |
| M2 Satochip v0.16 / SeedKeeper v2 | 🔨 staged | CAPs downloaded; clients in PRs #41/#42; personalization flows being proven on seat 1. **Runbook sessions B + C** are the M2 gate procedures; v0.16 conformance notes [docs/satochip-v016.md](../docs/satochip-v016.md) |
| M3 upstream sells | 📋 planned | see below — **T=1 story leads with upstream f469-disco #41** (half-duplex TE/RE echo race), #40 timing as follow-up RFC (writeup corrected in PR #39 docs) |
| HIL track | 🔨 planned (P6) | **PR #43** (`feature/hil`): flag-gated TestMode events, framebuffer PNG dumps, hotplug, TEST_WIPE_SECRETS, #23 resilient VCP, #31 badge; runner + labgrid place template + CI below |

## Milestones & gates
- **M1 — J3R180 + MemoryCard**: #39 (T=1, carries f469-disco pin) + #40 (slim keystore).
  GATE: real-card e2e on device, automated HIL run green, screenshots captured,
  docs/J3R180.md complete. → Procedure: runbook **sessions A (J3R180 CAP install +
  smoke) and D (wallet e2e gate)**; HIL automation via `test/integration/hil_runner.py`.
- **M2 — Satochip & SeedKeeper**: #42 (Satochip client verified vs applet v0.16-0.1
  semantics: factory-reset PIN/PUK, Lc-less secure-channel) + #41 (SeedKeeper client incl.
  #22 EEPROM-corruption handling). GATE: per-card e2e sign/store flows + HIL. →
  Procedure: runbook **sessions B (Satochip e2e sign) and C (SeedKeeper e2e +
  provisioning)**.
- **M3 — upstream**: lead with diybitcoinhardware/f469-disco#41 (half-duplex TE/RE echo
  fix — the load-bearing T=1 reliability change; corroborated by osmo-ccid-firmware + our
  ccid-firmware-rs); f469-disco#40 (T=1 timing) as follow-up RFC; specter-diy M1/M2 PRs on
  top of rebase #38; refresh our open upstream HIL PR cryptoadvance/specter-diy#347 (March)
  with P6 improvements instead of a new PR; specter-javacard PR#4 upstream (upstream repo
  dead since 2023 — may need maintainer ping or fork-as-home decision).
- **Isolated**: feature/cap-installer (in-firmware CAP/GP installer) stays OUT of M1–M3
  (upstream-resistance isolation).
- **M3-prep stretch goal — DRY keystore refactor** (owner: *"possibly, not a given"*):
  converge the near-duplicate keystore classes (MemoryCard/SeedKeeper/Satochip share
  unlock/PIN/connection flows). Reference: the archived refactoring plan
  `docs/JAVACARD_REFACTORING_PLAN.md` on `javacard-experiments` (phases 1–3 were executed
  there; the clean-topology JavaCardKeyStore base on the m-branches is its living core).
  Only pursue if an upstream sell would otherwise be blocked by the duplication.

## Testing roadmap (layers, each milestone gates through all applicable)
1. Simulator unit (run_sim.py + simulator.jar, CI-gated per PR)
2. Native pytest (July infra; protocol logic incl. #22 regression vectors —
   `test_seedkeeper_eeprom_corruption.py`, `test_satochip_v016.py`)
3. vpcd virtual-card (hardware-free host integration; bench vpcd slots exist)
4. **HIL via labgrid** (PR #43): place `stm32-f469-diy`
   ([template](../test/integration/labgrid-place-stm32-f469-diy.yaml)); runner
   [`test/integration/hil_runner.py`](../test/integration/hil_runner.py) with
   acquire→flash→test→**restore ccid firmware**→release (bench exclusivity encoded,
   exit 2 on failed restore); JSON-lines results
   ([hil_events.py](../test/integration/util/hil_events.py)); framebuffer-dump screenshots;
   nightly + label CI ([hil.yml](../.github/workflows/hil.yml), pattern shared w/ bolty-rs
   #54). Design: [docs/hil-architecture.md](./hil-architecture.md) §9.
5. Release evidence pack per milestone (see below)

## Show-off strategy (evidence per milestone)
- Framebuffer-dump PNG sequence stitched to GIF/MP4 of the display flow (sign with
  Satochip, store to SeedKeeper) — automatable from HIL (`FramebufferAssembler` +
  `rgb565_to_png` host-side; upstream sim-side parallel: f469-disco PR #39 SDL screenshot)
- APDU transcript beside terminal output (card-level proof)
- Green HIL run log + CI badge (labgrid)
- GitHub release per milestone (tag m1-j3r180 etc.) with firmware + CAP artifacts +
  embedded GIF + user story in notes
- User stories demoed in upstream specter-diy-web-simulator for the Python/UI layer
- Portfolio-level: project-context case study + consulting narrative ("DIY airgapped
  wallet + established javacard products")

## Blockers / risks
- F469 seat 2 dark (re-diagnosis running; labgrid exporter fix authorized) — blocks
  device gates
- Card-seat wiring identity on F469 (specter-shield USART slot vs ccid bench slot) —
  verify once board live
- USB VCP flake #23 — fix in P6 HIL scope (`resilient_query` landed in PR #43; device-side
  root cause open)
- Upstream bootloader 1.0.2 key rotation — irrelevant for ST-LINK flashing; revisit only
  for production signed-update story (runbook bench rule 2 keeps the check anyway)
- Card personalization PINs must be consistent across both seats (cardbench doctrine)

## Ownership
- worker `javacard` (herdr w1N:pY): branches/PRs, runbook, roadmap doc, HIL (P6)
- worker `cardbench` (herdr w1N:pZ): card installs/smoke both seats, M1/M2-tagged evidence
  → `.audit-lanes/cardbench-2026-11-02.md`
- owner: F469 wiring, card swaps if brick, merges, upstream sends
- Coordination ledger: project-context `.audit-lanes/issue-sweep-2026-11-01.md` (dispatch
  blocks) + `javacard-revive-2026-11-02.md`
