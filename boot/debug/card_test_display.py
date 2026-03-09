# Combined Card Detection Test - Display + LEDs
import sys
import time
from pyb import LED
import display
import lvgl as lv

# LEDs
led1, led2, led3, led4 = LED(1), LED(2), LED(3), LED(4)
for led in [led1, led2, led3, led4]:
    led.off()

# Init display
display.init(False)
lv.init()

# Create a simple status display
scr = lv.obj()
scr.set_style_bg_color(lv.color_hex(0x000000), 0)

title = lv.label(scr)
title.set_text("SeedKeeper Card Test")
title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
title.set_style_text_font(lv.font_montserrat_24, 0)
title.align(lv.ALIGN.TOP_MID, 0, 20)

status_label = lv.label(scr)
status_label.set_style_text_color(lv.color_hex(0x00FF00), 0)
status_label.set_style_text_font(lv.font_montserrat_20, 0)
status_label.align(lv.ALIGN.CENTER, 0, 0)

def update_status(text, color=0x00FF00):
    status_label.set_text(text)
    status_label.set_style_text_color(lv.color_hex(color), 0)
    lv.timer_handler()

# Boot flash
for _ in range(3):
    for led in [led1, led2, led3, led4]:
        led.on()
    time.sleep_ms(100)
    for led in [led1, led2, led3, led4]:
        led.off()
    time.sleep_ms(100)

# Step 1: Import module
update_status("Loading smartcard module...", 0xFFFF00)
try:
    from keystore.javacard.util import get_reader, get_connection
    led1.on()
    update_status("Module loaded OK", 0x00FF00)
except Exception as e:
    update_status("FAIL: Module import", 0xFF0000)
    while True:
        led3.on()
        time.sleep_ms(100)
        led3.off()
        time.sleep_ms(100)

time.sleep_ms(500)

# Step 2: Check card
update_status("Checking for card...", 0xFFFF00)
try:
    conn = get_connection()
    if conn.isCardInserted():
        led2.on()
        update_status("CARD PRESENT!", 0x00FF00)
        time.sleep_ms(1000)
    else:
        update_status("NO CARD - Insert and reset", 0xFFFF00)
        while True:
            led2.on()
            time.sleep_ms(500)
            led2.off()
            time.sleep_ms(500)
except Exception as e:
    update_status("FAIL: Card check", 0xFF0000)
    while True:
        led2.on()
        led3.on()
        time.sleep_ms(200)
        led2.off()
        led3.off()
        time.sleep_ms(200)

time.sleep_ms(500)

# Step 3: T=1 Connection with retries
update_status("Connecting T=1...", 0xFFFF00)
connected = False
for attempt in range(5):
    try:
        time.sleep_ms(100 * (attempt + 1))
        conn.connect(conn.T1_protocol)
        led3.on()
        connected = True
        update_status("T=1 Connected!", 0x00FF00)
        break
    except:
        led3.on()
        time.sleep_ms(50)
        led3.off()

if not connected:
    update_status("FAIL: T=1 connection", 0xFF0000)
    time.sleep_ms(2000)
    # Try continuing anyway - some cards don't need explicit connect

time.sleep_ms(500)

# Step 4: Select SeedKeeper applet
update_status("Selecting applet...", 0xFFFF00)
SEEDKEEPER_AID = bytes([0x53, 0x65, 0x65, 0x64, 0x4B, 0x65, 0x65, 0x70, 0x65, 0x72])

try:
    response, sw1, sw2 = conn.sendAPDU(0xB0, 0xA4, 0x04, 0x00, SEEDKEEPER_AID)
    status = (sw1 << 8) | sw2
    
    if status == 0x9000:
        led4.on()
        update_status("SEEDKEEPER FOUND!", 0x00FF00)
        # All 4 LEDs on = SUCCESS
        time.sleep_ms(2000)
        update_status("ALL TESTS PASSED!", 0x00FF00)
    elif status == 0x6A82:
        update_status("Applet not found", 0xFFFF00)
        while True:
            led4.on()
            time.sleep_ms(200)
            led4.off()
            time.sleep_ms(200)
    else:
        update_status("Status: " + hex(status), 0xFFFF00)
        
except Exception as e:
    update_status("FAIL: " + str(e)[:30], 0xFF0000)
    while True:
        led3.on()
        led4.on()
        time.sleep_ms(200)
        led3.off()
        led4.off()
        time.sleep_ms(200)
