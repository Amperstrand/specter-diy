from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.seedkeeper_applet import SeedKeeperApplet
from .javacard.applets.applet import ISOException, AppletException
from .javacard.util import get_connection
from platform import CriticalErrorWipeImmediately
import asyncio
from gui.screens import Alert, Progress, Menu, Prompt, PinScreen


class SeedKeeper(RAMKeyStore):
    """
    KeyStore that loads secrets from a SeedKeeper smartcard.
    SeedKeeper is a read-only keystore - secrets are generated and stored
    on the card, not saved from the device.
    """

    NAME = "SeedKeeper"
    COLOR = "FF8C00"
    NOTE = "Loads Bitcoin key from a SeedKeeper smartcard (requires devkit)."
    # Button to go to storage menu
    storage_button = "SeedKeeper storage"
    load_button = "Open SeedKeeper card"
    # javacard connection
    connection = get_connection()

    def __init__(self):
        super().__init__()
        # applet
        self.applet = SeedKeeperApplet(self.connection)
        self._pin_unlocked = False
        self.connected = False

    @classmethod
    def is_available(cls):
        """Check if SeedKeeper card is available and responsive."""
        if not cls.connection.isCardInserted():
            return False
        try:
            cls.connection.connect(cls.connection.T1_protocol)
            applet = SeedKeeperApplet(cls.connection)
            applet.select()
            # Check card status (byte 11 = needs_secure_channel flag)
            # get_card_status() does NOT require secure channel
            applet.get_card_status()
            cls.connection.disconnect()
            return True
        except Exception as e:
            print(e)
            cls.connection.disconnect()
            return False

    @property
    def is_pin_set(self):
        """SeedKeeper always has PIN set."""
        return True

    @property
    def is_locked(self):
        """Returns True if PIN has not been verified yet."""
        return not self._pin_unlocked

    @property
    def is_ready(self):
        """Returns True if connected, unlocked, and has a fingerprint."""
        return self.connected and self._pin_unlocked and self.fingerprint is not None

    def _unlock(self, pin):
        """
        Unlock the keystore by verifying PIN on the card.
        Raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        try:
            success, attempts = self.applet.verify_pin(pin)
            if success:
                self._pin_unlocked = True
                return
            # Not successful - this shouldn't happen as verify_pin raises on failure
            if attempts is not None:
                raise PinError("Invalid PIN!\n%d attempts left..." % attempts)
        except ISOException as e:
            # Handle specific ISO exceptions based on status word
            sw = str(e).lower()
            # Card is bricked - no more attempts
            if sw == "9c0c" or sw == "6983":
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            # Wrong PIN: SW = 63Cx where x = remaining attempts
            if sw.startswith("63c") and len(sw) == 4:
                try:
                    attempts_left = int(sw[3], 16)
                except ValueError:
                    attempts_left = None
                if attempts_left is not None:
                    raise PinError(
                        "Invalid PIN!\n%d attempts left..." % attempts_left
                    )
                raise PinError("Invalid PIN!")
            # Any other ISO error is unexpected here
            raise
        except AppletException as e:
            # Handle applet-level exceptions
            if "6983" in str(e) or "9c0c" in str(e):
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            raise
    async def unlock(self):
        """Override: after PIN verification, auto-load first secret."""
        await super().unlock()
        # PIN verified — auto-load first secret from card
        try:
            self.show_loader("Loading secret from the card...")
            mnemonic = self.applet.get_bip39_secret()
            self.set_mnemonic(mnemonic, "")
            print("[SeedKeeper] Key loaded automatically after PIN")
        except Exception as e:
            print("[SeedKeeper] Auto-load failed:", e)
            # Fall through to initmenu — user can retry manually

    async def check_card(self, check_pin=False):
        """Check card presence and connect if needed."""
        if not self.connection.isCardInserted():
            # wait for card
            scr = Progress(
                "SeedKeeper card not inserted",
                "Please insert the SeedKeeper card...",
                button_text="",
            )  # no button - empty string means no button
            asyncio.create_task(self.wait_for_card(scr))
            await self.show(scr)

        # SeedKeeperApplet doesn't have ping, check card presence via connection
        # If not connected, we'll reconnect
        if not self.connected:
            self.show_loader(title="Connecting to the card...")
            # connect and select applet
            try:
                self.connection.connect(self.connection.T1_protocol)
            except:
                raise KeyStoreError("Failed to communicate with the card.")
            try:
                self.applet.select()
            except:
                raise KeyStoreError("Failed to select the applet")

            # CRITICAL: select() MUST be called BEFORE init_secure_channel(). NEVER after.
            # SELECT resets secure channel, so the order is:
            # connect → select → get_card_status() → init_secure_channel()
            self.show_loader(title="Establishing secure channel...")
            self.applet.init_secure_channel()

            self.connected = True

        # Verify applet is responsive
        self.applet.get_seedkeeper_status()

        if check_pin and not self._pin_unlocked:
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

        await self.check_card()
        # the rest can be done with parent
        await super().init(show_fn, show_loader)

    async def load_mnemonic(self):
        """Load mnemonic from SeedKeeper card."""
        await self.check_card(check_pin=True)
        self.show_loader("Loading secret from the card...")
        mnemonic = self.applet.get_bip39_secret()
        self.set_mnemonic(mnemonic, "")
        print("[SeedKeeper] Loaded mnemonic successfully")
        return True

    async def save_mnemonic(self):
        """SeedKeeper is read-only - cannot save mnemonic to card."""
        raise KeyStoreError("SeedKeeper is read-only")

    @property
    def is_key_saved(self):
        """SeedKeeper always has a key saved (on the card)."""
        return self._pin_unlocked

    async def get_pin(self, title="Enter your PIN code", with_cancel=False):
        """
        Override to NOT pass get_word parameter.
        SeedKeeper doesn't support anti-phishing words.
        """
        scr = PinScreen(title=title, note=None, get_word=None, with_cancel=with_cancel)
        return await self.show(scr)

    async def storage_menu(self):
        """Manage storage, return True if new key was loaded."""
        enabled = self.connection.isCardInserted()
        buttons = [
            # id, text, enabled, color
            (None, "SeedKeeper storage"),
            (0, "Load key from SeedKeeper", enabled),
            (1, "Card info", enabled),
        ]

        # we stay in this menu until back is pressed
        while True:
            # wait for menu selection
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            # process the menu button:
            # back button
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
        """Display card information."""
        try:
            status = self.applet.get_seedkeeper_status()
            props = [
                "\n#7f8fa4 CARD INFO: #",
                "Card name: SeedKeeper",
                "Secrets stored: %d" % status.get("nb_secrets", 0),
            ]
            scr = Alert("SeedKeeper info", "\n\n".join(props))
            scr.message.set_recolor(True)
            await self.show(scr)
        except Exception as e:
            await self.show(Alert("Error", "Failed to get card info:\n%s" % str(e)))
