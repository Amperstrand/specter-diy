from .core import KeyStoreError, PinError
from .javacard_keystore import JavaCardKeyStore
from .javacard.applets.seedkeeper_applet import SeedKeeperApplet
from .javacard.applets.applet import AppletException
import asyncio
from gui.screens import Alert, Menu, Progress


class SeedKeeper(JavaCardKeyStore):
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

    def __init__(self):
        super().__init__()
        # applet instance
        self.applet = SeedKeeperApplet(self.connection)
        # SeedKeeper-specific state
        self.wallet_label = "SeedKeeper"
        self.selected_secret_id = None

    def _sanitize_wallet_label(self, label):
        if not label:
            return "SeedKeeper"
        return label.replace("&", "_")

    def set_wallet_label_on_card(self, label):
        clean = self._sanitize_wallet_label(label)
        self.applet.set_card_label(clean)
        self.wallet_label = clean
        print('[BootTrace][SeedKeeper] Card label updated to:', clean)
        return clean

    @classmethod
    def is_available(cls):
        """Check if SeedKeeper card is available and responsive."""
        print('[BootTrace][SeedKeeper] is_available() called')
        if not cls.connection.isCardInserted():
            return False
        try:
            import time
            time.sleep_ms(20)  # Give card time to stabilize after previous disconnect
            cls.connection.connect(cls.connection.T1_protocol)
            applet = SeedKeeperApplet(cls.connection)
            applet.select()
            # Check card status (byte 11 = needs_secure_channel flag)
            # get_card_status() does NOT require secure channel
            applet.get_card_status()
            cls.connection.disconnect()
            print('[BootTrace][SeedKeeper] is_available = True')
            return True
        except Exception as e:
            print('[BootTrace][SeedKeeper] Probe failed:', e)
            cls.connection.disconnect()
            return False

    @property
    def is_ready(self):
        """Returns True if connected, unlocked, and has a fingerprint."""
        return self.connected and self._pin_unlocked and self.fingerprint is not None

    async def unlock(self):
        """Override: prompt for PIN via touchscreen, then auto-load mnemonic."""
        print('[BootTrace][SeedKeeper] unlock() called')
        
        # Establish secure channel before PIN verification
        await self.check_card(check_pin=False)
        
        # Query card for PIN attempts remaining (byte 4 of card_status response)
        # get_card_status() works WITHOUT secure channel
        pin_attempts = None
        try:
            resp_data, sw1, sw2 = self.applet.get_card_status()
            if len(resp_data) >= 8:
                pin_attempts = resp_data[4]
                print('[BootTrace][SeedKeeper] PIN attempts remaining:', pin_attempts)
        except Exception as e:
            print('[BootTrace][SeedKeeper] Failed to get card status:', e)
        
        # PIN prompt loop with error handling
        while self.is_locked:
            # Build note with attempts info
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
                # Wrong PIN - show error alert, then loop back to PIN screen
                await self.show(Alert('PIN Error', str(e)))
                # Re-query card for updated attempts
                try:
                    resp_data, sw1, sw2 = self.applet.get_card_status()
                    if len(resp_data) >= 8:
                        pin_attempts = resp_data[4]
                        print('[BootTrace][SeedKeeper] PIN attempts remaining:', pin_attempts)
                except:
                    pass
                continue
            # CriticalErrorWipeImmediately is NOT caught - propagates up correctly
        
        # Set enc_secret manually (base class is_locked hack is bypassed by our override)
        from helpers import tagged_hash
        self.enc_secret = tagged_hash('enc', self.secret)
        
        print('[BootTrace][SeedKeeper] PIN verified successfully')

        # Multi-secret support: list and select BIP39-capable secrets
        try:
            headers = self.applet.list_secret_headers()
            for h in headers:
                print('[BootTrace][SeedKeeper] Header:',
                      'id=', h.get('id'),
                      'type=', hex(h.get('type')),
                      'subtype=', h.get('subtype'),
                      'label=', h.get('label'),
                      'fp=', h.get('fingerprint'),
                      'nb_plain=', h.get('export_nbplain'),
                      'nb_secure=', h.get('export_nbsecure'),
                      'counter=', h.get('export_counter'))
            bip39_headers = [
                h for h in headers
                if h['type'] in (0x10, 0x30, 0x31) 
                and (h['type'] != 0x10 or h.get('subtype') == 1)
            ]
            print('[BootTrace][SeedKeeper] Found %d BIP39 secrets' % len(bip39_headers))
            
            # Handle secret selection
            if len(bip39_headers) == 0:
                await self.show(Alert('Error', 'No BIP39 secrets found on card'))
                return  # is_ready stays False, returns to boot init menu
            
            elif len(bip39_headers) == 1:
                # Auto-select single secret
                selected = bip39_headers[0]
                print('[BootTrace][SeedKeeper] Selected secret id:', selected['id'], 'label:', selected['label'])
            else:
                # Show menu for multi-secret selection (no back button - must select)
                buttons = [(h['id'], h['label'] if h['label'] else 'Secret #%d' % h['id']) for h in bip39_headers]
                selected_id = await self.show(Menu(buttons, title='Select secret'))
                selected = next(h for h in bip39_headers if h['id'] == selected_id)
                print('[BootTrace][SeedKeeper] Selected secret id:', selected['id'], 'label:', selected['label'])
            
            card_label = ''
            try:
                card_label = self.applet.get_card_label()
            except Exception as e:
                print('[BootTrace][SeedKeeper] Card label read failed:', e)

            selected_label = selected['label'] if selected['label'] else 'SeedKeeper'
            self.wallet_label = self._sanitize_wallet_label(card_label or selected_label)
            self.selected_secret_id = selected['id']
            print('[BootTrace][SeedKeeper] Using secret id:', selected['id'], 'label:', selected['label'])
            print('[BootTrace][SeedKeeper] Effective wallet label:', self.wallet_label)
            
            # Load mnemonic from selected secret
            self.show_loader('Loading mnemonic from card...')
            mnemonic = self.applet.get_bip39_secret(secret_id=selected['id'], secret_type=selected['type'])
            self.set_mnemonic(mnemonic, "")
            print('[BootTrace][SeedKeeper] Mnemonic loaded successfully')
            
        except AppletException as e:
            # Failed to load mnemonic - show error and let boot continue to init menu
            await self.show(Alert('Error', 'Failed to load key from card:\n%s' % str(e)))
            # is_ready stays False since fingerprint is not set

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

        # Verify applet is responsive with encrypted command (ONLY after PIN verification)
        if self._pin_unlocked:
            self.applet.get_seedkeeper_status()

        if check_pin and not self._pin_unlocked:
            pin = await self.get_pin()
            self._unlock(pin)

    async def load_mnemonic(self):
        """Load mnemonic from SeedKeeper card."""
        await self.check_card(check_pin=True)
        self.show_loader("Loading secret from the card...")
        
        # Multi-secret support: list and select BIP39-capable secrets
        try:
            headers = self.applet.list_secret_headers()
            for h in headers:
                print('[SeedKeeper] Header:',
                      'id=', h.get('id'),
                      'type=', hex(h.get('type')),
                      'subtype=', h.get('subtype'),
                      'label=', h.get('label'),
                      'fp=', h.get('fingerprint'),
                      'nb_plain=', h.get('export_nbplain'),
                      'nb_secure=', h.get('export_nbsecure'),
                      'counter=', h.get('export_counter'))
            bip39_headers = [
                h for h in headers
                if h['type'] in (0x10, 0x30, 0x31) 
                and (h['type'] != 0x10 or h.get('subtype') == 1)
            ]
            print('[SeedKeeper] Found %d BIP39 secrets' % len(bip39_headers))
            
            # Handle secret selection
            if len(bip39_headers) == 0:
                await self.show(Alert('Error', 'No BIP39 secrets found on card'))
                return False
            
            elif len(bip39_headers) == 1:
                # Auto-select single secret
                selected = bip39_headers[0]
                print('[SeedKeeper] Selected secret id:', selected['id'], 'label:', selected['label'])
            else:
                # Show menu for multi-secret selection
                buttons = [(h['id'], h['label'] if h['label'] else 'Secret #%d' % h['id']) for h in bip39_headers]
                selected_id = await self.show(Menu(buttons, title='Select secret', last=(255, None)))
                if selected_id == 255:  # Back/cancel
                    return False
                selected = next(h for h in bip39_headers if h['id'] == selected_id)
                print('[SeedKeeper] Selected secret id:', selected['id'], 'label:', selected['label'])
            
            card_label = ''
            try:
                card_label = self.applet.get_card_label()
            except Exception as e:
                print('[SeedKeeper] Card label read failed:', e)

            selected_label = selected['label'] if selected['label'] else 'SeedKeeper'
            self.wallet_label = self._sanitize_wallet_label(card_label or selected_label)
            self.selected_secret_id = selected['id']
            print('[SeedKeeper] Effective wallet label:', self.wallet_label)
            
            # Load mnemonic from selected secret
            mnemonic = self.applet.get_bip39_secret(secret_id=selected['id'], secret_type=selected['type'])
            self.set_mnemonic(mnemonic, "")
            
        except AppletException as e:
            await self.show(Alert('Error', 'Failed to load key from card:\n%s' % str(e)))
            return False
        
        print("[SeedKeeper] Loaded mnemonic successfully")
        return True

    async def save_mnemonic(self):
        """SeedKeeper is read-only - cannot save mnemonic to card."""
        raise KeyStoreError("SeedKeeper is read-only")

    @property
    def is_key_saved(self):
        """SeedKeeper always has a key saved (on the card)."""
        return self._pin_unlocked


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
            
            # Get detailed card status
            status = self.applet.get_seedkeeper_status()
            
            if status:
                props.extend([
                    "\n#7f8fa4 STORAGE INFO #",
                    "Secrets stored: %d" % status.get('nb_secrets', 0),
                ])
                
                # Memory info
                total_mem = status.get('total_memory', 0)
                free_mem = status.get('free_memory', 0)
                if total_mem > 0:
                    used_mem = total_mem - free_mem
                    props.append("Memory used: %d / %d bytes" % (used_mem, total_mem))
                
                # Log info
                nb_logs_total = status.get('nb_logs_total', 0)
                nb_logs_avail = status.get('nb_logs_avail', 0)
                if nb_logs_total > 0:
                    props.append("Logs available: %d / %d" % (nb_logs_avail, nb_logs_total))
            else:
                props.extend([
                    "\n#7f8fa4 STORAGE INFO #",
                    "Status: Unable to read",
            ])
            
            # List all secrets by type for debugging
            try:
                headers = self.applet.list_secret_headers()
                secret_types = {}
                for h in headers:
                    t = h['type']
                    if t not in secret_types:
                        secret_types[t] = []
                    secret_types[t].append(h)
                
                if secret_types:
                    props.append("\n#7f8fa4 SECRETS BY TYPE: #")
                    # Map type codes to names
                    type_names = {
                        0x10: "Masterseed",
                        0x30: "BIP39",
                        0x31: "BIP39 v2",
                        0x40: "Electrum",
                        0x50: "Shamir",
                        0x60: "PrivKey",
                        0x70: "PubKey",
                        0x80: "SymKey",
                        0x90: "Password",
                        0xB0: "2FA",
                        0xC0: "Data",
                        0xC1: "Descriptor",
                    }
                    for t, secrets in sorted(secret_types.items()):
                        type_name = type_names.get(t, "0x%02X" % t)
                        props.append("%s: %d" % (type_name, len(secrets)))
                        
                    # Show descriptor contents as debug text
                    if 0xC1 in secret_types:
                        descriptors = self.applet.get_descriptor_secrets()
                        if descriptors:
                            props.append("\n#7f8fa4 DESCRIPTORS (debug): #")
                            for d in descriptors[:3]:  # Limit to 3 to avoid overflow
                                label = d.get('label', 'No label')
                                desc = d.get('descriptor', '')
                                # Truncate long descriptors
                                if len(desc) > 60:
                                    desc = desc[:57] + "..."
                                props.append("[%s] %s" % (label, desc))
            except Exception as e:
                print('[SeedKeeper] Failed to list secrets:', e)
            
            scr = Alert("SeedKeeper info", "\n\n".join(props))
            scr.message.set_recolor(True)
            await self.show(scr)
        except Exception as e:
            await self.show(Alert("Error", "Failed to get card info:\n%s" % str(e)))
