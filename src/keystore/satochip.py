from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.satochip_applet import SatochipApplet
from .javacard.applets.applet import ISOException, AppletException
from .javacard.util import get_connection
from platform import CriticalErrorWipeImmediately
import asyncio
from gui.screens import Alert, Progress, Menu, Prompt, PinScreen
from embit.transaction import SIGHASH
from embit import bip32
from embit.networks import NETWORKS
from binascii import hexlify

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
        self.network = "main"

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
        """Returns True if connected, unlocked, and identity keys are set."""
        return (
            self.connected
            and self._pin_unlocked
            and self.fingerprint is not None
            and self.idkey is not None
        )
    
    @property
    def can_export_seed(self):
        """Satochip cannot export the mnemonic - seed stays on card."""
        return False

    @property
    def supports_taproot(self):
        return False

    def set_network(self, network):
        self.network = network

    def _is_mainnet(self):
        net = NETWORKS.get(self.network, NETWORKS["main"])
        return net.get("bip32", 0) == 0

    def _infer_xtype(self, path):
        if not isinstance(path, str):
            return "p2wpkh"
        if not path.startswith("m/"):
            return "p2wpkh"
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            return "p2wpkh"
        try:
            purpose = int(parts[1].rstrip("h'"))
        except Exception:
            return "p2wpkh"
        if purpose == 44:
            return "standard"
        if purpose == 49:
            return "p2wpkh-p2sh"
        if purpose == 84:
            return "p2wpkh"
        if purpose == 86:
            return "standard"
        if purpose == 48:
            if len(parts) >= 5:
                try:
                    script_branch = int(parts[4].rstrip("h'"))
                    if script_branch == 1:
                        return "p2wsh-p2sh"
                    if script_branch == 2:
                        return "p2wsh"
                except Exception:
                    pass
            return "p2wsh"
        return "p2wpkh"

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

        # Get authentikey and derive fingerprint + idkey.
        # Fail fast if this identity step fails; downstream wallet storage relies on idkey.
        self.show_loader('Reading card info...')
        self.fingerprint = None
        self.idkey = None
        try:
            authentikey_bytes = self.applet.get_authentikey()
        except Exception as e:
            print('[BootTrace][Satochip] get_authentikey failed:', e)
            raise KeyStoreError("Failed to read card authentikey. Please reconnect card and try again.")

        if not authentikey_bytes:
            print('[BootTrace][Satochip] Empty authentikey response')
            raise KeyStoreError("Satochip returned empty authentikey")

        # Compress pubkey for fingerprint/idkey derivation
        if len(authentikey_bytes) == 65:
            x = authentikey_bytes[1:33]
            y_last = authentikey_bytes[64]
            prefix = b'\x03' if y_last % 2 else b'\x02'
            compressed = prefix + x
            key_format = "uncompressed"
        elif len(authentikey_bytes) > 65:
            # Some applet responses include extra bytes around the uncompressed key.
            # Keep compatibility with observed 106-byte responses.
            x = authentikey_bytes[1:33]
            y_last = authentikey_bytes[64]
            prefix = b'\x03' if y_last % 2 else b'\x02'
            compressed = prefix + x
            key_format = "extended"
        elif len(authentikey_bytes) == 33:
            compressed = authentikey_bytes
            key_format = "compressed"
        else:
            print('[BootTrace][Satochip] Unexpected authentikey length:', len(authentikey_bytes))
            raise KeyStoreError("Unexpected authentikey format from Satochip")

        print('[BootTrace][Satochip] Authentikey format:', key_format)

        # hash160 = RIPEMD160(SHA256(data))
        try:
            import hashlib
            sha256_hash = hashlib.sha256(compressed).digest()
            ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
        except Exception as e:
            print('[BootTrace][Satochip] Fingerprint derivation failed:', e)
            raise KeyStoreError("Failed to derive card fingerprint")

        self.fingerprint = ripemd160[:4]
        print('[BootTrace][Satochip] Fingerprint set:', hexlify(self.fingerprint).decode())

        # Derive idkey from authentikey for wallet file encryption
        # This ensures the same Satochip card always gets the same idkey
        try:
            from helpers import tagged_hash
            self.idkey = tagged_hash("satochip idkey", compressed)
        except Exception as e:
            print('[BootTrace][Satochip] idkey derivation failed:', e)
            raise KeyStoreError("Failed to derive wallet encryption key from card identity")

        if self.idkey is None:
            raise KeyStoreError("Failed to initialize wallet encryption key")

        print('[BootTrace][Satochip] idkey derived: True')
        print('[BootTrace][Satochip] Ready state: connected=%s unlocked=%s fingerprint=%s idkey=%s' % (
            self.connected,
            self._pin_unlocked,
            self.fingerprint is not None,
            self.idkey is not None,
        ))

    async def get_pin(self, title="Enter your PIN code", subtitle=None, note=None, with_cancel=False):
        """
        Show PIN screen for entry.
        Uses get_word=None to disable anti-phishing words (Satochip-specific).
        """
        scr = PinScreen(title=title, note=note, get_word=None, subtitle=subtitle, with_cancel=with_cancel)
        return await self.show(scr)

    async def init(self, show_fn, show_loader):
        """Initialize Satochip - generates in-memory secret for settings.
        
        Note: We do NOT call super().init() because Satochip doesn't use flash storage.
        All secrets are stored on the card. We generate an in-memory secret
        for settings_key to work properly.
        """
        from rng import get_random_bytes
        self.show_loader = show_loader
        self.show = show_fn
        await self.check_card()
        # Generate in-memory secret for settings_key (used by hosts)
        # This is not persisted - settings are ephemeral for Satochip
        if self.secret is None:
            self.secret = get_random_bytes(32)
        self.initialized = True

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
                    "Fingerprint: %s" % hexlify(fingerprint).decode(),
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

    # ========================================
    # Key ownership - override to avoid root dependency
    # ========================================

    def owns(self, key):
        """Check if key belongs to this Satochip card.
        
        Since self.root is None, we derive ownership from xpub
        fetched from the card using get_xpub().
        """
        # Check fingerprint first
        if key.fingerprint is not None and key.fingerprint != self.fingerprint:
            return False
        
        # Get the xpub at the derivation path from the card
        if key.derivation is None:
            # Compare against root xpub (path "m")
            try:
                our_xpub = self.get_xpub("m")
                return key.key == our_xpub.key
            except Exception as e:
                print('[Satochip] owns() failed to get root xpub:', e)
                return False
        
        # Compare against derived xpub from card
        try:
            our_xpub = self.get_xpub(key.derivation)
            return key.key == our_xpub.key
        except Exception as e:
            print('[Satochip] owns() failed to get derived xpub:', e)
            return False

    def sign_recoverable(self, derivation, msghash: bytes):
        """Sign with recovery flag - not supported by Satochip.
        
        Satochip does not support recoverable signatures.
        This is used for message signing (BIP-322, SignMessage).
        """
        raise KeyStoreError("Satochip does not support recoverable signatures!\nMessage signing is not available.")

    # ========================================
    # Signing methods - delegated to Satochip card
    # ========================================
    
    def get_xpub(self, path):
        """Override: get xpub from card instead of deriving from root key.
        
        Args:
            path: Derivation path (string like "m/84h/0h/0h" or list of integers)
        
        Returns:
            HDKey: Extended public key object
        """
        if self.is_locked:
            raise KeyStoreError("Keystore is not ready")
        
        # Convert list path to string if needed
        if isinstance(path, (list, tuple)):
            path_str = "m"
            for p in path:
                if p >= 0x80000000:
                    path_str += "/" + str(p - 0x80000000) + "h"
                else:
                    path_str += "/" + str(p)
            path = path_str

        xtype = self._infer_xtype(path)
        is_mainnet = self._is_mainnet()

        print('[Satochip] get_xpub for path:', path, 'xtype:', xtype, 'network:', self.network)

        # Get xpub from card via applet
        return self.applet.get_xpub(path, xtype=xtype, is_mainnet=is_mainnet)
    
    def sign_hash(self, derivation, msghash: bytes):
        """Sign a 32-byte hash with key at derivation path.
        
        Args:
            derivation: Derivation path (string or list)
            msghash: 32-byte message hash to sign
        
        Returns:
            bytes: DER-encoded signature
        """
        if self.is_locked:
            raise KeyStoreError("Keystore is not ready")
        
        print('[Satochip] sign_hash for derivation:', derivation)
        
        # Convert derivation to path string if needed
        if isinstance(derivation, (list, tuple)):
            path_str = "m"
            for p in derivation:
                if p >= 0x80000000:
                    path_str += "/" + str(p - 0x80000000) + "h"
                else:
                    path_str += "/" + str(p)
            derivation = path_str
        
        # Convert path to bytes and set it on card
        path_bytes = self.applet._path_to_bytes(derivation)
        
        # First, get the extended key to set the derivation path on the card
        # The card tracks the current path for signing
        self.applet.get_extended_key(path_bytes)
        
        # Now sign the hash with keynbr=0xFF (BIP32 current path)
        der_sig = self.applet.sign_transaction_hash(0xFF, msghash)
        
        print('[Satochip] Signature:', hexlify(der_sig).decode())
        return der_sig
    
    def sign_psbt(self, psbt, sighash=SIGHASH.ALL):
        """Sign a PSBT by iterating inputs and delegating to card.
        
        Args:
            psbt: PSBT object to sign
            sighash: Sighash type (default ALL)
        
        Returns:
            int: Number of signatures added
        """
        if self.is_locked:
            raise KeyStoreError("Keystore is not ready")
        
        print('[Satochip] sign_psbt called')
        sig_count = 0
        
        # Get our fingerprint
        my_fp = self.fingerprint
        if my_fp is None:
            print('[Satochip] No fingerprint set, cannot sign')
            return 0
        
        # Iterate over inputs
        for i, inp in enumerate(psbt.inputs):
            # Get input's sighash type if specified
            inp_sighash = inp.sighash_type or sighash
            if inp_sighash == SIGHASH.DEFAULT:
                inp_sighash = SIGHASH.ALL
            
            # Find derivations matching our fingerprint
            for pub in inp.bip32_derivations:
                der_path = inp.bip32_derivations[pub]
                if der_path.fingerprint == my_fp:
                    print('[Satochip] Signing input %d with derivation:' % i, der_path.derivation)
                    
                    try:
                        msghash = self._get_sighash(psbt, i, inp, sighash)
                        if msghash:
                            # Sign via card
                            der_sig = self.sign_hash(der_path.derivation, msghash)
                            
                            # Add signature to PSBT (use input's actual sighash type)
                            sig_with_hashtype = der_sig + bytes([inp_sighash])
                            inp.partial_sigs[pub] = sig_with_hashtype
                            sig_count += 1
                            print('[Satochip] Added signature for input %d' % i)
                    except Exception as e:
                        import traceback
                        print('[Satochip] Failed to sign input %d:' % i, e)
                        traceback.print_exc()
        
        print('[Satochip] sign_psbt complete, %d signatures added' % sig_count)
        return sig_count
    
    def _get_sighash(self, psbt, i, inp, sighash_type):
        """Compute the sighash for a PSBT input.
        
        Args:
            psbt: PSBT object
            i: Input index
            inp: PSBT input object
            sighash_type: Sighash type
        
        Returns:
            bytes: 32-byte sighash
        """
        # Get input's sighash type if specified
        inp_sighash = inp.sighash_type or sighash_type
        if inp_sighash == SIGHASH.DEFAULT:
            inp_sighash = SIGHASH.ALL
        
        # Check if segwit
        if inp.witness_utxo:
            # Segwit signing (BIP 143)
            from embit.script import Script
            
            # Get the scriptcode
            if inp.witness_utxo.script_pubkey.is_p2wpkh():
                # For P2WPKH, scriptcode is P2PKH script
                scriptcode = Script(b"\x76\xa9\x14" + inp.witness_utxo.script_pubkey.data + b"\x88\xac")
            elif inp.witness_script:
                scriptcode = inp.witness_script
            else:
                scriptcode = inp.witness_utxo.script_pubkey
            
            # Compute segwit sighash manually (BIP 143)
            msghash = self._compute_segwit_sighash(
                psbt.tx, i, scriptcode, inp.witness_utxo.value, inp_sighash
            )
            return msghash
        
        elif inp.non_witness_utxo:
            # Legacy signing
            prev_tx = inp.non_witness_utxo
            prev_index = psbt.tx.vin[i].vout
            prev_output = prev_tx.vout[prev_index]
            
            # Compute legacy sighash
            msghash = self._compute_legacy_sighash(
                psbt.tx, i, prev_output.script_pubkey, inp_sighash
            )
            return msghash
        
        else:
            print('[Satochip] No UTXO info for input', i)
            return None
    
    def sign_input(self, psbtv, i, sig_stream, sighash=SIGHASH.ALL, extra_scope_data=None):
        """Sign a single PSBT input.
        
        Args:
            psbtv: PSBTView object
            i: Input index
            sig_stream: Stream for displaying progress (unused)
            sighash: Sighash type
            extra_scope_data: Additional scope data
        
        Returns:
            int: Number of signatures added
        """
        if self.is_locked:
            raise KeyStoreError("Keystore is not ready")
        
        print('[Satochip] sign_input called for input %d' % i)
        
        # Get fingerprint
        my_fp = self.fingerprint
        if my_fp is None:
            return 0
        
        inp = psbtv.input(i)
        if extra_scope_data:
            inp.update(extra_scope_data)
        
        sig_count = 0
        
        # Get input's sighash type if specified
        inp_sighash = inp.sighash_type or sighash
        if inp_sighash == SIGHASH.DEFAULT:
            inp_sighash = SIGHASH.ALL
        
        # Find derivations matching our fingerprint
        for pub in inp.bip32_derivations:
            der_path = inp.bip32_derivations[pub]
            if der_path.fingerprint == my_fp:
                print('[Satochip] Signing with derivation:', der_path.derivation)
                
                try:
                    # Compute sighash
                    msghash = self._get_sighash_from_view(psbtv, i, inp, sighash)
                    if msghash:
                        # Sign via card
                        der_sig = self.sign_hash(der_path.derivation, msghash)
                        
                        # Add to partial_sigs (use input's actual sighash type)
                        sig_with_hashtype = der_sig + bytes([inp_sighash])
                        inp.partial_sigs[pub] = sig_with_hashtype
                        sig_count += 1
                except Exception as e:
                    import traceback
                    print('[Satochip] Failed to sign:', e)
                    traceback.print_exc()
        
        return sig_count
    
    def _get_sighash_from_view(self, psbtv, i, inp, sighash_type):
        """Compute sighash from PSBTView input."""
        # Get input's sighash type if specified
        inp_sighash = inp.sighash_type or sighash_type
        if inp_sighash == SIGHASH.DEFAULT:
            inp_sighash = SIGHASH.ALL
        
        # Use PSBTView's built-in sighash method
        try:
            msghash = psbtv.sighash(i, sighash=inp_sighash, input_scope=inp)
            return msghash
        except Exception as e:
            print('[Satochip] sighash computation failed:', e)
            return None

    def _compute_segwit_sighash(self, tx, input_index, scriptcode, value, sighash_type):
        """Compute segwit sighash (BIP 143).
        
        Args:
            tx: Transaction object
            input_index: Index of input being signed
            scriptcode: The script code (P2PKH for P2WPKH, witness script for P2WSH)
            value: Value of the UTXO being spent (in satoshis)
            sighash_type: Sighash type (SIGHASH.ALL, etc.)
        
        Returns:
            bytes: 32-byte sighash
        """
        import hashlib
        from embit import hashes
        
        # BIP 143 sighash computation
        # https://github.com/bitcoin/bips/blob/master/bip-0143.mediawiki
        
        # Extract sighash flags
        sh = sighash_type & 0x1f  # Base sighash (ALL, NONE, SINGLE)
        anyonecanpay = sighash_type & 0x80
        
        # Start building the preimage
        h = hashlib.sha256()
        
        # 1. Version (4 bytes, little-endian)
        h.update(tx.version.to_bytes(4, 'little'))
        
        # 2. HashPrevouts (32 bytes)
        if anyonecanpay:
            h.update(b"\x00" * 32)
        else:
            prevouts = b''.join(
                inp.txid + inp.vout.to_bytes(4, 'little') 
                for inp in tx.vin
            )
            h.update(hashlib.sha256(hashlib.sha256(prevouts).digest()).digest())
        
        # 3. HashSequence (32 bytes)
        if anyonecanpay or sh in (0x02, 0x03):  # NONE or SINGLE
            h.update(b"\x00" * 32)
        else:
            sequences = b''.join(
                inp.sequence.to_bytes(4, 'little') 
                for inp in tx.vin
            )
            h.update(hashlib.sha256(hashlib.sha256(sequences).digest()).digest())
        
        # 4. Outpoint (36 bytes: txid + vout)
        tx_in = tx.vin[input_index]
        h.update(tx_in.txid)
        h.update(tx_in.vout.to_bytes(4, 'little'))
        
        # 5. ScriptCode (var bytes)
        h.update(scriptcode.serialize())
        
        # 6. Value (8 bytes, little-endian)
        h.update(value.to_bytes(8, 'little'))
        
        # 7. Sequence (4 bytes, little-endian)
        h.update(tx_in.sequence.to_bytes(4, 'little'))
        
        # 8. HashOutputs (32 bytes)
        if sh == 0x02:  # NONE
            h.update(b"\x00" * 32)
        elif sh == 0x03:  # SINGLE
            if input_index < len(tx.vout):
                outputs = tx.vout[input_index].serialize()
                h.update(hashlib.sha256(hashlib.sha256(outputs).digest()).digest())
            else:
                h.update(b"\x00" * 32)
        else:  # ALL (0x01)
            outputs = b''.join(out.serialize() for out in tx.vout)
            h.update(hashlib.sha256(hashlib.sha256(outputs).digest()).digest())
        
        # 9. Locktime (4 bytes, little-endian)
        h.update(tx.locktime.to_bytes(4, 'little'))
        
        # 10. Sighash type (4 bytes, little-endian)
        h.update(sighash_type.to_bytes(4, 'little'))
        
        # Final double-SHA256
        return hashlib.sha256(hashlib.sha256(h.digest()).digest()).digest()
    
    def _compute_legacy_sighash(self, tx, input_index, script_pubkey, sighash_type):
        """Compute legacy sighash.
        
        Args:
            tx: Transaction object
            input_index: Index of input being signed
            script_pubkey: The scriptPubKey of the UTXO
            sighash_type: Sighash type
        
        Returns:
            bytes: 32-byte sighash
        """
        import hashlib
        
        # Extract sighash flags
        sh = sighash_type & 0x1f
        anyonecanpay = sighash_type & 0x80
        
        # Build the preimage
        h = hashlib.sha256()
        
        # Version
        h.update(tx.version.to_bytes(4, 'little'))
        
        # Inputs count
        if anyonecanpay:
            h.update((1).to_bytes(1, 'little'))
        else:
            h.update(len(tx.vin).to_bytes(1, 'little'))
        
        # Inputs
        if anyonecanpay:
            # Only the input being signed
            inp = tx.vin[input_index]
            h.update(inp.txid)
            h.update(inp.vout.to_bytes(4, 'little'))
            h.update(script_pubkey.serialize())
            h.update(inp.sequence.to_bytes(4, 'little'))
        else:
            for i, inp in enumerate(tx.vin):
                h.update(inp.txid)
                h.update(inp.vout.to_bytes(4, 'little'))
                if i == input_index:
                    h.update(script_pubkey.serialize())
                else:
                    h.update(b'')  # Empty script
                h.update(inp.sequence.to_bytes(4, 'little'))
        
        # Outputs count
        if sh == 0x02:  # NONE
            h.update((0).to_bytes(1, 'little'))
        else:
            h.update(len(tx.vout).to_bytes(1, 'little'))
        
        # Outputs
        if sh == 0x01:  # ALL
            for out in tx.vout:
                h.update(out.serialize())
        elif sh == 0x03:  # SINGLE
            if input_index < len(tx.vout):
                h.update(tx.vout[input_index].serialize())
        # NONE (0x02) - no outputs
        
        # Locktime
        h.update(tx.locktime.to_bytes(4, 'little'))
        
        # Sighash type
        h.update(sighash_type.to_bytes(4, 'little'))
        
        return hashlib.sha256(hashlib.sha256(h.digest()).digest()).digest()
