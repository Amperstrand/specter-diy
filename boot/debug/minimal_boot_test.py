# Minimal LED Boot Test - No dependencies
# Just blinks LEDs to prove firmware boots

from pyb import LED
import time

leds = [LED(i) for i in range(1, 5)]

# Turn all off
for led in leds:
    led.off()

# Blink pattern: 1-2-3-4 repeating = firmware is running
while True:
    for led in leds:
        led.on()
        time.sleep_ms(200)
        led.off()
        time.sleep_ms(100)
