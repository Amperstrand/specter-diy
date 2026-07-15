"""Tests for frozen MemoryCard DGP data integrity."""
import sys
import hashlib

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs
    setup_native_stubs()

from unittest import TestCase
from binascii import unhexlify

from keystore.javacard.gp.loader import extract_package_aid, extract_applet_aid
from keystore.javacard.memorycard_dgp import DGP_DATA

EXPECTED_SHA256 = "ab52bb9cde9225b58cfeab32dbd31e5da5b60accd8d012a5434e07e80f6f4c44"
EXPECTED_SIZE = 10115
EXPECTED_PACKAGE_AID = unhexlify("B00B5111CB")
EXPECTED_APPLET_AID = unhexlify("B00B5111CB01")


class TestMemoryCardDGP(TestCase):

    def test_size(self):
        self.assertEqual(len(DGP_DATA), EXPECTED_SIZE)

    def test_sha256(self):
        sha = hashlib.sha256(DGP_DATA).hexdigest()
        if sys.implementation.name == 'micropython':
            from ubinascii import hexlify
            sha = hexlify(hashlib.sha256(DGP_DATA).digest()).decode()
        self.assertEqual(sha, EXPECTED_SHA256)

    def test_header_tag(self):
        self.assertEqual(DGP_DATA[0], 0x01, "First byte must be Header tag 0x01")

    def test_deca_magic(self):
        self.assertEqual(DGP_DATA[3:5], b'\xDE\xCA', "Header must contain DECA magic")

    def test_package_aid(self):
        aid = extract_package_aid(DGP_DATA)
        self.assertEqual(aid, EXPECTED_PACKAGE_AID)

    def test_applet_aid(self):
        aid = extract_applet_aid(DGP_DATA)
        self.assertEqual(aid, EXPECTED_APPLET_AID)

    def test_first_component_is_header(self):
        self.assertEqual(DGP_DATA[0], 0x01)
        self.assertEqual(DGP_DATA[3:5], b'\xDE\xCA')

    def test_components_sorted_by_tag(self):
        offsets = []
        i = 0
        while i < len(DGP_DATA):
            tag = DGP_DATA[i]
            if tag not in range(0x01, 0x0A):
                break
            length = (DGP_DATA[i + 1] << 8) | DGP_DATA[i + 2]
            i += 3
            offsets.append(tag)
            i += length
        self.assertEqual(offsets, [1, 2, 3, 4, 5, 6, 7, 8, 9])
