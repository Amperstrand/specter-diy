"""
Test mode for automated Satochip testing via serial.

Commands:
  TEST_PIN:1234           - Unlock with PIN
  TEST_XPUB:m/84h/0h/0h   - Get XPUB at path
  TEST_SIGN:<hex_sighash> - Sign a 32-byte sighash
  TEST_STATUS             - Get current status
  TEST_RESET              - Reset connection

Responses:
  OK:<data>
  ERROR:<message>
"""

import sys
from binascii import hexlify, unhexlify

class TestMode:
    def __init__(self, specter_ref=None):
        self.specter = specter_ref  # Reference to Specter instance
        self.running = False
        
    def find_satochip(self):
        """Find Satochip keystore instance from active Specter."""
        if self.specter is not None and hasattr(self.specter, 'keystore'):
            ks = self.specter.keystore
            if ks is not None and hasattr(ks, 'NAME') and ks.NAME == "Satochip":
                return ks
        return None
    
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
                                    await self._process_command(buffer.strip())
                                buffer = ""
                            else:
                                buffer += char
                    else:
                        await asyncio.sleep_ms(50)
                        
                except Exception as e:
                    print("[TestMode] Poll error:", e)
                    await asyncio.sleep_ms(100)
                        
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
            elif cmd == "TEST_RESET":
                await self._cmd_reset()
            else:
                self._respond("ERROR:Unknown command")
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    def _respond(self, msg):
        """Send response."""
        print("[TestMode] RESP:", msg)
    
    async def _cmd_status(self):
        """Get current status."""
        satochip = self.find_satochip()
        status = {
            "satochip_found": satochip is not None,
            "card_inserted": satochip.connection.isCardInserted() if satochip else False,
            "connected": getattr(satochip, 'connected', False) if satochip else False,
            "unlocked": getattr(satochip, '_pin_unlocked', False) if satochip else False,
            "fingerprint": hexlify(satochip.fingerprint).decode() if satochip and hasattr(satochip, 'fingerprint') and satochip.fingerprint else None,
        }
        self._respond("OK:" + str(status))
    
    async def _cmd_pin(self, pin):
        """Unlock with PIN."""
        satochip = self.find_satochip()
        if not satochip:
            self._respond("ERROR:Satochip not found")
            return
            
        if not satochip.connection.isCardInserted():
            self._respond("ERROR:No card inserted")
            return
            
        try:
            # Connect if needed
            if not getattr(satochip, 'connected', False):
                satochip.connection.connect(satochip.connection.T1_protocol)
                satochip.applet.select()
                satochip.applet.init_secure_channel()
                satochip.connected = True
            
            # Verify PIN
            satochip._unlock(pin)
            self._respond("OK:PIN verified")
            
            # Get authentikey for fingerprint
            authentikey_bytes = satochip.applet.get_authentikey()
            print("[TestMode] Authentikey length:", len(authentikey_bytes) if authentikey_bytes else 0)
            if authentikey_bytes:
                import hashlib
                # Handle different authentikey formats:
                # - 65 bytes: uncompressed pubkey (04 || x || y)
                # - 107 bytes: might include additional data
                if len(authentikey_bytes) == 65:
                    x = authentikey_bytes[1:33]
                    y_last = authentikey_bytes[64]
                    prefix = b'\x03' if y_last % 2 else b'\x02'
                    compressed = prefix + x
                elif len(authentikey_bytes) >= 65:
                    # Try to extract the 65-byte pubkey from the response
                    # The pubkey might start at offset 0 or have a prefix
                    x = authentikey_bytes[1:33]
                    y_last = authentikey_bytes[64]
                    prefix = b'\x03' if y_last % 2 else b'\x02'
                    compressed = prefix + x
                else:
                    print("[TestMode] Unexpected authentikey length:", len(authentikey_bytes))
                    return
                sha256_hash = hashlib.sha256(compressed).digest()
                ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
                satochip.fingerprint = ripemd160[:4]
                print("[TestMode] Fingerprint:", hexlify(satochip.fingerprint).decode())
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    async def _cmd_xpub(self, path):
        """Get XPUB at path."""
        satochip = self.find_satochip()
        if not satochip or not getattr(satochip, '_pin_unlocked', False):
            self._respond("ERROR:Not unlocked")
            return
            
        try:
            xpub = satochip.get_xpub(path)
            xpub_str = str(xpub)
            self._respond("OK:" + xpub_str)
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    async def _cmd_sign(self, sighash_hex):
        """Sign a sighash."""
        satochip = self.find_satochip()
        if not satochip or not getattr(satochip, '_pin_unlocked', False):
            self._respond("ERROR:Not unlocked")
            return
            
        try:
            sighash = unhexlify(sighash_hex)
            if len(sighash) != 32:
                self._respond("ERROR:Sighash must be 32 bytes")
                return
                
            signature = satochip.applet.sign_transaction_hash(0xFF, sighash)
            self._respond("OK:" + hexlify(signature).decode())
        except Exception as e:
            self._respond("ERROR:" + str(e))
    
    async def _cmd_reset(self):
        """Reset connection."""
        satochip = self.find_satochip()
        if satochip:
            try:
                satochip.connection.disconnect()
            except:
                pass
            satochip.connected = False
            satochip._pin_unlocked = False
            self._respond("OK:Reset")
        else:
            self._respond("ERROR:No Satochip")
