# Card Detection Test - LED Status Indicators
# No serial or display needed - just watch the LEDs!

import time
from pyb import LED

# LEDs on STM32F469 Discovery:
# LED1 (green)  - Reader initialized
# LED2 (orange) - Card present  
# LED3 (red)    - T=1 connection
# LED4 (blue)   - SeedKeeper applet found

led1 = LED(1)  # Green
led2 = LED(2)  # Orange  
led3 = LED(3)  # Red
led4 = LED(4)  # Blue
leds = [led1, led2, led3, led4]

# Turn all off initially
for led in leds:
    led.off()

# Boot indicator - flash all LEDs 3 times
for _ in range(3):
    for led in leds:
        led.on()
    time.sleep_ms(100)
    for led in leds:
        led.off()
    time.sleep_ms(100)

time.sleep_ms(500)

# Step 1: Initialize reader
try:
    from keystore.javacard.util import get_reader, get_connection
    led1.on()  # Green = Reader OK
except Exception:
    # Error - rapid flash red LED
    while True:
        led3.on()
        time.sleep_ms(100)
        led3.off()
        time.sleep_ms(100)

time.sleep_ms(500)

# Step 2: Check card presence
try:
    conn = get_connection()
    if conn.isCardInserted():
        led2.on()  # Orange = Card present
        card_present = True
    else:
        # No card - pulse orange slowly
        while True:
            led2.on()
            time.sleep_ms(500)
            led2.off()
            time.sleep_ms(500)
except Exception:
    # Error - flash red + orange
    while True:
        led2.on()
        led3.on()
        time.sleep_ms(200)
        led2.off()
        led3.off()
        time.sleep_ms(200)

time.sleep_ms(500)

# Step 3: Connect T=1 protocol
try:
    conn.connect(conn.T1_protocol)
    led3.on()  # Red = T=1 connected
except Exception:
    # Connection failed - alternating red/orange
    while True:
        led2.on()
        time.sleep_ms(200)
        led2.off()
        led3.on()
        time.sleep_ms(200)
        led3.off()

time.sleep_ms(500)

# Step 4: Select SeedKeeper applet
SEEDKEEPER_AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])

try:
    response, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, SEEDKEEPER_AID)
    
    if sw1 == 0x90 and sw2 == 0x00:
        # SUCCESS! All 4 LEDs on solid
        led4.on()  # Blue = Applet found
        # Keep all LEDs on to indicate complete success
        # (they should all be on now)
    elif sw1 == 0x6A and sw2 == 0x82:
        # Applet not found - blue LED blinks
        while True:
            led4.on()
            time.sleep_ms(200)
            led4.off()
            time.sleep_ms(200)
    else:
        # Unexpected response - error pattern
        while True:
            led3.on()
            led4.on()
            time.sleep_ms(100)
            led3.off()
            led4.off()
            time.sleep_ms(100)
except Exception:
    # Applet selection error
    while True:
        led1.on()
        led4.on()
        time.sleep_ms(100)
        led1.off()
        led4.off()
        time.sleep_ms(100)
