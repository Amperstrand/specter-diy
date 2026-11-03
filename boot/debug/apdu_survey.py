# APDU survey - on-device battery for MemoryCard / Satochip v0.14 / SeedKeeper v0.2
# Single session, SELECT-switched between families (sidesteps reader connection cap).
# All output to UART3 (if02) with [tag] lines + timings; supervisor logs everything.
# SAFETY: no seed import/reset, no factory reset, wrong-PIN capped at 1 per applet
# with immediate recovery, PIN/label changes always round-tripped back.

import time
from pyb import LED, UART

leds = [LED(i) for i in range(1, 5)]
uart = UART(3, 115200)
uart.init(115200, bits=8, parity=None, stop=1)

PIN = "1234"

def log(tag, msg=""):
    uart.write("[%s] %s\r\n" % (tag, msg))

def timed(tag, fn, *a, **kw):
    t0 = time.ticks_us()
    try:
        r = fn(*a, **kw)
        dt = time.ticks_diff(time.ticks_us(), t0)
        log(tag + ".OK", "%d us" % dt)
        return r
    except Exception as e:
        dt = time.ticks_diff(time.ticks_us(), t0)
        log(tag + ".ERR", "%d us: %s" % (dt, e))
        return None

for l in leds:
    l.off()

log("SURVEY", "=== apdu survey start ===")

# ---------------------------------------------------------------- connection
from keystore.javacard.util import get_reader

reader = get_reader()
conn = reader.createConnection()
conn.connect(conn.T1_protocol)
atr = getattr(conn, "atr", None)
try:
    atr_s = bytes(atr).hex() if atr else "n/a"
except Exception:
    atr_s = str(atr)
log("ATR", atr_s)

# ---------------------------------------------------------------- helpers
def select(aid_bytes):
    apdu = bytes([0x00, 0xA4, 0x04, 0x00, len(aid_bytes)]) + aid_bytes
    resp, sw1, sw2 = conn.transmit(apdu)
    return (sw1 << 8) | sw2, resp

def raw(cla, ins, p1, p2, data=b"", le=None):
    hdr = bytes([cla, ins, p1, p2])
    if data or le is not None:
        hdr += bytes([len(data)])
    apdu = hdr + data
    if le is not None:
        apdu += bytes([le])
    resp, sw1, sw2 = conn.transmit(apdu)
    return resp, (sw1 << 8) | sw2

AID_MC = bytes([0xB0, 0x0B, 0x51, 0x11, 0xCB, 0x01])
AID_SK = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
AID_SC = bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70])

# ================================================================ PHASE 1: MemoryCard
leds[0].on()
log("P1", "--- MemoryCard ---")
sw = timed("MC.select", lambda: select(AID_MC)[0])
if sw != 0x9000:
    log("P1", "SELECT failed %04X - skipping family" % sw)
else:
    from keystore.javacard.applets.memorycard import MemoryCardApplet
    mc = MemoryCardApplet(conn)
    timed("MC.sc_open", lambda: mc.sc.open_channel())

    # plaintext ops
    r = timed("MC.get_random", lambda: mc.get_random())
    r = timed("MC.get_pubkey", lambda: mc.get_pubkey())

    # PIN flows via the client's secure channel
    try:
        st = mc.request(bytes([0x03, 0x00]))
        log("MC.pin_status.raw", str(st)[:120])
    except Exception as e:
        log("MC.pin_status.ERR", str(e))

    # storage boundaries
    for n in (0, 1, 220, 221):
        blob = bytes([0xA5] * n)
        try:
            t0 = time.ticks_us()
            mc.save_secret(blob)
            got = mc.get_secret()
            dt = time.ticks_diff(time.ticks_us(), t0)
            ok = bytes(got) == blob
            log("MC.storage.%d" % n, "OK" if ok else "MISMATCH", )
        except Exception as e:
            log("MC.storage.%d.ERR" % n, str(e))

    timed("MC.sc_close", lambda: mc.close_channel())

# ================================================================ PHASE 2: Satochip
leds[1].on()
log("P2", "--- Satochip v0.14 ---")
sw = timed("SC.select", lambda: select(AID_SC)[0])
if sw != 0x9000:
    log("P2", "SELECT failed %04X - skipping family" % sw)
else:
    from keystore.javacard.applets.satochip_applet import SatochipApplet
    sc = SatochipApplet(conn)
    timed("SC.sc_init", lambda: sc.init_secure_channel())

    st = timed("SC.get_status", lambda: sc.get_card_status())
    log("SC.status.raw", str(st)[:200])

    r = timed("SC.verify_pin", lambda: sc.verify_pin(PIN))

    # BIP32 derivations incl. BIP85 paths (host verifies offline)
    for path in ("m", "m/44h/0h/0h", "m/84h/0h/0h", "m/83696968h/0h/0h", "m/83696968h/128h/0h"):
        try:
            pub, cc = sc.get_extended_key(path if isinstance(path, bytes) else sc._path_to_bytes(path))
            log("SC.xpub.%s" % path, "pub=%s cc=%s" % (bytes(pub).hex(), bytes(cc).hex()))
        except Exception as e:
            log("SC.xpub.%s.ERR" % path, str(e))

    # sign a known hash, host verifies against m/84h xpub
    import hashlib
    msg = b"amperstrand m1 survey"
    h = hashlib.sha256(msg).digest()
    try:
        sig = sc.sign_transaction_hash(0xFF, h)
        log("SC.sign.ff", bytes(sig).hex()[:180])
    except Exception as e:
        log("SC.sign.ff.ERR", str(e))

    # PIN change round-trip
    try:
        sc.change_pin(PIN, "4321")
        log("SC.pin_change", "to 4321 OK")
        sc.verify_pin("4321")
        sc.change_pin("4321", PIN)
        log("SC.pin_change", "restored OK")
    except Exception as e:
        log("SC.pin_change.ERR", str(e))

# ================================================================ PHASE 3: SeedKeeper
leds[2].on()
log("P3", "--- SeedKeeper v0.2 ---")
sw = timed("SK.select", lambda: select(AID_SK)[0])
if sw != 0x9000:
    log("P3", "SELECT failed %04X - skipping family" % sw)
else:
    from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet
    sk = SeedKeeperApplet(conn)
    timed("SK.sc_init", lambda: sk.init_secure_channel())

    st = timed("SK.get_status", lambda: sk.get_seedkeeper_status())
    log("SK.status.raw", str(st)[:200])

    r = timed("SK.verify_pin", lambda: sk.verify_pin(PIN))

    lbl = timed("SK.label_get", lambda: sk.get_card_label())
    log("SK.label", str(lbl))
    try:
        sk.set_card_label("survey-tag")
        now = sk.get_card_label()
        sk.set_card_label(lbl if lbl else "")
        log("SK.label_rt", "roundtrip OK" if now == "survey-tag" else "MISMATCH")
    except Exception as e:
        log("SK.label_rt.ERR", str(e))

    hdrs = timed("SK.list_headers", lambda: sk.list_secret_headers())
    log("SK.headers", str(hdrs)[:400])

    try:
        mn = sk.get_bip39_secret()
        log("SK.bip39", "***exported %d-word mnemonic***" % (len(mn.split()) if mn else 0))
    except Exception as e:
        log("SK.bip39.ERR", str(e))

    # one typed-secret round-trip (password type 0x90) - import then delete
    try:
        from keystore.javacard.applets.seedkeeper_applet import SeedKeeperApplet as _SK
        log("SK.typed_secret", "password-type roundtrip requires import INS - documented, not auto-executed")
    except Exception as e:
        log("SK.typed.ERR", str(e))

# ================================================================ PHASE 4: cross-family
leds[3].on()
log("P4", "--- cross-family SELECT switching ---")
for name, aid in (("MC", AID_MC), ("SK", AID_SK), ("SC", AID_SC), ("MC", AID_MC), ("SC", AID_SC)):
    sw, _ = select(aid)
    log("P4.switch.%s" % name, "%04X" % sw)

# ================================================================ PHASE 5: session end
log("P5", "--- session lifecycle ---")
try:
    conn.disconnect()
    log("P5.disconnect", "OK")
except Exception as e:
    log("P5.disconnect.ERR", str(e))
try:
    conn2 = reader.createConnection()
    conn2.connect(conn2.T1_protocol)
    log("P5.reconnect", "OK - cap not hit on fresh reader cycle")
    conn2.disconnect()
except Exception as e:
    log("P5.reconnect.ERR", str(e))

log("SURVEY", "=== apdu survey complete ===")
for l in leds:
    l.off()

# park: visible idle pattern so the supervisor knows we finished
while True:
    leds[0].toggle()
    time.sleep_ms(800)
