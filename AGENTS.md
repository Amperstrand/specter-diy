# AGENTS.md

## Project Overview

Specter-DIY is a DIY hardware Bitcoin wallet based on STM32. This repository contains firmware, bootloader, host software, and tools.

## Java Card Management

### Command Line Tool: `tools/jc_manager.py`

A Python CLI tool for managing Java Card applets on a Gemalto (or compatible) smart card reader using `gp.jar`. Supports both **interactive** (menu-driven) and **non-interactive** (CLI flags) modes.

#### Usage

```bash
# Interactive mode (menu-driven)
python3 tools/jc_manager.py

# Non-interactive / CLI mode
python3 tools/jc_manager.py --detect                    # Detect card with default keys
python3 tools/jc_manager.py --detect-factory             # Detect card with factory keys
python3 tools/jc_manager.py --detect --list              # Detect then list
python3 tools/jc_manager.py --list                      # List apps (after --detect in same run)
python3 tools/jc_manager.py --delete 5361746F4368697000  # Delete by AID
python3 tools/jc_manager.py --install applet.cap         # Install CAP file
python3 tools/jc_manager.py --install applet.cap --applet-aid 5361746F4368697001
python3 tools/jc_manager.py --load applet.cap            # Load CAP file only
python3 tools/jc_manager.py --info                      # Show CPLC card info
python3 tools/jc_manager.py --apdu 00A4040000           # Send plaintext APDU
python3 tools/jc_manager.py --secure-apdu 00A4040000     # Send secure APDU
python3 tools/jc_manager.py --detect-factory --set-default-keys  # Detect + set default keys
python3 tools/jc_manager.py --unlock                    # Unlock card to default keys

# Use custom or factory keys for the session
python3 tools/jc_manager.py --factory --list
python3 tools/jc_manager.py --key <32-hex-chars> --list
```

Run `python3 tools/jc_manager.py --help` for full CLI reference.

#### Prerequisites

- Java 8+ (required by gp.jar)
- A PC/SC smart card reader with a Java Card inserted
- **GlobalPlatformPro v25.10.20 or newer** at the path in `GP_JAR_PATHS` in the script (currently `/home/ubuntu/src/record/specter-flash/gp.jar`)

#### IMPORTANT: gp.jar Version

**Only use GlobalPlatformPro v25.10.20 or newer.** The old v20.01.23 (found in nix store at `/nix/store/kdqfij55hhz5sdsawdv5hh6cwyxsiqzl-source/gp.jar`) has critical bugs:

- The `--key` flag **hangs indefinitely** — never use it
- Takes ~20s per command (timeout-prone)
- May produce cryptogram mismatch errors that increment the card's SCP02 error counter, **permanently blocking the key**

**Do NOT use the nix store gp.jar.** The correct version lives at `/home/ubuntu/src/record/specter-flash/gp.jar`.

Download newer versions from: https://github.com/martinpaljak/GlobalPlatformPro/releases

#### Card: NXP JCOP4 (J3H145)

| Property | Value |
|---|---|
| Card | NXP JCOP4 (J3H145) |
| ATR | `3B D5 18 FF 81 91 FE 1F C3 80 73 C8 21 10 0A` |
| Protocol | T=1, SCP02 |
| Key Version | 1 (0x01) |
| Reader | Gemalto PC Twin Reader (08e6:3437) |

#### Interactive Menu Options

| Menu Option | Action |
|---|---|
| 1 | Detect card (default GP keys 404142...4F) |
| 2 | Detect card (Gemalto factory keys) — prompts before attempt |
| 3 | List all applets, packages, and ISD on the card |
| 4 | Delete an applet or package (interactive selection) |
| 5 | Install a CAP file (with optional applet/package AID) |
| 6 | Load a CAP file to the card |
| 7 | Show card info (CPLC data, etc.) |
| 8 | Send a plaintext APDU (hex) |
| 9 | Send a secure (encrypted) APDU (hex) |
| 10 | Set a custom master key for the session |
| 11 | Unlock the card (reset to default keys) |
| 12 | Set default keys on a factory-key card |
| 0 | Quit |

#### Card Detection

The tool does **NOT** auto-probe on startup. The user must explicitly choose to detect with default or factory keys:

1. **Default keys** (option 1 / `--detect`) — Tries GlobalPlatform default test keys (`404142...4F`). Safe to retry.
2. **Factory keys** (option 2 / `--detect-factory`) — In interactive mode, prompts with a warning before a **single** authentication attempt. In CLI mode, proceeds directly (single attempt). If the card responds, it is identified as fresh/unmodified.
3. **Custom keys** (`--key <hex>`) — User specifies their own key for the session.

#### Known Keys

| Key Set | ENC | MAC | DEK |
|---|---|---|---|
| GP default test | `404142434445464748494A4B4C4D4E4F` | same | same |
| Gemalto factory transport | `5A9E63D03BADBC2A240FE8F534709EDF` | `7CCC1E79D64FC5FA263B8F2955282998` | `B040703EC3DE23EE8AE4CFB6D632AA80` |

#### Safety Features

- **No auto-probing**: Detection is explicit — no accidental auth attempts on startup
- **Factory key warning**: Warns about error counter before factory key probe
- **Error reporting**: Every gp.jar output is checked for error codes (6982, 6985, 6A80, cryptogram invalid, etc.) and a human-readable explanation is shown
- **Brick risk detection**: If gp.jar emits "DO NOT RE-TRY" warning, the tool stops and explains the risk
- **Key state tracking**: Shows whether a card is detected and which key is active
- **EOF safety**: All `input()` calls handle piped stdin gracefully (no crashes in either mode)

#### Notes

- The tool auto-detects and labels known AIDs (SatoChip, SatoDim, SmartPGP, card OS packages) with names and license info.
- Card OS packages (ISD, GlobalPlatform Card Manager, Gemalto MultiApp OS, dCDocLite, biometry) cannot be deleted.
- When deleting, the tool first tries the applet, then the package, with `--op201` flag for compatibility.
- Factory key probing is done with a single attempt to avoid incrementing the card's error counter.
- If default keys stop working ("cryptogram invalid"), the key version may be permanently blocked from too many failed auth attempts. Try factory keys (option 2) to recover.

#### Troubleshooting

**"Card cryptogram invalid"**: The key version on the card has been permanently blocked by too many failed authentication attempts. This is irreversible for that key version. If the card still has factory keys on a different key version, use option [2] to detect and option [12] to set new default keys.

**"Timed out"**: Card may not be inserted, reader disconnected, or wrong keys causing the SCP02 handshake to hang.

**"Security status not satisfied (6982)"**: Wrong keys. The card rejected authentication.

#### How to Recover a Card with Blocked Default Keys

If the default key version is permanently blocked:

```bash
# Step 1: Detect with factory keys
python3 tools/jc_manager.py --detect-factory

# Step 2: Set new default keys
python3 tools/jc_manager.py --detect-factory --set-default-keys
```

Or in interactive mode: use option [2] then option [12].
