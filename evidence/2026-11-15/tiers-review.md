# Tiered harness review — specter-diy/test/integration/tiers/

Date: 2026-11-15 · Reviewer context: `evidence/2026-11-14/hil-workflow-review.md`
(best-practice survey: agentic-hil, LoopHIL, labgrid/pytest, Squish/Dvergr,
Renode, ubxlib — sources cited there). Read: `tiers/README.md`, `conftest.py`,
`test_tiers.py`, `test_sign_battery.py` @ branch v2212-t1pin (commits ca11b7a,
c39156f). Live probe: place `f469-specter-film` found FREE this morning;
acquire→release round-trip verified (`acquired place …`, rc=0).

---

## 1. Verdict — is the tier abstraction sound?

**Yes, with two semantic fixes.** One-suite/escalate-by-parameter is exactly
the researched ladder (host/fakes → sim → real-silicon) compressed into
pytest, and it inherits the right disciplines:

| Harness property | Practice it matches |
|---|---|
| same assertions at every tier | LoopHIL verification ladder — the harness, not the agent, judges |
| `needs` markers + clean skips | labgrid `lg_feature` / clean-skip discipline |
| session-scoped labgrid lease, release in `finally` | agentic-hil leases; ubxlib lock+cleanup hygiene |
| device tier speaks only via daemon FIFO | the single-owner rule (2026-11-14 lesson) — enforced by construction |
| dry-first default | "fast-by-default" — correct CI economics |
| sign battery as verify-the-verifier control | genuinely good: a control group that proves the assertion code works before real cards enter |

The two semantic problems (§3.3, §3.4): the dry tier is credited with
capabilities it doesn't exercise, and "transcript replay" is claimed but
doesn't exist. Both are fixable without touching the architecture.

## 2. What's already right (keep)

- The `Bench` uniform-interface + `provides` set + autouse `_needs` skip —
  minimal, correct, ~10 lines; better than a plugin framework at this size.
- `--backend` as a pytest option (not env-only) — CI-friendly matrixing.
- Escalation never silently degrades (skip, don't downgrade asserts).
- Lease lifecycle in the fixture, not the tests.

## 3. Correctness bugs (priority order)

### 3.1 CRITICAL — `_lease()` false-positive on a foreign hold
`"acquired" in out or "already" in out.lower()` — labgrid's FAILURE message
for a held place is of the form *"Place … is already acquired by …"*, which
contains both `acquired` and `already`. A place held by **another lane**
parses as leased → the run then greps the console log while that lane drives
the DUT → cross-lane interference, the exact failure the lease exists to
prevent. (High-confidence from labgrid's message format; the bench's own
lock-janitor issues #50/#52 exist because of this message class. Not
reproduced live today — place was free.) **Fix:** check the subprocess exit
code, not substring optimism; fail fast (`pytest.fail`) when the lease isn't
held — never run device-tier assertions unlocked.

### 3.2 CRITICAL — device tier can PASS on stale data
Three compounding silent failures: `console_send` swallows OSError (FIFO
absent → command never sent), `console_reply` is `time.sleep(16)` + grep of
an append-only log (matches a STALE reply from a previous run), and nothing
correlates request→reply. Result: a device run with a dead daemon reads
yesterday's `OK` lines and reports green. **Fixes:** (a) FIFO write failure
= hard fail; (b) daemon-v2 request-id/ack framing (conwrt-bench #172
sub-task 2 — this harness is the strongest argument for it); until then,
parse the daemon's ISO timestamp on the matched line and require it within
the command's window; (c) replace fixed sleeps with poll-until-pattern with
a bound (the every-wait-needs-a-bound rule) — also cuts ~15s/op to ~2-5s.

### 3.3 README/code drift at birth
README lists `bench_dry.py`, `bench_sim.py`, `bench_cardman.py`,
`bench_device.py`, `labgrid_lease.py` — **none exist**; everything is inline
in conftest.py. README promises `--record` (transcript regeneration) and
"reports compare tiers" — neither exists. DryBench is two hardcoded strings,
not the promised "recorded APDU transcripts … committed fixtures". Per your
own canon (docs remember, tests prevent drift): either build the files or
fix the README to describe what IS. A future session trusting the README
will flounder.

### 3.4 Capability semantics — dry `provides {"card"}` overclaims
`test_sign_battery` is `needs("card")` and green at dry — but the dry path
signs with **host embit keys and verifies with the same key object**: a
tautological control, zero APDU logic exercised. Valuable as a verifier
self-test; mislabeled as card coverage. The README table's dry row
("client protocol logic, APDU shapes, reply parsing") is not what DryBench
does today. **Fix:** split capabilities `card-mock` vs `card-real`; rename
the dry battery test `…_verifier_control`; keep `needs("card")` meaning
real-or-recorded-card only once transcripts exist.

### 3.5 Designed-but-dead CardMan API
`test_sign_battery`'s else-branch calls `backend.authentikey_for(path)` —
no Bench class defines it; `CardManBench.__init__` raises skip; so the
branch is unreachable today and will `AttributeError` the day cardman is
blessed. Define the method on the Bench interface (raise
NotImplementedError) so mismatches fail loudly at construction, not mid-test.

### 3.6 Smaller
- `.replace(chr(92), "")` strips ALL backslashes from replies — mangles any
  payload containing hex/escapes; unescape reprs properly (see
  conwrt-bench `tools/fb_capture.py::reconstruct_stream` for the pattern).
- `TIER_BACKEND` env is read into BACKEND and never used (option only).
- `sys.path.insert` into `f469-disco/libs/common` for embit — cross-repo
  absolute-path coupling; use the repo's own embit/submodule or a proper dep.
- `sh()` = shell=True f-strings; fine with constants today, but use argv
  lists before any user input reaches it.
- `test_sign_returns_der`: the `hasattr(request.config,…)` guard is dead
  code; `--sign-count` always exists.

## 4. What's missing to scale

### 4.1 Record/replay (the README's unkept promise)
Design it properly once: record at cardman/device = capture (command →
APDU/JSON exchange, outcome) tagged with **firmware sha + card CPLC + date**;
dry replays by keying inputs; on metadata mismatch → skip with the drift
named, never replay stale transcripts against changed firmware. Precedents:
Renode RESD/record-replay (time-controlled, deterministic), the framed
PNG_BEGIN/END capture pattern. The transcripts then become golden fixtures
— diffable, reviewable artifacts.

### 4.2 Request-id transport (blocks real device-tier speed/reliability)
Depends on conwrt-bench #172 daemon v2. Until then §3.2's timestamp-bound
grep is the stopgap. The end state: `bench_device.py` writes
`{"id": N, "cmd": …}` to the FIFO, reads the reply stream by id —
event-driven, no sleeps, no grep.

### 4.3 CI wiring (nothing exists yet)
Ladder the tiers (the economics are the point): dry+sim on every PR
(ubuntu runner, no hardware); device on a **self-hosted runner on
ai-legion-small**, nightly + label-triggered (`hil` label), with:
timeout-bounded stages, retry(3) only on flash/transport (never on
assertions), junit XML per tier, artifacts = evidence dirs. The bench-side
plumbing already exists in conwrt-bench: `evidence-file.py` (manifested
artifacts), `fb_capture.py`/`screen_assert.py` (screen evidence + verdicts),
`s20-shot.sh` (camera evidence), `f469-blame.sh` (attach the failing layer
on device-tier red — the LoopHIL blame-device pattern, zero new code).
Wire the device tier to END each run by filing `evidence/<date>/<fw-sha>/`.

### 4.4 Multi-DUT
Hardcoded `DEVICE_PLACE`/`COORDINATOR` is fine for one seat; the scale
path is already in labgrid: put capability metadata in **place tags**
(`labgrid-client set-tags card=real screen=fb …`) and make `needs` check
the acquired place's tags instead of hardcoded `provides` sets. Then
`--place` parametrization gives N seats for free, and tier-vs-seat
matrices are declarative. (This also retires the per-class `provides`
duplication — the tag source becomes single.)

### 4.5 State & fixtures discipline
The device tier leaks state across tests (PIN unlocked persists; card
personalization persists across RUNS — the ledger's stale-session lessons).
Needs: a session-scoped bench-state fixture asserting documented
preconditions (boot state, card setup) before/after; card-state probes
(`is_setup`) rather than assumptions; explicit test-ordering policy or
per-test state reset where cheap. The cardman tier additionally needs the
connection-lifecycle discipline (single session, explicit free — the
connection-cap lesson from the M1 probe loops).

### 4.6 Flakiness policy
No retry markers, no known-flaky quarantine, fixed sleeps (the flake
generator). Adopt: bounded poll helper; `@pytest.mark.flaky` quarantine
list per tier; never_retry-on-assert semantics (retry transport only).

### 4.7 Result contract
"Same result dict shape" is claimed, not enforced: DryBench lacks
`fingerprint`, SimBench returns Nones. Define one TypedDict/dataclass
`BenchStatus`, validate at the fixture boundary (parse-don't-validate),
and the promised tier-comparison report falls out for free.

## 5. Prioritized fixes

| # | Item | Effort | Depends on |
|---|---|---|---|
| 1 | Lease exit-code check + fail-closed (§3.1) | S | — |
| 2 | Stale-reply guards: FIFO fail-fast, timestamp-bound grep, bounded poll (§3.2) | S–M | — (stopgap until 6) |
| 3 | README truth pass + split files as listed (or README fixed) (§3.3) | S | — |
| 4 | Capability split `card-mock`/`card-real` + rename dry battery control (§3.4) | S | — |
| 5 | `BenchStatus` contract + authentikey_for on the interface (§3.5, §4.7) | S | — |
| 6 | Daemon v2 request-ids (conwrt-bench #172.2) → event-driven device tier | M | #172 |
| 7 | Record/replay with fw-sha-bound transcripts + `--record` (§4.1) | M | 6 (device), none (cardman) |
| 8 | CI ladder: dry+sim PR / device nightly self-hosted + evidence filing + blame attach (§4.3) | M | 1,2 |
| 9 | Place-tags capability source + `--place` (§4.4) | M | — |
| 10 | Bench-state fixtures + cardman lifecycle (§4.5) + flakiness policy (§4.6) | M | 7 |

Sequencing: 1+2 immediately (correctness), 3–5 in the same hour (truth in
docs/semantics), 6 rides #172, 7–10 are the scale-out. Item 1 is the only
one that can currently produce a WRONG GREEN on shared-bench hardware —
treat it as the blocker for any CI wiring (8) landing.
