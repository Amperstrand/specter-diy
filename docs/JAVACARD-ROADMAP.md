# Javacard program roadmap & testing strategy (M0–M3)

> **Mirror of [Amperstrand/specter-diy issue #45](https://github.com/Amperstrand/specter-diy/issues/45)**
> — the issue is the single source of truth; this doc is the in-repo mirror plus
> pointers to the artifacts that implement each track. Maintained by worker `javacard`
> (status table updated as milestones progress).

## Roadmap: branches and goals (2026-11-04, coordinator #45 latest)

Framing: every deliverable is a **small, independently reviewable branch** — each one enables a specific feature set, carries its own tests, and stands on a pure-upstream base (mirror master = cryptoadvance v1.10.5+).

### Board layer — Amperstrand/f469-disco (submodule, pinned by m1-t1-usart)
| Branch/PR | Enables | Status |
|---|---|---|
| f469-disco #41 (half-duplex TE/RE) | Reliable T=1 card communication (fixes echo races) | proven on hardware (8-variant matrix + device) |
| f469-disco #40 (T=1 timing) | ISO 7816-3-compliant timing | proven |
| cardbench/unix-pyscard-backend | Simulator talking to real cards via any PCSC reader | green (suite 6/6) |

### specter-diy branches (base: mirror master)
| Branch | Enables | Status |
|---|---|---|
| `m1-t1-usart` (1 commit) | T=1 cards working with specter-diy | ✅ proven on device |
| `m1-specter-applet` (+1 commit) | Javacard-seed keystore (MemoryCard) on J3R180 — slim client + base class + tests + docs | ✅ **M1 CLOSED** (device e2e) |
| `m2-satochip` | Satochip cards as keystore (v0.14-0.2: select/auth/sign) | ✅ all fixes landed (47/47) + P2=0x00 signing fix @ `caa0096` — review-ready |
| `m2-seedkeeper` | SeedKeeper secret storage (v0.2-0.1: store/retrieve/export) | ✅ all fixes landed (44/44) + SETUP flow @ `1f6cb9a` — review-ready |
| `feature/hil` | Automated on-device testing: TestMode console, JSON events, framebuffer screenshots | ✅ working (produced the M1 evidence) |
| `feature/no-qspi-safemode` | Booting on boards with dead/missing external QSPI flash | paused, documented |
| `feature/cap-installer` | Installing/uninstalling CAP files from within the firmware | not started (kept separate) |

### Test & demo tiers
| Piece | Enables | Status |
|---|---|---|
| Unified suite (pytest, story-id→test-id) | Same tests across device / CardMan / simulator | 🔨 porting onto m2 clients |
| Reference vectors (pysatochip-derived) | Regression-proof client fixes | 🔨 packaging |
| Amperstrand/specter-playground (fork of k9ert's) | Scenario demos: `make simulate SCRIPT=memorycard-unlock` etc. + automated screenshot capture | fork ready; scenarios after M2 green |
| conwrt-bench #119 | Labgrid-native flashing + CI runner → nightly matrix | queued |

### Immediate goals (ordered)
1. Land the four client conformance fixes with hardware verification → m2 branches green.
2. Unified suite green across device + CardMan + simulator for all three applet families.
3. Playground scenarios + GIF evidence for each user story.
4. ~~Refresh f469-disco #41 and prepare specter-diy minimal-branch PRs~~ **DOGFOOD-ONLY (owner 2026-11-14): no upstream filing — T=1 #40/#41, HIL #347, and the micropython fork patches all stay local as bench infrastructure; revisit after the M2 gate closes.**

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
