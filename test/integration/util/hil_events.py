"""HIL structured-events tooling (P6).

Firmware side (src/test_mode.py) emits JSON-lines events prefixed with 'J:'
alongside legacy OK:/ERROR: responses on the UART3 VCP:
  J:{"event": "result", "cmd": ..., "ok": ..., "reply": ...}
  J:{"event": "card", "present": true|false}          (hotplug detection)
  J:{"event": "fb", "seq": N, "rgb565": "hex..."}     (framebuffer chunks)

This module parses those streams and reassembles framebuffer dumps into
PNG files (pure python - zlib + struct, no external image deps).
"""
import json
import struct
import zlib
from typing import Any, Dict, Iterable, List, Optional


class HILEventStream:
    """Accumulates raw UART lines, yielding structured events.

    Feed every non-empty line via feed(); legacy lines are returned as
    {"event": "legacy", "line": ...} so callers keep one code path.
    """

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def feed(self, line: bytes) -> Optional[Dict[str, Any]]:
        text = line.decode('utf-8', errors='replace').strip()
        if not text:
            return None
        if text.startswith('J:'):
            try:
                evt = json.loads(text[2:])
            except ValueError:
                evt = {"event": "malformed", "line": text}
            self.events.append(evt)
            return evt
        evt = {"event": "legacy", "line": text}
        self.events.append(evt)
        return evt

    def of_kind(self, kind: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e.get("event") == kind]

    def card_events(self) -> List[Dict[str, Any]]:
        return self.of_kind("card")


class FramebufferAssembler:
    """Reassembles TEST_FB_DUMP chunk events into a PNG image.

    Input: OK:FB:width:height:chunks header + 'fb' events with 'seq' and
    'rgb565' hex (512 pixels = 1024 hex chars per chunk, big-endian RGB565).
    Output: grayscale preview or full RGB PNG via rgb565_to_png().
    """

    def __init__(self, width: int, height: int, chunks: int) -> None:
        self.width = width
        self.height = height
        self.chunks = chunks
        self._parts: Dict[int, str] = {}

    def feed(self, evt: Dict[str, Any]) -> bool:
        """Add one 'fb' event; returns True when the image is complete."""
        if evt.get("event") != "fb":
            raise ValueError("not an fb event: %r" % (evt,))
        self._parts[int(evt["seq"])] = evt["rgb565"]
        return len(self._parts) >= self.chunks

    def rgb565_bytes(self) -> bytes:
        """Full framebuffer as little-endian RGB565 bytes (width*height*2)."""
        if len(self._parts) < self.chunks:
            raise ValueError(
                "incomplete framebuffer: %d/%d chunks" % (len(self._parts), self.chunks)
            )
        hexstr = "".join(self._parts[i] for i in range(self.chunks))
        return bytes.fromhex(hexstr)


def rgb565_to_png(width: int, height: int, rgb565: bytes) -> bytes:
    """Convert a big-endian-per-word RGB565 buffer to a PNG (RGB, 8-bit).

    The firmware dumps each 16-bit word as 4 hex digits (network order);
    this decoder matches that encoding. Pure-python PNG encoder.
    """
    raw = bytearray()
    pixels = struct.unpack(">%dH" % (width * height), rgb565)
    for row_start in range(0, width * height, width):
        raw.append(0)  # filter type 0 per scanline
        for px in pixels[row_start:row_start + width]:
            r = ((px >> 11) & 0x1F) << 3
            g = ((px >> 5) & 0x3F) << 2
            b = (px & 0x1F) << 3
            raw.extend((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def parse_fb_header(reply_line: bytes) -> Optional[tuple]:
    """Parse 'OK:FB:width:height:chunks' from the TEST_FB_DUMP reply."""
    text = reply_line.decode('utf-8', errors='replace').strip()
    if not text.startswith("OK:FB:"):
        return None
    try:
        w, h, c = (int(x) for x in text[len("OK:FB:"):].split(":"))
    except ValueError:
        return None
    return (w, h, c)
