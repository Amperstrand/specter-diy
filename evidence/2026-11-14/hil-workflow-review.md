# HIL Workflow Review — bitcoin-wallet bench (F469 specter-diy + javacard)

Date: 2026-11-14 · Scope: research → review → prioritized improvements
Inputs read: `specter-diy/docs/BENCH-OPERATIONS.md`, `project-context/.audit-lanes/javacard-revive-2026-11-02.md` (11-13/14 entries), `specter-diy/evidence/2026-11-14/` (fb-assemble.py + PNGs + S20 photo), `conwrt-bench/deploy/exporter-nfc-small.yaml` (live SSOT state).
Constraints honored: read-only on hardware, no external posts.

---

## 1. Research summary

### 1.1 AI-agent-driven hardware-in-the-loop testing

The 2025/26 crop of agentic-HIL systems converges on the same architecture our bench evolved organically — typed tool boundary, deterministic execution, leases, evidence:

- **agentic-hil** (https://github.com/agentic-hil/agentic-hil/ + https://agentic-hil.github.io/docs/use-cases/develop-on-your-board/) — MCP tools for Claude Code/Codex/OpenCode + a pytest plugin for CI. Key patterns: reviewable **YAML test plans** validated *before* touching hardware; **device leases** against interference; **grant/revoke permissions** (`allow_mass_erase`, `allow_raw_debugger_commands` refused alongside flashing); **SHA-256 audit chain** making the hardware record tamper-evident; failed runs keep their verdict while **configured recovery actions** restore the bench; ST-Link via OpenOCD/CubeProgrammer, CMSIS-DAP via pyOCD. "A successful build alone does not establish that the firmware works on the board."
- **Synapsio / Better Devices** (https://betterdevices.io/case-studies/synapsio-gateway-hil-validation/ + https://betterdevices.io/blog/ai-in-hardware-in-the-loop-testing-the-loop-embedded-never-closed/) — strictly isolate non-deterministic reasoning (planning) from deterministic hardware execution (compile/flash/measure); compiler diagnostics fed back into the agent loop; "no unverified binary ever touches physical silicon"; agent must be **watchable and stoppable**; for embedded "a wrong write can brick a board, that is not optional."
- **LoopHIL** (arXiv, https://arxiv.org/abs/2610.24231) — LLM agents on an RF bench via **typed tools only**; a **verification ladder** takes its own measurements independent of the agent and **names the failing device/layer** ("blame device"); safety limits enforced **in code, not prompts**. HIL raises task completion 54→79% (17→83% hardest). Critical caveat: *"small models often report unverified claims, so independent hardware checks remain necessary."*
- **IoT-SkillsBench** (https://arxiv.org/html/2603.19583v1) — 378 hardware-validated runs: **concise human-expert skills (structured bench knowledge) yield near-perfect agent success** where bare-LLM knowledge fails. Validates our BENCH-OPERATIONS.md "expert skills file" approach.
- **embeff ExecutionPlatform** (https://embeff.com/ai-agents-for-embedded-testing/) — pin-level processor-in-the-loop; **agents and humans use the same text interface** (Robot/Python/YAML), no GUI-only path.
- **BootLoop** (https://embeddedcomputing.com/technology/ai-machine-learning/ai-dev-tools-frameworks/product-of-the-week-bootloop-test-ai-powered-hardware-in-the-loop) — agent generates tests from schematics/datasheets; bench+CI+EOL on one platform.

**Takeaways for us:** typed TestMode protocol ✓, evidence discipline ✓; missing: independent verification ladder (pass/fail judged by harness, not agent claims), YAML-style declarative test plans, tamper-evidenced audit trail, code-enforced (not convention-enforced) permissions.

### 1.2 Camera-in-the-loop screen verification

- **Dvergr / Mjølner** (https://mjolner.dk/en/dvergr/) — commercial tool doing **exactly our FB-dump architecture**: SWD-based live framebuffer readout over the pins already used for flashing, host-side pixel-perfect comparison, event injection into queues, no firmware modification, semantic screen knowledge host-side. Validates the approach; also shows the next rung (event injection, logical-UI awareness).
- **Squish for MCUs** (https://www.qt.io/quality-assurance/blog/how-to-automate-ui-testing-for-qt-quick-ultrite-applications-on-mcu-devices + /platform-mcu-gui-testing) — DeviceLink runtime compiled into the app gives **framebuffer snapshots → image comparison + OCR** and synthetic input; works without object access or network stack.
- **EmbeddedCI AI vision** (https://www.embeddedci.com/resources/ai-vision-for-embedded-testing) — practical check taxonomy: `wait_for(text, region, timeout)`, `compare(ref, mask=[...])`, `screen_health()` (not black/frozen/flickering/dim/stuck pixels), identify-which-screen; **attach the last frame + diff to the test report** so failures show what the screen looked like.
- **Vision-LLM screenshot loop** (https://github.com/go-go-golems/esp32-s3-m5/blob/86ca2fd7/ttmp/2026/01/01/0025-CARDPUTER-LVGL--cardputer-lvgl-demo-firmware/playbooks/01-screenshot-verification-feedback-loop-cardputer-lvgl.md) — console `screenshot` → **framed PNG protocol (`PNG_BEGIN <len>` … `PNG_END`)** → host capture script with exclusive port access ("one-serial-consumer rule") → OCR/vision-LLM verify → before/after regression diff. Cheap, directly transferable.
- **Optics framework** (https://optics-framework.org/docs/elements/text-and-images) — layered element lookup: UI tree → OCR → template matching, vision only when faster sources fail; OCR engine table (EasyOCR local/accurate, Tesseract light/exact-word, cloud).
- Older but foundational: VizLens/Display Reader (camera + CV for appliance displays, https://www.google.com/url?q=https://dl.acm.org/doi/10.1145/2984511.2984522-level work), GUI-testing-with-CV survey (https://arxiv.org/html/2310.13518v2).

**Takeaways:** the industry ladder is **semantic screen-state → framebuffer pixels → camera photo**, ascending in cost and descending in fidelity. Photos are for state-level/milestone evidence (our S20 role), framebuffers are the assertion source (our TEST_FB_DUMP), OCR only on crisp framebuffer-derived images.

### 1.3 Device-lab orchestration (labgrid / pytest / farms)

- **labgrid docs** (https://labgrid.readthedocs.io/en/stable/, /en/stable/usage.html, /en/latest/getting_started.html, /en/latest/man/exporter.html) — coordinator/exporter/client; pytest plugin (`--lg-env`, `env`/`target`/`strategy` fixtures, `never_retry`, `lg_feature` marks); **USBVideo resource + USBVideoDriver** with `get_screenshot()` and camera-model database (zread: labgrid/driver/usbvideodriver.py); power driver zoo incl. **ExternalPowerDriver (arbitrary shell commands)** and YKUSH USB power (https://zread.ai/labgrid-project/labgrid/11-power-control-drivers-and-management, /10-driver-architecture-and-protocol-implementation); OpenOCDDriver with `load_commands` (ADI example); systemd units in contrib; fs.protected_regular hardening.
- **ADI hw-test "Register a board"** (https://analogdevicesinc.github.io/hw-test/register-a-board/) — canonical flow: stable USB IDs → exporter.yaml → **place config lives on the coordinator** so every client/CI sees identical drivers → verify from CLI → *start with one test, not `pytest tests`*.
- **labgrid-plugins guides** (https://tfcollins.github.io/labgrid-plugins/user-guide/exporter-setup.html, /exporter-deployment.html, /coordinator-testing.html) — **validate exporter YAML before deploy** (schema check); group naming `<BOARD>_<CHIP>` for stable match patterns; ser2net ≥4.6.1 caveat (4.6.0 hangs on RFC2217 purge); smoke tier vs hardware tier for coordinator tests.
- **ubxlib Jenkins farm** (https://github.com/u-blox/ubxlib/blob/0237d5d3/port/platform/common/automation/Jenkinsfile) — production pattern for USB-powered DUT farms: `uhubctl` power-up → wait for enumeration → `retry(3)` flash → timeout-bounded test → **power-down hygiene in `finally`** (uhubctl off + `echo 0 > .../authorized` for ports that re-power themselves).

**Takeaways:** our coordinator/exporter/SSOT setup matches the canon; gaps: no power resource exported, no pytest binding, place config not carrying the driver stack, exporter config not pre-validated, restart-unsafe orphans.

### 1.4 Closing visual feedback loops cheaply (OCR vs framebuffer vs photo)

- **ulr-ocr** (https://github.com/stefbo/ulr-ocr) — Tesseract fails on ultra-low-res screen text; **6× cubic upscale ≈ 300 dpi** makes it usable; **template matching beats OCR for small glyphs/icons/symbols**. 
- **Robot Framework imagecompare thread** (https://forum.robotframework.org/t/image-comparison-with-area-text-masking/9420) — golden-image comparison with **fixed-position and regex masks** for dynamic regions (clocks, counters); EasyOCR with 4× superresolution lifted confidences 0.72→0.95; prefer masks over global confidence thresholds (they hide real diffs).
- **Reddit r/embedded "How do you test UI LCD?"** (https://www.reddit.com/r/embedded/comments/1fvlvq6/how_do_you_test_ui_lcd) — practitioners sniff SPI-to-LCD packets; framebuffer/LTDC reads are the cleaner equivalent on our board.

**Takeaways:** for assertions prefer (1) semantic state (TEST_SCREEN), (2) masked pixel-diff of framebuffer PNGs (numpy/Pillow only — zero new heavy deps), (3) template matching for glyphs, (4) OCR last. Photos never for assertions — only evidence.

### 1.5 Fault-injection harness patterns

- **Renode** (https://renode.readthedocs.io/en/latest/introduction/testing.html, /basic/renode-testing-api.html; https://antmicro.com/blog/2023/10/fuzzing-zephyr-with-afl-renode) — deterministic full-system simulation with **peripheral hooks executing arbitrary Python**, fault models like MRAM partial-write/power-cut (`InjectPartialWrite`, `FaultAtWordWrite`, https://github.com/renode/renode/issues/875), Robot Framework tests, automatic **snapshots of failed tests** for later inspection, AFL++ fuzzing of unmodified firmware.
- **Engineermaxxing testing ladder** (https://www.engineermaxxing.com/micro/lessons/fw-core-10-testing-firmware.html) — fault taxonomy for sensor/bus drivers: **dead bus (0xFF/0x00), never-ready, overrun, glitch, wrong-chip**; **fault-as-hook with a call-count trigger** (`inject(fault, after_calls)`) — "you cannot cut a wire at call number 7, 100 times, in a CI job — a fake can"; **every wait needs a bound**; coverage proves error branches ran.
- **uhubctl** (https://github.com/mvp/uhubctl/) + **seL4 devkit remote power-cycle activity** (https://sel4devkit.github.io/activity/remote_power_cycle/main.html) — PPPS (per-port power switching) USB hubs give remote VBUS cycling for ~$30; verify VBUS actually drops (some hubs only disconnect data); fixed hub-location/port map; **labgrid ExternalPowerDriver or YKUSHPowerDriver wraps this natively**.
- Our own B5 (card VCC kill via SWD PC5 BSRR, app recovered with HBs unbroken) is exactly the engineermaxxing "defensive driver" experiment executed on real silicon.

---

## 2. Workflow review

### 2.1 What we're doing well (validated against practice)

| Ours | Industry equivalent | Verdict |
|---|---|---|
| TestMode typed JSON protocol (TEST_STATUS/SCREEN/PIN/FB_DUMP/REBOOT) over UART3 | agentic-hil typed tools; Synapsio deterministic execution layer | ✓ matches best practice; survived the invisible-print-channel class because errors were routed to the same channel |
| SWD LTDC framebuffer read → host PNG assembly | Dvergr (commercial, SWD framebuffer readout); Squish DeviceLink captures | ✓ we independently built the state of the art; supersedes blurry photos for UI evidence |
| Single-owner console daemon (FIFO in / log out, never open the port twice) | agentic-hil device leases; one-serial-consumer rule (go-go-golems) | ✓ correct discipline, ✗ enforcement is convention-only (see 2.2) |
| Visible-exception harness (_dbg→UART3, TASK-DIED tracebacks) | LoopHIL observability; Renode peripheral logs | ✓ turned silent deaths into console evidence — the single highest-leverage fix of the arc |
| Fault injection: card VCC toggle via SWD BSRR (PC5), retry-guard resilience proven | engineermaxxing fault-as-hook; Renode InjectPartialWrite | ✓ real-silicon fault injection, already parameterizable |
| Evidence + knowledge persistence: BENCH-OPERATIONS.md travels with code; ledger; tags; evidence/ PNGs | IoT-SkillsBench: expert skills → near-perfect agent success | ✓ the strongest thing we do — keep investing here |
| labgrid coordinator 26.0 + exporter SSOT (exporter-nfc-small.yaml), place f469-specter-film, enrollment-token id_path pinning | ADI hw-test flow; labgrid-plugins SSOT doctrine | ✓ registered correctly, incl. the RawSerialPort class fix |
| ST-Link wedge recovery without replug (stlink-usbreset userspace ioctl) | uhubctl/USBDEVFS_RESET practice | ✓ cheaper than replug; documented |

### 2.2 What is fragile

1. **FB dump transport robustness.** First dump was 83% chunks; stray losses when other commands race the dump ("send NOTHING else during a dump" is a convention, not a mechanism); no per-chunk checksum, no re-request; `fb-assemble.py` regex-mines the *live rotating console log* (`/tmp/opencode/f469-console.log`) and hardcodes geometry (W,H=800,480) that disagrees with BENCH-OPERATIONS.md's "480x800 portrait, rotate -90" — the layout knowledge lives in two places. Compare the framed `PNG_BEGIN/PNG_END` protocol + exclusive-port capture script pattern (go-go-golems) — one small framing change removes the whole class.
2. **No remote power control — the top single-owner bottleneck.** The 11-03 latch-up ("FULL POWER CYCLE FIRST" rule), the 11-08 "hardware legs blocked on owner: card re-seat + USB power-cycle", and ST-Link full wedges all required owner hands. Nothing in exporter-nfc-small.yaml exports power. A PPPS hub + uhubctl (or YKUSH) + labgrid ExternalPowerDriver converts the bench's most expensive failure class into a 2-second remote operation.
3. **Console arbitration outside labgrid.** The place lease and the FIFO daemon are disconnected: an agent (or human) can `printf` into `/tmp/opencode/f469-console.in` without holding f469-specter-film. labgrid's whole acquire/release model assumes resources gate access; ours currently gates nothing functional (RawSerialPort is exported but the daemon owns the port).
4. **Verification is agent-judged, not harness-judged.** LoopHIL's core lesson: independent checks matter because agents report unverified claims. Our TEST_* replies are good primitives, but pass/fail lives in ad-hoc printf loops and eyeballs; no declarative test plan, no audit chain, no auto-attached failure artifacts (last frame + console tail).
5. **pytest/labgrid not wired on the bench side.** hil_runner.py (acquire→flash→test→RESTORE in finally, exit 2 on restore failure — the ubxlib `finally`-hygiene pattern, already right!) exists on feature/hil but is parked pending the #119 relocation ruling to conwrt-bench. The M2 unified suite (device + CardMan + sim) is designed, not running.
6. **S20 rig is evidence-grade, not assertion-grade.** Fixed mount out of focus ("structure, not glyphs"); exported as bare USBDevice presence; adb driving is ad hoc. Fine for milestone photos — but nothing closes a vision loop today.
7. **/tmp fragility.** Console log, FIFO, watcher, assembler input all under /tmp/opencode — the exporter YAML itself warns "/tmp is sweep-fragile on this host". Irreplaceable evidence can vanish.
8. **Exporter restart hazard.** m5stick-usb + nucula-c3 live-only config-orphans (documented warning) — the SSOT file still can't be safely restarted onto.
9. **Build loop.** 15-min full-clean nix builds as reflex; the ledger proved 1–3-min incremental nix is safe. Every debug iteration pays the full-clean tax unnecessarily.
10. **No watchdog automation.** The console watcher (exit-code contract: 0=ALIVE, 4=USB gone, 3=TTL) is a tmux session, not a monitored unit; PARTNO 0x0 wedges still need manual usbreset; HB-loss has no automated response.

### 2.3 What is missing (vs surveyed practice)

- Independent verification ladder with blame attribution (which layer failed: harness / console / firmware / card / reader).
- Declarative YAML test plans executed by a reactor that validates before touching hardware (agentic-hil pattern).
- Masked golden-image regression on FB PNGs + screen-health checks (black/frozen) (EmbeddedCI, Robot imagecompare).
- Fault-injection *campaigns* (parameterized shots + post-shot state verification) rather than one-off probes.
- Power resource, screenshot resource, and recovery actions as first-class labgrid citizens on the place.
- CI leg: nightly self-hosted runner acquiring the place (the .github/workflows/hil.yml sketch on feature/hil — unfrozen after #119).

---

## 3. Prioritized improvements

Effort: **S** ≤ 2 h · **M** = half day–1 day · **L** > 1 day. All are small, reversible, and increase automation coverage or remove owner-hands/single-owner bottlenecks. Hardware items need owner hands once (install), then never again.

### P0 — removes the biggest failure classes

| # | Improvement | What / how | Why (practice refs) | Effort |
|---|---|---|---|---|
| 1 | **PPPS USB hub + uhubctl → labgrid power resource** | Put the F469 bench power (and/or ST-Link VBUS) on a per-port-switching hub (e.g. MEGA4-class from the uhubctl supported list); verify VBUS actually drops with the power LED; wrap `uhubctl -l <loc> -p <n> -a cycle` as an **ExternalPowerDriver** on f469-specter-film. Kills the latch-up / degraded-VCP / ST-Link-wedge / board-park classes of owner-hands events. | uhubctl (https://github.com/mvp/uhubctl/); seL4 PPPS activity (https://sel4devkit.github.io/activity/remote_power_cycle/main.html); labgrid powerdrivers (https://zread.ai/labgrid-project/labgrid/11-power-control-drivers-and-management); ubxlib farm hygiene (https://github.com/u-blox/ubxlib/blob/0237d5d3/port/platform/common/automation/Jenkinsfile) | S (software) + one owner hands install |
| 2 | **Frame the FB dump; stop parsing the live log** | Firmware: emit `FB_BEGIN <w>x<h> <chunks>` … per-chunk `seq:crc16` … `FB_END`; on `FB_END` host re-requests missing/corrupt seqs once, then assembles from a dedicated capture file (daemon already serializes commands — add a "dump mode" that hard-blocks the FIFO so racing is a mechanism, not a rule). Geometry (480x800 + rotate -90, ARGB8888, base 0xC0000000) read from the header/config in ONE place; delete the duplicate from fb-assemble.py. | Framed PNG protocol + one-serial-consumer rule (https://github.com/go-go-golems/esp32-s3-m5/blob/86ca2fd7/ttmp/2026/01/01/0025-CARDPUTER-LVGL--cardputer-lvgl-demo-firmware/playbooks/01-screenshot-verification-feedback-loop-cardputer-lvgl.md); Renode failed-test snapshots (evidence preservation) | S–M |
| 3 | **Ship the pytest+labgrid leg (execute the #119 ruling)** | Relocate hil_runner/place template to conwrt-bench; add a small custom labgrid **driver** exposing `TestModeProtocol` (status/screen/pin/fb/reboot) bound to the console resource; pytest fixtures per labgrid plugin docs; smoke test = 1 test first (`test_status.py`: acquire → ALIVE/HB wait → TEST_STATUS → release). This converts the printf-driven bench into a CI-able suite and makes pass/fail harness-judged. | labgrid pytest plugin (https://labgrid.readthedocs.io/en/stable/usage.html); custom drivers (https://zread.ai/labgrid-project/labgrid/14-custom-driver-development); "start with one test" (https://analogdevicesinc.github.io/hw-test/register-a-board/); agentic-hil pytest reactor (https://github.com/agentic-hil/agentic-hil/) | M |

### P1 — closes loops and hardens daily operation

| # | Improvement | What / how | Why (practice refs) | Effort |
|---|---|---|---|---|
| 4 | **Screen-assertion library on FB PNGs** | (a) masked pixel-diff vs golden PNGs (numpy+Pillow, zero new deps; masks for clock/battery regions); (b) `screen_health()` = not-black/not-frozen (two dumps differ) checks; (c) optional template matching (OpenCV) for glyph-level checks where TEST_SCREEN text is insufficient; OCR only as advisor on crisp FB images (tesseract needs ~6× upscale). Attach last frame + diff + console tail to failure output (EmbeddedCI report pattern). Keep TEST_SCREEN semantic asserts primary — cheapest truth. | EmbeddedCI (https://www.embeddedci.com/resources/ai-vision-for-embedded-testing); ulr-ocr (https://github.com/stefbo/ulr-ocr); masked comparison (https://forum.robotframework.org/t/image-comparison-with-area-text-masking/9420); Optics layering (https://optics-framework.org/docs/elements/text-and-images) | M |
| 5 | **S20 rig: refocus + scripted capture; keep camera as evidence, not assertion** | Owner 5-min: refocus the fixed mount (photos said "structure, not glyphs"); script `adb shell screencap`/keyevent capture into the evidence flow with timestamps; optionally add a cheap USB webcam on the LCD exported as **USBVideo** → native `USBVideoDriver.get_screenshot()` for a labgrid-native camera loop. FB dumps remain the assertion source; S20 photos remain milestone/state evidence (the layered ladder). | labgrid USBVideo (https://zread.ai/labgrid-project/labgrid/13-usb-and-storage-drivers); Dvergr/Squish layering (§1.2) | S |
| 6 | **Bind console daemon to the labgrid lease** | Daemon checks `labgrid-client -p f469-specter-film who` before accepting each FIFO command (or holds its own acquire); add request-id/ack JSON-lines framing to the FIFO so replies are attributable. Turns single-owner *convention* into *mechanism* — the labgrid acquire/release model becomes load-bearing. | agentic-hil leases + audit chain (https://github.com/agentic-hil/agentic-hil/); labgrid place model (https://labgrid.readthedocs.io/en/stable/usage.html) | S–M |
| 7 | **Watcher + auto-recovery as systemd units** | Convert f469-console-watcher from tmux to a systemd unit (pattern already in conwrt-bench/deploy/: bench-liveness.service, labgrid-lock-janitor.timer). On HB-loss or PARTNO 0x0: run stlink-usbreset, then (post-#1) power-cycle once, re-arm. Bounded retries, alert on exhaustion — every wait bounded. | engineermaxxing bounded waits (https://www.engineermaxxing.com/micro/lessons/fw-core-10-testing-firmware.html); conwrt-bench deploy/ precedents | S |
| 8 | **Evidence auto-filing out of /tmp** | Each run: `evidence/<date>/<firmware-sha>/` with console log slice, FB PNGs, TEST_* JSON, S20 photo; auto-commit or rsync to the repo/persistent store at cycle end. The host's own docs call /tmp sweep-fragile; recovery artifacts are irreplaceable (AGENTS.md lab rule). | Renode failed-test snapshots; ubxlib archiveArtifacts-in-finally | S |

### P2 — coverage expansion

| # | Improvement | What / how | Why (practice refs) | Effort |
|---|---|---|---|---|
| 9 | **Fault-injection campaign module** | Parameterized pytest-tagged shots on our own board/card only: card-VCC kill at delay *d* after op start, RST wiggle, mid-transaction cut (fault-as-hook with call-count/delay trigger); each shot followed by TEST_STATUS + HB-integrity assert + FB screen-assert = the M2 retry-guard regression, executable nightly. | engineermaxxing fault-as-hook taxonomy; our B5 precedent; Renode inject-API shape (https://github.com/renode/renode/issues/875) | M |
| 10 | **Exporter SSOT cleanup + config validation** | Resolve the m5stick-usb / nucula-c3 config-orphan warning (owning lanes SSOT or bless the drop), add a validate step (schema check à la labgrid-plugins validate.py) to the deploy path so restarts become safe and boring. | labgrid-plugins exporter setup/deployment guides (https://tfcollins.github.io/labgrid-plugins/user-guide/exporter-setup.html) | S |
| 11 | **Default to incremental nix builds** | Ledger already proved 1–3-min incremental `make debug` inside nix; make full-clean a release-gate/nightly action, not the debug-loop reflex; cache objcopy'd .bin per git SHA next to evidence. Cuts the flash-test iteration tax ~5–10×. | local evidence (ledger 2026-11-04 "dev loop proven"); Synapsio fast-observation loop rationale | S |
| 12 | **Verification ladder + blame helper (host-side)** | Small host util that, on a failed leg, walks the ladder console→(HB? ALIVE? TEST reply?)→card (status flags)→reader and names the failing layer in one line — codifying what the 11-14 arc did manually across two days of misdiagnosis. | LoopHIL verification ladder + blame device (https://arxiv.org/abs/2610.24231) | M |

**Sequencing suggestion:** 1→2→3 unblock everything else (power + reliable captures + harness-judged tests); 4–5 make UI evidence assertable; 6–8 harden daily ops; 9–12 expand coverage. Items 2, 4, 6, 8–12 are pure software, reversible in a single commit each; item 1 needs one owner-hands install then pays back forever; item 3 executes an already-ruled relocation (#119).
