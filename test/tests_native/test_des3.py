"""DES/3DES unit tests using NIST known-answer test vectors.

Tests run on desktop CPython against src/keystore/javacard/gp/des3.py
which is pure Python and MicroPython-compatible.
"""
import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs
setup_native_stubs()

from unittest import TestCase
from binascii import unhexlify

from keystore.javacard.gp.des3 import (
    _des_encrypt_block,
    _des_decrypt_block,
    des3_ecb_encrypt,
    des3_ecb_decrypt,
    des3_cbc_encrypt_raw,
    des3_cbc_decrypt_raw,
    des_cbc_encrypt_raw,
    des_cbc_mac_full,
)
from keystore.javacard.gp.scp02 import _mac_des_3des


class TestDESSingleBlock(TestCase):
    """NIST FIPS 46-3 Appendix B test vectors."""

    def test_encrypt_vector_1(self):
        key = unhexlify("0133457799BBCDFF")
        pt  = unhexlify("0123456789ABCDEF")
        ct  = unhexlify("1ED2CD64849078B9")
        self.assertEqual(_des_encrypt_block(key, pt), ct)

    def test_encrypt_vector_2(self):
        key = unhexlify("0000000000000000")
        pt  = unhexlify("0000000000000000")
        ct  = unhexlify("8CA64DE9C1B123A7")
        self.assertEqual(_des_encrypt_block(key, pt), ct)

    def test_encrypt_vector_3(self):
        key = unhexlify("FFFFFFFFFFFFFFFF")
        pt  = unhexlify("FFFFFFFFFFFFFFFF")
        ct  = unhexlify("7359B2163E4EDC58")
        self.assertEqual(_des_encrypt_block(key, pt), ct)

    def test_encrypt_vector_4(self):
        key = unhexlify("0123456789ABCDEF")
        pt  = unhexlify("FEDCBA9876543210")
        ct  = unhexlify("12C626AF058B433B")
        self.assertEqual(_des_encrypt_block(key, pt), ct)

    def test_decrypt_vector_1(self):
        key = unhexlify("0133457799BBCDFF")
        ct  = unhexlify("1ED2CD64849078B9")
        pt  = unhexlify("0123456789ABCDEF")
        self.assertEqual(_des_decrypt_block(key, ct), pt)

    def test_decrypt_vector_2(self):
        key = unhexlify("0000000000000000")
        ct  = unhexlify("8CA64DE9C1B123A7")
        pt  = unhexlify("0000000000000000")
        self.assertEqual(_des_decrypt_block(key, ct), pt)

    def test_encrypt_decrypt_roundtrip(self):
        key = unhexlify("FEDCBA9876543210")
        pt  = unhexlify("0123456789ABCDEF")
        ct  = _des_encrypt_block(key, pt)
        self.assertEqual(_des_decrypt_block(key, ct), pt)


class Test3DESECB(TestCase):
    """3DES-EDE2 (2-key) ECB test vectors."""

    def test_encrypt_nist_vector(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        pt  = unhexlify("4E6F772069732074")
        ct  = unhexlify("D80A0D8B2BAE5E4E")
        self.assertEqual(des3_ecb_encrypt(key, pt), ct)

    def test_decrypt_nist_vector(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        ct  = unhexlify("D80A0D8B2BAE5E4E")
        pt  = unhexlify("4E6F772069732074")
        self.assertEqual(des3_ecb_decrypt(key, ct), pt)

    def test_roundtrip(self):
        key = unhexlify("4041424344454647" "48494A4B4C4D4E4F")
        pt  = unhexlify("0123456789ABCDEF")
        ct  = des3_ecb_encrypt(key, pt)
        self.assertEqual(des3_ecb_decrypt(key, ct), pt)

    def test_all_zeros(self):
        key = unhexlify("0000000000000000" "0000000000000000")
        pt  = unhexlify("0000000000000000")
        ct  = des3_ecb_encrypt(key, pt)
        self.assertEqual(des3_ecb_decrypt(key, ct), pt)


class Test3DESCBC(TestCase):
    """3DES-CBC encrypt/decrypt tests."""

    def test_single_block_cbc(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        iv  = unhexlify("1234567890ABCDEF")
        pt  = unhexlify("4E6F772069732074")
        ct  = des3_cbc_encrypt_raw(key, iv, pt)
        self.assertEqual(len(ct), 8)
        self.assertEqual(des3_cbc_decrypt_raw(key, iv, ct), pt)

    def test_multi_block_cbc(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        iv  = unhexlify("FEDCBA9876543210")
        pt  = unhexlify("4E6F772069732074" "68652074696D6520")
        ct  = des3_cbc_encrypt_raw(key, iv, pt)
        self.assertEqual(len(ct), 16)
        self.assertEqual(des3_cbc_decrypt_raw(key, iv, ct), pt)

    def test_cbc_roundtrip_32_bytes(self):
        key = unhexlify("4041424344454647" "48494A4B4C4D4E4F")
        iv  = b'\x00' * 8
        pt  = b'\x01\x02\x03\x04\x05\x06\x07\x08' * 4
        ct  = des3_cbc_encrypt_raw(key, iv, pt)
        self.assertEqual(des3_cbc_decrypt_raw(key, iv, ct), pt)


class TestDESCBCMAC(TestCase):
    """DES-CBC-MAC (ISO 9797-1 algorithm 3) tests."""

    def test_mac_single_block(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        data = unhexlify("4E6F772069732074")
        mac = _mac_des_3des(key, data, b'\x00' * 8)
        self.assertEqual(len(mac), 8)

    def test_mac_multi_block(self):
        key = unhexlify("4041424344454647" "48494A4B4C4D4E4F")
        data = b'\x01\x02\x03\x04\x05\x06\x07\x08' * 4
        mac = _mac_des_3des(key, data, b'\x00' * 8)
        self.assertEqual(len(mac), 8)

    def test_mac_full_3des(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        data = unhexlify("4E6F772069732074")
        mac = des_cbc_mac_full(key, b'\x00' * 8, data)
        self.assertEqual(len(mac), 8)

    def test_icv_chaining(self):
        key = unhexlify("0123456789ABCDEF" "FEDCBA9876543210")
        data = unhexlify("0123456789ABCDEF")
        mac1 = _mac_des_3des(key, data, b'\x00' * 8)
        mac2 = _mac_des_3des(key, data, mac1)
        self.assertNotEqual(mac1, mac2)
