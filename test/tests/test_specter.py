import importlib
import os
import sys
import types
from unittest import TestCase
from unittest.mock import MagicMock, patch


_ = sys.modules.setdefault("pyb", MagicMock())
_ = sys.modules.setdefault("machine", MagicMock())
_ = sys.modules.setdefault("platform", MagicMock())


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _clear_specter_modules():
    for key in list(sys.modules.keys()):
        if key == "specter" or key.startswith("specter."):
            _ = sys.modules.pop(key)


def _import_specter_module():
    _clear_specter_modules()

    platform_module = types.ModuleType("platform")

    class CriticalErrorWipeImmediately(Exception):
        pass

    setattr(platform_module, "CriticalErrorWipeImmediately", CriticalErrorWipeImmediately)
    setattr(platform_module, "reboot", MagicMock())
    setattr(platform_module, "maybe_mkdir", MagicMock())
    setattr(platform_module, "wipe", MagicMock())
    setattr(platform_module, "get_version", MagicMock(return_value="1.0.0"))
    setattr(platform_module, "get_git_info", MagicMock(return_value=("repo", "main", "abc123")))
    setattr(platform_module, "get_battery_status", MagicMock(return_value=(95, False)))
    setattr(platform_module, "get_build_type", MagicMock(return_value="release"))
    setattr(platform_module, "get_firmware_boot_mode", MagicMock(return_value="normal"))
    setattr(platform_module, "get_flash_read_protection_status", MagicMock(return_value="enabled"))
    setattr(platform_module, "get_flash_write_protection_status", MagicMock(return_value="enabled"))

    hosts_module = types.ModuleType("hosts")

    class Host:
        parent = None

    class HostError(Exception):
        pass

    setattr(hosts_module, "Host", Host)
    setattr(hosts_module, "HostError", HostError)

    app_module = types.ModuleType("app")

    class BaseApp:
        GLOBAL = {}

    setattr(app_module, "BaseApp", BaseApp)

    embit_module = types.ModuleType("embit")
    bip39_module = types.ModuleType("embit.bip39")
    setattr(bip39_module, "WORDLIST", ["abandon"] * 2048)
    liquid_module = types.ModuleType("embit.liquid")
    networks_module = types.ModuleType("embit.liquid.networks")
    setattr(networks_module, "NETWORKS", {"main": {"name": "Bitcoin Mainnet"}})

    gui_settings_module = types.ModuleType("gui.screens.settings")
    setattr(gui_settings_module, "HostSettings", MagicMock())

    gui_mnemonic_module = types.ModuleType("gui.screens.mnemonic")
    setattr(gui_mnemonic_module, "MnemonicPrompt", MagicMock())

    gui_debug_module = types.ModuleType("gui.screens.debug_info")
    setattr(gui_debug_module, "DebugInfoScreen", MagicMock())

    helpers_module = types.ModuleType("helpers")
    setattr(helpers_module, "gen_mnemonic", MagicMock(return_value="mnemonic"))
    setattr(helpers_module, "fix_mnemonic", MagicMock(side_effect=lambda m: m))

    errors_module = types.ModuleType("errors")

    class BaseError(Exception):
        NAME = "Base error"

    setattr(errors_module, "BaseError", BaseError)

    debug_trace_module = types.ModuleType("debug_trace")
    setattr(debug_trace_module, "log", MagicMock())
    setattr(debug_trace_module, "log_exception", MagicMock())

    mocked_modules = {
        "platform": platform_module,
        "hosts": hosts_module,
        "app": app_module,
        "embit": embit_module,
        "embit.bip39": bip39_module,
        "embit.liquid": liquid_module,
        "embit.liquid.networks": networks_module,
        "gui.screens.settings": gui_settings_module,
        "gui.screens.mnemonic": gui_mnemonic_module,
        "gui.screens.debug_info": gui_debug_module,
        "helpers": helpers_module,
        "errors": errors_module,
        "debug_trace": debug_trace_module,
    }

    with patch.dict(sys.modules, mocked_modules):
        module = importlib.import_module("specter")

    return module, {"platform": platform_module, "hosts": hosts_module}


class SpecterTest(TestCase):
    def test_specter_mock_setup(self):
        module, mocked = _import_specter_module()
        gui = MagicMock()
        keystore_instance = MagicMock()
        keystore_ctor = MagicMock(return_value=keystore_instance)

        specter = module.Specter(
            gui=gui,
            keystores=[keystore_ctor],
            hosts=[],
            apps=[],
            settings_path="/tmp/specter-tests",
        )

        keystore_ctor.assert_called_once_with()
        self.assertIs(specter.keystore, keystore_instance)
        self.assertIs(mocked["hosts"].Host.parent, specter)

    def test_device_initialization(self):
        module, mocked = _import_specter_module()
        gui = MagicMock()
        host1 = MagicMock()
        host2 = MagicMock()

        specter = module.Specter(
            gui=gui,
            keystores=[MagicMock(return_value=MagicMock())],
            hosts=[host1, host2],
            apps=[],
            settings_path="/tmp/specter-tests",
        )

        with patch.object(module.asyncio, "run") as run_mock:
            run_mock.side_effect = lambda coro: coro.close()
            specter.start()

        gui.set_battery_callback.assert_called_once_with(mocked["platform"].get_battery_status, 3000)
        gui.start.assert_called_once_with()
        host1.start.assert_called_once_with(specter)
        host2.start.assert_called_once_with(specter)
        run_mock.assert_called_once()

    def test_wallet_management(self):
        module, _ = _import_specter_module()
        gui = MagicMock()
        keystore = MagicMock()
        app = MagicMock()

        specter = module.Specter(
            gui=gui,
            keystores=[MagicMock(return_value=keystore)],
            hosts=[],
            apps=[app],
            settings_path="/tmp/specter-tests",
        )

        next_menu = specter.set_mnemonic("  test mnemonic words  ", "passphrase")

        keystore.set_mnemonic.assert_called_once_with("test mnemonic words", "passphrase")
        app.init.assert_called_once_with(
            keystore,
            "main",
            gui.show_loader,
            specter.cross_app_communicate,
        )
        self.assertIs(next_menu.__self__, specter)
        self.assertIs(next_menu.__func__, specter.mainmenu.__func__)
        self.assertIs(specter.current_menu.__self__, specter)
        self.assertIs(specter.current_menu.__func__, specter.mainmenu.__func__)
