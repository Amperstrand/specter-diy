from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.seedkeeper_applet import SeedKeeperApplet, _is_bip39_header
from .javacard.applets.applet import AppletException
from .javacard.util import get_connection
from platform import CriticalErrorWipeImmediately
import platform
from helpers import tagged_hash
from gui.screens import Alert, Progress, Menu
import asyncio


class SeedKeeper(RAMKeyStore):
    """
    KeyStore that loads secrets from a SeedKeeper smartcard.
    Read-only — secrets are generated and stored on the card, not saved from the device.
    Multi-secret — card can hold multiple BIP39 secrets; user selects which to use.

    Mirrors MemoryCard architecture: extends RAMKeyStore, manages its own
    applet and connection, implements the same keystore interface.
    """

    NAME = "SeedKeeper"
    COLOR = "FF8C00"
    NOTE = "Loads Bitcoin key from a SeedKeeper smartcard (requires devkit)."
    storage_button = "SeedKeeper storage"
    load_button = "Load key from SeedKeeper"

    connection = get_connection()

    def __init__(self):
        super().__init__()
        self.applet = SeedKeeperApplet(self.connection)
        self.connected = False
        self._pin_unlocked = False
        self.selected_secret_id = None
        self._is_key_saved = False

    @classmethod
    def is_available(cls):
        import time
        time.sleep_ms(20)
        if not cls.connection.isCardInserted():
            return False
        try:
            cls.connection.connect(cls.connection.T1_protocol)
            applet = SeedKeeperApplet(cls.connection)
            applet.select()
            applet.get_card_status()
            cls.connection.disconnect()
            return True
        except Exception:
            try:
                cls.connection.disconnect()
            except Exception:
                pass
            return False

    @property
    def is_pin_set(self):
        return True

    @property
    def pin_attempts_left(self):
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                return resp_data[4]
        except Exception:
            pass
        return None

    @property
    def pin_attempts_max(self):
        return 5

    @property
    def is_locked(self):
        return not self._pin_unlocked

    @property
    def is_ready(self):
        return self.connected and self._pin_unlocked and self.fingerprint is not None

    def _unlock(self, pin):
        try:
            success, attempts = self.applet.verify_pin(pin)
            if success:
                self._pin_unlocked = True
                self.enc_secret = tagged_hash('enc', self.secret)
                return
        except Exception as e:
            err = str(e)
            if err == "9c02":  # wrong PIN
                attempts = self.pin_attempts_left
                if attempts is not None and attempts == 0:
                    raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
                raise PinError(
                    "Invalid PIN!\n%d of %d attempts left..."
                    % (attempts or 0, self.pin_attempts_max)
                )
            elif err == "9c03":  # bricked
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            else:
                raise e

    def _change_pin(self, old_pin, new_pin):
        try:
            self.applet.change_pin(old_pin, new_pin)
        except Exception as e:
            err_str = str(e).lower()
            if '63c' in err_str or 'wrong' in err_str or 'invalid' in err_str:
                raise PinError("Invalid old PIN!")
            raise KeyStoreError("Failed to change PIN: %s" % e)

    def lock(self):
        self._pin_unlocked = False

    async def check_card(self, check_pin=False):
        try:
            from platform import hil_test_mode
        except Exception:
            hil_test_mode = False
        if not self.connection.isCardInserted():
            scr = Progress(
                "SeedKeeper card not inserted",
                "Please insert the SeedKeeper card...",
                button_text="",
            )
            asyncio.create_task(self.wait_for_card(scr))
            await self.show(scr)

        if not self.connected:
            self.show_loader(title="Connecting to the card...")
            if hil_test_mode:
                from debug_trace import log
                log("SK", "check_card: connecting...")
            try:
                self.connection.connect(self.connection.T1_protocol)
            except Exception as e:
                if hil_test_mode:
                    log("SK", "check_card: connect failed: %s" % e)
                raise KeyStoreError("Failed to communicate with the card.")
            try:
                self.applet.select()
            except Exception as e:
                if hil_test_mode:
                    log("SK", "check_card: select failed: %s" % e)
                raise KeyStoreError("Failed to select the applet")
            if hil_test_mode:
                log("SK", "check_card: initiating secure channel...")
            self.show_loader(title="Establishing secure channel...")
            self.applet.init_secure_channel()
            if hil_test_mode:
                log("SK", "check_card: secure channel established")
            self.connected = True

        if check_pin and self.is_locked:
            pin = await self.get_pin()
            self._unlock(pin)

    async def wait_for_card(self, scr):
        while not self.connection.isCardInserted():
            await asyncio.sleep_ms(30)
            scr.tick(5)
        if scr.waiting:
            scr.waiting = False

    async def init(self, show_fn, show_loader):
        self.show_loader = show_loader
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)
        await self.check_card()
        await super().init(show_fn, show_loader)

    async def get_pin(self, title="Enter your PIN code", with_cancel=False, note=None):
        from gui.screens import PinScreen
        scr = PinScreen(
            title=title,
            note=note if note else "Do you recognize these words?",
            get_word=None,
            subtitle="SeedKeeper card detected",
            with_cancel=with_cancel,
        )
        return await self.show(scr)

    async def unlock(self):
        await self.check_card(check_pin=False)

        pin_attempts = self.pin_attempts_left

        while self.is_locked:
            note = None
            if pin_attempts is not None:
                note = "%d PIN attempts remaining" % pin_attempts

            pin = await self.get_pin(note=note)
            self.show_loader('Verifying PIN code...')
            try:
                self._unlock(pin)
            except PinError as e:
                await self.show(Alert('PIN Error', str(e)))
                pin_attempts = self.pin_attempts_left
                continue

        selected = await self._select_bip39_secret()
        self.selected_secret_id = selected['id']
        self.show_loader('Loading mnemonic from card...')
        mnemonic = self.applet.get_bip39_secret(selected['id'], selected['type'])
        self.set_mnemonic(mnemonic, "")
        self._is_key_saved = True

    async def _select_bip39_secret(self):
        """List BIP39 secrets on card, let user select if multiple.
        Returns the selected header dict.
        """
        headers = self.applet.list_secret_headers()
        bip39 = [h for h in headers if _is_bip39_header(h)]

        if len(bip39) == 0:
            raise KeyStoreError("No BIP39 secrets found on card")
        if len(bip39) == 1:
            return bip39[0]

        buttons = [
            (h['id'], h.get('label') or 'Secret #%d' % h['id'])
            for h in bip39
        ]
        selected_id = await self.show(Menu(buttons, title='Select secret', last=(255, None)))
        if selected_id == 255:
            raise KeyStoreError("Secret selection cancelled")
        return next(h for h in bip39 if h['id'] == selected_id)

    async def load_mnemonic(self):
        await self.check_card(check_pin=True)
        self.show_loader("Loading secret from the card...")

        try:
            selected = await self._select_bip39_secret()
            self.selected_secret_id = selected['id']
            mnemonic = self.applet.get_bip39_secret(selected['id'], selected['type'])
            self.set_mnemonic(mnemonic, "")
            self._is_key_saved = True
            return True
        except AppletException as e:
            await self.show(Alert('Error', 'Failed to load key from card:\n%s' % str(e)))
            return False
        except KeyStoreError as e:
            await self.show(Alert('Error', str(e)))
            return False

    async def save_mnemonic(self):
        await self.show(Alert(
            "Read-only",
            "SeedKeeper is a read-only device.\n"
            "Keys are generated and stored on the card."
        ))
        raise KeyStoreError("SeedKeeper is read-only")

    @property
    def is_key_saved(self):
        return self._is_key_saved

    async def storage_menu(self):
        enabled = self.connection.isCardInserted()
        buttons = [
            (None, "SeedKeeper storage"),
            (0, "Load key from SeedKeeper", enabled),
            (1, "Card info", enabled),
        ]

        while True:
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            if menuitem == 255:
                return False
            elif menuitem == 0:
                await self.load_mnemonic()
                await self.show(
                    Alert("Success!", "Your key is loaded from SeedKeeper.", button_text="OK")
                )
                return True
            elif menuitem == 1:
                await self.show_card_info()
            else:
                raise KeyStoreError("Invalid menu")

    async def show_card_info(self):
        try:
            props = []

            card_label = None
            try:
                card_label = self.applet.get_card_label()
            except Exception:
                pass

            props.extend([
                "\n#7f8fa4 PLATFORM #",
                "Implementation: %s" % self.applet.platform,
                "Version: %s v%s" % (self.applet.NAME, self.applet.version),
            ])
            if card_label:
                props.append("Card label: %s" % card_label)

            status = self.applet.get_seedkeeper_status()
            if status:
                props.extend([
                    "\n#7f8fa4 STORAGE INFO #",
                    "Secrets stored: %d" % status.get('nb_secrets', 0),
                ])
                total_mem = status.get('total_memory', 0)
                free_mem = status.get('free_memory', 0)
                if total_mem > 0:
                    props.append("Memory used: %d / %d bytes" % (total_mem - free_mem, total_mem))

            try:
                headers = self.applet.list_secret_headers()
                secret_types = {}
                for h in headers:
                    t = h['type']
                    if t not in secret_types:
                        secret_types[t] = []
                    secret_types[t].append(h)

                if secret_types:
                    type_names = {
                        0x10: "Masterseed", 0x30: "BIP39", 0x31: "BIP39 v2",
                        0x40: "Electrum", 0x50: "Shamir", 0x90: "Password",
                        0xC0: "Data", 0xC1: "Descriptor",
                    }
                    props.append("\n#7f8fa4 SECRETS BY TYPE #")
                    for t, secrets in sorted(secret_types.items()):
                        tname = type_names.get(t, "0x%02X" % t)
                        props.append("%s: %d" % (tname, len(secrets)))
            except Exception:
                pass

            scr = Alert("SeedKeeper info", "\n\n".join(props))
            scr.message.set_recolor(True)
            await self.show(scr)
        except Exception as e:
            await self.show(Alert("Error", "Failed to get card info:\n%s" % str(e)))
