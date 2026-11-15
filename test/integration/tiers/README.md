# Tiered test harness — fast-by-default, escalate-to-hardware by parameter

One test suite, four execution tiers. `pytest --backend=TIER` (or
`TIER_BACKEND=TIER`) escalates the SAME test from milliseconds to real
hardware. Hardware tiers run inside a labgrid lease (place acquire/release
= the exclusivity mutex; acquisition failure fails closed — the run never
falls back to reading a stale console log).

## Tiers

| --backend= | transport | speed | verifies |
|---|---|---|---|
| `dry` | canned reply shapes inline in conftest (MOCK — no APDU logic yet) | ms | test/parse code + the verifier control (see below) |
| `sim` | micropython_unix (`make test` path) | s | app logic on the unix port |
| `cardman` | host pcscd → CardMan 3121 → J3R180 | s | real applet ↔ real client protocol (pending cardbench bless; skips cleanly) |
| `device` | console daemon FIFO → TestMode on the F469 | ~2-5s/op | full firmware integration + real card + real GUI stack |

## Layout (all in this directory — single conftest, no submodules)

- `conftest.py` — everything: the `backend` fixture (session-scoped Bench
  object: `status()`, `pin(pin)`, `sign(message, path)`,
  `authentikey_for(path)`, `pin_status()`), the four Bench classes
  (Dry/Sim/CardMan/Device), the labgrid lease, and the needs-marker skip
  logic.
- `test_tiers.py` — cross-tier assertions (status, PIN flow, sign shape).
- `test_sign_battery.py` — signing endurance battery.

## Device-tier transport contract (2026-11-15 hardening)

- The daemon log is `<ISO-ts> b'…repr…'` per line; TestMode emits
  `J:{"reply": …, "ok": …, "cmd": …, "event": "result"}` JSON events.
  `console_reply()` unescapes the repr layer, JSON-parses the event, and
  correlates by a timestamp taken BEFORE the send — bounded poll, no
  fixed sleeps, no stale-run matches.
- The tier never opens the serial port directly — only the daemon FIFO
  (single-owner rule). A FIFO that refuses writes = hard fail, not hope.
- The lease is judged by `labgrid-client`'s EXIT CODE only (its
  held-place failure message contains the word "acquired" too — substring
  matching once produced a false lease signal).

## Capability vocabulary (needs markers)

- `needs("a", "b")` — ALL capabilities required; missing any → clean skip.
- `needs_any("card-real", "card-mock")` — ANY one suffices → clean skip
  only when the backend provides none.
- `logic` — any tier.
- `card` — a card-shaped signing path (any kind).
- `card-mock` — mock/recorded card replies (dry). The sign battery there
  is the **verifier control** — host keys sign and verify tautologically,
  proving the assertion machinery.
- `card-real` — a physical card (device today; cardman when blessed).
- `firmware`, `gui`, `screen` — on-device only.

## Rules

- A test declares `@pytest.mark.needs("card")` etc.; tiers missing the
  capability skip cleanly — escalation never silently degrades.
- Every Bench implements the full interface; unimplemented operations
  raise (NotImplementedError / pytest.skip), so tier gaps fail loudly at
  construction, never mid-test as AttributeError.
- Status dicts share one key set (`connected, keystore_found, unlocked,
  card_inserted, fingerprint`).

## Planned (not built yet — do not assume)

- Transcript record/replay: record device/cardman exchanges tagged with
  firmware sha + card CPLC; `--record` regenerates; dry replays them
  (today's dry tier is canned shapes, NOT recorded transcripts).
- Request-id framing on the FIFO (conwrt-bench #172 daemon v2) — removes
  the timestamp-correlation heuristic.
- CI ladder (dry+sim per PR; device nightly on a self-hosted runner).
- Review with full details: `evidence/2026-11-15/tiers-review.md`.
