from .specter import SpecterGUI
import pyb
import json
import asyncio
import sys

class TCPGUI(SpecterGUI):
    """
    Simulated GUI for testing.
    User interaction can be provided over telnet on port 8787.
    
    Control commands (for HIL testing - work on both simulator and hardware):
        TEST_STATUS  -> OK:READY           (liveness check)
        TEST_SCREEN  -> OK:SCREEN:<class>:<id>  (current screen info)
        TEST_RESET   -> OK:RESET           (reset device/simulator)
        <json>       -> <screen-class>     (existing JSON passthrough)
    """
    def __init__(self, *args, **kwargs):
        self.tcp = pyb.UART('"S') # will be on port 8787
        super().__init__(*args, **kwargs)

    def start(self, *args, **kwargs):
        super().start(*args, **kwargs)
        asyncio.create_task(self.tcp_loop())

    async def tcp_loop(self):
        """Main control loop - handles control commands then JSON passthrough."""
        res = b""
        while True:
            await asyncio.sleep_ms(30)
            try:
                # trying to read something
                chunk = self.tcp.read(100)
                # if we didn't get anything - return
                if chunk is None:
                    continue
                res += chunk
                if b"\r" in res or b"\n" in res:
                    arr = res.replace(b"\r",b"\n").split(b"\n")
                    line = arr[0].strip()
                    res = b""
                    
                    # ═══════════════════════════════════════════════════
                    # CONTROL COMMANDS (for HIL testing)
                    # ═══════════════════════════════════════════════════
                    
                    # TEST_STATUS - liveness check
                    if line == b"TEST_STATUS":
                        self._tcp_reply(b"OK:READY")
                        continue
                    
                    # TEST_SCREEN - query current screen
                    if line == b"TEST_SCREEN":
                        scr = self.scr
                        if scr is None:
                            self._tcp_reply(b"OK:SCREEN:None:0")
                        else:
                            self._tcp_reply(b"OK:SCREEN:%s:%d" % (
                                type(scr).__name__.encode(),
                                id(scr)
                            ))
                        continue
                    
                    # TEST_RESET - reset device/simulator
                    if line == b"TEST_RESET":
                        self._tcp_reply(b"OK:RESET")
                        self.do_reset()
                        continue
                    
                    # ═══════════════════════════════════════════════════
                    # JSON PASSTHROUGH (existing logic - unchanged)
                    # ═══════════════════════════════════════════════════
                    
                    try:
                        cmd = line.decode()
                        if cmd == "quit":
                            print("QUIT!")
                            sys.exit(1)
                        val = json.loads("[%s]" % cmd)[0]
                        if self.scr is not None:
                            self.scr.set_value(val)
                    except Exception as e:
                        # JSON parse error or other - silently ignore
                        pass
                        
            except Exception as e:
                print(e)
                res = b""
    
    def _tcp_reply(self, msg):
        """Send response over transport."""
        try:
            self.tcp.write(msg + b"\r\n")
        except:
            pass
    
    def do_reset(self):
        """Reset device/simulator. Override in subclass for hardware."""
        # Simulator: exit process, test runner will restart
        sys.exit(0)

    async def open_popup(self, scr):
        try:
            self.tcp.write(b"%s\r\n" % type(scr).__name__)
        except:
            pass
        return await super().open_popup(scr)


    async def load_screen(self, scr):
        try:
            self.tcp.write(b"%s\r\n" % type(scr).__name__)
        except:
            pass
        return await super().load_screen(scr)
