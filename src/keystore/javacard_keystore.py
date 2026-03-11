"""
JavaCardKeyStore - Base class for JavaCard-based keystores.

This class provides common functionality for all JavaCard keystores:
- Card detection and insertion
- Secure channel management
- PIN verification
- Connection state tracking

Both SeedKeeper and Satochip (and potentially MemoryCard) inherit from this class,eliminating ~130 lines of duplicated code.
"""
import asyncio
from gui.screens import Alert, Progress, PinScreen
from .core import KeyStoreError, PinError
from platform import CriticalErrorWipeImmediately


from .javacard.util import get_connection


class JavaCardKeyStore(RAMKeyStore):
    """
    Base class for JavaCard-based keystores.
    
    Provides:
    - Card detection via is_available()
    - Card presence and waiting
    - PIN verification with attempt tracking
    - Secure channel management
    - Common connection state
    
    Subclasses must implement:
    - get_applet() -> Applet instance
    - _on_pin_verified() -> Called after successful PIN verification
    - Any applet-specific initialization
    """
    
    # Shared class-level
    connection = get_connection()
    
    def __init__(self):
        """Initialize keystore with connection."""
        super().__init__()
        # Instance state
        self.applet = None  # Set by subclass
        self._pin_unlocked = False
        self.connected = False
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if card is available and responsive.
        
        Must be implemented by subclass.
        """
        raise NotImplementedError("is_available() must be implemented by subclass")
    
    @property
    def is_pin_set(self) -> bool:
        """JavaCard keystores always have PIN set."""
        return True
    
    @property
    def is_locked(self) -> bool:
        """Returns True if PIN has not been verified yet."""
        return not self._pin_unlocked
    
    @property
    def is_ready(self) -> bool:
        """Returns True if connected, unlocked, and has fingerprint.
        
        Must be overridden by subclass if additional requirements.
        """
        return self.connected and self._pin_unlocked
    
    async def check_card(self, check_pin=False):
        """Check card presence and connect if needed.
        
        Args:
            check_pin: If True, prompt for PIN after card is inserted
        """
        if not self.connection.isCardInserted():
            # Wait for card
            scr = Progress(
                f"{self.applet.NAME} card not inserted",
                "Please insert the card...",
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
                self._on_pin_verified()
                return
            if attempts is not None:
                raise PinError(
                    f"Invalid PIN!\n{attempts} attempts left..."
                )
        except Exception as e:
            # Handle specific ISO exceptions
            from .javacard.util import handle_pin_iso_exception
            attempts, should_raise, exc = handle_pin_iso_exception(e)
            
            if should_raise:
                raise exc
    
    def _on_pin_verified(self):
        """
        Called after successful PIN verification.
        
        Override in subclass to perform any applet-specific initialization
        (e.g., loading mnemonic, getting authentikey).
        """
        pass
    
    async def get_pin(self, title="Enter your PIN code", subtitle=None, note=None, with_cancel=False):
        """
        Show PIN screen for entry.
        
        Override if anti-phishing words are needed (MemoryCard).
        """
        scr = PinScreen(title=title, note=note, get_word=None, subtitle=subtitle, with_cancel=with_cancel)
        return await self.show(scr)
    
    async def unlock(self):
        """
        Unlock the keystore by prompting for PIN.
        
        Shows PIN attempts remaining from calls verify_pin.
        """
        # Query card for PIN attempts
        pin_attempts = None
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                pin_attempts = resp_data[4]
                print(f'[{self.applet.NAME}] PIN attempts remaining:', pin_attempts)
        except Exception as e:
            print(f'[{self.applet.NAME}] Failed to get card status:', e)
        
        # PIN prompt loop
        while self.is_locked:
            note = f"{pin_attempts} PIN attempts remaining" if pin_attempts else None
            
            pin = await self.get_pin(
                subtitle=f"{self.applet.NAME} card detected",
                note=note,
            )
            self.show_loader('Verifying PIN code...')
            try:
                self._unlock(pin)
            except PinError as e:
                # Wrong PIN - show error alert
                await self.show(Alert('PIN Error', str(e)))
                # Re-query card for updated attempts
                try:
                    resp_data, sw1, sw2 = self.applet.get_card_status()
                    if len(resp_data) >= 8:
                        pin_attempts = resp_data[4]
                except:
                    pass
    
    async def init(self, show_fn, show_loader):
        """
        Initialize keystore - waits for card and and loads internal state.
        """
        self.show_loader = show_loader
        self.show = show_fn
        
        await self.check_card()
        # Subclasses should call super().init() for additional setup
