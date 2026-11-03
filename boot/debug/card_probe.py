# M1 card probe v5 - clean session lifecycle + multi-AID SELECT
# Fresh connection per attempt, disconnect in finally (fixes stale
# "already connected" sessions), presence-gated, ATR reported, SELECT
# with CLA=00 against all three applet AIDs, LED-coded progress.

import time
from pyb import LED, UART

leds = [LED(i) for i in range(1, 5)]
for led in leds:
    led.off()

uart = UART(3, 115200)
uart.init(115200, bits=8, parity=None, stop=1)

def log(msg):
    uart.write(msg + "\r\n")

AIDS = [
    ("SeedKeeper", bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])),
    ("MemoryCard", bytes([0xB0, 0x0B, 0x51, 0x11, 0xCB, 0x01])),
    ("Satochip", bytes([0x53, 0x61, 0x74, 0x6F, 0x43, 0x68, 0x69, 0x70])),
]

for _ in range(3):
    for l in leds:
        l.on()
    time.sleep_ms(100)
    for l in leds:
        l.off()
    time.sleep_ms(100)

log("=" * 46)
log("M1 card probe v5 - clean-session multi-AID")
log("=" * 46)

iteration = 0
while True:
    iteration += 1
    leds[0].on()
    conn = None
    try:
        from keystore.javacard.util import get_reader
        log("")
        log("[i%d] opening fresh connection..." % iteration)
        reader = get_reader()
        conn = reader.createConnection()
        if not conn.isCardInserted():
            log("[i%d] no card - waiting" % iteration)
            leds[0].off()
            time.sleep(2)
            continue
        conn.connect(conn.T1_protocol)
        leds[1].on()
        atr = getattr(conn, "atr", None)
        try:
            atr_s = bytes(atr).hex() if atr else "n/a"
        except Exception:
            atr_s = str(atr)
        log("[i%d] T=1 connected. ATR=%s" % (iteration, atr_s))
        for name, aid in AIDS:
            apdu = bytes([0x00, 0xA4, 0x04, 0x00, len(aid)]) + aid
            resp, sw1, sw2 = conn.transmit(apdu)
            sw = (sw1 << 8) | sw2
            log("[i%d] SELECT %-11s -> %04X" % (iteration, name, sw))
            if sw == 0x9000:
                log("[i%d] *** %s SELECTED ***" % (iteration, name))
                leds[2].on()
        leds[3].on()
    except Exception as e:
        log("[i%d] ERR: %s" % (iteration, e))
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass
        for l in leds:
            l.off()
    time.sleep(2)
