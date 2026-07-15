"""MemoryCard HIL integration tests.

Requires:
  - HIL firmware (make hil && make hilflash)
  - JCOP4 card with GP default keys in the reader
  - No MemoryCard installed at start (tests manage install/delete)

Tests are ordered: read-only first, then destructive install/delete.
GP-level tests (direct commands) run before GUI-level tests (screen injection).
"""

import time
import unittest


def has_memorycard():
    try:
        from util.controller import sim
        return sim.keystore_type.lower() == "smartcard"
    except Exception:
        return False


class MemoryCardGPTest(unittest.TestCase):
    """GP-level tests using direct debug UART commands.

    These bypass the GUI entirely and are fast (~5s total).
    They require a card with GP default keys but no MemoryCard installed.
    """

    @classmethod
    def setUpClass(cls):
        from util.controller import sim
        cls.sim = sim
        print("\n=== MemoryCard GP Tests ===")

    def test_01_card_probe(self):
        ok, info = self.sim.mc_probe()
        self.assertTrue(ok, f"Card probe failed: {info}")

    def test_02_card_status(self):
        status = self.sim.mc_status()
        self.assertIn("ISD", status, f"Expected ISD in status: {status}")

    def test_03_not_installed(self):
        self.assertFalse(self.sim.mc_verify("B00B5111CB01"),
                         "MemoryCard should not be installed yet")

    def test_04_install(self):
        self.assertTrue(self.sim.mc_install(), "MemoryCard install failed")

    def test_05_verify_installed(self):
        self.assertTrue(self.sim.mc_verify("B00B5111CB01"),
                        "MemoryCard not found after install")

    def test_06_status_shows_mc(self):
        status = self.sim.mc_status()
        self.assertIn("B00B5111", status,
                      f"MemoryCard AID not in status: {status}")

    def test_07_delete(self):
        self.assertTrue(self.sim.mc_delete(), "Delete failed")

    def test_08_verify_deleted(self):
        self.assertFalse(self.sim.mc_verify("B00B5111CB01"),
                         "MemoryCard still found after delete")

    def test_09_status_clean(self):
        status = self.sim.mc_status()
        self.assertNotIn("B00B5111", status,
                         f"MemoryCard AID still in status after delete: {status}")

    def test_10_reinstall(self):
        self.assertTrue(self.sim.mc_install(), "Reinstall failed")

    def test_11_verify_reinstalled(self):
        self.assertTrue(self.sim.mc_verify("B00B5111CB01"),
                        "MemoryCard not found after reinstall")

    def test_12_final_cleanup(self):
        self.assertTrue(self.sim.mc_delete(), "Final cleanup delete failed")
        self.assertFalse(self.sim.mc_verify("B00B5111CB01"),
                         "Card not clean after final delete")


class MemoryCardGUITest(unittest.TestCase):
    """GUI-level tests that drive the Specter-DIY interface.

    These require MemoryCard to NOT be installed (tests install it
    via GUI and verify the flow). Slower than GP tests (~30-60s).
    """

    @classmethod
    def setUpClass(cls):
        from util.controller import sim
        cls.sim = sim
        print("\n=== MemoryCard GUI Tests ===")

    def _wait_for_screen(self, prefix, timeout=15):
        t0 = time.time()
        while time.time() - t0 < timeout:
            screen = self.sim.gui.screen()
            if prefix in screen:
                return screen
            time.sleep(0.3)
        raise AssertionError(f"Screen {prefix} not found within {timeout}s, last: {screen}")

    def _dismiss_alerts(self, max=5):
        for _ in range(max):
            screen = self.sim.gui.screen()
            if b"OK:SCREEN:Alert:" in screen:
                self.sim.gui.send(True)
                time.sleep(0.5)
            else:
                return
        raise AssertionError("Too many alerts to dismiss")

    def test_01_navigate_to_smartcard_storage(self):
        screen = self.sim.gui.screen()
        if b"OK:SCREEN:Menu:" not in screen:
            self.skipTest("Not on init menu")
        self.sim.gui.send(4)
        time.sleep(1)
        screen = self._wait_for_screen(b"OK:SCREEN:Menu:")
        self.assertIn(b"Smartcard storage", screen,
                      f"Expected Smartcard storage menu, got: {screen}")

    def test_02_get_card_info(self):
        screen = self.sim.gui.screen()
        if b"Smartcard storage" not in screen:
            self.skipTest("Not on Smartcard storage menu")
        self.sim.gui.send(0)
        time.sleep(2)
        self._dismiss_alerts()
        screen = self._wait_for_screen(b"OK:SCREEN:", timeout=15)
        self.sim.gui.send(True)
        time.sleep(1)

    def test_03_install_from_menu(self):
        screen = self.sim.gui.screen()
        if b"Smartcard storage" not in screen:
            self.skipTest("Not on Smartcard storage menu")
        self.sim.gui.send(1)
        time.sleep(0.5)
        screen = self._wait_for_screen(b"OK:SCREEN:Prompt:", timeout=5)
        self.sim.gui.send(True)
        time.sleep(15)
        screen = self._wait_for_screen(b"OK:SCREEN:", timeout=30)
        if b"ProvisioningProgressScreen" in screen or b"MemoryCard" in screen:
            print("  Install flow started (waiting for completion)...")
            for _ in range(60):
                screen = self.sim.gui.screen()
                if b"OK:SCREEN:Prompt:" in screen:
                    break
                if b"OK:SCREEN:Alert:" in screen:
                    break
                time.sleep(1)
        self._dismiss_alerts()

    def test_04_verify_installed_via_gp(self):
        self.assertTrue(self.sim.mc_verify("B00B5111CB01"),
                        "MemoryCard not installed after GUI install")

    def test_05_cleanup(self):
        self.assertTrue(self.sim.mc_delete(), "Cleanup delete failed")
        self.assertFalse(self.sim.mc_verify("B00B5111CB01"),
                         "Card not clean after cleanup")


class MemoryCardBootTest(unittest.TestCase):
    """Tests that require device reset with MemoryCard installed.

    These install MemoryCard, reset the device, and verify
    the boot flow detects it as the active keystore.
    """

    @classmethod
    def setUpClass(cls):
        from util.controller import sim
        cls.sim = sim
        print("\n=== MemoryCard Boot Tests ===")

    def test_01_install_for_boot(self):
        if self.sim.mc_verify("B00B5111CB01"):
            print("  MemoryCard already installed, skipping install")
            return
        self.assertTrue(self.sim.mc_install(), "Install for boot test failed")
        self.assertTrue(self.sim.mc_verify("B00B5111CB01"),
                        "Install verification failed")

    def test_02_reset_device(self):
        resp = self.sim.gui.command("TEST_RESET", timeout=5)
        self.assertIn(b"OK:RESET", resp)
        time.sleep(3)
        self.sim.gui._reopen()
        for _ in range(60):
            resp = self.sim.gui.status()
            if b"OK:READY" in resp:
                break
            time.sleep(0.5)
        else:
            self.fail("Device not ready after reset")

    def test_03_detects_smartcard_keystore(self):
        t0 = time.time()
        while time.time() - t0 < 30:
            resp = self.sim.gui.command("TEST_KEYSTORE", timeout=2)
            if b"OK:KEYSTORE:smartcard" in resp:
                print("  Detected keystore: smartcard")
                return
            if b"OK:KEYSTORE:" in resp:
                name = resp.split(b"OK:KEYSTORE:", 1)[1].strip().decode()
                if name not in ("unknown", ""):
                    print(f"  Detected keystore: {name} (not smartcard)")
                    break
            time.sleep(0.5)
        self.fail(f"Smartcard keystore not detected within 30s, last: {resp}")

    def test_04_pin_entry(self):
        screen = self.sim.gui.screen()
        if b"PinScreen" in screen:
            self.sim.gui.send("")
            time.sleep(1)
            print("  PIN entered")
        else:
            print(f"  No PIN screen, current: {screen}")

    def test_05_cleanup_after_boot(self):
        self.sim.mc_card_reset()
        time.sleep(1)
        self.assertTrue(self.sim.mc_delete(), "Post-boot cleanup failed")
        self.assertFalse(self.sim.mc_verify("B00B5111CB01"),
                         "Card not clean after post-boot cleanup")
