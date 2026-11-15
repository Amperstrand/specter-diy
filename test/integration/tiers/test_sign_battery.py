"""Signing-endurance battery — dry tier now (host-key deterministic sigs),
cardman tier when blessed (real Satochip card sigs). SAME verification code
at both tiers; only the key source differs.

    pytest test/integration/tiers/test_sign_battery.py -q --backend=dry --sign-count 200
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                "f469-disco", "libs", "common"))

from embit.ec import PrivateKey  # noqa: E402
from embit.hashes import tagged_hash  # noqa: E402
import hashlib  # noqa: E402


def _dry_key_at(i):
    """Deterministic bench key per index: private = tagged_hash('bench', i)."""
    seed = tagged_hash("bench-sign-battery", str(i).encode())
    return PrivateKey(seed[:32])


def _verify(pubkey, sig, msg):
    return pubkey.verify(sig, msg)


@pytest.mark.needs_any("card-real", "card-mock")
class TestSignBattery:
    """Every signature verified against its pubkey; failure count must be 0."""

    def test_sign_all_verified(self, backend, request):
        n = request.config.getoption("--sign-count")
        fails = []
        for i in range(n):
            msg = hashlib.sha256(b"bench message %d" % i).digest()
            path = "m/84h/0h/0h/0/%d" % i
            if backend.name == "dry":
                key = _dry_key_at(i)
                sig = key.sign(msg)
                pub = key.get_public_key()
            else:
                sig_bytes = backend.sign(msg, path)
                pub = backend.authentikey_for(path)
                assert pub is not None, f"no authentikey for {path}"
                fails_flag = not _verify(pub, sig_bytes, msg)
                if fails_flag:
                    fails.append(i)
                continue
            if not _verify(pub, sig, msg):
                fails.append(i)
        assert not fails, f"signature verification failures at indices: {fails[:10]}"

    def test_sign_shapes(self, backend, request):
        n = min(16, request.config.getoption("--sign-count"))
        for i in range(n):
            msg = hashlib.sha256(b"shape %d" % i).digest()
            if backend.name == "dry":
                sig = _dry_key_at(i).sign(msg).serialize()
            else:
                sig = backend.sign(msg, "m/84h/0h/0h/0/%d" % i)
            assert 8 <= len(sig) <= 72, f"DER length out of range: {len(sig)}"
