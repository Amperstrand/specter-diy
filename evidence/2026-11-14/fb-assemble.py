import ast, re, sys
from PIL import Image

stream = []
for line in open('/tmp/opencode/f469-console.log', 'rb').read().decode('utf-8', 'replace').splitlines():
    m = re.search(r"b('(?:[^'\\]|\\.)*')\s*$", line)
    if not m:
        continue
    try:
        data = ast.literal_eval('b' + m.group(1))
    except Exception:
        continue
    stream.append(data)
stream = b''.join(stream).decode('utf-8', 'replace')

chunks = {}
for m in re.finditer(r'"event": "fb", "seq": (\d+), "argb": "([^"]+)"', stream):
    chunks[int(m.group(1))] = m.group(2)
n = len(chunks)
W, H = 800, 480
total_px = W * H
have_px = sum(len(v) // 8 for v in chunks.values())
print(f"chunks: {n}/1500, pixels: {have_px}/{total_px}")
if not n:
    sys.exit(1)

img = Image.new('RGB', (W, H))
px = img.load()
for seq, hexdata in chunks.items():
    for i in range(0, len(hexdata) - 7, 8):
        tok = hexdata[i:i+8]
        if tok[0] == '-':
            v = -int(tok[1:], 16)
        else:
            v = int(tok, 16)
        v &= 0xFFFFFFFF
        r = (v >> 16) & 0xff
        g = (v >> 8) & 0xff
        b = v & 0xff
        idx = seq * 256 + i // 8
        if idx < total_px:
            px[idx % W, idx // W] = (r, g, b)
img.save(sys.argv[1] if len(sys.argv) > 1 else '/tmp/opencode/fb.png')
print("saved")
