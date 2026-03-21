"""GP Delete: remove applet instances and packages from the card.

Reference: GlobalPlatform Card Specification v2.3, Section 11.6
"""

from binascii import hexlify


class GPDeleteError(Exception):
    pass


def delete_aid(session, aid, delete_related=True):
    """Delete an AID from the card.

    If delete_related is True, uses P2=0x80 to also delete
    related objects (e.g., package when deleting an applet instance).

    Returns (sw1, sw2) of the DELETE response.
    """
    p2 = 0x80 if delete_related else 0x00
    data = bytes([0x4F, len(aid)]) + aid
    resp_data, sw1, sw2 = session.send_command(0x80, 0xE4, 0x00, p2, data)

    if sw1 != 0x90 and sw1 != 0x91:
        raise GPDeleteError("DELETE failed for %s: SW=%02X%02X"
                            % (hexlify(aid).decode(), sw1, sw2))

    if sw1 == 0x91:
        remaining = sw2
        if remaining > 0:
            resp_data, sw1, sw2 = session.send_command(
                0x80, 0xC0, 0x00, 0x00, bytes([remaining]))
            if sw1 != 0x90 and sw2 != 0x00:
                raise GPDeleteError("GET RESPONSE after DELETE failed: SW=%02X%02X"
                                    % (sw1, sw2))

    return sw1, sw2


def delete_applet(session, applet_aid):
    """Delete an applet instance by its AID.

    This deletes the applet instance but may leave the package.
    """
    return delete_aid(session, applet_aid, delete_related=True)


def delete_package(session, package_aid):
    """Delete an executable load file (package) by its AID.

    Deletes the package and all contained applets.
    """
    return delete_aid(session, package_aid, delete_related=True)
