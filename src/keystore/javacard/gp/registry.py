"""GP Registry: query card for installed packages and applets.

Implements GET STATUS command to enumerate the card's content registry.
Reference: GlobalPlatform Card Specification v2.3, Section 11.4
"""

from binascii import hexlify


class GPRegistryError(Exception):
    pass


def _parse_tlv(data, offset=0, end=None):
    """Parse a single TLV entry. Returns (tag, value, next_offset)."""
    if end is None:
        end = len(data)
    if offset >= end:
        return None, None, offset
    tag = data[offset]
    offset += 1
    length = data[offset]
    offset += 1
    if length == 0x81:
        length = data[offset]
        offset += 1
    elif length == 0x82:
        length = (data[offset] << 8) | data[offset + 1]
        offset += 2
    value = data[offset:offset + length]
    return tag, value, offset + length


def _parse_entries(data):
    """Parse all TLV entries in a GET STATUS response."""
    entries = []
    offset = 0
    while offset < len(data):
        tag, value, next_offset = _parse_tlv(data, offset)
        if tag is None:
            break
        if tag == 0xE3:
            entry = _parse_entry(value)
            if entry is not None:
                entries.append(entry)
        offset = next_offset
    return entries


def _parse_entry(data):
    """Parse a single E3 entry (ISD, app, or package)."""
    entry = {
        "aid": b"",
        "lifecycle": None,
        "privileges": None,
        "version": None,
        "module_aids": [],
        "associated_sd": b"",
    }
    offset = 0
    while offset < len(data):
        tag, value, next_offset = _parse_tlv(data, offset)
        if tag is None:
            break
        if tag == 0x4F:
            entry["aid"] = value
        elif tag == 0x9F70:
            entry["lifecycle"] = value[0] if len(value) > 0 else None
        elif tag == 0xC5:
            entry["privileges"] = value
        elif tag == 0xCC:
            entry["associated_sd"] = value
        elif tag == 0xCE:
            if len(value) >= 2:
                entry["version"] = "%d.%d" % (value[0], value[1])
            elif len(value) == 1:
                entry["version"] = "%d.0" % value[0]
        elif tag == 0x84:
            entry["module_aids"].append(value)
        offset = next_offset
    return entry


def get_status(session, element_type):
    """Send GET STATUS and parse the response.

    element_type:
      0x80 - Issuer Security Domain
      0x40 - Applications and their load files
      0x20 - Executable load files and their modules
      0x10 - Load files, modules, and their packages

    Returns list of entry dicts.
    """
    p2 = 0x00
    all_entries = []
    while True:
        data = bytes([0x4F, 0x00])
        resp_data, sw1, sw2 = session.send_command(0x80, 0xF2, element_type, p2, data)

        if sw1 == 0x6A and sw2 == 0x86:
            return all_entries

        if sw1 != 0x90 or sw2 != 0x00:
            if sw1 == 0x61:
                resp_data, sw1, sw2 = session.send_command(
                    0x80, 0xC0, 0x00, 0x00, bytes([sw2]))
                if sw1 != 0x90 or sw2 != 0x00:
                    break
            else:
                raise GPRegistryError(
                    "GET STATUS failed: SW=%02X%02X" % (sw1, sw2))

        entries = _parse_entries(resp_data)
        all_entries.extend(entries)

        if sw1 == 0x61:
            p2 = 0x02
        else:
            break

    return all_entries


def list_all(session):
    """List all installed elements on the card.

    Returns dict with keys: 'isd', 'apps', 'packages', 'load_files'
    """
    result = {
        "isd": [],
        "apps": [],
        "packages": [],
        "load_files": [],
    }
    try:
        result["isd"] = get_status(session, 0x80)
    except Exception:
        pass
    try:
        result["apps"] = get_status(session, 0x20)
    except Exception:
        pass
    try:
        result["load_files"] = get_status(session, 0x40)
    except Exception:
        pass
    try:
        result["packages"] = get_status(session, 0x10)
    except Exception:
        pass
    return result


def find_aid(session, aid):
    """Check if a specific AID is installed on the card.

    Returns the entry dict if found, None otherwise.
    """
    all_entries = get_status(session, 0x20) + get_status(session, 0x10)
    for entry in all_entries:
        if entry["aid"] == aid:
            return entry
    return None


def format_registry(registry):
    """Format registry for human-readable display."""
    lines = []
    for category, entries in registry.items():
        if not entries:
            continue
        lines.append("--- %s ---" % category.upper())
        for e in entries:
            aid_hex = hexlify(e["aid"]).decode()
            lc = e.get("lifecycle")
            lc_str = "LC=%02X" % lc if lc is not None else "LC=?"
            ver = e.get("version", "")
            priv = hexlify(e.get("privileges", b"")).decode() if e.get("privileges") else ""
            line = "  %s %s" % (aid_hex, lc_str)
            if ver:
                line += " v%s" % ver
            if priv:
                line += " priv=%s" % priv
            lines.append(line)
    if not lines:
        lines.append("(empty)")
    return "\n".join(lines)
