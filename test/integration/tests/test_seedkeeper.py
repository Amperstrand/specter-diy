from unittest import TestCase, skipUnless
from util.controller import sim


def has_seedkeeper():
    return hasattr(sim, 'keystore_type') and sim.keystore_type == "seedkeeper"


@skipUnless(has_seedkeeper(), "SeedKeeper card not detected")
class SeedKeeperTest(TestCase):

    def test_get_fingerprint(self):
        res = sim.query(b"fingerprint")
        self.assertTrue(len(res) == 8, "fingerprint should be 8 hex chars, got: %s" % repr(res))

    def test_get_xpub(self):
        res = sim.query(b"xpub m/44h/1h/0h")
        self.assertTrue(res.startswith(b"tpub") or res.startswith(b"xpub"), "expected xpub, got: %s" % repr(res))

    def test_read_only_mnemonic_import(self):
        res = sim.query(b"set_mnemonic abandon about abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about")
        self.assertTrue(b"error" in res.lower() or b"Invalid" in res, "expected error, got: %s" % repr(res))
