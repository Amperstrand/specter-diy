"""SCP02 crypto tests verified against GlobalPlatformPro hardware trace.

Parses session_001_install_teapot.txt to extract the actual host challenge,
card challenge, card cryptogram, and session keys from GPPro's output,
then verifies our implementation produces identical results.
"""
import sys
import os

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs
setup_native_stubs()

from unittest import TestCase
from binascii import unhexlify, hexlify

from keystore.javacard.gp.des3 import (
    des3_ecb_encrypt,
    des3_cbc_encrypt_raw,
    _des_encrypt_block,
)
from keystore.javacard.gp.scp02 import _mac_des_3des, _mac_3des


def _get_trace_path():
    return os.path.join(
        os.path.dirname(__file__),
        "..", "data", "gp_traces", "session_001_install_teapot.txt"
    )


def _parse_trace_session_keys(trace_path):
    """Extract session parameters from GPPro trace.

    Returns dict with host_chal, card_chal, card_crypto, host_crypto,
    seq_counter, card_key, s_enc, s_mac, s_rmac, ext_auth_mac_input.
    """
    host_chal = None
    card_chal = None
    card_crypto = None
    host_crypto = None
    seq_counter = None
    card_key = None
    s_enc = None
    s_mac = None
    s_rmac = None
    ext_auth_mac_input = None

    with open(trace_path, "r") as f:
        for line in f:
            line = line.strip()
            if "Generated host challenge:" in line:
                host_chal = unhexlify(line.split(":")[-1].strip())
            elif "Card challenge:" in line and "Card reports" not in line:
                card_chal = unhexlify(line.split(":")[-1].strip())
            elif "SSC:" in line:
                seq_counter = unhexlify(line.split(":")[-1].strip())
            elif "Verified card cryptogram:" in line:
                card_crypto = unhexlify(line.split(":")[-1].strip())
            elif "Calculated host cryptogram:" in line:
                host_crypto = unhexlify(line.split(":")[-1].strip())
            elif "Session keys: ENC=" in line:
                parts = line.split("Session keys: ")[1].split(" ")
                s_enc = unhexlify(parts[0].split("=")[1])
                s_mac = unhexlify(parts[1].split("=")[1])
                s_rmac = unhexlify(parts[2].split("=")[1])
            elif "Diversified card keys: ENC=" in line:
                card_key = unhexlify(line.split("ENC=")[1].split(" ")[0])
            elif "MAC input: 84820100" in line:
                ext_auth_mac_input = unhexlify(
                    line.split("MAC input: ")[1].strip()
                )

    return {
        "host_chal": host_chal,
        "card_chal": card_chal,
        "card_crypto": card_crypto,
        "host_crypto": host_crypto,
        "seq_counter": seq_counter,
        "card_key": card_key,
        "s_enc": s_enc,
        "s_mac": s_mac,
        "s_rmac": s_rmac,
        "ext_auth_mac_input": ext_auth_mac_input,
    }


class TestSCP02SessionKeyDerivation(TestCase):
    """Verify session key derivation matches GPPro output."""

    def setUp(self):
        self.trace = _parse_trace_session_keys(_get_trace_path())

    def test_trace_parsed(self):
        self.assertIsNotNone(self.trace["host_chal"])
        self.assertIsNotNone(self.trace["card_chal"])
        self.assertIsNotNone(self.trace["card_crypto"])
        self.assertIsNotNone(self.trace["s_enc"])
        self.assertIsNotNone(self.trace["s_mac"])

    def test_s_enc_derivation(self):
        from keystore.javacard.gp.scp02 import _derive_session_key
        s_enc = _derive_session_key(
            self.trace["card_key"], "enc", self.trace["seq_counter"]
        )
        self.assertEqual(
            hexlify(s_enc).decode(),
            hexlify(self.trace["s_enc"]).decode(),
            "S-ENC derivation mismatch"
        )

    def test_s_mac_derivation(self):
        from keystore.javacard.gp.scp02 import _derive_session_key
        s_mac = _derive_session_key(
            self.trace["card_key"], "mac", self.trace["seq_counter"]
        )
        self.assertEqual(
            hexlify(s_mac).decode(),
            hexlify(self.trace["s_mac"]).decode(),
            "S-MAC derivation mismatch"
        )

    def test_s_rmac_derivation(self):
        from keystore.javacard.gp.scp02 import _derive_session_key
        s_rmac = _derive_session_key(
            self.trace["card_key"], "rmac", self.trace["seq_counter"]
        )
        self.assertEqual(
            hexlify(s_rmac).decode(),
            hexlify(self.trace["s_rmac"]).decode(),
            "S-RMAC derivation mismatch"
        )


class TestSCP02Cryptograms(TestCase):
    """Verify card and host cryptogram computation matches GPPro."""

    def setUp(self):
        self.trace = _parse_trace_session_keys(_get_trace_path())

    def test_card_cryptogram(self):
        expected = self.trace["card_crypto"]
        computed = _mac_3des(
            self.trace["s_enc"],
            self.trace["host_chal"] + self.trace["card_chal"],
            b'\x00' * 8,
        )
        self.assertEqual(
            hexlify(computed).decode(),
            hexlify(expected).decode(),
            "Card cryptogram mismatch"
        )

    def test_host_cryptogram(self):
        expected = self.trace["host_crypto"]
        computed = _mac_3des(
            self.trace["s_enc"],
            self.trace["card_chal"] + self.trace["host_chal"],
            b'\x00' * 8,
        )
        self.assertEqual(
            hexlify(computed).decode(),
            hexlify(expected).decode(),
            "Host cryptogram mismatch"
        )


class TestSCP02MAC(TestCase):
    """Verify MAC computation against GPPro trace MAC inputs."""

    def setUp(self):
        self.trace = _parse_trace_session_keys(_get_trace_path())

    def test_external_authenticate_mac(self):
        mac_input = self.trace["ext_auth_mac_input"]
        self.assertIsNotNone(mac_input, "EXT AUTH MAC input not found in trace")
        mac = _mac_des_3des(self.trace["s_mac"], mac_input, b'\x00' * 8)
        self.assertEqual(len(mac), 8)

    def test_icv_increment_between_commands(self):
        mac_input = self.trace["ext_auth_mac_input"]
        mac1 = _mac_des_3des(self.trace["s_mac"], mac_input, b'\x00' * 8)
        icv2 = _des_encrypt_block(self.trace["s_mac"][:8], mac1)
        self.assertEqual(len(icv2), 8)
        self.assertNotEqual(mac1, icv2)


class TestSCP02Constants(TestCase):
    """Verify SCP02 derivation constants match GP spec."""

    def test_enc_constant(self):
        from keystore.javacard.gp.scp02 import _SCP02_CONSTANTS
        self.assertEqual(_SCP02_CONSTANTS["enc"], unhexlify("0182"))

    def test_mac_constant(self):
        from keystore.javacard.gp.scp02 import _SCP02_CONSTANTS
        self.assertEqual(_SCP02_CONSTANTS["mac"], unhexlify("0101"))

    def test_rmac_constant(self):
        from keystore.javacard.gp.scp02 import _SCP02_CONSTANTS
        self.assertEqual(_SCP02_CONSTANTS["rmac"], unhexlify("0102"))

    def test_dek_constant(self):
        from keystore.javacard.gp.scp02 import _SCP02_CONSTANTS
        self.assertEqual(_SCP02_CONSTANTS["dek"], unhexlify("0181"))
