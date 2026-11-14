# F469 bench operations — distilled from the 2026-11-13/14 debug arc

For any future session driving the specter-diy bench board. The full narrative
lives in the lane ledger (`project-context/.audit-lanes/javacard-revive-2026-11-02.md`,
2026-11-14 entries); this file is the operator's quick reference.

## The board, the console, the rules

- **Board**: STM32F469 (specter-diy variant), ST-Link USB to ai-legion-small.
  One cable carries SWD + the VCP console (`if02`).
- **Console daemon** (single-owner discipline — NEVER open the port twice,
  reader races steal bytes): tmux session `f469-console`, script
  `conwrt-bench/tools/f469-console-daemon.py`. Read: `/tmp/opencode/f469-console.log`.
  Write commands: `printf 'TEST_STATUS\n' > /tmp/opencode/f469-console.in`.
- **ST-Link adapter wedge** (PARTNO 0x0 on attach): recover with
  `conwrt-bench/tools/stlink-usbreset /dev/bus/usb/003/002` — no replug needed.
- **Flashing**: SWD via openocd (adapter serial 066FFF505567494867224125).
  Firmware builds MUST use nix (`nix --extra-experimental-features
  'nix-command flakes' develop --command make debug`), full-clean first,
  ~15 min/build. objcopy the ELF to .bin, `program ... verify` + `reset run`.

## The two channels that lie to you

1. `_dbg()` in main.py writes DIRECTLY to UART3 (visible on the console).
   Plain `print()`/tracebacks go to the target's own USB CDC — NOT bridged,
   INVISIBLE. Any error you need to see must be routed to UART3.
2. `pyb.UART(3)` = USART3 = PB10/PB11 = the ST-Link bridge. The smartcard
   reader uses USART2 (PA2/PA4) + RST PG10 + presence PC2 + power PC5
   (active-low).

## Firmware gotchas (all fixed in v2.2.13 on branch v2212-t1pin)

- The vendored f469-disco asyncio has NO `asyncio.Lock` — the compat shim in
  `test_mode.py` must survive "cleanups" (it killed TestMode silently for
  v2.2.6c–v2.2.9).
- The f469-disco pin MUST be the T=1-patched `fe68368` (m1-gate-board).
  The upstream pin (9dd8515) = no ATR + broken presence read = "dead card"
  illusion. Six scard commits depend on it (see v2.2.12 commit).
- `machine.mem16` is subscriptable (`mem16[addr]`), not callable.
- select_keystore's retry guard + memorycard's chip-probe bypass are bench
  hardening — keep them.

## Driving the app

TestMode protocol over the console: TEST_STATUS, TEST_BOOT_STATE, TEST_SCREEN,
TEST_PIN:<pin> (device PIN flow: choose screen accepts it, then Menu),
TEST_WALLET_SMOKE (first-boot: "Keystore not ready" = expected boundary),
TEST_FB_DUMP (header OK:FB:W:H:CHUNKS, then fb events), TEST_REBOOT.
Heartbeat `[TestMode] HB` every ~10 s = healthy loop.
Boot evidence: `[TestMode] ALIVE T5` right after task creation.

## Card facts

J3R180 #2 (CPLC 50942720) in the F469 slot; card PIN 1234 (TEST_PIN answers
6984 at the applet level — benign, unlock still succeeds). CardMan 3121 on
pcscd = cardbench's seat (coordinate). J3H145 = locked, never auth it.
SWD card cold-reset: PC5 BSRR toggle (0x20 off / 0x200000 on, ~2 s apart).
