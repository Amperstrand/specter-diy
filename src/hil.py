"""
Hardware-in-the-Loop (HIL) test mode module.

Enables automated testing over the debug UART (ST-Link VCP).
Activated by setting HIL_ENABLED = True in build_config.py (generated at build time).

Commands (sent over UART, newline-terminated):
  TEST_STATUS              -> OK:READY
  TEST_SCREEN              -> OK:SCREEN:<ClassName>:<id>[:<title>]
  TEST_KEYSTORE            -> OK:KEYSTORE:<name>
  TEST_UI:<json>           -> OK:UI (pass JSON value to screen.set_value)
  TEST_WIPE                -> OK:WIPED (wipe wallet storage, then reset)
  TEST_RESET               -> OK:RESET (soft reset)
  TEST_FINGERPRINT         -> OK:FINGERPRINT:<hex>
  TEST_MNEMONIC            -> OK:MNEMONIC:<words>

Examples:
  TEST_UI:""               -> set_value("") - proceed with default
  TEST_UI:1                -> set_value(1) - select option 1
  TEST_UI:true             -> set_value(True) - confirm
  TEST_UI:false            -> set_value(False) - cancel
  TEST_UI:"abandon ..."    -> set_value("abandon ...") - mnemonic
"""

HIL_DEFAULT_PIN = "1234"

_active_keystore_name = "unknown"
_active_keystore_ref = None


def set_keystore_name(name):
    global _active_keystore_name
    _active_keystore_name = name


def set_keystore_ref(ks):
    global _active_keystore_ref
    _active_keystore_ref = ks


def _get_keystore():
    return _active_keystore_ref


import json
from debug_trace import log, log_exception


class HILCommandHandler:
    """Handles HIL test commands received over UART.
    
    Mirrors the behavior of TCPGUI.tcp_loop() from the simulator.
    """

    def __init__(self, uart, gui=None):
        self.uart = uart
        self.gui = gui
        self._buffer = b""

    def set_gui(self, gui):
        """Set GUI reference after initialization."""
        self.gui = gui

    def poll(self):
        """Poll UART for incoming commands and process them.
        
        Called periodically by _hil_listener task.
        Returns True if a command was processed, False otherwise.
        """
        if self.uart is None:
            return False

        # Read available data
        try:
            chunk = self.uart.read(64)
        except Exception as e:
            log("HIL", "read error: %s" % e)
            return False

        if chunk is None or len(chunk) == 0:
            return False

        log("HIL", "RECV: %d bytes" % len(chunk))

        # Accumulate in buffer
        self._buffer += chunk

        # Process complete lines (newline-terminated)
        processed = 0
        while b"\n" in self._buffer:
            try:
                line, self._buffer = self._buffer.split(b"\n", 1)
            except ValueError:
                break

            line = line.strip()
            if len(line) == 0:
                continue

            self._process_line(line.decode())
            processed += 1

        if processed > 0:
            log("HIL", "Processed %d commands" % processed)

        return True

    def _process_line(self, line):
        """Process a single command line."""
        log("HIL", "CMD: %s" % line[:50])

        # TEST_STATUS - device ready check
        if line == "TEST_STATUS":
            self._respond("OK:READY")
            return

        if line == "TEST_SCREEN":
            self._respond(self._screen_info())
            return

        if line == "TEST_KEYSTORE":
            self._respond("OK:KEYSTORE:%s" % _active_keystore_name)
            return

        # TEST_UI:<json> - inject value into current screen
        if line.startswith("TEST_UI:"):
            json_val = line[len("TEST_UI:"):]
            self._inject_value(json_val)
            return

        # TEST_RESET - soft reset
        if line == "TEST_RESET":
            self._respond("OK:RESET")
            import pyb
            pyb.hard_reset()
            return

        # TEST_WIPE - wipe wallet and keystore storage
        if line == "TEST_WIPE":
            self._wipe_storage()
            return

        # TEST_SECRETS - list BIP39 secret IDs and labels from SeedKeeper
        if line == "TEST_SECRETS":
            self._list_secrets()
            return

        # TEST_ALL_SECRETS - list ALL secrets (including descriptors, passwords, etc.)
        if line == "TEST_ALL_SECRETS":
            self._list_all_secrets()
            return

        # TEST_IMPORT_SECRET:<hex_data>[:<label>] - import BIP39 secret to card
        if line.startswith("TEST_IMPORT_SECRET:"):
            self._import_secret(line[len("TEST_IMPORT_SECRET:"):])
            return

        # TEST_DELETE_SECRET:<sid> - delete secret by ID
        if line.startswith("TEST_DELETE_SECRET:"):
            self._delete_secret(line[len("TEST_DELETE_SECRET:"):])
            return

        # TEST_CARD_RESET - power cycle the smartcard (disconnect + reconnect)
        if line == "TEST_CARD_RESET":
            self._card_reset()
            return

        # TEST_FINGERPRINT - get current keystore fingerprint
        if line == "TEST_FINGERPRINT":
            self._get_fingerprint()
            return

        # TEST_MNEMONIC - export currently loaded mnemonic
        if line == "TEST_MNEMONIC":
            self._get_mnemonic()
            return

        # TEST_GP_INIT - open SCP03 session with card
        if line == "TEST_GP_INIT":
            self._gp_init()
            return

        # TEST_GP_STATUS - list card registry via GP GET STATUS
        if line == "TEST_GP_STATUS":
            self._gp_status()
            return

        # TEST_GP_DELETE:<hex_aid> - delete AID from card
        if line.startswith("TEST_GP_DELETE:"):
            self._gp_delete(line[len("TEST_GP_DELETE:"):])
            return

        # TEST_GP_INSTALL[:<path>] - install applet from DGP file
        if line.startswith("TEST_GP_INSTALL"):
            arg = line[len("TEST_GP_INSTALL"):].strip()
            if arg.startswith(":"):
                arg = arg[1:]
            self._gp_install(arg if arg else None)
            return

        # TEST_GP_VERIFY[:<hex_aid>] - verify AID is installed
        if line.startswith("TEST_GP_VERIFY"):
            arg = line[len("TEST_GP_VERIFY"):].strip()
            if arg.startswith(":"):
                arg = arg[1:]
            self._gp_verify(arg if arg else None)
            return

        # TEST_GP_PROBE - non-destructive card probe
        if line == "TEST_GP_PROBE":
            self._gp_probe()
            return

        # Fallback: try to parse as JSON (mirrors TCPGUI behavior)
        try:
            json.loads("[%s]" % line)
            self._inject_value(line)
            return
        except Exception:
            pass

        log("HIL", "Unknown command: %s" % line)
        self._respond("ERR:UNKNOWN")

    def _respond(self, message):
        """Send response over UART."""
        if self.uart is not None:
            self.uart.write(("%s\r\n" % message).encode())
        log("HIL", "RSP: %s" % message)

    def _inject_value(self, json_val):
        """Parse JSON value and inject into current screen.
        
        Mirrors TCPGUI.tcp_loop() behavior:
        - val = json.loads("[%s]" % cmd)[0]
        - if self.scr is not None: self.scr.set_value(val)
        """
        if self.gui is None:
            log("HIL", "No GUI for value injection")
            self._respond("ERR:NO_GUI")
            return

        # Parse JSON value (wrapped in array to handle all types)
        try:
            val = json.loads("[%s]" % json_val)[0]
        except Exception as e:
            log("HIL", "JSON parse error: %s" % e)
            self._respond("ERR:JSON")
            return

        # Inject into current screen (same pattern as TCPGUI)
        try:
            scr = self.gui.scr
            if scr is not None:
                if type(scr).__name__ == "PinScreen" and hasattr(scr, "pin"):
                    pin_val = val
                    if pin_val == "":
                        pin_val = HIL_DEFAULT_PIN
                    if pin_val is None:
                        pin_val = ""
                    scr.pin.set_text(str(pin_val))
                    scr.release()
                else:
                    scr.set_value(val)
                log("HIL", "Injected: %s" % repr(val)[:50])
                self._respond("OK:UI")
            else:
                log("HIL", "No screen available")
                self._respond("ERR:NO_SCREEN")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:INJECT")

    def _screen_info(self):
        if self.gui is None:
            return "ERR:NO_GUI"
        try:
            scr = self.gui.scr
            if scr is None:
                return "OK:SCREEN:None:0"
            title = ""
            try:
                if hasattr(scr, 'title'):
                    t = scr.title
                    if hasattr(t, 'get_text'):
                        title = t.get_text()
                    elif isinstance(t, str):
                        title = t
            except Exception:
                pass
            if title:
                return "OK:SCREEN:%s:%d:%s" % (type(scr).__name__, id(scr), title)
            return "OK:SCREEN:%s:%d" % (type(scr).__name__, id(scr))
        except Exception:
            return "ERR:NO_SCREEN"

    def _wipe_storage(self):
        import platform
        try:
            wallet_path = platform.fpath("/qspi/wallets")
            try:
                platform.delete_recursively(wallet_path)
            except OSError:
                pass
            log("HIL", "Wiped: %s" % wallet_path)
            keystore_path = platform.fpath("/flash/keystore")
            if keystore_path:
                try:
                    platform.delete_recursively(keystore_path)
                except OSError:
                    pass
                log("HIL", "Wiped: %s" % keystore_path)
            self._respond("OK:WIPED")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:WIPE_FAIL")

    def _get_fingerprint(self):
        try:
            ks = _get_keystore()
            if ks is None:
                self._respond("ERR:NO_KEYSTORE")
                return
            fp = ks.fingerprint
            if fp is None:
                self._respond("ERR:NO_FINGERPRINT")
            else:
                from binascii import hexlify
                self._respond("OK:FINGERPRINT:%s" % hexlify(fp).decode())
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:FINGERPRINT_FAIL")

    def _get_mnemonic(self):
        try:
            ks = _get_keystore()
            if ks is None:
                self._respond("ERR:NO_KEYSTORE")
                return
            mn = ks.mnemonic
            if mn is None:
                self._respond("ERR:NO_MNEMONIC")
            else:
                self._respond("OK:MNEMONIC:%s" % mn)
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:MNEMONIC_FAIL")

    def _list_secrets(self):
        try:
            ks = _get_keystore()
            if ks is None or not hasattr(ks, 'applet'):
                self._respond("ERR:NO_SEEDKEEPER")
                return
            headers = ks.applet.list_secret_headers()
            bip39 = [
                h for h in headers
                if h['type'] in (0x10, 0x30, 0x31)
                and (h['type'] != 0x10 or h.get('subtype') == 1)
            ]
            parts = []
            for h in bip39:
                label = h.get('label', '')
                if not isinstance(label, str) or len(label) == 0:
                    label = 'Secret #%d' % h['id']
                fp = h.get('fingerprint', '????????')
                parts.append("%d:%s:%s" % (h['id'], label, fp))
            self._respond("OK:SECRETS:%s" % ",".join(parts))
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:SECRETS_FAIL")

    def _list_all_secrets(self):
        try:
            ks = _get_keystore()
            if ks is None or not hasattr(ks, 'applet'):
                self._respond("ERR:NO_SEEDKEEPER")
                return
            headers = ks.applet.list_secret_headers()
            type_names = {
                0x10: "MASTERSEED", 0x30: "BIP39", 0x31: "BIP39v2",
                0x40: "ELECTRUM", 0x90: "PASSWORD", 0xC0: "DATA",
                0xC1: "DESCRIPTOR",
            }
            parts = []
            for h in headers:
                label = h.get('label', '')
                if not isinstance(label, str) or len(label) == 0:
                    label = 'Secret #%d' % h['id']
                tname = type_names.get(h['type'], "0x%02x" % h['type'])
                fp = h.get('fingerprint', '????????')
                parts.append("%d:%s:%s:%s" % (h['id'], tname, label, fp))
            self._respond("OK:ALL_SECRETS:%s" % ",".join(parts))
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:ALL_SECRETS_FAIL")

    def _import_secret(self, args):
        try:
            from binascii import unhexlify
            ks = _get_keystore()
            if ks is None or not hasattr(ks, 'applet'):
                self._respond("ERR:NO_SEEDKEEPER")
                return
            parts = args.split(":", 1)
            hex_data = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 else ""
            secret_data = unhexlify(hex_data)
            sid, fp = ks.applet.import_secret(secret_data, secret_type=0x30, label=label)
            self._respond("OK:IMPORT:%d:%s" % (sid, fp))
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:IMPORT_FAIL:%s" % str(e))

    def _delete_secret(self, sid_str):
        try:
            ks = _get_keystore()
            if ks is None or not hasattr(ks, 'applet'):
                self._respond("ERR:NO_SEEDKEEPER")
                return
            sid = int(sid_str.strip())
            ks.applet.delete_secret(sid)
            self._respond("OK:DELETED:%d" % sid)
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:DELETE_FAIL:%s" % str(e))

    def _card_reset(self):
        try:
            import time as _time
            from keystore.javacard.util import get_connection
            ks = _get_keystore()
            conn = get_connection()
            try:
                conn.disconnect()
            except Exception:
                pass
            _time.sleep_ms(500)
            conn.connect(conn.T1_protocol)
            if ks is not None and hasattr(ks, 'applet'):
                ks.applet.select()
                ks.applet.init_secure_channel()
                ks.applet.verify_pin(ks._last_pin or "1234")
                ks.connected = True
                ks._pin_unlocked = True
            self._respond("OK:CARD_RESET")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:CARD_RESET_FAIL:%s" % str(e))

    def _gp_connect(self):
        """Disconnect existing connection, wait, and reconnect for GP operations."""
        from keystore.javacard.util import get_connection
        import time as _time
        conn = get_connection()
        try:
            conn.disconnect()
        except Exception:
            pass
        _time.sleep_ms(500)
        conn.connect(conn.T1_protocol)
        return conn

    def _gp_init(self):
        try:
            from binascii import hexlify
            from keystore.javacard.gp.profiles import JCOP4_PROFILE
            from keystore.javacard.gp.scp02 import open_session

            conn = self._gp_connect()
            session = open_session(conn, JCOP4_PROFILE)
            parts = [
                "SCP02",
                "kvi=%d" % JCOP4_PROFILE["key_version"],
                "mac=%d" % (1 if session.mac else 0),
                "enc=%d" % (1 if session.enc else 0),
            ]
            self._respond("OK:GP_INIT:%s" % ",".join(parts))
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_INIT_FAIL:%s" % str(e))

    def _gp_status(self):
        try:
            from keystore.javacard.gp.profiles import JCOP4_PROFILE
            from keystore.javacard.gp.scp02 import open_session
            from keystore.javacard.gp.registry import list_all, format_registry

            conn = self._gp_connect()
            session = open_session(conn, JCOP4_PROFILE)
            registry = list_all(session)
            text = format_registry(registry)
            self._respond("OK:GP_STATUS:%s" % text)
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_STATUS_FAIL:%s" % str(e))

    def _gp_delete(self, hex_aid):
        try:
            from binascii import unhexlify
            from keystore.javacard.gp.profiles import JCOP4_PROFILE
            from keystore.javacard.gp.scp02 import open_session
            from keystore.javacard.gp.deleter import delete_aid

            aid = unhexlify(hex_aid.strip())
            conn = self._gp_connect()
            session = open_session(conn, JCOP4_PROFILE)
            delete_aid(session, aid)
            self._respond("OK:GP_DELETED:%s" % hex_aid.strip())
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_DELETE_FAIL:%s" % str(e))

    def _gp_install(self, path=None):
        try:
            from keystore.javacard.gp.profiles import JCOP4_PROFILE
            from keystore.javacard.gp.scp02 import open_session
            from keystore.javacard.gp.loader import (
                install_from_dgp, extract_package_aid, verify_install,
            )
            from binascii import hexlify as _h

            default_path = "/flash/gp/TeapotApplet.dgp"
            filepath = path if path else default_path

            try:
                f = open(filepath, "rb")
                dgp_data = f.read()
                f.close()
            except Exception:
                self._respond("ERR:GP_INSTALL_FAIL:file not found: %s" % filepath)
                return

            pkg_aid = extract_package_aid(dgp_data)
            pkg_aid_hex = _h(pkg_aid).decode()
            self._respond("OK:GP_INSTALL:loading pkg=%s size=%d" % (
                pkg_aid_hex, len(dgp_data)))

            conn = self._gp_connect()
            session = open_session(conn, JCOP4_PROFILE)
            sd_aid = JCOP4_PROFILE["isd_aid"]

            installed = install_from_dgp(session, dgp_data, sd_aid)

            instance_aid = installed + b"\x01"
            if verify_install(session, instance_aid):
                self._respond("OK:GP_INSTALL:success %s" % _h(installed).decode())
            else:
                self._respond("ERR:GP_INSTALL_FAIL:verify failed")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_INSTALL_FAIL:%s" % str(e))

    def _gp_verify(self, hex_aid=None):
        try:
            from keystore.javacard.gp.profiles import JCOP4_PROFILE
            from keystore.javacard.gp.scp02 import open_session
            from keystore.javacard.gp.registry import find_aid
            from binascii import unhexlify, hexlify as _h

            conn = self._gp_connect()
            session = open_session(conn, JCOP4_PROFILE)

            if hex_aid:
                instance_aid = unhexlify(hex_aid.strip())
            else:
                instance_aid = unhexlify("B00B5111CB01")
            entry = find_aid(session, instance_aid)
            if entry is not None:
                self._respond("OK:GP_VERIFY:installed %s" % _h(instance_aid).decode())
            else:
                self._respond("OK:GP_VERIFY:not_found %s" % _h(instance_aid).decode())
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_VERIFY_FAIL:%s" % str(e))

    def _gp_probe(self):
        try:
            from binascii import hexlify
            from keystore.javacard.gp.probe import probe_card

            conn = self._gp_connect()
            result = probe_card(conn)
            kind = result["kind"]
            atr = hexlify(result.get("atr", b"")).decode() if result.get("atr") else ""
            mc = "mc=%d" % (1 if result.get("memorycard_installed") else 0)
            self._respond("OK:GP_PROBE:%s,atr=%s,%s" % (kind, atr, mc))
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:GP_PROBE_FAIL:%s" % str(e))
