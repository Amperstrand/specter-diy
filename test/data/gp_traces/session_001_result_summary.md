# JavaCard CAP Install/Uninstall Reference Trace - Session 001

## A. Summary Document

### Environment
| Item | Value |
|------|-------|
| Timestamp | 2026-03-20T10:37:05Z |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) |
| Kernel | 6.17.0-19-generic x86_64 |
| Java | OpenJDK 21.0.10 |
| GPPro | v25.10.20 (gp.jar from GitHub releases) |
| pcscd | v2.0.3 (debug mode, standalone foreground) |
| pcsc-spy | Custom-built from Ludovic Rousseau source |
| tshark | 4.2.2 |
| Reader | Gemalto PC Twin Reader (08e6:3437), USB Bus 1 Dev 2, serial BCF852F0 |
| CCID | v1.01, T=0+T=1, max data rate 825806 bps, max IFSD 254 |

### Card Metadata
| Item | Value |
|------|-------|
| ATR | `3B D5 18 FF 81 91 FE 1F C3 80 73 C8 21 10 0A` |
| Protocol | T=1 (negotiated) |
| ISD AID | A000000151000000 |
| ISD State | OP_READY |
| SCP Mode | SCP02 |
| Key Version | 1 (0x01) |
| Key Diversification Data (KDD) | `00003129509209206782` |
| Keys Used | Default keys `404142434445464748494A4B4C4D4E4F` (all three: ENC, MAC, DEK) |
| Card Platform | NXP JCOP4 (inferred from ATR + SCP02 KDD pattern) |

### Pre-existing Card Contents
- ISD: A000000151000000 (OP_READY)
- APP: SatoChip (5361746F4368697000) - SELECTABLE
- APP: 3.0.8... (A000000308000010000100) - SELECTABLE  
- PKG: A0000001515350 - SSD creation package
- PKG: A00000016443446F634C697465 (dCDocLite) v1.0
- PKG: A0000000620204 (javacardx.biometry1toN) v1.0
- PKG: A0000000620202 (javacardx.biometry) v1.3
- PKG: 5361746F44696D65 (SatoDime) v0.1
- PKG: 5361746F43686970 (SatoChip) v0.1
- PKG: A000000308000010 (3.0.8...) v1.0

### Artifact Hashes
| File | SHA256 | Size |
|------|--------|------|
| gp.jar | `c88e0c5093032ec4571571f5397b6174e56bf632667950fa5bb716338534b122` | 14,840,623 bytes |
| MemoryCardApplet.cap | `5f855f0c490402ac2f1e4cb1fc39cf6e4ce3d633fcb407fe024d275677f0efb4` | 61,325 bytes |
| TeapotApplet.cap | `ef5dda7b70d3bfc563d3cd19c7543eda8978bd11545592d324ab3cc1b18b143d` | 7,644 bytes |

### GPPro Command Lines Used

1. **List card contents:**
   ```
   GP_TRACE=true java -jar gp.jar -dv -l
   ```

2. **Install MemoryCardApplet.cap (FAILED at INSTALL for install):**
   ```
   GP_TRACE=true java -jar gp.jar -dv --install MemoryCardApplet.cap
   ```

3. **Install TeapotApplet.cap (SUCCESS):**
   ```
   GP_TRACE=true java -jar gp.jar -dv --install TeapotApplet.cap
   ```

4. **Verify installation:**
   ```
   GP_TRACE=true java -jar gp.jar -dv -l
   ```

5. **Uninstall TeapotApplet.cap:**
   ```
   GP_TRACE=true java -jar gp.jar -dv --uninstall TeapotApplet.cap
   ```

6. **Verify removal + cleanup:**
   ```
   GP_TRACE=true java -jar gp.jar -dv -l
   GP_TRACE=true java -jar gp.jar -dv -delete B00B5111CB
   ```

### Result Summary

| Operation | Result | Notes |
|-----------|--------|-------|
| List card contents | SUCCESS | Default keys work, SCP02 key ver 1 |
| MemoryCardApplet install | **FAILED** (LOAD ok, INSTALL `6F00`) | CAP compiled for JC3.0.4, card is JCOP4. Need recompile. |
| TeapotApplet install | **SUCCESS** | Package B00B5111CA loaded, applet B00B5111CA01 instantiated |
| Post-install SELECT | **SUCCESS** | TeapotApplet visible as SELECTABLE |
| TeapotApplet uninstall | **SUCCESS** | DELETE returned `00 9000` |
| Verify removal | **SUCCESS** | TeapotApplet no longer in registry |
| MemoryCard pkg cleanup | **SUCCESS** | Deleted orphaned package B00B5111CB |
| USB capture | **SUCCESS** | 243KB pcapng captured on usbmon1 |

### APDU Protocol Sequence (from TeapotApplet successful install/uninstall)

**GP Command Flow observed:**

1. `SELECT ISD` (A000000151000000) - plain APDU, returns 9000
2. `INITIALIZE UPDATE` (80500000 08 + host challenge) - SCP02, returns diversification data + card challenge
3. `EXTERNAL AUTHENTICATE` (84820100 10 + host cryptogram + MAC) - SCP02, returns 9000
4. `GET STATUS` (84F28002) - SCP02-wrapped GET DATA, returns ISD info
5. `GET STATUS` (84F24002) - returns APP data (existing applets)
6. `GET STATUS` (84F21002) - returns PKG data (continued in 84F21003)
7. `INSTALL [for load]` (84E60200) - SCP02-wrapped, returns 9000
8. `LOAD` blocks (84E80000..84E80025) - 37 x 255-byte blocks, all return 9000
9. `INSTALL [for install and make selectable]` (84E60C00) - returns 9000
10. `GET STATUS` (multiple 84F2*) - verify installation
11. `DELETE` (84E40080) - SCP02-wrapped DELETE, returns 9000

**Key APDU bytes (raw):**
- See `08_gppro_install_teapot_debug.txt` for complete LOAD sequence (all 37 blocks)
- See `10_gppro_uninstall_teapot.txt` for DELETE sequence

### C. Raw Artifacts

All files in `/home/ubuntu/src/record/specter-flash/session_001/`:

| File | Description | Size |
|------|-------------|------|
| `00_environment.txt` | Environment summary | 937B |
| `01_card_atr.txt` | Card ATR via opensc-tool | 45B |
| `02_gppro_list_debug.txt` | Initial card listing (default keys) | 9.2KB |
| `03_gppro_install_debug.txt` | MemoryCardApplet install (LOAD ok, INSTALL failed) | 60KB |
| `04_gppro_verify_partial.txt` | Verify after partial MemoryCard load | 9.9KB |
| `05_gppro_create_debug.txt` | MemoryCard create attempt (failed) | 9.1KB |
| `08_gppro_install_teapot_debug.txt` | **TeapotApplet full install (SUCCESS)** | **20KB** |
| `09_gppro_verify_teapot.txt` | Verify Teapot installed | 11KB |
| `10_gppro_uninstall_teapot.txt` | **TeapotApplet uninstall (SUCCESS)** | **9.4KB** |
| `11_gppro_verify_removed.txt` | Verify Teapot removed | 9.9KB |
| `12_gppro_delete_memorycard_pkg.txt` | Delete orphaned MemoryCard package | 8.4KB |
| `08_usb_capture.pcapng` | USB CCID raw capture (Bus 1) | 243KB |

Parent directory:
- `/home/ubuntu/src/record/specter-flash/gp.jar` - GPPro v25.10.20
- `/home/ubuntu/src/record/specter-flash/MemoryCardApplet.cap` - specter-javacard v0.1.0
- `/home/ubuntu/src/record/specter-flash/TeapotApplet.cap` - specter-javacard v0.1.0

### D. Interpretation Notes

#### SCP02 Secure Channel Establishment
- **INITIAL UPDATE**: CLA=`80`, P1=`50`, P2=`00`, Lc=`08`, Data=8-byte host challenge
  - Response: 12 bytes (KDD) + 4 bytes (SSC) + 8 bytes (card challenge) + 8 bytes (card cryptogram)
- **EXTERNAL AUTHENTICATE**: CLA=`84`, P1=`82`, P2=`01`, Lc=`10`, Data=8-byte host cryptogram + 8-byte MAC
  - Response: `9000` on success

#### LOAD Block Format
- CLA=`84`, P1=`E8`, P2=`00` (or sequence number), Lc=`FF`
- Data: 255 bytes of CAP binary (DGP, Method, Component, etc.)
- MAC: 4 bytes appended to each block
- Each block returns `00 9000`

#### INSTALL [for load]
- CLA=`84`, P1=`E6`, P2=`00`, Lc=variable
- TLV payload: Package AID, ISD AID, load parameters
- Returns `00 9000`

#### INSTALL [for install and make selectable]
- CLA=`84`, P1=`E6`, P2=`0C`, Lc=variable
- TLV payload: Package AID, Applet AID, Instance AID, privileges
- Privileges byte: `C900` = CardReset
- Returns `00 9000` on success

#### DELETE
- CLA=`84`, P1=`E4`, P2=`00` (or `80` for force), Lc=variable
- TLV payload: AID to delete
- Returns `00 9000` on success

### E. Notes for MicroPython Reproduction

1. **SCP02 is used**, not SCP03. The card reports SCP02 with key version 1.
2. **Default keys** `404142434445464748494A4B4C4D4E4F` work for this card.
3. **Session key derivation**: 3DES-based DES-CBC with card challenge + host challenge. See GPPro trace for exact derivation.
4. **MAC on every command**: 4-byte MAC appended after each SCP02-wrapped APDU.
5. **LOAD block size**: 255 bytes per block (max for T=1 with this reader's IFSD=254).
6. **MemoryCardApplet incompatibility**: The CAP compiled for JC3.0.4 fails `INSTALL [for install]` with `6F00` on this JCOP4 card. The applet's `install()` method likely throws an exception. You'll need to recompile for the target card's JavaCard version.
7. **TeapotApplet** (same repo, same JC3.0.4 compilation) installs successfully on this card - suggesting the issue is MemoryCardApplet-specific (possibly uses an API not available on this card's JVM).
