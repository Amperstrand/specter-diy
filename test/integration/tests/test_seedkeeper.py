"""
SeedKeeper HIL tests.

All tests are skipped unless a SeedKeeper card is detected by the
HardwareController at load time. When no card is present (or T=1
USART fix is not available), SeedKeeper.is_available() returns False,
the controller falls back to internal flash, and has_seedkeeper()
returns False — so every test here is skipped with zero impact.
"""
from unittest import TestCase, skipUnless
from util.controller import sim


def has_seedkeeper():
    return hasattr(sim, 'keystore_type') and sim.keystore_type.lower() == "seedkeeper"


@skipUnless(has_seedkeeper(), "SeedKeeper card not detected")
class SeedKeeperTest(TestCase):

    def test_get_fingerprint(self):
        res = sim.query(b"fingerprint")
        self.assertEqual(len(res), 8, "fingerprint should be 8 hex chars, got: %s" % repr(res))
        int(res, 16)

    def test_fingerprint_stable(self):
        fp1 = sim.query(b"fingerprint")
        fp2 = sim.query(b"fingerprint")
        self.assertEqual(fp1, fp2, "fingerprint should be stable: %s vs %s" % (fp1, fp2))

    def test_get_xpub(self):
        res = sim.query(b"xpub m/44h/1h/0h")
        self.assertTrue(res.startswith(b"tpub") or res.startswith(b"xpub"),
                        "expected xpub, got: %s" % repr(res))

    def test_xpub_multiple_paths(self):
        xpub1 = sim.query(b"xpub m/44h/0h/0h")
        xpub2 = sim.query(b"xpub m/49h/0h/0h")
        self.assertNotEqual(xpub1, xpub2,
                            "different derivation paths should give different xpubs")

    def test_read_only_mnemonic_import(self):
        res = sim.query(b"set_mnemonic abandon about abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
        self.assertTrue(b"error" in res.lower() or b"invalid" in res,
                        "expected error for mnemonic import, got: %s" % repr(res))

    def test_card_secrets_list(self):
        resp = sim.gui.command("TEST_SECRETS", timeout=5)
        self.assertIn(b"OK:SECRETS", resp,
                      "TEST_SECRETS should return OK:SECRETS, got: %s" % repr(resp))

    def test_card_all_secrets_list(self):
        resp = sim.gui.command("TEST_ALL_SECRETS", timeout=5)
        self.assertIn(b"OK:ALL_SECRETS", resp,
                      "TEST_ALL_SECRETS should return OK:ALL_SECRETS, got: %s" % repr(resp))
