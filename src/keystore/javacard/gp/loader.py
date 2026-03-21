"""GP Loader: install CAP files onto the card.

Implements INSTALL [for load], chunked LOAD, and INSTALL [for install and make selectable].
Reference: GlobalPlatform Card Specification v2.3, Sections 11.5-11.7
APDU format verified against GlobalPlatformPro SCP02 trace on JCOP4.
"""


class GPLoadError(Exception):
    pass


LOAD_BLOCK_SIZE = 247


def _encode_length(length):
    """Encode a length value in BER-TLV format."""
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
    """Build data field for INSTALL [for load].

    Format (matches GPPro/GP spec):
      package_aid_len | package_aid | sd_aid_len | sd_aid | 0x00 | 0x00 | 0x00
    """
    data = bytes([len(package_aid)]) + package_aid
    data += bytes([len(sd_aid)]) + sd_aid
    data += bytes([0x00, 0x00, 0x00])
    return data


def _build_install_for_install_data(package_aid, applet_aid, instance_aid,
                                     privileges=b"\x00", install_params=b"\xC9\x00"):
    """Build data field for INSTALL [for install and make selectable].

    Format (matches GPPro/GP spec):
      package_aid_len | package_aid
      | applet_aid_len | applet_aid
      | instance_aid_len | instance_aid
      | privileges_len | privileges
      | install_params_len | install_params
      | 0x00
    """
    data = bytes([len(package_aid)]) + package_aid
    data += bytes([len(applet_aid)]) + applet_aid
    data += bytes([len(instance_aid)]) + instance_aid
    data += bytes([len(privileges)]) + privileges
    data += bytes([len(install_params)]) + install_params
    data += bytes([0x00])
    return data


def install_for_load(session, package_aid, sd_aid):
    """Send INSTALL [for load] command."""
    data = _build_install_for_load_data(package_aid, sd_aid)
    resp_data, sw1, sw2 = session.send_command(0x80, 0xE6, 0x02, 0x00, data)
    if sw1 != 0x90 or sw2 != 0x00:
        raise GPLoadError("INSTALL for load failed: SW=%02X%02X" % (sw1, sw2))
    return resp_data


def load_cap(session, cap_data, block_size=LOAD_BLOCK_SIZE):
    """Send CAP file data via chunked LOAD commands.

    First block includes C4 header with total CAP length,
    followed by as much CAP data as fits within block_size.
    Subsequent blocks are raw continuation data.
    Last block has P1=0x80.
    """
    cap_len = len(cap_data)
    c4_header = bytes([0xC4]) + _encode_length(cap_len)
    header_size = len(c4_header)
    first_block_data_size = block_size - header_size

    offset = 0
    seq = 0

    while offset < cap_len:
        remaining = cap_len - offset
        if seq == 0:
            chunk_size = min(first_block_data_size, remaining)
            payload = c4_header + cap_data[offset:offset + chunk_size]
        else:
            chunk_size = min(block_size, remaining)
            payload = cap_data[offset:offset + chunk_size]
        offset += chunk_size

        is_last = (offset >= cap_len)
        p1 = 0x80 if is_last else 0x00

        resp_data, sw1, sw2 = session.send_command(0x80, 0xE8, p1, seq, payload)
        if sw1 != 0x90 or sw2 != 0x00:
            raise GPLoadError("LOAD block %d failed (offset %d/%d): SW=%02X%02X"
                              % (seq, offset, cap_len, sw1, sw2))

        seq = (seq + 1) & 0xFF
        if seq == 0:
            raise GPLoadError("LOAD: sequence counter overflow (>255 blocks)")


def install_for_install(session, package_aid, applet_aid, instance_aid,
                        privileges=b"\x00", install_params=b"\xC9\x00"):
    """Send INSTALL [for install and make selectable]."""
    data = _build_install_for_install_data(
        package_aid, applet_aid, instance_aid, privileges, install_params)
    resp_data, sw1, sw2 = session.send_command(0x80, 0xE6, 0x0C, 0x00, data)
    if sw1 != 0x90 or sw2 != 0x00:
        raise GPLoadError("INSTALL for install failed: SW=%02X%02X" % (sw1, sw2))
    return resp_data


def install_applet(session, cap_data, package_aid, applet_aid, instance_aid,
                   sd_aid, privileges=b"\x00", install_params=b"\xC9\x00"):
    """Full applet installation flow.

    1. INSTALL [for load]
    2. Chunked LOAD of CAP data
    3. INSTALL [for install and make selectable]
    """
    install_for_load(session, package_aid, sd_aid)
    load_cap(session, cap_data)
    install_for_install(session, package_aid, applet_aid, instance_aid,
                        privileges, install_params)


def extract_package_aid(dgp_data):
    """Extract package AID from a DGP file.

    DGP format: sequence of CAP components, each prefixed with
    1-byte tag + 2-byte big-endian length. The first component is
    always the Header (tag 0x01) containing:
      magic (2B) | minor_ver (1B) | major_ver (1B) | flags (1B)
      [if flags & 0x01: exportable_package_size (4B)]
      aid_len (1B) | aid (aid_len B)

    Returns: package AID as bytes.
    Raises: GPLoadError if format is invalid.
    """
    if len(dgp_data) < 10:
        raise GPLoadError("DGP data too short")
    if dgp_data[0] != 0x01:
        raise GPLoadError("DGP first component is not Header (tag 0x01)")
    if dgp_data[3:5] != b'\xDE\xCA':
        raise GPLoadError("DGP Header magic mismatch (expected DECA)")

    flags = dgp_data[7]
    if flags & 0x01:
        aid_len_offset = 12
    else:
        aid_len_offset = 8

    aid_len = dgp_data[aid_len_offset]
    if aid_len == 0 or aid_len_offset + 1 + aid_len > len(dgp_data):
        raise GPLoadError("DGP Header package AID is invalid")
    return dgp_data[aid_len_offset + 1:aid_len_offset + 1 + aid_len]


def install_from_dgp(session, dgp_data, sd_aid,
                      privileges=b"\x00", install_params=b"\xC9\x00"):
    """Install applet from DGP data with auto-derived AIDs.

    Parses the package AID from the DGP Header, derives applet and
    instance AIDs by appending 0x01, then runs the full install flow:
    INSTALL [for load] -> LOAD -> INSTALL [for install and make selectable].

    Returns: package_aid (bytes).
    """
    from binascii import hexlify
    pkg_aid = extract_package_aid(dgp_data)
    applet_aid = pkg_aid + b"\x01"
    instance_aid = applet_aid
    install_applet(session, dgp_data, pkg_aid, applet_aid, instance_aid,
                   sd_aid, privileges, install_params)
    return pkg_aid


def verify_install(session, instance_aid):
    """Verify that an applet instance is installed."""
    from .registry import find_aid
    entry = find_aid(session, instance_aid)
    return entry is not None
