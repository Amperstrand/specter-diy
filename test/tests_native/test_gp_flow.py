"""GP flow integration tests using mock smartcard connection.

Tests APDU formatting (INSTALL, LOAD, DELETE, GET STATUS) against
expected data from the GPPro hardware trace, without needing real hardware.
"""
import sys
import os

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs
setup_native_stubs()

from unittest import TestCase
from binascii import unhexlify, hexlify

from keystore.javacard.gp.loader import (
    _build_install_for_load_data,
    _build_install_for_install_data,
    _encode_length,
    _encode_tlv,
    extract_package_aid,
    LOAD_BLOCK_SIZE,
)
from keystore.javacard.gp.deleter import delete_aid
from keystore.javacard.gp.registry import (
    _parse_compact_entries,
    _parse_e3_entries,
    _parse_entries,
    find_aid,
)


class MockConnection:
    """Mock smartcard connection that records APDUs and returns canned responses."""

    def __init__(self, responses=None):
        self.apdu_log = []
        self.responses = responses or []
        self._idx = 0

    def transmit(self, apdu):
        self.apdu_log.append(apdu)
        if self._idx < len(self.responses):
            resp = self.responses[self._idx]
            self._idx += 1
            return resp
        return [b"", 0x90, 0x00]

    def connect(self, protocol):
        pass

    def disconnect(self):
        pass

    @property
    def T1_protocol(self):
        return 1

    def getATR(self):
        return unhexlify("3BD518FF8191FE1FC38073C821100A")


class MockSession:
    """Mock SCP02 session that records wrapped commands."""

    def __init__(self, conn):
        self.conn = conn
        self.mac = True
        self.enc = False
        self.commands = []
        self._icv = b'\x00' * 8

    def send_command(self, cla, ins, p1, p2, data=b""):
        self.commands.append((cla, ins, p1, p2, data))
        return b"", 0x90, 0x00

    def send_command_plain(self, cla, ins, p1, p2, data=b""):
        self.commands.append((cla, ins, p1, p2, data))
        return b"", 0x90, 0x00


class TestInstallForLoad(TestCase):
    """Verify INSTALL FOR LOAD data field matches GPPro trace."""

    def test_data_format(self):
        pkg_aid = unhexlify("B00B5111CA")
        sd_aid = unhexlify("A000000151000000")
        data = _build_install_for_load_data(pkg_aid, sd_aid)
        expected = unhexlify("05B00B5111CA08A000000151000000000000")
        self.assertEqual(data, expected)

    def test_data_length(self):
        pkg_aid = unhexlify("B00B5111CA")
        sd_aid = unhexlify("A000000151000000")
        data = _build_install_for_load_data(pkg_aid, sd_aid)
        self.assertEqual(len(data), 18)

    def test_trace_match(self):
        pkg_aid = unhexlify("B00B5111CA")
        sd_aid = unhexlify("A000000151000000")
        data = _build_install_for_load_data(pkg_aid, sd_aid)
        trace_data = unhexlify("05B00B5111CA08A000000151000000000000")
        self.assertEqual(hexlify(data).decode(), hexlify(trace_data).decode())


class TestInstallForInstall(TestCase):
    """Verify INSTALL FOR INSTALL data field matches GPPro trace."""

    def test_data_format(self):
        pkg_aid = unhexlify("B00B5111CA")
        applet_aid = unhexlify("B00B5111CA01")
        instance_aid = unhexlify("B00B5111CA01")
        data = _build_install_for_install_data(pkg_aid, applet_aid, instance_aid)
        expected = unhexlify("05B00B5111CA06B00B5111CA0106B00B5111CA01010002C90000")
        self.assertEqual(data, expected)

    def test_custom_privileges(self):
        pkg_aid = unhexlify("B00B5111CA")
        applet_aid = unhexlify("B00B5111CA01")
        instance_aid = unhexlify("B00B5111CA01")
        data = _build_install_for_install_data(
            pkg_aid, applet_aid, instance_aid,
            privileges=unhexlify("C900"), install_params=b"\xC9\x00"
        )
        expected = unhexlify(
            "05B00B5111CA06B00B5111CA0106B00B5111CA0102C90002C90000"
        )
        self.assertEqual(data, expected)

    def test_trace_match(self):
        pkg_aid = unhexlify("B00B5111CA")
        applet_aid = unhexlify("B00B5111CA01")
        instance_aid = unhexlify("B00B5111CA01")
        data = _build_install_for_install_data(pkg_aid, applet_aid, instance_aid)
        trace_mac_input_data = unhexlify(
            "05B00B5111CA06B00B5111CA0106B00B5111CA01010002C90000"
        )
        self.assertEqual(hexlify(data).decode(),
                        hexlify(trace_mac_input_data).decode())


class TestLoadCap(TestCase):
    """Verify LOAD block structure and C4 header encoding."""

    def test_encode_length_short(self):
        self.assertEqual(_encode_length(0x7F), bytes([0x7F]))

    def test_encode_length_1byte(self):
        self.assertEqual(_encode_length(0x80), bytes([0x81, 0x80]))

    def test_encode_length_2byte(self):
        self.assertEqual(_encode_length(0x033F), bytes([0x82, 0x03, 0x3F]))

    def test_c4_header_for_831_bytes(self):
        cap_len = 831
        c4_header = bytes([0xC4]) + _encode_length(cap_len)
        self.assertEqual(c4_header, unhexlify("C482033F"))
        self.assertEqual(len(c4_header), 4)

    def test_load_block_size(self):
        self.assertEqual(LOAD_BLOCK_SIZE, 247)

    def test_first_block_data_size(self):
        cap_len = 831
        c4_header = bytes([0xC4]) + _encode_length(cap_len)
        header_size = len(c4_header)
        first_block_data_size = LOAD_BLOCK_SIZE - header_size
        self.assertEqual(first_block_data_size, 243)

    def test_block_counts_for_831_bytes(self):
        cap_len = 831
        c4_header = bytes([0xC4]) + _encode_length(cap_len)
        header_size = len(c4_header)
        first_block_data_size = LOAD_BLOCK_SIZE - header_size
        remaining_after_first = cap_len - first_block_data_size
        full_blocks = remaining_after_first // LOAD_BLOCK_SIZE
        last_block = remaining_after_first % LOAD_BLOCK_SIZE
        total_blocks = 1 + full_blocks + (1 if last_block > 0 else 0)
        self.assertEqual(total_blocks, 4)
        self.assertEqual(first_block_data_size, 243)
        self.assertEqual(LOAD_BLOCK_SIZE, 247)
        self.assertEqual(last_block, 94)


class TestDeleteAID(TestCase):
    """Verify DELETE command format."""

    def test_delete_format(self):
        session = MockSession(None)
        aid = unhexlify("B00B5111CA01")
        delete_aid(session, aid)
        cla, ins, p1, p2, data = session.commands[0]
        self.assertEqual(cla, 0x80)
        self.assertEqual(ins, 0xE4)
        self.assertEqual(p1, 0x00)
        self.assertEqual(p2, 0x80)
        expected_data = unhexlify("4F06B00B5111CA01")
        self.assertEqual(data, expected_data)


class TestRegistryParsing(TestCase):
    """Verify registry parsing for both E3 and compact formats."""

    def test_parse_e3_entries(self):
        data = unhexlify(
            "E3114F095361746F4368697000C503000000"
        )
        entries = _parse_e3_entries(data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["aid"], unhexlify("5361746F4368697000"))
        self.assertEqual(entries[0]["privileges"], unhexlify("000000"))

    def test_parse_compact_isd(self):
        data = unhexlify("08A000000151000000079E")
        entries = _parse_compact_entries(data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["aid"], unhexlify("A000000151000000"))
        self.assertEqual(entries[0]["lifecycle"], 0x07)
        self.assertEqual(entries[0]["privileges"], unhexlify("9E"))

    def test_auto_detect_e3(self):
        data = unhexlify("E3074F05B00B5111CB9F700101CE020000")
        entries = _parse_entries(data)
        self.assertEqual(len(entries), 1)

    def test_auto_detect_compact(self):
        data = unhexlify("095361746F43686970000700")
        entries = _parse_entries(data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["aid"], unhexlify("5361746F4368697000"))

    def test_parse_compact_with_modules(self):
        data = unhexlify("095361746F4368697000070006B00B5111CA01")
        entries = _parse_compact_entries(data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(entries[0]["module_aids"]), 1)
        self.assertEqual(entries[0]["module_aids"][0], unhexlify("B00B5111CA01"))


class TestExtractPackageAID(TestCase):
    """Verify DGP package AID extraction from Header component."""

    def test_teapot_dgp(self):
        data = unhexlify(
            "01000FDECAFFED010204000005B00B5111CA"
        )
        aid = extract_package_aid(data)
        self.assertEqual(aid, unhexlify("B00B5111CA"))

    def test_teapot_dgp_with_remaining_data(self):
        data = unhexlify(
            "01000FDECAFFED010204000005B00B5111CA"
            "02001F000F001F000A00150072002401FC"
        )
        aid = extract_package_aid(data)
        self.assertEqual(aid, unhexlify("B00B5111CA"))

    def test_non_exportable_package(self):
        data = unhexlify("01000ADECAFFED0204AABBCCDD0000")
        aid = extract_package_aid(data)
        self.assertEqual(aid, unhexlify("AABBCCDD"))

    def test_invalid_tag(self):
        data = unhexlify("02000FDECAFFED010204000005B00B5111CA")
        with self.assertRaises(Exception):
            extract_package_aid(data)

    def test_invalid_magic(self):
        data = unhexlify("01000FDEADDEED010204000005B00B5111CA")
        with self.assertRaises(Exception):
            extract_package_aid(data)

    def test_too_short(self):
        data = unhexlify("0100FF")
        with self.assertRaises(Exception):
            extract_package_aid(data)
