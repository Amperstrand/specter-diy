"""Provisioning screens for JavaCard applet management.

Provides:
- ProvisioningProgressScreen: shows install/delete progress
- ProvisioningDetailsScreen: shows card info and registry dump
"""
import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button
from ..core import update
from ..decorators import on_release, cb_with_args


class ProvisioningProgressScreen(Screen):
    """Shows provisioning progress with step-by-step status."""

    def __init__(self, title="Provisioning"):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")

        self.step_label = add_label("", scr=self, style="hint")
        self.step_label.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        self.detail_label = add_label("", scr=self, style="small")
        self.detail_label.align(self.step_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.error_label = add_label("", scr=self, style="warning")
        self.error_label.align(self.detail_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.done_btn = add_button(
            "Done",
            on_release(cb_with_args(self.set_value, True)),
            scr=self,
            y=700,
        )
        self.done_btn.set_hidden(True)

    def load(self):
        lv.scr_load(self)
        update()

    def set_step(self, text):
        self.step_label.set_text(text)
        self.error_label.set_text("")
        update()

    def set_detail(self, text):
        self.detail_label.set_text(text)
        update()

    def set_error(self, text):
        self.error_label.set_text(text)
        self.done_btn.set_hidden(False)
        update()

    def set_done(self):
        self.step_label.set_text("Done!")
        self.error_label.set_text("")
        self.done_btn.set_hidden(False)
        update()


class ProvisioningDetailsScreen(Screen):
    """Shows card info, detected applets, and registry dump."""

    def __init__(self, info):
        super().__init__()
        self.title = add_label("Card Details", scr=self, style="title")

        kind = info.get("kind", "unknown")
        atr = info.get("atr", b"")
        applets = info.get("applets", [])

        from binascii import hexlify
        lines = "Type: %s" % kind
        if atr:
            lines += "\nATR: %s" % hexlify(atr).decode()

        if applets:
            lines += "\n\nDetected:"
            for name in applets:
                lines += "\n  %s" % name
        else:
            lines += "\n\nNo known applets"

        self.info_label = add_label(lines, scr=self, style="hint")
        self.info_label.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.registry_label = add_label("", scr=self, style="small")
        self.registry_label.align(self.info_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        add_button(
            "Back",
            on_release(cb_with_args(self.set_value, True)),
            scr=self,
            y=700,
        )

    def load(self):
        lv.scr_load(self)
        update()

    def set_registry(self, text):
        self.registry_label.set_text(text)
        update()

    def update_info(self, info):
        from binascii import hexlify
        kind = info.get("kind", "unknown")
        atr = info.get("atr", b"")
        applets = info.get("applets", [])
        lines = "Type: %s" % kind
        if atr:
            lines += "\nATR: %s" % hexlify(atr).decode()
        if applets:
            lines += "\n\nDetected:"
            for name in applets:
                lines += "\n  %s" % name
        else:
            lines += "\n\nNo known applets"
        self.info_label.set_text(lines)
        update()
