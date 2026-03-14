"""
GUI module tests using mocks for LVGL dependencies.
"""

import asyncio
import importlib
import os
import sys
import types
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch


_ = sys.modules.setdefault("lvgl", MagicMock())
_ = sys.modules.setdefault("ucryptolib", MagicMock())
_ = sys.modules.setdefault("uhashlib", MagicMock())


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
GUI_DIR = os.path.join(SRC_DIR, "gui")


def _clear_gui_modules():
    for key in list(sys.modules.keys()):
        if key == "gui" or key.startswith("gui."):
            _ = sys.modules.pop(key)


def _import_async_gui_module():
    _clear_gui_modules()
    gui_pkg = types.ModuleType("gui")
    gui_pkg.__path__ = [GUI_DIR]

    core_module = types.ModuleType("gui.core")
    setattr(core_module, "init", MagicMock())
    setattr(core_module, "update", MagicMock())

    screens_module = types.ModuleType("gui.screens")
    setattr(screens_module, "Menu", MagicMock())
    setattr(screens_module, "Alert", MagicMock())
    setattr(screens_module, "QRAlert", MagicMock())
    setattr(screens_module, "Prompt", MagicMock())
    setattr(screens_module, "InputScreen", MagicMock())

    components_pkg = types.ModuleType("gui.components")
    components_pkg.__path__ = [os.path.join(GUI_DIR, "components")]

    modal_module = types.ModuleType("gui.components.modal")
    setattr(modal_module, "Modal", MagicMock())

    battery_module = types.ModuleType("gui.components.battery")

    class Battery:
        VALUE: object = None
        CHARGING: object = None

    setattr(battery_module, "Battery", Battery)

    lv = MagicMock()
    old_screen = MagicMock()
    old_screen.del_async = MagicMock()
    lv.scr_act.return_value = old_screen

    mock_modules = {
        "gui": gui_pkg,
        "gui.core": core_module,
        "gui.screens": screens_module,
        "gui.components": components_pkg,
        "gui.components.modal": modal_module,
        "gui.components.battery": battery_module,
        "lvgl": lv,
    }

    with patch.dict(sys.modules, mock_modules):
        module = importlib.import_module("gui.async_gui")

    return module, lv


def _import_screen_module():
    _clear_gui_modules()
    gui_pkg = types.ModuleType("gui")
    gui_pkg.__path__ = [GUI_DIR]

    screens_pkg = types.ModuleType("gui.screens")
    screens_pkg.__path__ = [os.path.join(GUI_DIR, "screens")]

    components_pkg = types.ModuleType("gui.components")
    components_pkg.__path__ = [os.path.join(GUI_DIR, "components")]

    class FakeObj:
        def __init__(self, *args, **kwargs):
            self.__dict__["_y"] = 0

        def set_style(self, style):
            self.__dict__["style"] = style

        def set_size(self, w, h):
            self.__dict__["size"] = (w, h)

        def set_pos(self, x, y):
            self.__dict__["pos"] = (x, y)

        def align(self, *args):
            self.__dict__["aligned"] = args

    class FakeStyle:
        def __init__(self):
            self.body = types.SimpleNamespace(
                main_color=None,
                grad_color=None,
                opa=None,
                radius=None,
                border=types.SimpleNamespace(width=None),
            )

    class FakeLV:
        obj = FakeObj
        style_t = FakeStyle
        ALIGN = types.SimpleNamespace(IN_TOP_RIGHT=1)

        @staticmethod
        def color_hex(value):
            return value

        @staticmethod
        def style_copy(dst, src):
            del src
            return dst

    common_module = types.ModuleType("gui.common")
    setattr(common_module, "HOR_RES", 480)
    setattr(common_module, "styles", {
        "theme": types.SimpleNamespace(style=types.SimpleNamespace(btn=types.SimpleNamespace(rel=object())))
    })

    core_module = types.ModuleType("gui.core")
    setattr(core_module, "update", MagicMock())

    modal_module = types.ModuleType("gui.components.modal")
    setattr(modal_module, "Modal", MagicMock())

    battery_module = types.ModuleType("gui.components.battery")

    class Battery:
        def __init__(self, parent):
            self.__dict__["parent"] = parent

        def align(self, *args):
            self.__dict__["aligned"] = args

        def update(self):
            pass

    setattr(battery_module, "Battery", Battery)

    mock_modules = {
        "gui": gui_pkg,
        "gui.screens": screens_pkg,
        "gui.components": components_pkg,
        "gui.common": common_module,
        "gui.core": core_module,
        "gui.components.modal": modal_module,
        "gui.components.battery": battery_module,
        "lvgl": FakeLV,
    }

    with patch.dict(sys.modules, mock_modules):
        module = importlib.import_module("gui.screens.screen")

    return module, core_module


def _import_keyboard_module():
    _clear_gui_modules()
    gui_pkg = types.ModuleType("gui")
    gui_pkg.__path__ = [GUI_DIR]

    components_pkg = types.ModuleType("gui.components")
    components_pkg.__path__ = [os.path.join(GUI_DIR, "components")]

    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self.__dict__["hidden"] = None
            self.__dict__["text"] = ""
            self.__dict__["pos"] = (0, 0)

        def set_size(self, w, h):
            self.__dict__["size"] = (w, h)

        def set_hidden(self, value):
            self.__dict__["hidden"] = value

        def set_text(self, text):
            self.__dict__["text"] = text

        def set_style(self, *args):
            self.__dict__["style"] = args

        def set_pos(self, x, y):
            self.__dict__["pos"] = (x, y)

    class FakeBtnm(FakeWidget):
        def set_event_cb(self, cb):
            self.__dict__["_event_cb"] = cb

    class FakePoint:
        def __init__(self):
            self.x = 0
            self.y = 0

    class FakeLV:
        btnm = FakeBtnm
        btn = FakeWidget
        label = FakeWidget
        point_t = FakePoint
        EVENT = types.SimpleNamespace(PRESSING=1, RELEASED=2)

        @staticmethod
        def indev_get_act():
            return object()

        @staticmethod
        def indev_get_point(indev, point):
            del indev
            point.x = 110
            point.y = 180

    decorators_module = types.ModuleType("gui.decorators")
    setattr(decorators_module, "feed_touch", MagicMock())

    theme_module = types.ModuleType("gui.components.theme")
    setattr(theme_module, "styles", {"title": object()})

    mock_modules = {
        "gui": gui_pkg,
        "gui.components": components_pkg,
        "gui.decorators": decorators_module,
        "gui.components.theme": theme_module,
        "lvgl": FakeLV,
    }

    with patch.dict(sys.modules, mock_modules):
        module = importlib.import_module("gui.components.keyboard")

    return module, decorators_module, FakeLV


class AsyncGUITest(TestCase):
    def test_async_mock_setup(self):
        module, _ = _import_async_gui_module()
        gui = module.AsyncGUI()
        gui.release(1, test=True)
        self.assertTrue(gui.waiting)
        self.assertEqual(gui.args, (1,))
        self.assertEqual(gui.kwargs, {"test": True})

    def test_show_screen_popup_flow(self):
        module, _ = _import_async_gui_module()
        gui = module.AsyncGUI()
        gui.open_popup = AsyncMock()
        gui.close_popup = AsyncMock()
        gui.load_screen = AsyncMock()
        scr = MagicMock()
        scr.result = AsyncMock(return_value="accepted")

        result = asyncio.run(gui.show_screen(popup=True)(scr))

        self.assertEqual(result, "accepted")
        gui.open_popup.assert_awaited_once_with(scr)
        gui.close_popup.assert_awaited_once()
        gui.load_screen.assert_not_called()

    def test_update_battery_updates_screen_and_exits(self):
        module, _ = _import_async_gui_module()
        gui = module.AsyncGUI()

        values = iter([(72, True), (None, False)])
        gui.battery_callback = lambda: next(values)
        gui.scr = MagicMock()
        gui.scr.battery = MagicMock()
        gui.scr.battery.update = MagicMock()

        with patch.object(module.asyncio, "sleep_ms", AsyncMock(return_value=None), create=True):
            asyncio.run(gui.update_battery(5))

        self.assertEqual(module.Battery.VALUE, 72)
        self.assertTrue(module.Battery.CHARGING)
        gui.scr.battery.update.assert_called_once()


class ScreenTest(TestCase):
    def test_screen_mock_setup(self):
        module, _ = _import_screen_module()
        screen = module.Screen()
        screen.set_value("done")
        self.assertEqual(screen.get_value(), "done")
        self.assertFalse(screen.waiting)

    def test_loader_show_and_hide(self):
        module, core_module = _import_screen_module()
        modal = MagicMock()
        with patch.object(module, "Modal", return_value=modal):
            screen = module.Screen()
            screen.show_loader("working", "title")
            module.Modal.assert_called_once_with(screen)
            modal.set_text.assert_called_once()
            self.assertEqual(core_module.update.call_count, 2)

            screen.hide_loader()
            modal.del_async.assert_called_once()
            self.assertIsNone(screen.mbox)


class ComponentTest(TestCase):
    def test_component_mock_setup(self):
        module, decorators, lv = _import_keyboard_module()
        keyboard = module.HintKeyboard(MagicMock())
        active_obj = MagicMock()
        active_obj.get_active_btn_text.return_value = "a"

        keyboard.cb(active_obj, lv.EVENT.PRESSING)

        decorators.feed_touch.assert_called_once()
        self.assertFalse(keyboard.hint.hidden)
        self.assertEqual(keyboard.hint_lbl.text, "a")
        self.assertEqual(keyboard.hint.pos, (85, 50))

    def test_component_release_event_hides_hint_and_forwards_cb(self):
        module, _, lv = _import_keyboard_module()
        keyboard = module.HintKeyboard(MagicMock())
        callback = MagicMock()
        keyboard.set_event_cb(callback)
        active_obj = MagicMock()

        keyboard.cb(active_obj, lv.EVENT.RELEASED)

        self.assertTrue(keyboard.hint.hidden)
        callback.assert_called_once_with(active_obj, lv.EVENT.RELEASED)
