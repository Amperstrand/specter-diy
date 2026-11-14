import sys
import types
import unittest


class LocklessAsyncioRegressionTest(unittest.TestCase):
    """The vendored f469-disco asyncio (old uasyncio v2, frozen for disco
    builds) has no Lock class. A bare asyncio.Lock() in TestMode.__init__
    killed the constructor on hardware, and the AttributeError vanished into
    the unbridged USB CDC stdout — two days of bench silence (v2.2.6c-v2.2.9,
    2026-11-14). TestMode must construct cleanly against a Lock-less asyncio.
    """

    def _import_test_mode_with_stubs(self):
        fake_platform = types.ModuleType("platform")
        fake_platform.simulator = True

        fake_pyb = types.ModuleType("pyb")

        lockless_asyncio = types.ModuleType("asyncio")
        lockless_asyncio.create_task = lambda coro: coro
        self.assertFalse(hasattr(lockless_asyncio, "Lock"), "test premise: stub lacks Lock")

        saved = {m: sys.modules.get(m) for m in ("platform", "pyb", "asyncio")}
        sys.modules["platform"] = fake_platform
        sys.modules["pyb"] = fake_pyb
        sys.modules["asyncio"] = lockless_asyncio
        try:
            if "test_mode" in sys.modules:
                del sys.modules["test_mode"]
            import test_mode
            return test_mode
        finally:
            for name, mod in saved.items():
                if mod is not None:
                    sys.modules[name] = mod

    def test_ctor_survives_lockless_asyncio(self):
        test_mode = self._import_test_mode_with_stubs()
        try:
            tm = test_mode.TestMode(specter_ref=None)
        except AttributeError as e:
            self.fail(f"TestMode.__init__ raised AttributeError against Lock-less asyncio: {e}")
        self.assertIsNone(tm.uart)
        self.assertIsNotNone(tm._ch_lock)
        self.assertIsNone(tm._last_reply)

    def test_ch_lock_is_async_context_manager(self):
        import asyncio as real_asyncio

        async def _exercise():
            async with tm._ch_lock:
                pass

        test_mode = self._import_test_mode_with_stubs()
        tm = test_mode.TestMode(specter_ref=None)
        real_asyncio.run(_exercise())


if __name__ == "__main__":
    unittest.main()
