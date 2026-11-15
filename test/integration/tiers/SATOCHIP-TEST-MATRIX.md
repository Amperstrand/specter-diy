# Multi-version Satochip test matrix — design (2026-11-15)

Goal: extensive e2e + unit coverage for ALL Satochip applet versions, real
and emulated, per javacard-ecosystem best practice. Trigger: today's
channel-KDF regression (mock-validated client met the real v0.14 card and
failed — the class of gap this matrix makes structurally impossible).

## The principle: execute the applet, don't mock it

Mocks encode assumptions; simulators execute the real applet bytecode.
The matrix runs the CLIENT against REAL APPLET LOGIC at every layer where
hardware isn't strictly required.

## Layers

| Layer | Applet under test | Client under test | Speed | Tooling |
|---|---|---|---|---|
| L0 unit | none (wire shapes) | client per-version paths | ms | pytest + recorded transcripts (`--record` fixtures) |
| L1 emulated | applet SOURCE built per tag in **jCardSim** (bench fork @ its commits; Toporin/SatochipApplet @ v0.14/v0.15/v0.16 tags) | full client | s | specter-javacard/tests: simulator.py + simulator.jar (EXISTS on this host) |
| L2 pcscd-integrated | L1 sim served over **vpcd** → pcscd reader | full client via pcscd (identical code path to real reader!) | s | the bench's proven vpcd infra + tiers `cardman` backend pointed at vpcd readers |
| L3 real cards | one J3R180 per version (a "version farm": current v0.14-personalized card + cards re-personalized per release via the pysaudit GP tooling) | full client | s-min | CardMan seat; version probe asserts identity before each run |
| L4 device | whatever card is seated | firmware client (the F469) | min | the campaign harness (version-independent integration) |

## Key mechanics

1. **Version-parameterized client**: GET_STATUS probe → channel/INS gating
   (dual-channel: v0.14-family vs SeedKeeper-style; INS sets per version).
   ONE client, all versions — no forks.
2. **jCardSim builds per tag**: the applet source builds in the simulator
   at any commit — `pytest --applet-version=v0.14|v0.15|v0.16` becomes a
   build+load of that tag's source into the sim. The sim jars live in
   specter-javacard/tests (extend to per-tag builds).
3. **pcscd identity**: L2's vpcd readers are indistinguishable from the
   CardMan at the client API level — the SAME cardman-backend tests run
   against emulated and real cards by reader-name parameter only.
4. **Transcript pinning**: every L3 run records (`--record`); transcripts
   feed L0 — real-card wire behavior becomes regression fixtures, with
   firmware/card sha provenance.
5. **Version farm provisioning**: the pysaudit personalization tooling
   (GP install + setup) scripted per release; each farm card labeled +
   registered in the labgrid SSOT as its own place. Re-provisioning a
   card to a new version = an explicit, logged operation.
6. **Regression rule**: any client change runs L0+L1 for ALL versions in
   CI (fast, no hardware); L3 nightly or on-card-touching PRs.

## What today's incident becomes under this matrix

The channel-KDF regression: L2/L3 against v0.14 would have failed the
DRY-refactor PR the day it landed — at sim speed, in CI, before any
hardware session. That is the standard this matrix holds.
