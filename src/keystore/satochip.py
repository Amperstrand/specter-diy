from .core import KeyStoreError, PinError
from .javacard_keystore import JavaCardKeyStore
from .javacard.applets.satochip_applet import SatochipApplet
import asyncio
from gui.screens import Alert, Menu, Progress
from embit.transaction import SIGHASH
from embit import bip32
from embit.networks import NETWORKS
from binascii import hexlify

class Satochip(JavaCardKeyStore):
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
    def __init__(self):
        super().__init__()
        # applet instance
        self.applet = SatochipApplet(self.connection)
        # Satochip-specific state
        self.wallet_label = "Satochip"
        self.network = "main"
        self.idkey = None
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

        # Use shared utility function for fingerprint derivation
        from .javacard.util import derive_fingerprint
        
        try:
            self.fingerprint = derive_fingerprint(authentikey_bytes)
        except Exception as e:
            print('[BootTrace][Satochip] Fingerprint derivation failed:', e)
            raise KeyStoreError("Failed to derive card fingerprint")
        
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
        """Display detailed card information."""
        print('[BootTrace][Satochip] show_card_info() called')
        try:
            props = []
            
            # Get card status for version info
            try:
                resp_data, sw1, sw2 = self.applet.get_card_status()
                status = self.applet.parse_status(resp_data)
                
                if status:
                    version = "%s v%d.%d" % (
                        self.applet.NAME,
                        status.get('applet_major_version', 0),
                        status.get('applet_minor_version', 0)
                    )
                    protocol = "Protocol v%d.%d" % (
                        status.get('protocol_major_version', 0),
                        status.get('protocol_minor_version', 0)
                    )
                    pin_attempts = status.get('PIN0_remaining_tries', '?')
                    
                    props.extend([
                        "\n#7f8fa4 PLATFORM #",
                        "Implementation: %s" % self.applet.platform,
                        "Version: %s" % version,
                        protocol,
                    ])
                else:
                    props.extend([
                        "\n#7f8fa4 PLATFORM #",
                        "Implementation: %s" % self.applet.platform,
                        "Version: %s v%s" % (self.applet.NAME, self.applet.version),
                    ])
                    pin_attempts = '?'
            except Exception as e:
                print('[Satochip] Failed to get card status:', e)
                props.extend([
                    "\n#7f8fa4 PLATFORM #",
                    "Implementation: %s" % self.applet.platform,
                    "Version: %s v%s" % (self.applet.NAME, self.applet.version),
                ])
                pin_attempts = '?'
            
            # Get authentikey and calculate fingerprint
            props.append("\n#7f8fa4 KEY INFO: #")
            try:
                authentikey_bytes = self.applet.get_authentikey()
                if authentikey_bytes and len(authentikey_bytes) > 0:
                    # Use shared utility for fingerprint derivation
                    from .javacard.util import derive_fingerprint
                    fingerprint = derive_fingerprint(authentikey_bytes)
                    
                    props.append("Fingerprint: %s" % hexlify(fingerprint).decode())
                    props.append("Seed initialized: Yes")
                    props.append("PIN attempts left: %s" % pin_attempts)
                else:
                    props.append("Seed initialized: No")
                    props.append("PIN attempts left: %s" % pin_attempts)
            except Exception as e:
                print('[Satochip] Failed to get authentikey:', e)
                props.append("Seed status: Unknown")
            
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
        """Compute the sighash for a PSBT input using embit's built-in methods.
        
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
        
        # Use embit's Transaction.sighash_segwit() or Transaction.sighash_legacy()
        try:
            if inp.witness_utxo:
                # Segwit (BIP 143)
                # Get scriptcode
                from embit.script import Script
                if inp.witness_utxo.script_pubkey.is_p2wpkh():
                    scriptcode = Script(b"\x76\xa9\x14" + inp.witness_utxo.script_pubkey.data + b"\x88\xac")
                elif inp.witness_script:
                    scriptcode = inp.witness_script
                else:
                    scriptcode = inp.witness_utxo.script_pubkey
                
                return psbt.tx.sighash_segwit(i, scriptcode, inp.witness_utxo.value, inp_sighash)
            
            elif inp.non_witness_utxo:
                # Legacy
                prev_index = psbt.tx.vin[i].vout
                script_pubkey = inp.non_witness_utxo.vout[prev_index].script_pubkey
                return psbt.tx.sighash_legacy(i, script_pubkey, inp_sighash)
            
            else:
                print('[Satochip] No UTXO info for input', i)
                return None
                
        except Exception as e:
            print('[Satochip] Sighash computation failed:', e)
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

