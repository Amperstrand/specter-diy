from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.satochip_applet import SatochipApplet
from .javacard.applets.applet import ISOException, AppletException
from .javacard.util import get_connection
from platform import CriticalErrorWipeImmediately
import asyncio
from gui.screens import Alert, Progress, Menu, Prompt, PinScreen


class Satochip(RAMKeyStore):
    """
    KeyStore that loads secrets from a Satochip smartcard.
    Satochip is a hardware wallet that keeps the mnemonic secure on the card.
    First milestone: detection, PIN verification, fingerprint display only.
    """

    NAME = "Satochip"
    COLOR = "4CAF50"  # Green
    NOTE = "Loads Bitcoin key from a Satochip hardware wallet (requires devkit)."
    # Button to go to storage menu
    storage_button = "Satochip storage"
    load_button = "Open Satochip card"
    # javacard connection
    connection = get_connection()

    def __init__(self):
        super().__init__()
        # applet
        self.applet = SatochipApplet(self.connection)
        self._pin_unlocked = False
        self.connected = False
        self.wallet_label = "Satochip"

    @classmethod
    def is_available(cls):
        """Check if Satochip card is available and responsive."""
        print('[BootTrace][Satochip] is_available() called')
        if not cls.connection.isCardInserted():
            return False
        try:
            import time
            time.sleep_ms(20)  # Give card time to stabilize after previous disconnect
            cls.connection.connect(cls.connection.T1_protocol)
            applet = SatochipApplet(cls.connection)
            applet.select()
            applet.get_card_status()  # Non-secure check
            cls.connection.disconnect()
            print('[BootTrace][Satochip] is_available = True')
            return True
        except Exception as e:
            print('[BootTrace][Satochip] Probe failed:', e)
            cls.connection.disconnect()
            return False
    @property
    def is_pin_set(self):
        """Satochip always has PIN set."""
        return True

    @property
    def is_locked(self):
        """Returns True if PIN has not been verified yet."""
        return not self._pin_unlocked

    @property
    def is_ready(self):
        """Returns True if connected, unlocked, and has a fingerprint."""
        return self.connected and self._pin_unlocked and self.fingerprint is not None
    
    @property
    def hexid(self):
        """Unique identifier for the card."""
        # TODO: implement proper hexid from authentikey
        return "satochip"


    async def check_card(self, check_pin=False):
        """Check card presence and connect if needed."""
        if not self.connection.isCardInserted():
            scr = Progress(
                "Satochip card not inserted",
                "Please insert the Satochip card...",
                button_text="",
            )
            asyncio.create_task(self.wait_for_card(scr))
            await self.show(scr)

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

    async def wait_for_card(self, scr):
        """Wait for card insertion."""
        while not self.connection.isCardInserted():
            await asyncio.sleep_ms(30)
            scr.tick(5)
        if scr.waiting:
            scr.waiting = False

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
            if attempts is not None:
                raise PinError("Invalid PIN!\n%d attempts left..." % attempts)
        except ISOException as e:
            sw = str(e).lower()
            if sw == "9c0c" or sw == "6983":
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            if sw.startswith("63c") and len(sw) == 4:
                try:
                    attempts_left = int(sw[3], 16)
                except ValueError:
                    attempts_left = None
                if attempts_left is not None:
                    raise PinError("Invalid PIN!\n%d attempts left..." % attempts_left)
                raise PinError("Invalid PIN!")
            raise
        except AppletException as e:
            if "6983" in str(e) or "9c0c" in str(e):
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            raise

    async def unlock(self):
        """
        Prompt for PIN via touchscreen, then verify.
        """
        print('[BootTrace][Satochip] unlock() called')
        await self.check_card(check_pin=False)
        
        pin_attempts = None
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                pin_attempts = resp_data[4]
                print('[BootTrace][Satochip] PIN attempts remaining:', pin_attempts)
        except Exception as e:
            print('[BootTrace][Satochip] Failed to get card status:', e)
        
        while self.is_locked:
            note = None
            if pin_attempts is not None:
                note = "%d PIN attempts remaining" % pin_attempts
            
            pin = await self.get_pin(subtitle="Satochip card detected", note=note)
            self.show_loader('Verifying PIN code...')
            try:
                self._unlock(pin)
            except PinError as e:
                await self.show(Alert('PIN Error', str(e)))
                try:
                    resp_data, sw1, sw2 = self.applet.get_card_status()
                    if len(resp_data) >= 8:
                        pin_attempts = resp_data[4]
                except:
                    pass
                continue
        
        print('[BootTrace][Satochip] PIN verified successfully')

    async def get_pin(self, title="Enter your PIN code", subtitle=None, note=None, with_cancel=False):
        """
        Show PIN screen for entry.
        Uses get_word=None to disable anti-phishing words (Satochip-specific).
        """
        scr = PinScreen(title=title, note=note, get_word=None, subtitle=subtitle, with_cancel=with_cancel)
        return await self.show(scr)

    async def init(self, show_fn, show_loader):
        """Initialize Satochip and check card presence."""
        self.show_loader = show_loader
        self.show = show_fn
        await self.check_card()
        await super().init(show_fn, show_loader)

    async def storage_menu(self):
        """Manage storage, return True if new key was loaded."""
        enabled = self.connection.isCardInserted()
        buttons = [
            (None, "Satochip storage"),
            (0, "Load key from Satochip", enabled),
            (1, "Card info", enabled),
        ]
        while True:
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            if menuitem == 255:
                return False
            elif menuitem == 0:
                await self.show(Alert(
                    "Not supported",
                    "Satochip cannot export the mnemonic.\nThe seed stays secure on the card."
                ))
                return True
            elif menuitem == 1:
                await self.show_card_info()
            else:
                raise KeyStoreError("Invalid menu")

    async def show_card_info(self):
        print('[BootTrace][Satochip] show_card_info() called')
        try:
            # Get authentikey and calculate fingerprint
            authentikey_bytes = self.applet.get_authentikey()
            if authentikey_bytes and len(authentikey_bytes) > 0:
                # Compress pubkey: first byte (02/03) + x-coord (32 bytes)
                if len(authentikey_bytes) == 65:  # Uncompressed
                    # y = authentikey_bytes[33:65]
                    x = authentikey_bytes[1:33]
                    # Determine prefix based on y parity
                    y_last = authentikey_bytes[64]
                    prefix = b'\x03' if y_last % 2 else b'\x02'
                    compressed = prefix + x
                else:
                    compressed = authentikey_bytes
                
                # hash160 = RIPEMD160(SHA256(data))
                import hashlib
                sha256_hash = hashlib.sha256(compressed).digest()
                ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
                fingerprint = ripemd160[:4]
                
                props = [
                    "\n#7f8fa4 CARD INFO: #",
                    "Card name: Satochip",
                    "Fingerprint: %s" % fingerprint.hex(),
                ]
            else:
                props = [
                    "\n#7f8fa4 CARD INFO: #",
                    "Card name: Satochip",
                    "No seed initialized",
                ]
            scr = Alert("Satochip info", "\n\n".join(props))
            scr.message.set_recolor(True)
            await self.show(scr)
        except Exception as e:
            await self.show(Alert("Error", "Failed to get card info:\n%s" % str(e)))
    async def load_mnemonic(self):
        """Satochip cannot export the mnemonic - it stays secure on the card."""
        raise KeyStoreError("Satochip cannot export the mnemonic!\nThe seed stays secure on the card.\nUse 'Card info' to see card status.")