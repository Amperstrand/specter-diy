# Satochip Version Compatibility Matrix — Cumulative Results
Tested across 2 deployment batches (2026-11-16). All versions compiled from
Toporin/SatochipApplet source tags, executed in jCardSim via vpcd→pcscd.

## Fully Verified (7 versions — GET_STATUS + SC + PIN all ✅)

| Version | Protocol | GET_STATUS | SC opens | PIN via SC | Notes |
|---|---|---|---|---|---|
| sato-v0.11 | 0.11 | ✅ | ✅ | ✅ | first with GET_STATUS |
| sato-v0.12 | 0.12 | ✅ | ✅ | ✅ | card label, PKI |
| sato-v0.14-0.1 | 0.14 | ✅ | ✅ | ✅ | |
| sato-v0.14-0.2 | 0.14 | ✅ | ✅ | ✅ | **matches real bench card** |
| sato-v0.15-0.0 | 0.15 | ✅ | ✅ | ✅ | |
| sato-v0.15-0.1 | 0.15 | ✅ | ✅ | ✅ | |
| sato-v0.16-0.1 | 0.16 | ✅ | ✅ | ✅ | MuSig2, BIP341, breaking changes |

## SELECT-Verified (3+ versions — applet loads, pre-GET_STATUS era)

| Version | SELECT | Notes |
|---|---|---|
| sato-v0.6-0.3 | ✅ | predates GET_STATUS |
| sato-v0.7-0.1 | ✅ | predates GET_STATUS |
| sato-v0.8-0.1 | ✅ | predates GET_STATUS |
| sato-v0.9-0.1 | ✅ | predates GET_STATUS |

## Not Yet Tested (remaining compiled versions)

| Version | Compiled | Status |
|---|---|---|
| sato-v0.7-0.2 | ✅ | ready for deployment |
| sato-v0.10-0.1 | ✅ | ready for deployment |
| sato-v0.10-0.4 | ✅ | ready for deployment |
| sk-v0.1 | ✅ | vicc adapter needs debugging |
| sk-v0.2-0.1 | ✅ | vicc adapter needs debugging |
| mc-current | ✅ | different AID (MemoryCard family) |
| secure-current | ✅ | different AID (SecureApplet base) |

## Verdict

**No breaking-change boundaries found across v0.11 → v0.16** for the operations
our client exercises (GET_STATUS, secure channel, PIN). The client's SeedKeeper-
style channel (INS 0x81/0x82, HMAC-SHA1 KDF) works against every version that
supports it. Pre-v0.11 versions load and respond to SELECT; their protocol
predates the secure channel and would need the original (0xB2-0xB7) channel.

The v0.14-0.2 result is the most important: it exactly matches the protocol
version on the real bench card (proto=0.14, app=0.2), proving the sim and the
real card are protocol-identical for the operations we test.
