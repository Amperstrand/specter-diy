# MemoryCard keystore on J3R180 — M1 integration

Branch purpose (owner milestone M1, branch 2 of 2): the Specter-DIY firmware
uses the **MemoryCard JavaCard applet** as its keystore. This branch carries
the slim client stack for exactly that applet — SeedKeeper and Satochip
clients return on the M2 branches (`m2-seedkeeper`, `m2-satochip`), and the
in-firmware GP/CAP installer lives on its own `feature/cap-installer` line.

Verified against hardware: **J3R180 (NXP JCOP4 SECID)**, 2026-03-20 —
38/38 card tests, benchmarks in the specter-javacard repo
(`artifacts/benchmarks/20260320T163848Z-card.json`). Full operations guide
for the card side: [specter-javacard `docs/J3R180.md`](https://github.com/Amperstrand/specter-javacard/blob/master/docs/J3R180.md).

## What is on the card

The MemoryCard applet (package AID `B00B5111CB`, applet AID `B00B5111CB01`)
from [Amperstrand/specter-javacard](https://github.com/Amperstrand/specter-javacard)
— a PIN-protected blob store built on SecureApplet's secure channel
(ECDH secp256k1 + AES-CBC + HMAC). CAP files: CI artifacts from that repo
(reproducible builds), or build locally with `LANG=C.UTF-8 nix develop --command ant all`.

## Client stack on this branch

```
src/keystore/memorycard.py            MemoryCard keystore (PIN -> secret in MCU RAM, ColdCard-style)
src/keystore/javacard_keystore.py     JavaCardKeyStore base (connection, PIN, unlock flow)
src/keystore/javacard/util.py         reader/connection helpers (uscard), pubkey utils
src/keystore/javacard/applets/
    applet.py                         APDU base: select/request, ISOException
    secureapplet.py                   SecureApplet protocol client
    securechannel.py                  secure channel crypto (host side)
    memorycard.py                     GET_SECRET / SET_SECRET commands
```

Everything else from the fork's javacard directory is deliberately absent
here (M2 / feature lines).

## Owner session — card provision + wallet e2e (≤15 min)

Prereqs: J3R180 with known keys (see specter-javacard `AGENTS.md` card table),
Gemalto PC Twin Reader, `pcscd`, `gp.jar`.

1. Install the applet (delete the package first on reinstall — JCOP4 rejects
   duplicate package AIDs):

   ```sh
   java -jar gp.jar --key-enc <ENC> --key-mac <MAC> --key-dek <DEK> --key-ver <V> \
       --delete B00B5111CB --force
   java -jar gp.jar --key-enc <ENC> --key-mac <MAC> --key-dek <DEK> --key-ver <V> \
       --install MemoryCardApplet.cap
   java -jar gp.jar --key ... -l          # expect: SELECTABLE
   ```

2. Flash this branch's firmware onto the F469 (`make all`, then owner
   flashing flow from `HARDWARE-RUNBOOK.md` — note the F469 exclusivity rule:
   the board must not be running ccid-firmware-rs duties at the time).

3. Boot with the card seated: the device prompts for the card PIN; first
   secure-channel command of the session carries the applet's deferred
   crypto init (one-time cost, see specter-javacard `docs/J3R180.md`).

4. M1 gate check: create/load a wallet — mnemonic stored on the card,
   sign a PSBT end-to-end.

## Verification on this branch (executed 2026-11-03, clean re-stack on upstream-mirror master)

- `make test` — unix build + frozen-import-smoke + simulator suite: 19/19 OK
- `python3 test/run_native_tests.py` — upstream native runner: 80/80 OK
- `python3 -m pytest test/tests/test_javacard_util.py test/tests_native/` — module tests green
- Card-facing behavior: hardware evidence inherited from the 2026-03-20
  J3R180 session (applet protocol unchanged; applet files are byte-identical
  to upstream's); re-verification is part of the M1 gate session above.
