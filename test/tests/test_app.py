import importlib
import os
import sys
import types
from io import BytesIO
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch


_ = sys.modules.setdefault("pyb", MagicMock())
_ = sys.modules.setdefault("machine", MagicMock())
_ = sys.modules.setdefault("platform", MagicMock())


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _clear_app_modules():
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            _ = sys.modules.pop(key)


def _import_app_module():
    _clear_app_modules()

    platform_module = types.ModuleType("platform")
    setattr(platform_module, "maybe_mkdir", MagicMock())
    setattr(platform_module, "delete_recursively", MagicMock())

    errors_module = types.ModuleType("errors")

    class BaseError(Exception):
        NAME = "Base error"

    setattr(errors_module, "BaseError", BaseError)

    mocked_modules = {
        "platform": platform_module,
        "errors": errors_module,
    }

    with patch.dict(sys.modules, mocked_modules):
        module = importlib.import_module("app")

    return module, platform_module


class AppTest(TestCase):
    def test_app_mock_setup(self):
        module, platform_module = _import_app_module()
        app = module.BaseApp("/tmp/app-tests")
        platform_module.maybe_mkdir.assert_called_once_with("/tmp/app-tests")
        self.assertEqual(app.path, "/tmp/app-tests")

    def test_app_initialization(self):
        module, _ = _import_app_module()
        app = module.BaseApp("/tmp/app-tests")
        keystore = MagicMock()
        show_loader = MagicMock()
        communicate = AsyncMock()

        app.init(keystore, "test", show_loader, communicate)

        self.assertIs(app.keystore, keystore)
        self.assertEqual(app.network, "test")
        self.assertIs(app.show_loader, show_loader)
        self.assertIs(app.communicate, communicate)

    def test_screen_management(self):
        module, _ = _import_app_module()

        class DemoApp(module.BaseApp):
            prefixes = [b"wallet"]

        app = DemoApp("/tmp/app-tests")

        valid_stream = BytesIO(b"wallet list")
        self.assertTrue(app.can_process(valid_stream))
        self.assertEqual(valid_stream.read(), b"list")

        invalid_stream = BytesIO(b"unknown cmd")
        self.assertFalse(app.can_process(invalid_stream))
