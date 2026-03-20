"""GP Loader: install CAP files onto the card.

Implements INSTALL [for load], chunked LOAD, and INSTALL [for install and make selectable].
Reference: GlobalPlatform Card Specification v2.3, Sections 11.5-11.7
"""

from .deleter import GPDeleteError


class GPLoadError(Exception):
    pass


LOAD_BLOCK_SIZE = 231


def _encode_length(length):
    """Encode a length value in GP TLV format."""
    if length < 0x80:
        return bytes([length])
    elif length < 0x100:
        return bytes([0x81, length])
    elif length < 0x10000:
        return bytes([0x82, (length >> 8) & 0xFF, length & 0xFF])
    else:
        return bytes([0x83, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF])


def _encode_tlv(tag, value):
    return bytes([tag]) + _encode_length(len(value)) + value


def _build_install_for_load_data(package_aid, sd_aid):
    """Build the data field for INSTALL [for load].

    Format per GP spec:
      0x00 | package_aid_len | package_aid | sd_aid_len | sd_aid | 0x00
    """
    data = bytes([0x00])
    data += bytes([len(package_aid)]) + package_aid
    data += bytes([len(sd_aid)]) + sd_aid
    data += bytes([0x00])
    return data


def _build_install_for_install_data(package_aid, applet_aid, instance_aid, privileges):
    """Build the data field for INSTALL [for install and make selectable].

    Format per GP spec:
      0x04 0x00 Lc
      | exec_load_file_aid_len | exec_load_file_aid
      | exec_module_aid_len | exec_module_aid
      | application_aid_len | application_aid
      | 0x01 | privileges
      | install_params_field_len | install_params
    """
    data = bytes([0x04, 0x00])
    payload = b""
    payload += bytes([len(package_aid)]) + package_aid
    payload += bytes([len(applet_aid)]) + applet_aid
    payload += bytes([len(instance_aid)]) + instance_aid
    payload += bytes([0x01]) + privileges
    payload += bytes([0x00])
    data += _encode_length(len(payload))
    data += payload
    return data


def install_for_load(session, package_aid, sd_aid):
    """Send INSTALL [for load] command.

    Prepares the card to receive a CAP file load.
    """
    data = _build_install_for_load_data(package_aid, sd_aid)
    resp_data, sw1, sw2 = session.send_command(0x80, 0xE6, 0x00, 0x00, data)

    if sw1 != 0x90 or sw2 != 0x00:
        raise GPLoadError("INSTALL for load failed: SW=%02X%02X" % (sw1, sw2))

    return resp_data


def load_cap(session, cap_data, block_size=LOAD_BLOCK_SIZE):
    """Send CAP file data via chunked LOAD commands.

    First block includes the C4 header with file size.
    Subsequent blocks are raw continuation data.
    Last block has P1=0x80.
    """
    cap_len = len(cap_data)

    offset = 0
    seq = 0
    is_first = True

    while offset < cap_len:
        remaining = cap_len - offset
        chunk_size = min(block_size, remaining)
        chunk = cap_data[offset:offset + chunk_size]
        offset += chunk_size

        if is_first:
            header = _encode_tlv(0xC4, _encode_length(cap_len) + cap_data)
            payload = header
            is_first = False
        else:
            payload = chunk

        is_last = (offset >= cap_len)
        p1 = 0x80 if is_last else 0x00

        resp_data, sw1, sw2 = session.send_command(0x80, 0xE8, p1, seq, payload)

        if sw1 != 0x90 or sw2 != 0x00:
            raise GPLoadError("LOAD block %d failed (offset %d/%d): SW=%02X%02X"
                              % (seq, offset, cap_len, sw1, sw2))

        seq = (seq + 1) & 0xFF
        if seq == 0:
            raise GPLoadError("LOAD: sequence counter overflow (>255 blocks)")


def install_for_install(session, package_aid, applet_aid, instance_aid, privileges):
    """Send INSTALL [for install and make selectable].

    Creates the applet instance and makes it selectable.
    """
    data = _build_install_for_install_data(
        package_aid, applet_aid, instance_aid, privileges)
    resp_data, sw1, sw2 = session.send_command(0x80, 0xE6, 0x0C, 0x00, data)

    if sw1 != 0x90 or sw2 != 0x00:
        raise GPLoadError("INSTALL for install failed: SW=%02X%02X" % (sw1, sw2))

    return resp_data


def install_memorycard(session, cap_data, package_aid, applet_aid, instance_aid,
                       sd_aid, privileges):
    """Full MemoryCard installation flow.

    1. INSTALL [for load]
    2. Chunked LOAD of CAP data
    3. INSTALL [for install and make selectable]
    """
    install_for_load(session, package_aid, sd_aid)
    load_cap(session, cap_data)
    install_for_install(session, package_aid, applet_aid, instance_aid, privileges)


def verify_install(session, instance_aid):
    """Verify that an applet instance is installed by querying the registry.

    Returns True if found, False otherwise.
    """
    from .registry import find_aid
    entry = find_aid(session, instance_aid)
    return entry is not None
