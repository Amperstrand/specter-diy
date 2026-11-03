"""P6 HIL host-side tooling tests (no hardware).

Covers: JSON-lines event parsing, framebuffer chunk reassembly, the pure
PNG encoder round-trip, and the #23 USB-VCP-drop resilience of
UARTChannel.resilient_query (mocked serial).
"""
import os
import struct
import sys
import zlib
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "integration"))


class HILEventStreamTest(TestCase):
    def test_parses_json_events(self):
        from util.hil_events import HILEventStream

        stream = HILEventStream()
        evt = stream.feed(b'J:{"event": "card", "present": true}')
        self.assertEqual(evt, {"event": "card", "present": True})
        self.assertEqual(len(stream.card_events()), 1)

    def test_legacy_lines_preserved(self):
        from util.hil_events import HILEventStream

        stream = HILEventStream()
        evt = stream.feed(b'OK:READY')
        self.assertEqual(evt["event"], "legacy")
        self.assertEqual(evt["line"], "OK:READY")

    def test_malformed_json_flagged(self):
        from util.hil_events import HILEventStream

        stream = HILEventStream()
        evt = stream.feed(b'J:{"event": broken')
        self.assertEqual(evt["event"], "malformed")

    def test_result_event_shape(self):
        from util.hil_events import HILEventStream

        stream = HILEventStream()
        stream.feed(b'J:{"event": "result", "cmd": "TEST_STATUS", "ok": true, "reply": "OK:..."}')
        results = stream.of_kind("result")
        self.assertEqual(results[0]["cmd"], "TEST_STATUS")
        self.assertTrue(results[0]["ok"])


def _fb_events(width, height, pixels_be):
    """Build fb chunk events the way the firmware emits them (512 px/chunk)."""
    total = width * height
    chunk = 512
    chunks = (total + chunk - 1) // chunk
    evts = []
    for seq in range(chunks):
        part = pixels_be[seq * chunk * 2:(seq + 1) * chunk * 2]
        evts.append({"event": "fb", "seq": seq, "rgb565": part.hex()})
    return chunks, evts


class FramebufferTest(TestCase):
    WIDTH, HEIGHT = 64, 32  # 2048 px -> 4 chunks + remainder = 4 chunks

    def test_roundtrip_png(self):
        from util.hil_events import FramebufferAssembler, rgb565_to_png, parse_fb_header

        w, h = self.WIDTH, self.HEIGHT
        # red in RGB565 = 0xF800
        words = [0xF800] * (w * h)
        pixels_be = struct.pack(">%dH" % len(words), *words)

        chunks, evts = _fb_events(w, h, pixels_be)
        header = ("OK:FB:%d:%d:%d" % (w, h, chunks)).encode()
        self.assertEqual(parse_fb_header(header), (w, h, chunks))

        asm = FramebufferAssembler(*parse_fb_header(header))
        for i, evt in enumerate(evts):
            complete = asm.feed(evt)
        self.assertTrue(complete)
        self.assertEqual(asm.rgb565_bytes(), pixels_be)

        png = rgb565_to_png(w, h, pixels_be)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        w_, h_ = struct.unpack(">II", png[16:24])
        self.assertEqual((w_, h_), (w, h))
        # decompressible IDAT
        idat_start = png.find(b"IDAT") + 4
        idat_len = struct.unpack(">I", png[idat_start - 8:idat_start - 4])[0]
        idat = png[idat_start:idat_start + idat_len]
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), h * (1 + w * 3))
        # red pixel: first scanline filter byte 0 then (248, 0, 0)
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[1:4], bytes((0xF8, 0, 0)))

    def test_incomplete_dump_rejected(self):
        from util.hil_events import FramebufferAssembler

        chunks, evts = _fb_events(64, 32, b"\x00" * (64 * 32 * 2))
        asm = FramebufferAssembler(64, 32, chunks)
        asm.feed(evts[0])
        with self.assertRaises(ValueError):
            asm.rgb565_bytes()


class ResilientQueryTest(TestCase):
    def _channel(self):
        from util.uart_channel import UARTChannel

        chan = UARTChannel(port="/dev/ttyACM_FAKE")
        return chan

    def test_reconnects_after_vcp_drop(self):
        """#23: port vanishes mid-session; resilient_query reopens + retries."""
        chan = self._channel()
        reopened = MagicMock()
        reopened.is_open = True
        chan._reopen = MagicMock(return_value=True, side_effect=lambda: setattr(chan, "_serial", reopened))
        calls = {"n": 0}

        def flaky_query(cmd, timeout=5):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("[Errno 19] No such device")
            return b"OK:READY\n"

        chan.query = flaky_query
        chan._serial = None  # port gone -> forces the reopen path
        resp = chan.resilient_query("TEST_STATUS")
        self.assertEqual(resp, b"OK:READY\n")
        chan._reopen.assert_called_once()

    def test_raises_after_exhausted_retries(self):
        chan = self._channel()
        chan._reopen = MagicMock(return_value=False)
        with self.assertRaises(Exception):
            chan.resilient_query("TEST_STATUS", retries=2)


if __name__ == "__main__":
    import unittest
    unittest.main()
