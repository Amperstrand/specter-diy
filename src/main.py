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
    # D2: app's UART3 path (the suspected dead path)
    try:
        import pyb
        pyb.UART(3, 115200).write(("[MAIN-D2] " + msg + "\r\n").encode())
    except Exception:
        pass
    # D1: known-good path — print() to VCP/REPL (works in diagnostic era)
    try:
        print("[MAIN-D1] " + msg)
    except Exception:
        pass


def _dbg_stlk(msg):
    # D1: platform.py's stlk path ("YB" @ 9600, the proven diagnostic transport)
    try:
        import platform
        if hasattr(platform, 'stlk'):
            platform.stlk.write(("[MAIN-D1-stlk] " + msg + "\r\n").encode())
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

    import diag_ring
    diag_ring.trace("T0", "main() entered")

    settings_path = platform.fpath("/flash")
    _dbg('creating Specter...')
    diag_ring.trace("T1", "pre-Specter-ctor")
    specter = Specter(
        gui=gui,
        keystores=keystores,
        hosts=hosts,
        apps=apps,
        settings_path=settings_path,
        network=network,
    )
    diag_ring.trace("T1b", "post-Specter-ctor")

    try:
        import config
    except ImportError:
        import config_default as config
    hil = getattr(config, 'hil_enabled', False)
    diag_ring.trace("T2", "hil_enabled=%s" % hil)
    _dbg('hil_enabled=%s' % hil)

    if hil:
        try:
            diag_ring.trace("T3", "pre-import")
            from test_mode import TestMode
            diag_ring.trace("T3b", "pre-construct")

            import pyb as _pyb
            try:
                _tu = _pyb.UART(3, 115200)
                _tu.init(115200, bits=8, parity=None, stop=1, read_buf_len=512)
                _tu.write(b"[D9] UART3 init OK")
                diag_ring.trace("D9", "UART3@115200 OK")
                del _tu
            except Exception as _e:
                diag_ring.trace("D9-FAIL", str(_e)[:90])

            specter.test_mode = TestMode(specter)
            diag_ring.trace("T4", "TestMode constructed")
            _dbg('TestMode created')
            specter.test_mode.diag_ring = diag_ring
        except Exception as e:
            diag_ring.trace("T-EXC", str(e)[:90])
            print("[Main] Test mode not available:", e)
            specter.test_mode = None
    else:
        specter.test_mode = None

    diag_ring.trace("T5", "pre-specter-start")
    _dbg('starting specter...')
    specter.start()


if __name__ == "__main__":
    main()
