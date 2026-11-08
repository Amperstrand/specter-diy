# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal
import pyb, os, micropython, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

version = "<version:tag10>0100900001</version:tag10>"

leds = [pyb.LED(i) for i in range(1,5)]
# poweroff on button press
def pwrcb(e):
    micropython.schedule(poweroff, 0)

# callback scheduled from the interrupt
def poweroff(_):
    for led in leds:
        led.toggle()
    os.sync()
    time.sleep_ms(300)
    pwr.off()
    time.sleep_ms(300)
    # will never reach here
    for led in leds:
        led.toggle()

pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# configure usb from start if you want, 
# otherwise will be configured after PIN
# pyb.usb_mode("VCP+MSC") # debug mode with USB and mounted storages from start
pyb.usb_mode("VCP")  # D8: enables UART3 output on ST-Link VCP (proven v2.2.4/v2.2.5)
# disable at start
# pyb.usb_mode(None)
# os.dupterm(None,0)
# os.dupterm(None,1)

# inject version to platform module
import platform
platform.version = version
platform.bootloader_locked = False
platform.build_type = "debug"

# uncomment to run some custom main:
# pyb.main("apdu_survey.py")
