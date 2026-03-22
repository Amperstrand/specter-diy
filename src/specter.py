import sys
import gc
import json
from io import BytesIO
from binascii import unhexlify
import asyncio

from platform import (
    CriticalErrorWipeImmediately,
    reboot,
    maybe_mkdir,
    wipe,
    get_version,
    get_git_info,
    get_battery_status,
    get_build_type,
    get_firmware_boot_mode,
    get_flash_read_protection_status,
    get_flash_write_protection_status,
    hil_test_mode,
)
from hosts import Host, HostError
from app import BaseApp
from embit import bip39
from embit.liquid.networks import NETWORKS
from gui.screens.settings import HostSettings
from gui.screens.mnemonic import MnemonicPrompt
from gui.screens.debug_info import DebugInfoScreen

# small helper functions
from helpers import gen_mnemonic, fix_mnemonic
from errors import BaseError


class SpecterError(BaseError):
    NAME = "Specter error"


class Specter:
    """Specter class.
    Call .start() method to register in the event loop
    It will then call the .setup() and .main() functions to display the GUI
    """
    SETTINGS_DIR = None
    # global settings
    GLOBAL = {}

    def __init__(self, gui, keystores, hosts, apps, settings_path, network="main"):
        # so hosts can call methods of Specter
        Host.parent = self
        self.hosts = hosts
        self.keystores = keystores
        self.keystore = None
        if len(keystores) == 1:
            # instantiate the keystore class
            self.keystore = keystores[0]()
        self.network = network
        self.gui = gui
        self.path = settings_path
        self.current_menu = self.initmenu
        self.dev = False
        self.apps = apps

    async def _check_provisioning(self):
        """Check if a GP card needs MemoryCard provisioning after unlock."""
        try:
            from keystore.javacard.util import get_connection
            from keystore.javacard.gp.probe import probe_card
            conn = get_connection()
            result = probe_card(conn)
            if result["kind"] == "gp_installable":
                if await self.gui.prompt(
                    "Supported JavaCard detected",
                    "Specter MemoryCard is not installed.\n\n"
                    "Installing will modify the card.\n\n"
                    "Install now?",
                ):
                    await self._install_memorycard(result)
        except Exception:
            pass

    async def _install_memorycard(self, probe_result):
        """Run the MemoryCard installation flow with progress screen."""
        from gui.screens.provisioning import ProvisioningProgressScreen
        from keystore.javacard.util import get_connection
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        from keystore.javacard.gp.loader import install_memorycard, verify_install
        from keystore.javacard.memorycard_cap import CAP_DATA, CAP_SHA256
        import hashlib

        if probe_result.get("memorycard_installed"):
            if not await self.gui.prompt(
                "MemoryCard already installed",
                "MemoryCard is already on this card.\n\n"
                "Reinstalling will delete existing data.\n\n"
                "Continue?",
                warning="All stored data will be lost!",
            ):
                return
            await self._delete_memorycard(silent=True)

        scr = ProvisioningProgressScreen("Install MemoryCard")
        await self.gui.load_screen(scr)

        try:
            scr.set_step("Connecting to card...")
            conn = get_connection()
            conn.connect(conn.T1_protocol)

            scr.set_step("Authenticating...")
            session = open_session(conn, JCOP4_PROFILE)

            scr.set_step("Verifying CAP file...")
            sha = hashlib.sha256(CAP_DATA).hexdigest()
            if sha != CAP_SHA256:
                scr.set_error("CAP hash mismatch!\n%s" % sha)
                await scr.result()
                return

            scr.set_step("Loading package...")
            scr.set_detail("Sending %d bytes..." % len(CAP_DATA))
            package_aid = unhexlify("B00B5111CB")
            applet_aid = unhexlify("B00B5111CB01")
            instance_aid = unhexlify("B00B5111CB01")
            sd_aid = JCOP4_PROFILE["isd_aid"]
            privileges = JCOP4_PROFILE["privileges"]

            install_memorycard(
                session, CAP_DATA, package_aid, applet_aid,
                instance_aid, sd_aid, privileges)

            scr.set_step("Verifying installation...")
            if verify_install(session, instance_aid):
                scr.set_done()
            else:
                scr.set_error("Verification failed!")
            try:
                conn.disconnect()
            except Exception:
                pass
            await scr.result()
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            scr.set_error("Install failed:\n%s" % str(e))
            await scr.result()

    async def _provisioning_menu(self):
        """Developer provisioning menu: install, delete, diagnostics."""
        buttons = [
            (1, "Card info"),
            (2, "Install MemoryCard"),
            (3, "Delete MemoryCard"),
            (4, "Install SeedKeeper"),
            (5, "Delete SeedKeeper"),
        ]
        while True:
            menuitem = await self.gui.menu(
                buttons, title="JavaCard Provisioning",
                note=self._firmware_note(), last=(255, None))
            if menuitem == 255:
                return
            elif menuitem == 1:
                await self._show_card_details()
            elif menuitem == 2:
                from keystore.javacard.gp.probe import probe_card
                from keystore.javacard.util import get_connection
                conn = get_connection()
                result = probe_card(conn)
                await self._install_memorycard(result)
            elif menuitem == 3:
                await self._delete_memorycard()
            elif menuitem == 4:
                await self._install_seedkeeper()
            elif menuitem == 5:
                await self._delete_seedkeeper()

    async def _show_card_details(self):
        """Show card info, detected applets, and registry dump."""
        from gui.screens.provisioning import ProvisioningDetailsScreen
        from keystore.javacard.util import get_connection
        from keystore.javacard.card_scanner import scan_card_applets
        from keystore.javacard.gp.probe import probe_card
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        from keystore.javacard.gp.registry import list_all, format_registry

        conn = get_connection()
        result = probe_card(conn)

        scan = scan_card_applets(conn)
        result["applets"] = scan.get("applets", [])

        scr = ProvisioningDetailsScreen(result)
        await self.gui.load_screen(scr)

        if result.get("profile"):
            try:
                conn.connect(conn.T1_protocol)
                session = open_session(conn, result["profile"])
                registry = list_all(session)
                scr.set_registry(format_registry(registry))
                try:
                    conn.disconnect()
                except Exception:
                    pass
            except Exception:
                scr.set_registry("(failed to query registry)")

        await scr.result()

    async def _delete_memorycard(self, silent=False):
        """Delete MemoryCard applet from card."""
        if not silent:
            if not await self.gui.prompt(
                "Delete MemoryCard?",
                "This will remove the MemoryCard applet\n"
                "and all its data from the card.\n\n"
                "Are you sure?",
                warning="This action cannot be undone!",
            ):
                return

        from gui.screens.provisioning import ProvisioningProgressScreen
        from keystore.javacard.util import get_connection
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        from keystore.javacard.gp.deleter import delete_aid

        scr = ProvisioningProgressScreen("Delete MemoryCard")
        await self.gui.load_screen(scr)

        try:
            scr.set_step("Connecting to card...")
            conn = get_connection()
            conn.connect(conn.T1_protocol)

            scr.set_step("Authenticating...")
            session = open_session(conn, JCOP4_PROFILE)

            scr.set_step("Deleting applet...")
            applet_aid = unhexlify("B00B5111CB01")
            delete_aid(session, applet_aid)

            scr.set_step("Deleting package...")
            package_aid = unhexlify("B00B5111CB")
            try:
                delete_aid(session, package_aid)
            except Exception:
                pass

            if silent:
                return
            scr.set_done()
            try:
                conn.disconnect()
            except Exception:
                pass
            await scr.result()
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            if silent:
                raise
            scr.set_error("Delete failed:\n%s" % str(e))
            await scr.result()

    async def _install_seedkeeper(self):
        """Install SeedKeeper applet from DGP file on filesystem."""
        from keystore.javacard.gp.profiles import APPLET_AIDS

        sk_info = APPLET_AIDS.get("seedkeeper")
        dgp_path = sk_info["dgp_file"] if sk_info else "/flash/gp/SeedKeeper.dgp"

        try:
            f = open(dgp_path, "rb")
            f.close()
        except Exception:
            await self.gui.alert(
                "SeedKeeper.dgp not found",
                "Copy the DGP file to the device:\n\n"
                "mpremote cp SeedKeeper.dgp :%s" % dgp_path
            )
            return

        from keystore.javacard.util import get_connection
        from keystore.javacard.card_scanner import scan_card_applets

        conn = get_connection()
        scan = scan_card_applets(conn)
        already_installed = "SeedKeeper" in scan.get("applets", [])

        if already_installed:
            if not await self.gui.prompt(
                "SeedKeeper already installed",
                "SeedKeeper is already on this card.\n\n"
                "Reinstalling will delete existing secrets.\n\n"
                "Continue?",
                warning="All stored secrets will be lost!",
            ):
                return
            await self._delete_seedkeeper(silent=True)

        if not await self.gui.prompt(
            "Install SeedKeeper?",
            "This will install the SeedKeeper applet\n"
            "on the JavaCard.\n\n"
            "The card will be modified.\n\n"
            "Continue?",
        ):
            return

        from gui.screens.provisioning import ProvisioningProgressScreen
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        from keystore.javacard.gp.loader import install_from_dgp, verify_install
        from binascii import unhexlify

        scr = ProvisioningProgressScreen("Install SeedKeeper")
        await self.gui.load_screen(scr)

        try:
            scr.set_step("Loading DGP file...")
            f = open(dgp_path, "rb")
            dgp_data = f.read()
            f.close()

            scr.set_step("Connecting to card...")
            conn = get_connection()
            conn.connect(conn.T1_protocol)

            scr.set_step("Authenticating...")
            session = open_session(conn, JCOP4_PROFILE)

            scr.set_step("Installing (%d bytes)..." % len(dgp_data))
            sd_aid = unhexlify("A000000151000000")
            pkg_aid = install_from_dgp(session, dgp_data, sd_aid)

            scr.set_step("Verifying...")
            sk_inst = unhexlify("536565644b656570657201")
            if verify_install(session, sk_inst):
                scr.set_done()
            else:
                scr.set_error("Verification failed")

            try:
                conn.disconnect()
            except Exception:
                pass
            await scr.result()
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            scr.set_error("Install failed:\n%s" % str(e))
            await scr.result()

    async def _delete_seedkeeper(self, silent=False):
        """Delete SeedKeeper applet from card."""
        if not silent:
            if not await self.gui.prompt(
                "Delete SeedKeeper?",
                "This will remove the SeedKeeper applet\n"
                "and all its secrets from the card.\n\n"
                "Are you sure?",
                warning="This action cannot be undone!",
            ):
                return

        from gui.screens.provisioning import ProvisioningProgressScreen
        from keystore.javacard.util import get_connection
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        from keystore.javacard.gp.deleter import delete_aid
        from binascii import unhexlify

        scr = ProvisioningProgressScreen("Delete SeedKeeper")
        await self.gui.load_screen(scr)

        try:
            scr.set_step("Connecting to card...")
            conn = get_connection()
            conn.connect(conn.T1_protocol)

            scr.set_step("Authenticating...")
            session = open_session(conn, JCOP4_PROFILE)

            scr.set_step("Deleting applet...")
            sk_inst = unhexlify("536565644b656570657201")
            delete_aid(session, sk_inst)

            scr.set_step("Deleting package...")
            sk_pkg = unhexlify("536565644b6565706572")
            try:
                delete_aid(session, sk_pkg)
            except Exception:
                pass

            if silent:
                return
            scr.set_done()
            try:
                conn.disconnect()
            except Exception:
                pass
            await scr.result()
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            scr.set_error("Delete failed:\n%s" % str(e))
            await scr.result()

    def _firmware_note(self, include_details=False):
        primary_note = "Firmware version %s" % get_version()

        if not include_details:
            return primary_note

        sections = [primary_note]

        repo, branch, commit = get_git_info()
        repo_details = []
        if repo != "unknown":
            repo_details.append("Repo: %s" % repo)
        if branch != "unknown":
            repo_details.append("Branch: %s" % branch)
        if commit != "unknown":
            repo_details.append("Commit: %s" % commit)
        if repo_details:
            sections.append("\n".join(repo_details))

        def _format_status(value):
            if isinstance(value, str) and value:
                return value[0].upper() + value[1:]
            return value

        boot_mode = get_firmware_boot_mode()
        if boot_mode != "unknown":
            boot_mode_note = "Firmware mode: %s" % _format_status(boot_mode)
        else:
            boot_mode_note = "Firmware mode: Unknown"
        sections.append(boot_mode_note)

        read_protect = get_flash_read_protection_status()
        if read_protect != "unknown":
            read_note = "Read protection: %s" % _format_status(read_protect)
        else:
            read_note = "Read protection: Unknown"
        sections.append(read_note)

        write_protect = get_flash_write_protection_status()
        if write_protect != "unknown":
            write_note = "Write protection: %s" % _format_status(write_protect)
        else:
            write_note = "Write protection: Unknown"
        sections.append(write_note)

        build_type = get_build_type()
        if build_type == "unknown":
            build_note = "Build type: Unknown"
        else:
            build_note = "Build type: %s" % _format_status(build_type)
        sections.append(build_note)

        return "\n\n".join(sections)

    def start(self):
        # register battery monitor (runs every 3 seconds)
        self.gui.set_battery_callback(get_battery_status, 3000)
        # start the GUI
        self.gui.start()
        # register coroutines for all hosts
        for host in self.hosts:
            host.start(self)
        asyncio.run(self.setup())

    async def handle_exception(self, exception, next_fn):
        """
        Handle exception, show proper error message
        and return next function to call and await
        """
        self.gui.hide_loader()
        try:
            raise exception
        except CriticalErrorWipeImmediately as e:
            # show error
            await self.gui.error("Critical error, the device will be wiped.\n\n%s" % e)
            self.gui.show_loader(title="Wiping the device...")
            # wipe everything and reboot
            self.wipe()
        # catch an expected error
        except BaseError as e:
            # show error
            await self.gui.alert(e.NAME, "%s" % e)
            # restart
            return next_fn
        # show trace for unexpected errors
        except Exception as e:
            print(e)
            b = BytesIO()
            sys.print_exception(e, b)
            errmsg = "Something unexpected happened...\n\n"
            errmsg += b.getvalue().decode()
            await self.gui.error(errmsg)
            # restart
            return next_fn

    async def select_keystore(self):
        # if we have fixed keystore - just use it
        if len(self.keystores) == 1:
            self.keystore = self.keystores[0]()
            self._hil_set_keystore_ref(self.keystores[0])
            return
        # checking the first available keystore
        keystore_cls = None
        # show debug info screen if multiple keystores (e.g. MemoryCard + SeedKeeper)
        debug_screen = None
        connection = None
        for ks in self.keystores:
            if hasattr(ks, 'connection'):
                connection = ks.connection
                break
        poll_count = 0
        while keystore_cls is None:
            for keystore in self.keystores:
                if keystore.is_available():
                    keystore_cls = keystore
                    break
            if keystore_cls is None:
                # show debug screen on first iteration and every ~5s
                if debug_screen is None and connection is not None:
                    from keystore.javacard.card_scanner import scan_card_applets
                    debug_screen = DebugInfoScreen()
                    debug_screen.load()
                if debug_screen is not None and poll_count % 100 == 0:
                    from keystore.javacard.card_scanner import scan_card_applets
                    try:
                        info = scan_card_applets(connection)
                        debug_screen.update_info(info)
                    except Exception:
                        pass
                await asyncio.sleep_ms(50)
                poll_count += 1
        self.keystore = keystore_cls()
        self._hil_set_keystore_ref(keystore_cls)

    async def setup(self):
        # start HIL listener if in test mode
        if hil_test_mode:
            from debug_trace import log, log_exception
            self._hil_handler = self._init_hil_handler()
            if self._hil_handler is not None:
                asyncio.create_task(self._hil_listener())
            # Enable USBHost immediately in HIL mode for hardware testing
            # This must happen BEFORE unlock() so USB VCP is ready when tests run
            for host in self.hosts:
                if host.settings_button == "USB communication" and not host.is_enabled:
                    log("HIL", "Enabling USBHost early for hardware testing")
                    await host.enable()

        try:
            # check if the user already selected the keystore class
            if self.keystore is None:
                await self.select_keystore()

            if self.keystore is not None:
                self.load_network(self.path, self.network)

            # load secrets
            await self.keystore.init(self.gui.show_screen(), self.gui.show_loader)
            # unlock with PIN or set up the PIN code
            await self.unlock()
            # GP provisioning: check if card needs MemoryCard install
            await self._check_provisioning()
            # initialize apps if keystore loaded a key during unlock
            # (needed for keystores like SeedKeeper that auto-load mnemonic)
            if self.keystore.fingerprint is not None:
                self.init_apps()
                self.current_menu = self.mainmenu
        except Exception as e:
            if hil_test_mode:
                from debug_trace import log_exception
                log_exception("SETUP", e)
            next_fn = await self.handle_exception(e, self.setup)
            await next_fn()

        await self.main()

    def _init_hil_handler(self):
        """Initialize HIL command handler if available."""
        try:
            from hil import HILCommandHandler
            from debug_trace import log, log_exception
            import platform
            uart = platform.stlk
            handler = HILCommandHandler(uart, self.gui)
            log("HIL", "Handler initialized")
            return handler
        except Exception as e:
            log_exception("HIL", e)
            return None

    async def _hil_listener(self):
        """Listen for HIL test commands on debug UART."""
        from debug_trace import log, log_exception
        log("HIL", "Listener started")
        while True:
            await asyncio.sleep_ms(50)
            if self._hil_handler is not None:
                try:
                    self._hil_handler.poll()
                except Exception as e:
                    log_exception("HIL", e)

    async def host_exception_handler(self, e):
        try:
            raise e
        except HostError as ex:
            msg = "%s" % ex
        except:
            b = BytesIO()
            sys.print_exception(e, b)
            msg = b.getvalue().decode()
        await self.gui.error(msg, popup=True)

    def _hil_set_keystore_ref(self, keystore_cls):
        """Wire keystore reference for HIL test commands (fingerprint, mnemonic)."""
        if not hil_test_mode:
            return
        try:
            import hil
            hil.set_keystore_name(keystore_cls.NAME)
            hil.set_keystore_ref(self.keystore)
        except Exception:
            pass

    async def main(self):
        while True:
            try:
                # trigger garbage collector
                gc.collect()
                # show init menu and wait for the next menu
                # any menu returns next menu or
                # None if the same menu should be used
                next_menu = await self.current_menu()
                if next_menu is not None:
                    self.current_menu = next_menu

            except Exception as e:
                next_fn = await self.handle_exception(e, self.setup)
                await next_fn()

    def init_apps(self):
        for app in self.apps:
            app.init(self.keystore, self.network, self.gui.show_loader, self.cross_app_communicate)

    async def cross_app_communicate(self, stream, app:str=None, show_fn=None):
        if app == "": # root
            data = stream.read()
            if data.startswith(b"set_mnemonic "):
                mnemonic = data[len("set_mnemonic "):].decode()
                confirm = await self.gui.prompt(
                        "Load new mnemonic?",
                        "\nApp requested to load new mnemonic\n"
                        "Do you want to continue?\n\n"
                        "You will need to reboot the device to get back"
                        " to your current mnemonic.",
                )
                if confirm:
                    return self.set_mnemonic(mnemonic)
                else:
                    return True
            raise SpecterError("Invalid command '%s'" % data)
        return await self.process_host_request(stream, popup=False, appname=app, show_fn=show_fn)

    async def initmenu(self):
        # only enable passive hosts
        for host in self.hosts:
            if host.button:
                await host.enable()
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Generate new key"),
            (1, "Enter recovery phrase"),
            (777, "Import recovery phrase"),
        ]
        if self.keystore.is_key_saved and self.keystore.load_button:
            buttons.append((2, self.keystore.load_button))
        buttons += [(None, "Settings"), (3, "Device settings")]
        if self.keystore.storage_button is not None:
            buttons.append((4, self.keystore.storage_button))
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        if menuitem == 0:
            mnemonic = await self.gui.new_mnemonic(gen_mnemonic, bip39.WORDLIST, fix_mnemonic)
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                return self.set_mnemonic(mnemonic, "")
        # recover
        elif menuitem == 1:
            mnemonic = await self.gui.recover(
                bip39.mnemonic_is_valid, bip39.find_candidates, fix_mnemonic
            )
            if mnemonic is not None:
                # load keys using mnemonic and empty password
                return self.set_mnemonic(mnemonic, "")
        elif menuitem == 2:
            # try to load key, if user cancels -> return
            res = await self.keystore.load_mnemonic()
            if not res:
                return
            await self.gui.alert("Success!", "Key is loaded!")
            self.init_apps()
            return self.mainmenu
        elif menuitem == 3:
            await self.update_devsettings()
        elif menuitem == 4:
            res = await self.keystore.storage_menu()
            if res:
                self.init_apps()
                return self.mainmenu
        elif menuitem == 777:
            return await self.import_mnemonic()
        # lock device
        elif menuitem == 5:
            await self.lock()
            # go to PIN setup screen
            await self.unlock()
        else:
            print(menuitem, "menu is not implemented yet")
            raise SpecterError("Not implemented")

    async def import_mnemonic(self):
        host = await self.gui.menu(title="What to use for import?", note="\n",
            buttons=[(host, host.button) for host in self.hosts if host.is_enabled],
            last=(255, None))
        if host == 255:
            return
        stream = await host.get_data()
        if not stream:
            return
        data = stream.read()
        # digital mnemonic
        if len(data) >= 4*12 and len(data) <= 4*24 and len(data) % 12 == 0 and (b" " not in data):
            mnemonic = " ".join([bip39.WORDLIST[int(data[4*i:4*i+4])] for i in range(len(data)//4)])
        # binary mnemonic
        elif len(data) >= 16 and len(data) <= 32:
            mnemonic = bip39.mnemonic_from_bytes(data)
        # text mnemonic
        else:
            mnemonic = data.decode()
            # split on \n and \r to avoid double-scan
            mnemonic = mnemonic.split("\r")[0].split("\n")[0]
            if not bip39.mnemonic_is_valid(mnemonic):
                raise SpecterError("Invalid data: %r" % mnemonic)
        scr = MnemonicPrompt(title="Imported mnemonic:", mnemonic=mnemonic)
        # confirm mnemonic
        if not await self.gui.show_screen()(scr):
            return
        return self.set_mnemonic(mnemonic, "")

    def set_mnemonic(self, mnemonic, password=""):
        self.keystore.set_mnemonic(mnemonic.strip(), password)
        self.init_apps()
        self.current_menu = self.mainmenu
        return self.mainmenu

    async def mainmenu(self):
        # interactive hosts are enabled later
        for host in self.hosts:
            if not host.button:
                await host.enable()
        # buttons defined by host classes
        # only added if there is a GUI-triggered communication
        host_buttons = [
            (host, host.button) for host in self.hosts if host.button is not None and host.is_enabled
        ]
        # buttons defined by app classes
        app_buttons = [(app, app.button) for app in self.apps if app.button is not None]
        # for every button we use an ID
        # to avoid mistakes when editing strings
        # If ID is None - it is a section title, not a button
        buttons = (
            [
                # id, text
                (None, "Applications")
            ]
            + app_buttons
            + [(None, "Communication")]
            + host_buttons
            + [(None, "More")]  # delimiter
        )
        if hasattr(self.keystore, "lock"):
            buttons += [(2, "Lock device")]
        buttons += [(3, "Settings")]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons)

        # process the menu button:
        # lock device
        if menuitem == 2 and hasattr(self.keystore, "lock"):
            await self.lock()
            # go to the unlock screen
            await self.unlock()
        elif menuitem == 3:
            return await self.settingsmenu()
        elif isinstance(menuitem, BaseApp) and hasattr(menuitem, "menu"):
            app = menuitem
            # stay in this menu while something is returned
            while await app.menu(self.gui.show_screen()):
                pass
        # if it's a host
        elif isinstance(menuitem, Host) and hasattr(menuitem, "get_data"):
            host = menuitem
            stream = await host.get_data()
            # probably user cancelled
            if stream is not None:
                # check against all apps
                res = await self.process_host_request(stream, popup=False)
                if res not in [True, False, None]:
                    await host.send_data(*res)
        else:
            print(menuitem)
            raise SpecterError("Not implemented")

    async def settingsmenu(self):
        net = NETWORKS[self.network]["name"]
        buttons = [
            # id, text
            (None, "Network"),
            (5, "Switch network (%s)" % net),
            (None, "Key management"),
        ]
        if self.keystore.storage_button is not None:
            buttons.append((1, self.keystore.storage_button))
        buttons.append((2, "Enter passphrase"))
        if hasattr(self.keystore, "show_mnemonic"):
            buttons.append((3, "Show recovery phrase"))
        buttons.extend([(None, "Security"), (4, "Device settings")])  # delimiter
        buttons.extend([(None, "About"), (6, "About this device")])
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None), note=self._firmware_note())

        # process the menu button:
        # back button
        if menuitem == 255:
            return self.mainmenu
        elif menuitem == 1:
            res = await self.keystore.storage_menu()
            # storage_menu returns True if app reinit is required
            if res:
                self.init_apps()
        elif menuitem == 2:
            pwd = await self.gui.get_input()
            if pwd is None:
                return self.settingsmenu
            self.keystore.set_mnemonic(password=pwd)
            self.init_apps()
        elif menuitem == 3:
            await self.keystore.show_mnemonic()
        elif menuitem == 4:
            await self.update_devsettings()
        elif menuitem == 5:
            await self.select_network()
        elif menuitem == 6:
            await self.show_about()
        else:
            print(menuitem)
            raise SpecterError("Not implemented")
        return self.settingsmenu

    async def select_network(self):
        buttons = [
            (None, "Production"),
            ("main", "Bitcoin Mainnet"),
            ("liquidv1", "Liquid Mainnet"),
            (None, "Testnets"),
            ("test", "Testnet"),
            ("signet", "Signet"),
            ("regtest", "Regtest"),
            ("liquidtestnet", "Liquid Testnet"),
            ("elementsregtest", "Liquid Regtest"),
        ]
        # wait for menu selection
        menuitem = await self.gui.menu(buttons, last=(255, None))
        if menuitem != 255:
            self.set_network(menuitem)

    def set_network(self, net):
        if net not in NETWORKS:
            net = 'main'
        self.network = net
        self.gui.set_network(net)
        # save
        with open(self.path + "/network", "w") as f:
            f.write(net)
        if self.keystore.is_ready:
            # load wallets for this network
            self.init_apps()

    def load_network(self, path, network="main"):
        try:
            with open(path + "/network", "r") as f:
                network = f.read()
        except:
            pass
        self.set_network(network)

    async def show_about(self):
        await self.gui.alert(
            "About this device",
            self._firmware_note(include_details=True),
            button_text="Close",
        )

    async def communication_settings(self):
        buttons = [
            (None, "Communication channels")
        ] + [
            (host, host.settings_button)
            for host in self.hosts
            if host.settings_button is not None
        ]
        while True:
            menuitem = await self.gui.menu(buttons,
                                      title="Communication settings",
                                      note=self._firmware_note(),
                                      last=(255, None)
            )
            if menuitem == 255:
                return
            elif isinstance(menuitem, Host):
                reboot_required = await menuitem.settings_menu(self.gui.show_screen(), self.keystore)
                if reboot_required:
                    if await self.gui.prompt(
                        "Reboot required!",
                        "Settings have been updated and will become active after reboot.\n\n"
                        "Do you want to reboot now?",
                    ):
                        reboot()
            else:
                print(menuitem)
                raise SpecterError("Not implemented")

    @property
    def settings_fname(self):
        return self.SETTINGS_DIR+"/global.settings"

    def load_settings(self, fname=None):
        settings = {}
        try:
            if fname is None:
                fname = self.settings_fname
            adata, _ = self.keystore.load_aead(fname, key=self.keystore.settings_key)
            settings = json.loads(adata.decode())
        except Exception as e:
            print(e)
        return settings

    def save_settings(self, settings, fname=None):
        maybe_mkdir(self.SETTINGS_DIR)
        if fname is None:
            fname = self.settings_fname
        self.keystore.save_aead(fname,
                           adata=json.dumps(settings).encode(),
                           key=self.keystore.settings_key
        )

    async def experimental_settings(self):

        controls = [{
            "label": "Taproot",
            "hint": "Taproot support only for single-key wallets\nwithout tap script trees",
            "value": self.GLOBAL.get("experimental", {}).get("taproot", False)
        }]

        scr = HostSettings(
            controls,
            title="Experimental features",
            note="Experimental features are unstable,\n"
            "only enable them if you really want to try.\n"
            "Report developers in case of any issues.",
        )
        res = await self.gui.show_screen()(scr)
        if res is None:
            return
        taproot, *_ = res
        # for now only experimental, can be extended
        settings = {
            "experimental": {
                "taproot": taproot,
            }
        }
        self.GLOBAL = settings
        BaseApp.GLOBAL = settings
        self.save_settings(settings)

    async def update_devsettings(self):
        buttons = [
            (None, "Categories")
        ] + [
            (1, "Communication"),
            # (2, "Applications"),
            # (3, "Experimental"),
        ] + [
            (None, "Global settings"),
            (42, "About this device"),
        ]
        if hasattr(self.keystore, "lock"):
            buttons.extend([(777, "Change PIN code")])
        buttons += [
            (888, "JavaCard Provisioning"),
            (456, "Reboot"),
            (123, "Wipe the device", True, 0x951E2D),
        ]
        while True:
            menuitem = await self.gui.menu(buttons,
                                      title="Device settings",
                                      note=self._firmware_note(),
                                      last=(255, None)
            )
            if menuitem == 255:
                return
            elif menuitem == 3:
                await self.experimental_settings()
            elif menuitem == 456:
                if await self.gui.prompt(
                    "Reboot the device?",
                    "\n\nAre you sure?",
                ):
                    reboot()
                return
            # WIPE
            elif menuitem == 123:
                if await self.gui.prompt(
                    "Wiping the device will erase everything in the internal storage!",
                    "This includes multisig wallet files, keys, apps data etc.\n\n"
                    "But it doesn't include files stored on SD card or smartcard.\n\n"
                    "Are you sure?",
                ):
                    self.wipe()
                return
            elif menuitem == 777:
                await self.keystore.change_pin()
                return
            elif menuitem == 42:
                await self.show_about()
                return
            elif menuitem == 1:
                await self.communication_settings()
            elif menuitem == 888:
                await self._provisioning_menu()
                return
            else:
                print(menuitem)
                raise SpecterError("Not implemented")

    @property
    def fingerprint(self):
        return self.keystore.fingerprint

    def wipe(self):
        # TODO: wipe the smartcard as well?
        # platform.wipe
        wipe()

    async def lock(self):
        # lock the keystore
        if hasattr(self.keystore, "lock"):
            self.keystore.lock()
        # disable hosts
        for host in self.hosts:
            await host.disable()

    async def unlock(self):
        """
        - setup PIN if not set
        - enter PIN if set
        """
        await self.keystore.unlock()
        # now keystore is unlocked - we can load hosts configs
        for host in self.hosts:
            host.load_settings(self.keystore)
        settings = self.load_settings()
        self.GLOBAL = settings
        BaseApp.GLOBAL = settings

    async def maybe_import_mnemonic(self, stream, popup=False, show_fn=None):
        if show_fn is None:
            show_fn = self.gui.show_screen(popup)
        data = stream.read(240) # one word is at most 8 chars, so total len is < 240 even if it has prefix of some kind (for future)
        mnemonic_type = ""
        # digital mnemonic
        d = data.strip()
        if len(d) >= 4*12 and len(d) <= 4*24 and len(d) % 12 == 0 and (b" " not in d):
            mnemonic = " ".join([bip39.WORDLIST[int(d[4*i:4*i+4])] for i in range(len(d)//4)])
            mnemonic_type = "digital"
        # binary mnemonic
        elif len(data) >= 16 and len(data) <= 32:
            mnemonic = bip39.mnemonic_from_bytes(data)
            mnemonic_type = "binary"
        # text mnemonic
        else:
            mnemonic = data.decode()
            # split on \n and \r to avoid double-scan
            mnemonic = mnemonic.split("\r")[0].split("\n")[0]
            if not bip39.mnemonic_is_valid(mnemonic):
                raise SpecterError("Invalid data: %r" % mnemonic)
            mnemonic_type = "text"
        scr = MnemonicPrompt(title="Imported mnemonic:", mnemonic=mnemonic, note="Data looks like a %s mnemonic.\nDo you want to use it?" % mnemonic_type)
        # confirm mnemonic
        if not await show_fn(scr):
            return
        self.keystore.set_mnemonic(mnemonic, "")
        self.init_apps()

    async def process_host_request(self, stream, popup=True, appname=None, show_fn=None):
        """
        This method is called whenever we got data from the host.
        It tries to find a proper app and pass the stream with data to it.
        """
        self.gui.show_loader(title="Processing host data...")
        res = None
        if show_fn is None:
            show_fn = self.gui.show_screen(popup)
        try:
            matching_apps = []
            if appname is not None:
                for app in self.apps:
                    if app.name == appname:
                        matching_apps.append(app)
            else:
                for app in self.apps:
                    stream.seek(0)
                    # check if the app can process this stream
                    if app.can_process(stream):
                        matching_apps.append(app)
            if len(matching_apps) == 0:
                stream.seek(0)
                try:
                    await self.maybe_import_mnemonic(stream, popup, show_fn)
                    return
                except Exception as e:
                    print(e)
                    raise HostError("Can't find matching app for this request:\n\n %r" % stream.read(100))
            # TODO: if more than one - ask which one to use
            if len(matching_apps) > 1:
                raise HostError(
                    "Not sure what app to use...\n\nThere are %d" % len(matching_apps)
                )
            stream.seek(0)
            app = matching_apps[0]
            res = await app.process_host_command(stream, show_fn)
        except Exception as e:
            if isinstance(e, BaseError):
                # error that has a meaningfull message, will be sent to the host
                raise HostError(str(e))
            else:
                # converted to "unknown error" on the host
                raise e
        finally:
            self.gui.hide_loader()
        return res
