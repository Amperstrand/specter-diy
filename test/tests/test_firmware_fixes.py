import sys
import unittest
from unittest import mock


class _Done:
    def __await__(self):
        return
        yield


def drive(coro):
    """Step a coroutine whose yields are resolved inline (sleep stand-in)."""
    val = None
    while True:
        try:
            fut = coro.send(val)
        except StopIteration as e:
            return e.value
        val = None


class FakeConnection:
    T1_protocol = 1

    def __init__(self, inserted=False, connect_fails=0):
        self.inserted = inserted
        self.connect_calls = 0
        self.connect_fails = connect_fails
        self.disconnect_calls = 0

    def isCardInserted(self):
        return self.inserted

    def connect(self, proto):
        self.connect_calls += 1
        if self.connect_calls <= self.connect_fails:
            raise RuntimeError("no ATR")

    def disconnect(self):
        self.disconnect_calls += 1


class MemorycardProbeTest(unittest.TestCase):
    """v2.2.11 chip-probe: presence-absent triggers a forced activation;
    a failing probe returns False; presence-present does a single connect."""

    @classmethod
    def setUpClass(cls):
        import keystore.memorycard as mc
        cls.mc = mc

    def _is_available(self, conn):
        with mock.patch.object(self.mc.MemoryCard, "connection", conn), \
             mock.patch.object(self.mc, "MemoryCardApplet") as applet_cls:
            applet_cls.return_value.select.return_value = None
            applet_cls.return_value.open_secure_channel.return_value = None
            return self.mc.MemoryCard.is_available()

    def test_probe_when_presence_reads_absent(self):
        conn = FakeConnection(inserted=False)
        self.assertTrue(self._is_available(conn))
        self.assertGreaterEqual(conn.connect_calls, 1)

    def test_probe_failing_chip_returns_false(self):
        conn = FakeConnection(inserted=False, connect_fails=99)
        self.assertFalse(self._is_available(conn))

    def test_presence_true_single_full_check(self):
        conn = FakeConnection(inserted=True)
        self.assertTrue(self._is_available(conn))
        self.assertEqual(conn.connect_calls, 1)


class SelectKeystoreRetryTest(unittest.TestCase):
    """v2.2.8 retry guard: is_available() exceptions are swallowed and the
    loop retries until a keystore answers."""

    @classmethod
    def setUpClass(cls):
        import time as real_time
        if not hasattr(real_time, "ticks_ms"):
            real_time.ticks_ms = lambda: int(real_time.monotonic() * 1000)
            real_time.ticks_diff = lambda a, b: a - b
            real_time.ticks_add = lambda a, b: a + b
        import platform as real_stub_platform
        import config as real_config
        real_stub_platform.config = real_config
        for name in ("reboot", "maybe_mkdir", "wipe", "get_version", "get_git_info",
                     "get_battery_status", "get_build_type", "get_firmware_boot_mode",
                     "get_flash_read_protection_status", "get_flash_write_protection_status"):
            if not hasattr(real_stub_platform, name):
                setattr(real_stub_platform, name, lambda *a, **k: None)
        import asyncio as real_asyncio
        if not hasattr(real_asyncio, "sleep_ms"):
            real_asyncio.sleep_ms = lambda ms: _Done()
        import gui.screens.mnemonic as gm
        T = type("ScreenStub", (), {})
        for name in ("MnemonicPrompt", "MnemonicWait", "MnemonicNewKey"):
            if not hasattr(gm, name):
                setattr(gm, name, T)
        import specter
        cls.specter = specter

    def test_retry_guard_swallows_and_recovers(self):
        calls = {"n": 0}

        class FlakyKeystore:
            @classmethod
            def is_available(cls):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise RuntimeError("card floor error")
                return True

            def __init__(self):
                self.ok = True

        class SilentKeystore:
            @classmethod
            def is_available(cls):
                return False

            def __init__(self):
                raise AssertionError("must not be constructed")

        sp = self.specter.Specter.__new__(self.specter.Specter)
        sp.keystores = [FlakyKeystore, SilentKeystore]
        sp.keystore = None
        drive(self.specter.Specter.select_keystore(sp))
        self.assertEqual(calls["n"], 3)
        self.assertTrue(sp.keystore.ok)


if __name__ == "__main__":
    unittest.main()
