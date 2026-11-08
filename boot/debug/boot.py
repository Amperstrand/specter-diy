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
# D8: enable VCP so print() has a sink and ACM REPL prompt is observable
pyb.usb_mode("VCP")
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
