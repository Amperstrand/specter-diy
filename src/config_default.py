import sys
import os

simulator = sys.platform != "pyboard"

# to overwrite these settings create a config.py file

if simulator:
    if len(sys.argv) > 1:
        storage_root = sys.argv[1]
    else:
        storage_root = "./fs"
    try:
        os.mkdir(storage_root)
    except:
        pass

else:
    storage_root = ""

# pin that triggers QR code
# if command mode failed
QRSCANNER_TRIGGER = "D2"

# HIL test mode: OFF in production hardware builds; the simulator keeps
# it on for the test suite. Enable on hardware via a config.py override
# (hil_enabled = True) when flashing dedicated HIL firmware.
hil_enabled = simulator

# Framebuffer for TEST_FB_DUMP (STM32F469-DISCO: LTDC frame buffer in SDRAM,
# RGB565, 800x480) - tune in config.py if the board changes
fb_base_address = 0xD0000000
fb_width = 800
fb_height = 480
