#!/usr/bin/env python3
"""Convert JavaCard CAP file to DGP format for Specter-DIY.

DGP format is the CAP components concatenated in GlobalPlatform tag order
(tags 0x01-0x09), excluding Descriptor.cap (tag 0x0B or 0x0A).

Components are sorted by their actual tag byte (first byte of each file),
not by filename, since CAP ZIPs may use non-standard naming.

Usage:
    python cap_to_dgp.py input.cap output.dgp
"""

import sys
import zipfile
import hashlib

# Valid GP component tags for LOAD (excludes Descriptor)
GP_LOAD_TAGS = set(range(0x01, 0x0A))


def cap_to_dgp(cap_path, dgp_path):
    """Convert CAP file to DGP format."""
    print(f"Converting {cap_path} to DGP format...")

    with zipfile.ZipFile(cap_path, 'r') as zf:
        components = {}

        for name in zf.namelist():
            if not name.endswith('.cap'):
                continue

            data = zf.read(name)
            if len(data) < 3:
                continue

            tag = data[0]
            if tag in GP_LOAD_TAGS:
                if tag in components:
                    print(f"  WARNING: duplicate tag 0x{tag:02x}, keeping first")
                    continue
                components[tag] = (name, data)

        total_size = 0
        dgp_parts = []
        for tag in sorted(components.keys()):
            name, data = components[tag]
            dgp_parts.append(data)
            total_size += len(data)
            print(f"  tag=0x{tag:02x} {name}: {len(data)} bytes")

        dgp_data = b''.join(dgp_parts)
        sha256 = hashlib.sha256(dgp_data).hexdigest()

        print(f"\nDGP size: {len(dgp_data)} bytes")
        print(f"SHA256: {sha256}")

        with open(dgp_path, 'wb') as f:
            f.write(dgp_data)

        print(f"Written to {dgp_path}")

        if len(dgp_data) >= 10 and dgp_data[0] == 0x01 and dgp_data[3:5] == b'\xDE\xCA':
            flags = dgp_data[7]
            aid_off = 12 if flags & 0x01 else 8
            aid_len = dgp_data[aid_off]
            aid = dgp_data[aid_off + 1:aid_off + 1 + aid_len]
            print(f"Package AID: {aid.hex()} ({aid_len} bytes)")

        return sha256


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.cap output.dgp")
        sys.exit(1)

    cap_to_dgp(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
