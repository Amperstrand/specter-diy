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

## Framebuffer capture (working recipe, 2026-11-14)

TEST_FB_DUMP (v2.2.14+) reads the LIVE buffer from LTDC L1CFBAR (0xC0000000
on this board) as ARGB8888 via mem32. **The memory layout is 480x800
PORTRAIT** (L1CFBLR: line length 1920 = 480px*4, L1CFBLNR: 800 lines) —
assemble 480-wide then rotate -90 for the on-screen landscape view. Pixels
may print signed ('%08x' of negatives) — parse 8-char tokens, mask
&0xFFFFFFFF. Events split across console-log lines (1024-byte reads) —
reconstruct the byte stream before parsing. Assembler:
evidence/2026-11-14/fb-assemble.py. Stray chunk losses happen if other
commands race the dump — send NOTHING else during a dump.

## The asyncio resolution — FULLY RESOLVED (2026-11-15)

The vendored libs/common/asyncio (v3.0.0) exports Lock/Event via a lazy
module `__getattr__` — a VM feature the vendored micropython (v1.10-era)
lacks. So `asyncio.Lock` raised AttributeError on BOTH sim and device
while `asyncio.lock.Lock` always worked: an internal version-skew bug in
the f469-diso tree (async lib bumped, micropython not). Sim and device
resolve asyncio IDENTICALLY — the tiers were always aligned; the Lock bug
wasn't sim/hardware skew, it was an untested API on both.
Fix (proven in the specter-diy-sim worktree): replace the lazy loader with
an eager import loop — old-VM-safe, zero regressions (33+19 green).
The TestMode Lock shim (v2.2.10) stays as belt-and-suspenders.

## The USB autosuspend trap (root-caused 2026-11-15)

**The single biggest source of false recoveries.** Linux USB autosuspend
(`power/control=auto, power/autosuspend=2` on the ST-Link V2.1) suspends the
USB device after 2s of serial idle. When the console daemon's select() reports
the fd ready, the USB device is still waking up — read() returns 0 bytes,
pyserial raises "device reports readiness but returned no data", and error
clusters break the campaign's silence threshold, firing the recovery ladder.

**Fix** (installed, survives reboot):
- udev rule: `/etc/udev/rules.d/99-stlink-no-suspend.rules` matching
  `idVendor=0483, idProduct=374b` → `power/control=on, power/autosuspend=3600`
- Any USB-serial bench device with the same symptom: check
  `cat /sys/bus/usb/devices/<bus-pref>/power/control` — "auto" + short
  autosuspend = this trap. Set to "on" + long timeout.

**How to diagnose** (took us 868 errors and 18 recoveries to nail):
1. Count errors: `grep -c "err: device" <console-log>` — if constant regardless
   of hardware activity, it's not your device, it's the OS.
2. Correlate with injections: if <10% of errors are near fault-injection events,
   the cause is environmental, not test-induced.
3. Check power state: `cat /sys/bus/usb/devices/<dev>/power/{control,autosuspend}`
4. Fix the RIGHT device (lsusb to confirm bus position — ours was 3-1, not 3-2).

**Impact on campaign data**: 92% of port errors were this. After the fix: zero
errors in sustained monitoring. The recovery ladder stays as insurance for real
wedges only (vcc injection failures, firmware crashes). The WDT handles hangs.
