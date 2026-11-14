import os
from specter import Specter
from gui.specter import SpecterGUI

from keystore.core import KeyStore
from keystore.sdcard import SDKeyStore
from keystore.memorycard import MemoryCard

from hosts import SDHost, QRHost, USBHost, Host
import platform
from helpers import load_apps
from app import BaseApp
import display

def _dbg(msg):
    try:
        import pyb
        pyb.UART(3, 115200).write(("[MAIN] " + msg + "\r\n").encode())
    except Exception:
        pass


def main(apps=None, network="main", keystore_cls=None):
    """
    apps: list of apps to load
    network: default network to operate
    keystores: list of KeyStore classes that can be used
    """
    # Init display first as it also inits the SDRAM
    display.init(False)
    # create virtual file system /sdram
    # for temp untrusted data storage
    rampath = platform.mount_sdram()

    # set working path to empty folder in sdram
    if not platform.simulator:
        cwd = rampath+"/cwd"
        platform.maybe_mkdir(cwd)
        os.chdir(cwd)

    # define hosts - USB, QR, SDCard
    # each hosts gets it's own RAM folder for data
    # m1-gate fallback: bench board's QSPI chip is dead (JEDEC 00 00 00),
    # no-QSPI builds have no /qspi mount -> use internal flash
    try:
        os.stat("/qspi")
        storage_backend = "/qspi"
    except OSError:
        storage_backend = "/flash"
    Host.SETTINGS_DIR = platform.fpath(storage_backend + "/hosts")
    Specter.SETTINGS_DIR = platform.fpath(storage_backend + "/global")
    hosts = [
        USBHost(rampath + "/usb"),
        QRHost(rampath + "/qr"),
        SDHost(rampath+"/sd"),
    ]
    # temp storage in RAM for host commands processing
    BaseApp.TEMPDIR = rampath+"/tmp"

    # define GUI
    if not platform.simulator:
        gui = SpecterGUI()
    else:
        # this GUI can simulate user actions for automated testing
        from gui.tcp_gui import TCPGUI
        gui = TCPGUI()

    # inject the folder where keystore stores it's data
    KeyStore.path = platform.fpath("/flash/keystore")
    # detect keystore to use
    if keystore_cls is not None:
        keystores = [keystore_cls]
    else:
        keystores = [
            MemoryCard,
            SDKeyStore,
        ]

    # loading apps
    if apps is None:
        apps = load_apps()

    # make Specter instance
    settings_path = platform.fpath("/flash")
    _dbg('creating Specter...')
    specter = Specter(
        gui=gui,
        keystores=keystores,
        hosts=hosts,
        apps=apps,
        settings_path=settings_path,
        network=network,
    )
    # HIL test mode (flag gate: simulator default on, production hardware
    # off - config.py overrides; see docs/hil-architecture.md section 9)
    try:
        import config
    except ImportError:
        import config_default as config
    _dbg('hil_enabled=%s' % getattr(config, 'hil_enabled', False))
    if getattr(config, "hil_enabled", False):
        try:
            from test_mode import TestMode
            _dbg('TestMode created')
            specter.test_mode = TestMode(specter)
        except Exception as e:
            print("[Main] Test mode not available:", e)
            specter.test_mode = None
    else:
        specter.test_mode = None
    _dbg('starting specter...')
    _dbg('calling specter.start()')
    try:
        specter.start()
        _dbg('start() RETURNED (unexpected)')
    except BaseException as e:
        import uio, sys
        buf = uio.StringIO()
        sys.print_exception(e, buf)
        _dbg('start() THREW: ' + buf.getvalue()[:400])


if __name__ == "__main__":
    main()
