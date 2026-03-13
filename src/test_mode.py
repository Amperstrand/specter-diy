"""
Test mode for automated Satochip testing via serial.

Commands:
  TEST_PIN:1234           - Unlock with PIN
  TEST_XPUB:m/84h/0h/0h   - Get XPUB at path
  TEST_SIGN:<hex_sighash> - Sign a 32-byte sighash
  TEST_SIGN_AT:<path>:<hex_sighash> - Sign hash at explicit derivation path
  TEST_SET_NETWORK:<net>  - Set device network (main/test/signet/regtest)
  TEST_GET_ADDRESS:<path>:<index> - Get address at derivation path
  TEST_FULL_CHECK         - Comprehensive verification (boot, xpub, sign, address)
  TEST_STATUS             - Get current status
  TEST_BOOT_STATE         - Get detailed boot/readiness state
  TEST_WAIT_READY         - Wait until keystore is ready
  TEST_WALLET_SMOKE       - AEAD roundtrip smoke test using keystore
  TEST_SCREEN             - Get active GUI screen class/title
  TEST_UI_SET:<value>     - Set active screen result value (menus/prompts)
  TEST_UI_PIN:<digits>    - Enter PIN on active PinScreen and submit
  TEST_RESET              - Reset connection

Responses:
  OK:<data>
  ERROR:<message>
"""

import sys
import os
import platform
from binascii import hexlify, unhexlify


class TestMode:
    def __init__(self, specter_ref=None):
        self.specter = specter_ref  # Reference to Specter instance
        self.running = False
        self._current_source = 'stdin'  # Track command source for response routing
        
        # Initialize UART3 VCP for HIL testing on hardware only
        # UART3 uses PB10 (TX) / PB11 (RX) - ST-Link Virtual COM Port
        # NOT the debug UART (platform.py stlk = pyb.UART("YB", 9600))
        self.uart = None
        if not platform.simulator:
            try:
                import pyb
                self.uart = pyb.UART(3, 115200)
            except Exception as e:
                print("[TestMode] UART3 init failed:", e)
        
    def find_javacard_keystore(self):
        """Find any JavaCard keystore instance from active Specter.
        
        Returns the first available JavaCard keystore (Satochip, SeedKeeper, or MemoryCard).
        """
        if self.specter is not None and hasattr(self.specter, 'keystore'):
            ks = self.specter.keystore
            if ks is not None and hasattr(ks, 'NAME'):
                if ks.NAME in ("Satochip", "SeedKeeper", "Smartcard"):
                    return ks
        return None
    
    # Keep backward compatibility alias
    find_satochip = find_javacard_keystore
    def _network_name(self):
        if self.specter is not None and hasattr(self.specter, 'network'):
            return self.specter.network
        return 'main'

    def _coin_type(self):
        from embit.networks import NETWORKS
        net = NETWORKS.get(self._network_name(), NETWORKS['main'])
        return net.get('bip32', 0)

    def _default_account_path(self):
        return "m/84h/%dh/0h" % self._coin_type()
    
    async def _command_loop(self):
        """Main command processing loop - called from Specter.setup()."""
        print("[TestMode] Starting command loop...")
        
        import asyncio
        
        self.running = True
        buffer = ""
        
        print("[TestMode] Ready for commands. Send TEST_STATUS to check.")
        
        while self.running:
            try:
                # Try to read from stdin using uselect (MicroPython)
                try:
                    import uselect as select
                    poller = select.poll()
                    poller.register(sys.stdin, select.POLLIN)
                    
                    result = poller.poll(100)
                    if result:
                        char = sys.stdin.read(1)
                        if char:
                            if char == '\n' or char == '\r':
                                if buffer.strip().startswith('TEST_'):
                                    self._current_source = 'stdin'
                                    await self._process_command(buffer.strip())
                                buffer = ""
                            else:
                                buffer += char
                    else:
                        await asyncio.sleep_ms(50)
                        
                except Exception as e:
                    print("[TestMode] Poll error:", e)
                    await asyncio.sleep_ms(100)
                
                # Poll UART3 VCP for HIL testing (hardware only)
                if not platform.simulator and self.uart and self.uart.any():
                    try:
                        line = self.uart.readline()
                        if line:
                            cmd_str = line.decode().strip()
                            if cmd_str.startswith('TEST_'):
                                self._current_source = 'uart'
                                await self._process_command(cmd_str)
                    except Exception as e:
                        print("[TestMode] UART error:", e)
                        
            except Exception as e:
                print("[TestMode] Error in command loop:", e)
                await asyncio.sleep_ms(100)
    
    async def _process_command(self, cmd):
        """Process a single command."""
        print("[TestMode] CMD:", cmd)
        
        try:
            if cmd == "TEST_STATUS":
                await self._cmd_status()
            elif cmd.startswith("TEST_PIN:"):
                pin = cmd[9:]
                await self._cmd_pin(pin)
            elif cmd.startswith("TEST_XPUB:"):
                path = cmd[10:]
                await self._cmd_xpub(path)
            elif cmd.startswith("TEST_SIGN:"):
                sighash_hex = cmd[10:]
                await self._cmd_sign(sighash_hex)
            elif cmd.startswith("TEST_SIGN_AT:"):
                payload = cmd[13:]
                await self._cmd_sign_at(payload)
            elif cmd.startswith("TEST_SET_NETWORK:"):
                net = cmd[17:]
                await self._cmd_set_network(net)
            elif cmd == "TEST_RESET":
                await self._cmd_reset()
            elif cmd == "TEST_BOOT_STATE":
                await self._cmd_boot_state()
            elif cmd == "TEST_WAIT_READY":
                await self._cmd_wait_ready()
            elif cmd == "TEST_WALLET_SMOKE":
                await self._cmd_wallet_smoke()
            elif cmd == "TEST_SCREEN":
                await self._cmd_screen()
            elif cmd.startswith("TEST_UI_SET:"):
                value = cmd[12:]
                await self._cmd_ui_set(value)
            elif cmd.startswith("TEST_UI_PIN:"):
                pin = cmd[12:]
                await self._cmd_ui_pin(pin)
            elif cmd.startswith("TEST_GET_ADDRESS:"):
                # Format: TEST_GET_ADDRESS:m/84h/0h/0h/0/0 or TEST_GET_ADDRESS:m/84h/0h/0h:0
                addr_arg = cmd[17:]
                await self._cmd_get_address(addr_arg)
            elif cmd == "TEST_FULL_CHECK":
                await self._cmd_full_check()
            else:
                self._respond("ERROR:Unknown command")
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    def _respond(self, msg, source=None):
        """Send response to the appropriate transport.
        
        Args:
            msg: Response message to send
            source: 'stdin' or 'uart' - if None, uses _current_source
        """
        actual_source = source if source is not None else self._current_source
        
        if actual_source == 'uart' and self.uart is not None:
            # Route to UART3 VCP
            try:
                self.uart.write((msg + '\n').encode())
            except Exception as e:
                print("[TestMode] UART write error:", e)
                # Fallback to print
                print("[TestMode] RESP:", msg)
        else:
            # Route to stdout (stdin source or fallback)
            print("[TestMode] RESP:", msg)
    
    async def _cmd_status(self):
        """Get current status."""
        ks = self.find_javacard_keystore()
        status = {
            "keystore_type": ks.NAME if ks else None,
            "keystore_found": ks is not None,
            "card_inserted": ks.connection.isCardInserted() if ks else False,
            "connected": getattr(ks, 'connected', False) if ks else False,
            "unlocked": getattr(ks, '_pin_unlocked', False) if ks else False,
            "fingerprint": hexlify(ks.fingerprint).decode() if ks and hasattr(ks, 'fingerprint') and ks.fingerprint else None,
        }
        self._respond("OK:" + str(status))
    async def _cmd_boot_state(self):
        """Get detailed readiness state for boot diagnostics."""
        ks = self.find_javacard_keystore()
        state = {
            "keystore_type": ks.NAME if ks else None,
            "keystore_found": ks is not None,
            "card_inserted": ks.connection.isCardInserted() if ks else False,
            "connected": getattr(ks, 'connected', False) if ks else False,
            "unlocked": getattr(ks, '_pin_unlocked', False) if ks else False,
            "is_ready": ks.is_ready if ks else False,
            "fingerprint_set": bool(ks and getattr(ks, 'fingerprint', None)),
            "idkey_set": bool(ks and getattr(ks, 'idkey', None)),
            "secret_set": bool(ks and getattr(ks, 'secret', None)),
        }
        self._respond("OK:" + str(state))

    async def _cmd_wait_ready(self):
        """Wait up to 30s for keystore readiness."""
        import asyncio
        timeout_ms = 30000
        elapsed = 0
        while elapsed < timeout_ms:
            ks = self.find_javacard_keystore()
            if ks and ks.is_ready:
                self._respond("OK:ready")
                return
            await asyncio.sleep_ms(500)
            elapsed += 500
        self._respond("ERROR:timeout_waiting_for_ready")
    async def _cmd_wallet_smoke(self):
        """Run AEAD roundtrip to verify keystore encryption key availability."""
        ks = self.find_javacard_keystore()
        if not ks:
            self._respond("ERROR:JavaCard keystore not found")
            return
        if not ks.is_ready:
            self._respond("ERROR:Keystore not ready")
            return

        test_file = "/flash/testmode_wallet_smoke.aead"
        try:
            ks.save_aead(test_file, adata=b"tm", plaintext=b"ok")
            adata, plaintext = ks.load_aead(test_file)
            if adata == b"tm" and plaintext == b"ok":
                self._respond("OK:wallet_smoke_passed")
            else:
                self._respond("ERROR:wallet_smoke_mismatch")
        except Exception as e:
            self._respond("ERROR:" + str(e))
        finally:
            try:
                os.remove(test_file)
            except Exception:
                pass
    async def _cmd_screen(self):
        """Return active GUI screen information."""
        gui = getattr(self.specter, 'gui', None) if self.specter else None
        scr = getattr(gui, 'scr', None) if gui else None
        if scr is None:
            self._respond("ERROR:No active screen")
            return
        title = None
        if hasattr(scr, 'title') and scr.title is not None and hasattr(scr.title, 'get_text'):
            try:
                title = scr.title.get_text()
            except Exception:
                title = None
        waiting = getattr(scr, 'waiting', None)
        self._respond("OK:" + str({
            "screen": type(scr).__name__,
            "title": title,
            "waiting": waiting,
        }))

    async def _cmd_ui_set(self, raw_value):
        """Set active screen value for Menu/Prompt-style screens."""
        gui = getattr(self.specter, 'gui', None) if self.specter else None
        scr = getattr(gui, 'scr', None) if gui else None
        if scr is None:
            self._respond("ERROR:No active screen")
            return
        value = raw_value
        if raw_value.isdigit() or (raw_value.startswith('-') and raw_value[1:].isdigit()):
            value = int(raw_value)
        elif raw_value.lower() == 'true':
            value = True
        elif raw_value.lower() == 'false':
            value = False
        try:
            scr.set_value(value)
            self._respond("OK:UI value set")
        except Exception as e:
            self._respond("ERROR:" + str(e))

    async def _cmd_ui_pin(self, pin):
        """Enter PIN on active PinScreen and submit."""
        gui = getattr(self.specter, 'gui', None) if self.specter else None
        scr = getattr(gui, 'scr', None) if gui else None
        if scr is None:
            self._respond("ERROR:No active screen")
            return
        if not hasattr(scr, 'pin') or not hasattr(scr.pin, 'set_text'):
            self._respond("ERROR:Active screen is not PinScreen")
            return
        try:
            scr.pin.set_text(pin)
            if hasattr(scr, 'submit'):
                scr.submit()
            else:
                scr.release()
            self._respond("OK:PIN entered")
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    async def _cmd_pin(self, pin):
        """Unlock with PIN."""
        ks = self.find_javacard_keystore()
        if not ks:
            self._respond("ERROR:JavaCard keystore not found")
            return
        
        if not ks.connection.isCardInserted():
            self._respond("ERROR:No card inserted")
            return
        
        try:
            # Connect if needed
            if not getattr(ks, 'connected', False):
                ks.connection.connect(ks.connection.T1_protocol)
                ks.applet.select()
                ks.applet.init_secure_channel()
                ks.connected = True
            
            # Verify PIN
            ks._unlock(pin)
            self._respond("OK:PIN verified")
            
            # Get keystore-specific identity information
            keystore_type = ks.NAME if hasattr(ks, 'NAME') else 'Unknown'
            
            # For Satochip: get authentikey and derive fingerprint
            if keystore_type == "Satochip":
                authentikey_bytes = ks.applet.get_authentikey()
                print("[TestMode] Authentikey length:", len(authentikey_bytes) if authentikey_bytes else 0)
                
                if authentikey_bytes:
                    import hashlib
                    from helpers import tagged_hash
                    # Handle different authentikey formats
                    if len(authentikey_bytes) == 65:
                        x = authentikey_bytes[1:33]
                        y_last = authentikey_bytes[64]
                        prefix = b'\x03' if y_last % 2 else b'\x02'
                        compressed = prefix + x
                    elif len(authentikey_bytes) >= 65:
                        x = authentikey_bytes[1:33]
                        y_last = authentikey_bytes[64]
                        prefix = b'\x03' if y_last % 2 else b'\x02'
                        compressed = prefix + x
                    else:
                        print("[TestMode] Unexpected authentikey length:", len(authentikey_bytes))
                        return
                    
                    sha256_hash = hashlib.sha256(compressed).digest()
                    ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
                    ks.fingerprint = ripemd160[:4]
                    ks.idkey = tagged_hash("satochip idkey", compressed)
                    print("[TestMode] Fingerprint:", hexlify(ks.fingerprint).decode())
                    print("[TestMode] idkey set:", bool(ks.idkey))
            
            # For SeedKeeper: fingerprint is set when mnemonic is loaded
            elif keystore_type == "SeedKeeper":
                # fingerprint is already set by set_mnemonic()
                if hasattr(ks, 'fingerprint') and ks.fingerprint:
                    print("[TestMode] SeedKeeper fingerprint:", hexlify(ks.fingerprint).decode())
                else:
                    print("[TestMode] SeedKeeper: fingerprint not yet set")
            
            # For MemoryCard: fingerprint is derived from card pubkey
            elif keystore_type == "Smartcard":
                if hasattr(ks, 'fingerprint') and ks.fingerprint:
                    print("[TestMode] MemoryCard fingerprint:", hexlify(ks.fingerprint).decode())
                else:
                    print("[TestMode] MemoryCard: fingerprint not yet set")
        
        except Exception as e:
            self._respond("ERROR:" + str(e))
    async def _cmd_xpub(self, path):
        """Get XPUB at path."""
        ks = self.find_javacard_keystore()
        if not ks or not getattr(ks, '_pin_unlocked', False):
            self._respond("ERROR:Not unlocked")
            return
        
        # Only Satochip supports XPUB derivation from the card
        if ks.NAME != "Satochip":
            self._respond("ERROR:This keystore does not support XPUB derivation")
            return
        
        try:
            xpub = ks.get_xpub(path)
            xpub_str = str(xpub)
            self._respond("OK:" + xpub_str)
        except Exception as e:
            self._respond("ERROR:" + str(e))
    async def _cmd_sign(self, sighash_hex):
        """Sign a sighash."""
        ks = self.find_javacard_keystore()
        if not ks or not getattr(ks, '_pin_unlocked', False):
            self._respond("ERROR:Not unlocked")
            return
        
        # Only Satochip supports signing
        if ks.NAME != "Satochip":
            self._respond("ERROR:This keystore does not support signing")
            return
        
        try:
            sighash = unhexlify(sighash_hex)
            if len(sighash) != 32:
                self._respond("ERROR:Sighash must be 32 bytes")
                return
            
            path = self._default_account_path() + "/0/0"
            signature = ks.sign_hash(path, sighash)
            self._respond("OK:" + hexlify(signature).decode())
        except Exception as e:
            self._respond("ERROR:" + str(e))
    async def _cmd_sign_at(self, payload):
        """Sign a sighash at an explicit path.
        Format: m/84h/1h/0h/0/0:<hex_sighash>
        """
        ks = self.find_javacard_keystore()
        if not ks or not getattr(ks, '_pin_unlocked', False):
            self._respond("ERROR:Not unlocked")
            return
        
        # Only Satochip supports signing
        if ks.NAME != "Satochip":
            self._respond("ERROR:This keystore does not support signing")
            return
        
        if ':' not in payload:
            self._respond("ERROR:Invalid format, expected TEST_SIGN_AT:<path>:<hex_sighash>")
            return
        
        try:
            path, sighash_hex = payload.rsplit(':', 1)
            sighash = unhexlify(sighash_hex)
            if len(sighash) != 32:
                self._respond("ERROR:Sighash must be 32 bytes")
                return
            signature = ks.sign_hash(path, sighash)
            self._respond("OK:" + hexlify(signature).decode())
        except Exception as e:
            self._respond("ERROR:" + str(e))
    async def _cmd_set_network(self, net):
        """Set Specter active network and propagate to keystore/apps."""
        if self.specter is None or not hasattr(self.specter, 'set_network'):
            self._respond("ERROR:Specter reference not available")
            return
        valid = {'main', 'test', 'signet', 'regtest'}
        if net not in valid:
            self._respond("ERROR:Unsupported network")
            return
        try:
            self.specter.set_network(net)
            self._respond("OK:network_set:" + net)
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    async def _cmd_reset(self):
        """Reset connection."""
        ks = self.find_javacard_keystore()
        if ks:
            try:
                ks.connection.disconnect()
            except:
                pass
            ks.connected = False
            ks._pin_unlocked = False
            self._respond("OK:Reset")
        else:
            self._respond("ERROR:No JavaCard keystore found")
    async def _cmd_get_address(self, addr_arg):
        """Get address at derivation path.
        Format: m/84h/0h/0h/0/0 or m/84h/0h/0h:0 (account_path:index)
        """
        ks = self.find_javacard_keystore()
        if not ks or not ks.is_ready:
            self._respond("ERROR:Keystore not ready")
            return
        
        # Only Satochip supports address generation from card
        if ks.NAME != "Satochip":
            self._respond("ERROR:This keystore does not support address generation")
            return
        
        try:
            # Parse argument
            if ':' in addr_arg and not addr_arg.startswith('m'):
                # Format: account_path:index (e.g., m/84h/0h/0h:0)
                account_path, idx_str = addr_arg.rsplit(':', 1)
                idx = int(idx_str)
                full_path = account_path + "/0/" + str(idx)  # receive branch
            else:
                # Format: full path (e.g., m/84h/0h/0h/0/0)
                full_path = addr_arg
            
            print("[TestMode] Getting address for path:", full_path)
            
            # Get xpub at account level
            path_parts = full_path.split('/')
            if len(path_parts) < 6:
                self._respond("ERROR:Path too short, need at least m/purpose/coin/account/branch/index")
                return
            
            account_path = '/'.join(path_parts[:4])  # m/84h/0h/0h
            branch = int(path_parts[4].replace("'", "").replace("h", ""))
            idx = int(path_parts[5].replace("'", "").replace("h", ""))
            
            # Get account xpub
            xpub = ks.get_xpub(account_path)
            print("[TestMode] Account XPUB:", str(xpub))
            
            # Derive address using embit
            from embit.networks import NETWORKS
            from embit import bip32
            net_name = self._network_name()
            net = NETWORKS.get(net_name, NETWORKS['main'])
            
            # Derive child key at branch/index
            child = xpub.derive([branch, idx])
            
            # Generate address based on purpose (assume native segwit for now)
            # For m/84h paths - native segwit (bc1)
            # For m/49h paths - nested segwit (3)
            # For m/44h paths - legacy (1)
            purpose = int(path_parts[1].replace("'", "").replace("h", ""))
            
            if purpose == 84:
                # Native segwit - P2WPKH
                from embit.script import p2wpkh
                script_pubkey = p2wpkh(child)
                address = script_pubkey.address(net)
            elif purpose == 49:
                # Nested segwit - P2SH-P2WPKH
                from embit.script import p2sh, p2wpkh
                script_pubkey = p2sh(p2wpkh(child))
                address = script_pubkey.address(net)
            elif purpose == 44:
                # Legacy - P2PKH
                from embit.script import p2pkh
                script_pubkey = p2pkh(child)
                address = script_pubkey.address(net)
            else:
                # Default to native segwit
                from embit.script import p2wpkh
                script_pubkey = p2wpkh(child)
                address = script_pubkey.address(net)
            
            self._respond("OK:" + address)
            
        except Exception as e:
            print("[TestMode] _cmd_get_address error:", e)
            import sys
            sys.print_exception(e)
            self._respond("ERROR:" + str(e))

    
    async def _cmd_full_check(self):
        """Run comprehensive verification of JavaCard keystore functionality."""
        results = {}
        
        # 1. Check boot state
        ks = self.find_javacard_keystore()
        results['keystore_type'] = ks.NAME if ks else None
        results['keystore_found'] = ks is not None
        
        if not ks:
            self._respond("ERROR:JavaCard keystore not found")
            return
        
        results['card_inserted'] = ks.connection.isCardInserted() if ks else False
        results['connected'] = getattr(ks, 'connected', False)
        results['is_ready'] = ks.is_ready
        results['fingerprint_set'] = bool(getattr(ks, 'fingerprint', None))
        
        if not ks.is_ready:
            self._respond("ERROR:Keystore not ready - " + str(results))
            return
        
        # Satochip-specific tests (XPUB, signing, address)
        if ks.NAME == "Satochip":
            results['idkey_set'] = bool(getattr(ks, 'idkey', None))
            
            # Test XPUB derivation
            try:
                account_path = self._default_account_path()
                xpub = ks.get_xpub(account_path)
                results['xpub_ok'] = True
                results['xpub'] = str(xpub)[:20] + "..."
                results['account_path'] = account_path
            except Exception as e:
                results['xpub_ok'] = False
                results['xpub_error'] = str(e)
            
            # Test signing
            try:
                test_hash = b'\x00' * 32
                sig = ks.sign_hash(self._default_account_path() + "/0/0", test_hash)
                results['sign_ok'] = len(sig) > 0
                results['sign_len'] = len(sig)
            except Exception as e:
                results['sign_ok'] = False
                results['sign_error'] = str(e)
            
            # Test address generation
            try:
                from embit.networks import NETWORKS
                from embit.script import p2wpkh
                net = NETWORKS.get(self._network_name(), NETWORKS['main'])
                expected_hrp = net.get('bech32', 'bc')
                xpub = ks.get_xpub(self._default_account_path())
                child = xpub.derive([0, 0])
                address = p2wpkh(child).address(net)
                results['address_ok'] = address.startswith(expected_hrp + '1')
                results['address'] = address
            except Exception as e:
                results['address_ok'] = False
                results['address_error'] = str(e)
        
        # SeedKeeper-specific
        elif ks.NAME == "SeedKeeper":
            results['xpub_ok'] = 'N/A'
            results['sign_ok'] = 'N/A'
            results['address_ok'] = 'N/A'
            results['idkey_set'] = 'N/A'
            results['mnemonic_loaded'] = bool(getattr(ks, 'fingerprint', None))
        
        # MemoryCard-specific
        elif ks.NAME == "Smartcard":
            results['xpub_ok'] = 'N/A'
            results['sign_ok'] = 'N/A'
            results['address_ok'] = 'N/A'
            results['idkey_set'] = 'N/A'
            results['is_key_saved'] = getattr(ks, 'is_key_saved', False)
        
        # Test AEAD (available for all keystores)
        try:
            test_file = "/flash/testmode_full_check.aead"
            ks.save_aead(test_file, adata=b"chk", plaintext=b"test")
            adata, plaintext = ks.load_aead(test_file)
            results['aead_ok'] = (adata == b"chk" and plaintext == b"test")
            try:
                os.remove(test_file)
            except:
                pass
        except Exception as e:
            results['aead_ok'] = False
            results['aead_error'] = str(e)
        
        # Summary
        all_ok = all([
            results.get('keystore_found'),
            results.get('is_ready'),
            results.get('aead_ok'),
        ])
        
        # For Satochip, also require other tests
        if results.get('keystore_type') == "Satochip":
            all_ok = all_ok and all([
                results.get('fingerprint_set'),
                results.get('idkey_set'),
                results.get('xpub_ok'),
                results.get('sign_ok'),
                results.get('address_ok'),
            ])
        
        results['ALL_OK'] = all_ok
        
        if all_ok:
            self._respond("OK:FULL_CHECK_PASSED - " + str(results))
        else:
            self._respond("ERROR:FULL_CHECK_FAILED - " + str(results))
