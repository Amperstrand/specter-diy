# Tiered test harness — fast-by-default, escalate-to-hardware by parameter

One test suite, four execution tiers. `pytest --backend=TIER` escalates the
SAME test from milliseconds to real hardware. Hardware tiers run inside a
labgrid lease (place acquire/release = the exclusivity mutex).

## Tiers

| --backend= | transport | speed | verifies |
|---|---|---|---|
| `dry` | recorded APDU transcripts (MockConnection) | ms | client protocol logic, APDU shapes, reply parsing |
| `sim` | micropython_unix (`make test` path) | s | app logic on the unix port |
| `cardman` | host pcscd → CardMan 3121 → J3R180 | s | real applet ↔ real client protocol (pending cardbench bless) |
| `device` | console daemon FIFO → TestMode on the F469 | ~15s/op | full firmware integration + real card + real GUI stack |

## Layout (specter-diy/test/integration/tiers/)

- `conftest.py` — the `backend` fixture: builds a `Bench` object with
  `status()`, `pin(pin)`, `sign(message, path)`, `screen()`, plus
  `pytest.skip` for tiers a test declares out-of-scope.
- `bench_dry.py` — transcript MockConnection (the pysaudit APDU survey data
  as recorded fixtures; deterministic, zero hardware).
- `bench_sim.py` — unix-port invocation.
- `bench_cardman.py` — pcscd CardMan (raises Skipped until the bless lands).
- `bench_device.py` — FIFO writes + console-log reply capture (the daemon
  owns the port; this tier ACQUIRES the labgrid place for the run's duration).
- `labgrid_lease.py` — acquire/release wrapper (f469-specter-film for device;
  the CardMan seat place when blessed).

## Rules

- A test declares `needs = {"card"}` / `{"screen"}` / `{"gui"}`; the fixture
  skips tiers that cannot provide — escalation never silently degrades.
- Dry transcripts are recorded ONCE from the device/cardman tiers and
  committed; regenerating is an explicit `--record` run on hardware.
- The device tier never opens the serial port directly — only the daemon
  FIFO (single-owner rule).
- Every tier produces the same result dict shape; reports compare tiers.
