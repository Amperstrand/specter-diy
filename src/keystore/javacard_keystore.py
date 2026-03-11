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
    - is_available() -> Check if card is available
    - _on_pin_verified() -> Called after successful PIN verification
    
    Optional overrides:
    - _init_secure_channel() -> Custom secure channel initialization
    - _verify_pin(pin) -> Custom PIN verification
    - _get_pin_attempts() -> Get remaining PIN attempts
    """
    
    # Shared class-level connection
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
    
    def _init_secure_channel(self):
        """Initialize secure channel - can be overridden by subclasses.
        
        Default implementation calls applet.init_secure_channel().
        Subclasses using different interfaces (e.g., MemoryCard) should override.
        """
        self.applet.init_secure_channel()
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
            self._init_secure_channel()
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
    
    def _verify_pin(self, pin):
        """Verify PIN on the card - can be overridden by subclasses.
        
        Default implementation calls applet.verify_pin(pin).
        Subclasses using different interfaces (e.g., MemoryCard) should override.
        
        Returns:
            tuple: (success: bool, attempts_left: int or None)
        """
        return self.applet.verify_pin(pin)
    
    def _get_pin_attempts(self):
        """Get remaining PIN attempts - can be overridden by subclasses.
        
        Default implementation calls applet.get_card_status().
        Subclasses using different interfaces (e.g., MemoryCard) should override.
        
        Returns:
            int or None: Number of attempts remaining, or None if unavailable
        """
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                return resp_data[4]
        except Exception as e:
            print(f'[{self.applet.NAME}] Failed to get card status:', e)
        return None
    
    def _unlock(self, pin):
        """
        Unlock the keystore by verifying PIN on the card.
        
        Raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        try:
            success, attempts = self._verify_pin(pin)
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
        pin_attempts = self._get_pin_attempts()
        if pin_attempts:
            print(f'[{self.applet.NAME}] PIN attempts remaining:', pin_attempts)
        
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
                pin_attempts = self._get_pin_attempts()
    async def init(self, show_fn, show_loader):
        """
        Initialize keystore - waits for card and and loads internal state.
        """
        self.show_loader = show_loader
        self.show = show_fn
        
        await self.check_card()
        # Subclasses should call super().init() for additional setup
    
    def _change_pin(self, old_pin, new_pin):
        """
        Change PIN on the card.
        
        Args:
            old_pin: Current PIN code
            new_pin: New PIN code
        
        Raises:
            PinError: If old PIN is incorrect
            KeyStoreError: If PIN change fails
        """
        try:
            self.applet.change_pin(old_pin, new_pin)
            print(f'[{self.applet.NAME}] PIN changed successfully')
        except Exception as e:
            err_str = str(e).lower()
            # Handle wrong old PIN
            if '63c' in err_str or 'wrong' in err_str or 'invalid' in err_str:
                raise PinError(f"Invalid old PIN!")
            raise KeyStoreError(f"Failed to change PIN: {e}")
