from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.seedkeeper_applet import SeedKeeperApplet
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
    SeedKeeper is a read-only keystore - secrets are generated and stored
    on the card, not saved from the device.
    Inherits directly from RAMKeyStore with inline connection management.
    """

    NAME = "SeedKeeper"
    COLOR = "FF8C00"
    NOTE = "Loads Bitcoin key from a SeedKeeper smartcard (requires devkit)."
    # Button to go to storage menu
    storage_button = "SeedKeeper storage"
    load_button = "Load key from SeedKeeper"
    # javacard connection (shared class-level)
    connection = get_connection()

    def __init__(self):
        super().__init__()
        # applet instance
        self.applet = SeedKeeperApplet(self.connection)
        # connection state
        self.connected = False
        self._pin_unlocked = False
        # SeedKeeper-specific state
        self.wallet_label = "SeedKeeper"
        self.selected_secret_id = None
        self._is_key_saved = False

    @classmethod
    def is_available(cls):
        """Check if SeedKeeper card is available and responsive."""
        if not cls.connection.isCardInserted():
            return False
        try:
            cls.connection.connect(cls.connection.T1_protocol)
            applet = SeedKeeperApplet(cls.connection)
            applet.select()
            # get_card_status() does NOT require secure channel
            applet.get_card_status()
            cls.connection.disconnect()
            return True
        except Exception as e:
            print(e)
            try:
                cls.connection.disconnect()
            except:
                pass
            return False

    @property
    def is_pin_set(self):
        """SeedKeeper always has PIN set."""
        return True

    @property
    def pin_attempts_left(self):
        """Get remaining PIN attempts from card status."""
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                return resp_data[4]
        except Exception:
            pass
        return None

    @property
    def pin_attempts_max(self):
        """Maximum PIN attempts (standard is 5)."""
        return 5

    @property
    def is_locked(self):
        """Returns True if PIN has not been verified yet."""
        return not self._pin_unlocked

    @property
    def is_ready(self):
        """Returns True if connected, unlocked, and has fingerprint."""
        return (
            self.connected
            and self._pin_unlocked
            and self.fingerprint is not None
        )

    def _unlock(self, pin):
        """
        Unlock the keystore with PIN.
        Raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        try:
            success, attempts = self.applet.verify_pin(pin)
            self._pin_unlocked = True
            # Set enc_secret after PIN verification
            self.enc_secret = tagged_hash('enc', self.secret)
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

    def lock(self):
        """Lock the keystore (PIN required to unlock)."""
        self._pin_unlocked = False

    async def check_card(self, check_pin=False):
        """Check card presence and connect if needed."""
        if not self.connection.isCardInserted():
            # wait for card
            scr = Progress(
                "SeedKeeper card not inserted",
                "Please insert the SeedKeeper card...",
                button_text="",
            )
            asyncio.create_task(self.wait_for_card(scr))
            await self.show(scr)

        # only required if not connected yet
        if not self.connected:
            self.show_loader(title="Connecting to the card...")
            try:
                self.connection.connect(self.connection.T1_protocol)
            except:
                raise KeyStoreError("Failed to communicate with the card.")
            try:
                self.applet.select()
            except:
                raise KeyStoreError("Failed to select the applet")

            self.show_loader(title="Establishing secure channel...")
            self.applet.init_secure_channel()
            self.connected = True

        if check_pin and self.is_locked:
            pin = await self.get_pin()
            self._unlock(pin)

    async def wait_for_card(self, scr):
        """Wait for card insertion."""
        while not self.connection.isCardInserted():
            await asyncio.sleep_ms(30)
            scr.tick(5)
        if scr.waiting:
            scr.waiting = False

    async def init(self, show_fn, show_loader):
        """
        Waits for keystore media
        and loads internal secret and PIN state
        """
        self.show_loader = show_loader
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)

        await self.check_card()
        # the rest can be done with parent
        await super().init(show_fn, show_loader)

    async def unlock(self):
        """Override: prompt for PIN via touchscreen, then auto-load mnemonic."""
        # Establish secure channel before PIN verification
        await self.check_card(check_pin=False)

        # Query card for PIN attempts remaining
        pin_attempts = self.pin_attempts_left

        # PIN prompt loop with error handling
        while self.is_locked:
            note = None
            if pin_attempts is not None:
                note = "%d PIN attempts remaining" % pin_attempts

            pin = await self.get_pin(
                subtitle="SeedKeeper card detected",
                note=note,
            )
            self.show_loader('Verifying PIN code...')
            try:
                self._unlock(pin)
            except PinError as e:
                await self.show(Alert('PIN Error', str(e)))
                pin_attempts = self.pin_attempts_left
                continue

        print('[SeedKeeper] PIN verified successfully')

        # Multi-secret support: list and select BIP39-capable secrets
        try:
            headers = self.applet.list_secret_headers()
            bip39_headers = [
                h for h in headers
                if h['type'] in (0x10, 0x30, 0x31)
                and (h['type'] != 0x10 or h.get('subtype') == 1)
            ]
            print('[SeedKeeper] Found %d BIP39 secrets' % len(bip39_headers))

            if len(bip39_headers) == 0:
                await self.show(Alert('Error', 'No BIP39 secrets found on card'))
                return

            elif len(bip39_headers) == 1:
                selected = bip39_headers[0]
            else:
                # Show menu for multi-secret selection
                buttons = [(h['id'], h['label'] if h['label'] else 'Secret #%d' % h['id']) for h in bip39_headers]
                selected_id = await self.show(Menu(buttons, title='Select secret'))
                selected = next(h for h in bip39_headers if h['id'] == selected_id)

            self.selected_secret_id = selected['id']
            print('[SeedKeeper] Selected secret id:', selected['id'])

            # Load mnemonic from selected secret
            self.show_loader('Loading mnemonic from card...')
            mnemonic = self.applet.get_bip39_secret(secret_id=selected['id'], secret_type=selected['type'])
            self.set_mnemonic(mnemonic, "")
            self._is_key_saved = True
            print('[SeedKeeper] Mnemonic loaded successfully')

        except AppletException as e:
            await self.show(Alert('Error', 'Failed to load key from card:\n%s' % str(e)))

    async def load_mnemonic(self):
        """Load mnemonic from SeedKeeper card."""
        await self.check_card(check_pin=True)
        self.show_loader("Loading secret from the card...")

        try:
            headers = self.applet.list_secret_headers()
            bip39_headers = [
                h for h in headers
                if h['type'] in (0x10, 0x30, 0x31)
                and (h['type'] != 0x10 or h.get('subtype') == 1)
            ]

            if len(bip39_headers) == 0:
                await self.show(Alert('Error', 'No BIP39 secrets found on card'))
                return False

            elif len(bip39_headers) == 1:
                selected = bip39_headers[0]
            else:
                buttons = [(h['id'], h['label'] if h['label'] else 'Secret #%d' % h['id']) for h in bip39_headers]
                selected_id = await self.show(Menu(buttons, title='Select secret', last=(255, None)))
                if selected_id == 255:
                    return False
                selected = next(h for h in bip39_headers if h['id'] == selected_id)

            self.selected_secret_id = selected['id']
            mnemonic = self.applet.get_bip39_secret(secret_id=selected['id'], secret_type=selected['type'])
            self.set_mnemonic(mnemonic, "")
            self._is_key_saved = True
            return True

        except AppletException as e:
            await self.show(Alert('Error', 'Failed to load key from card:\n%s' % str(e)))
            return False

    async def save_mnemonic(self):
        """SeedKeeper is read-only - cannot save mnemonic to card."""
        await self.show(Alert(
            "Read-only",
            "SeedKeeper is a read-only device.\n"
            "Keys are generated and stored on the card."
        ))
        raise KeyStoreError("SeedKeeper is read-only")

    @property
    def is_key_saved(self):
        """Check if a key is available on the card."""
        return self._is_key_saved

    async def storage_menu(self):
        """Manage storage, return True if new key was loaded."""
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
        """Display detailed card information."""
        try:
            props = []

            # Get card label if available
            card_label = None
            try:
                card_label = self.applet.get_card_label()
            except Exception as e:
                print('[SeedKeeper] Card label not available:', e)

            # Platform info
            props.extend([
                "\n#7f8fa4 PLATFORM #",
                "Implementation: %s" % self.applet.platform,
                "Version: %s v%s" % (self.applet.NAME, self.applet.version),
            ])

            if card_label:
                props.append("Card label: %s" % card_label)

            # Get detailed card status (requires secure channel + PIN)
            if self._pin_unlocked:
                try:
                    status = self.applet.get_seedkeeper_status()
                    if status:
                        props.extend([
                            "\n#7f8fa4 STORAGE INFO #",
                            "Secrets stored: %d" % status.get('nb_secrets', 0),
                        ])

                        total_mem = status.get('total_memory', 0)
                        free_mem = status.get('free_memory', 0)
                        if total_mem > 0:
                            used_mem = total_mem - free_mem
                            props.append("Memory used: %d / %d bytes" % (used_mem, total_mem))
                except Exception as e:
                    print('[SeedKeeper] Failed to get status:', e)

            scr = Alert("SeedKeeper info", "\n\n".join(props))
            scr.message.set_recolor(True)
            await self.show(scr)
        except Exception as e:
            await self.show(Alert("Error", "Failed to get card info:\n%s" % str(e)))
