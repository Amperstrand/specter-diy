# Card Detection Test - Output via UART3 to ST-Link VCP
# Connect to /dev/ttyACM0 (ST-Link VCP bridge to UART3)
# UART3: PB10=TX, PB11=RX (internally connected to ST-Link)

import time
from pyb import LED, UART

# Initialize LEDs
leds = [LED(i) for i in range(1, 5)]
for led in leds:
    led.off()

# Initialize UART3 (connected to ST-Link VCP bridge)
# This is the serial port visible as /dev/ttyACM0
uart = UART(3, 115200)
uart.init(115200, bits=8, parity=None, stop=1)

def log(msg):
    """Output to UART3 (ST-Link VCP) and LED indicator"""
    uart.write(msg + "\r\n")
    # Small blink to show activity
    leds[0].on()
    time.sleep_ms(10)
    leds[0].off()

# Boot indicator
for _ in range(3):
    for led in leds:
        led.on()
    time.sleep_ms(100)
    for led in leds:
        led.off()
    time.sleep_ms(100)

log("")
log("=" * 50)
log("SeedKeeper Card Detection Test")
log("=" * 50)
log("")
log("Output via UART3 -> ST-Link VCP")
log("Connect to /dev/ttyACM0 at 115200 baud")
log("")

# Continuous test loop
while True:
    try:
        log("[STEP 1] Loading smartcard module...")
        from keystore.javacard.util import get_reader, get_connection
        log("         OK - Module loaded")
        leds[0].on()  # Green ON
        
        time.sleep_ms(300)
        
        log("[STEP 2] Getting reader...")
        reader = get_reader()
        log("         OK - Reader initialized")
        
        time.sleep_ms(300)
        
        log("[STEP 3] Checking card presence...")
        conn = get_connection()
        if conn.isCardInserted():
            log("         *** CARD PRESENT! ***")
            leds[1].on()  # Orange ON
            
            time.sleep_ms(300)
            
            log("[STEP 4] Connecting T=1 protocol...")
            try:
                conn.connect(conn.T1_protocol)
                log("         OK - T=1 connected")
                leds[2].on()  # Red ON
                
                time.sleep_ms(300)
                
                log("[STEP 5] Selecting SeedKeeper applet...")
                SEEDKEEPER_AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])
                response, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, SEEDKEEPER_AID)
                status = (sw1 << 8) | sw2
                
                log("         SW1=" + hex(sw1) + " SW2=" + hex(sw2))
                
                if status == 0x9000:
                    log("")
                    log("=" * 50)
                    log("SUCCESS! SEEDKEEPER APPLET FOUND!")
                    log("All 4 LEDs should be ON")
                    log("=" * 50)
                    leds[3].on()  # Blue ON
                    # Keep all LEDs on - SUCCESS!
                    while True:
                        time.sleep(1)
                else:
                    log("         Applet not found, status: " + hex(status))
                    # Blink blue
                    for _ in range(10):
                        leds[3].on()
                        time.sleep_ms(100)
                        leds[3].off()
                        time.sleep_ms(100)
                        
            except Exception as e:
                log("         T=1 failed: " + str(e))
                # Try continuing anyway
        else:
            log("         No card detected")
            leds[1].off()
        
        log("")
        log("Waiting 2 seconds before retry...")
        log("")
        
        # Turn off LEDs for retry
        for led in leds:
            led.off()
            
        time.sleep(2)
        
    except Exception as e:
        log("ERROR: " + str(e))
        for led in leds:
            led.off()
        time.sleep(2)
