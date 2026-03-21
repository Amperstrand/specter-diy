"""GP Registry: query card for installed packages and applets.

Implements GET STATUS command to enumerate the card's content registry.
Reference: GlobalPlatform Card Specification v2.3, Section 11.4

Supports two response formats:
- Standard E3-tagged TLV (GP spec, used by GPPro with P2=0x02)
- JCOP4 compact format (returned with P2=0x00)
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


def _parse_e3_entry(data):
    """Parse a single E3 entry from standard GP response."""
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


def _parse_e3_entries(data):
    """Parse standard E3-tagged GET STATUS response."""
    entries = []
    offset = 0
    while offset < len(data):
        tag, value, next_offset = _parse_tlv(data, offset)
        if tag is None:
            break
        if tag == 0xE3:
            entry = _parse_e3_entry(value)
            if entry is not None:
                entries.append(entry)
        offset = next_offset
    return entries


def _parse_compact_entries(data):
    """Parse JCOP4 compact GET STATUS response (P2=0x00).

    Format: [aid_len(1)][aid_bytes] then for each sub-item:
      [lifecycle(1)][flag(1)][sub_len(1)][sub_aid_bytes]
    Terminated by trailing lifecycle byte or end of data.
    """
    entries = []
    i = 0
    while i < len(data):
        aid_len = data[i]
        i += 1
        if aid_len == 0 or i + aid_len > len(data):
            break
        aid = data[i:i + aid_len]
        i += aid_len

        entry = {
            "aid": aid,
            "lifecycle": None,
            "privileges": None,
            "version": None,
            "module_aids": [],
            "associated_sd": b"",
        }

        while i < len(data):
            if i + 1 >= len(data):
                break
            lc = data[i]
            if lc not in (0x01, 0x07):
                break
            nxt = data[i + 1]
            if nxt == 0x00 and i + 2 < len(data):
                sub_len = data[i + 2]
                if sub_len == 0 or i + 3 + sub_len > len(data):
                    entry["lifecycle"] = lc
                    i += 2
                    break
                sub_aid = data[i + 3:i + 3 + sub_len]
                i += 3 + sub_len
                entry["lifecycle"] = lc
                if sub_len > 1:
                    entry["module_aids"].append(sub_aid)
            else:
                entry["lifecycle"] = lc
                entry["privileges"] = bytes([nxt])
                i += 2
                break

        entries.append(entry)

    return entries


def _parse_entries(data):
    """Parse GET STATUS response (auto-detects E3 or compact format)."""
    if len(data) == 0:
        return []
    if data[0] == 0xE3:
        return _parse_e3_entries(data)
    return _parse_compact_entries(data)


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
        result["apps"] = get_status(session, 0x40)
    except Exception:
        pass
    try:
        result["load_files"] = get_status(session, 0x20)
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
    all_entries = get_status(session, 0x40) + get_status(session, 0x10) + get_status(session, 0x20)
    for entry in all_entries:
        if entry["aid"] == aid:
            return entry
        for mod in entry.get("module_aids", []):
            if mod == aid:
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
            mods = e.get("module_aids", [])
            line = "  %s %s" % (aid_hex, lc_str)
            if ver:
                line += " v%s" % ver
            if priv:
                line += " priv=%s" % priv
            if mods:
                mod_strs = [hexlify(m).decode() for m in mods]
                line += "\n    mods: %s" % ", ".join(mod_strs)
            lines.append(line)
    if not lines:
        lines.append("(empty)")
    return "\n".join(lines)
