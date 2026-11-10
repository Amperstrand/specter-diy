"""Native tests for SeedKeeper review-debt fixes (issue #52, PR #21).

Covers two findings from the PR #21 audit:

1. storage_menu must respect load_mnemonic()'s return value instead of
   unconditionally reporting success (P2).
2. decrypt_response must fail closed on malformed card response envelopes
   (P1 residue — the card's response envelope carries NO MAC, see
   SecureChannelResponseTest docstring for the protocol evidence).
"""
import asyncio
import sys
import types
from unittest import TestCase

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

from keystore.seedkeeper import SeedKeeper
from keystore.javacard.applets.satochip_securechannel import (
    SatochipSecureChannel,
    SecureChannelError,
    pkcs7_pad,
)
from ucryptolib import aes


def make_keystore(load_result, menu_choice=0):
    ks = object.__new__(SeedKeeper)
    ks.connection = types.SimpleNamespace(isCardInserted=lambda: True)
    ks.applet = types.SimpleNamespace(
        sc=types.SimpleNamespace(card_pubkey=None)
    )
    ks.shown = []
    ks.load_calls = 0

    async def fake_show(screen, *args, **kwargs):
        ks.shown.append(type(screen).__name__)
        return menu_choice

    async def fake_load_mnemonic():
        ks.load_calls += 1
        return load_result

    ks.show = fake_show
    ks.load_mnemonic = fake_load_mnemonic
    return ks


class StorageMenuGuardTest(TestCase):
    def test_load_failure_returns_false_without_success_alert(self):
        ks = make_keystore(load_result=False)
        res = asyncio.run(ks.storage_menu())
        self.assertEqual(ks.load_calls, 1)
        self.assertIs(res, False)
        self.assertNotIn(
            "Alert", ks.shown,
            "failure path must not show the success alert",
        )

    def test_load_success_shows_alert_and_returns_true(self):
        ks = make_keystore(load_result=True)
        res = asyncio.run(ks.storage_menu())
        self.assertEqual(ks.load_calls, 1)
        self.assertIs(res, True)
        self.assertIn("Alert", ks.shown)


class SecureChannelResponseTest(TestCase):
    """Card response envelopes are [IV(16) | size(2) | ciphertext] — no MAC.

    Protocol evidence: Toporin/SatochipApplet SecureChannel.wrap() and
    Toporin/Seedkeeper-Applet SeedKeeper.process() both return exactly
    IV|size|ciphertext with no HMAC over the response (only client->card
    requests are MACed, in unwrap()); Toporin/pysatochip's
    decrypt_secure_channel() documents "The card response carries no MAC
    (the applet does not send one)". So the client cannot verify a MAC —
    but it MUST reject any envelope that does not match the wire format
    exactly: truncated data, trailing bytes, non-block-aligned sizes, and
    undecryptable/garbage padding fail closed.
    """

    KEY = bytes(range(16))
    IV = bytes(range(16, 32))

    def setUp(self):
        self.sc = SatochipSecureChannel()
        self.sc.aes_key = self.KEY
        self.sc.mac_key = bytes(range(20))
        self.sc.is_initialized = True

    def _envelope(self, plaintext=b"secret payload"):
        ciphertext = aes(self.KEY, 2, self.IV).encrypt(pkcs7_pad(plaintext))
        return self.IV + len(ciphertext).to_bytes(2, "big") + ciphertext

    def test_valid_envelope_roundtrip(self):
        self.assertEqual(self.sc.decrypt_response(self._envelope()), b"secret payload")

    def test_empty_response_rejected(self):
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(b"")

    def test_truncated_header_rejected(self):
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(bytes(10))

    def test_truncated_ciphertext_rejected(self):
        env = self._envelope()[:-4]
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(env)

    def test_trailing_bytes_rejected(self):
        env = self._envelope() + bytes(22)
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(env)

    def test_non_block_aligned_size_rejected(self):
        env = self.IV + (17).to_bytes(2, "big") + bytes(17)
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(env)

    def test_corrupt_padding_rejected(self):
        ciphertext = aes(self.KEY, 2, self.IV).encrypt(pkcs7_pad(b"x" * 16))
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0xFF
        env = self.IV + len(tampered).to_bytes(2, "big") + bytes(tampered)
        with self.assertRaises(SecureChannelError):
            self.sc.decrypt_response(env)
