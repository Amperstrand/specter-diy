import platform

from specter import Specter
from gui.specter import SpecterGUI

from keystore.core import KeyStore
from keystore.sdcard import SDKeyStore
from keystore.memorycard import MemoryCard
from keystore.seedkeeper import SeedKeeper

from hosts import SDHost, QRHost, USBHost, Host
from helpers import load_apps
from app import BaseApp
import display
import os


def main(apps=None, network="main", keystore_cls=None):
    if platform.hil_test_mode and network == "main":
        network = "regtest"

    display.init(False)
    rampath = platform.mount_sdram()

    if not platform.simulator:
        cwd = rampath+"/cwd"
        platform.maybe_mkdir(cwd)
        os.chdir(cwd)

    Host.SETTINGS_DIR = platform.fpath("/qspi/hosts")
    Specter.SETTINGS_DIR = platform.fpath("/qspi/global")
    hosts = [
        USBHost(rampath + "/usb"),
        QRHost(rampath + "/qr"),
        SDHost(rampath+"/sd"),
    ]
    BaseApp.TEMPDIR = rampath+"/tmp"

    if not platform.simulator:
        gui = SpecterGUI()
    else:
        from gui.tcp_gui import TCPGUI
        gui = TCPGUI()

    KeyStore.path = platform.fpath("/flash/keystore")
    if keystore_cls is not None:
        keystores = [keystore_cls]
    else:
        keystores = [
            MemoryCard,
            SeedKeeper,
            SDKeyStore,
        ]

    if apps is None:
        apps = load_apps()

    settings_path = platform.fpath("/flash")
    specter = Specter(
        gui=gui,
        keystores=keystores,
        hosts=hosts,
        apps=apps,
        settings_path=settings_path,
        network=network,
    )
    specter.start()


if __name__ == "__main__":
    main()
