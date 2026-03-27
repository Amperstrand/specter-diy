"""Debug info screen shown during multi-keystore detection.

Displays firmware version, card presence, and detected applets
while polling for an available keystore in select_keystore().
"""
import lvgl as lv
from .screen import Screen
from ..common import add_label
from ..core import update


class DebugInfoScreen(Screen):
    """Shows firmware version, card presence, and detected applets."""

    def __init__(self):
        super().__init__()
        self.title = add_label("Specter Debug Info", scr=self, style="title")

        self.version_label = add_label("", scr=self, style="hint")
        self.version_label.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.card_label = add_label("Card: checking...", scr=self, style="small")
        self.card_label.align(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        self.applets_label = add_label("Applets: --", scr=self, style="small")
        self.applets_label.align(self.card_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.status_label = add_label("", scr=self, style="hint")
        self.status_label.align(self.applets_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        self.hint_label = add_label("Waiting for keystore...", scr=self, style="hint")
        self.hint_label.set_y(700)

        self._set_firmware_info()

    def load(self):
        lv.scr_load(self)
        update()

    def _set_firmware_info(self):
        try:
            from platform import get_git_info, get_version
            repo, branch, commit = get_git_info()
            ver = get_version()
            lines = "Firmware: %s" % ver
            if branch != "unknown":
                lines += "\nBranch: %s" % branch
            if commit != "unknown":
                lines += "\nCommit: %s" % commit
            self.version_label.set_text(lines)
        except Exception:
            self.version_label.set_text("Firmware: unknown")

    def update_info(self, info: dict) -> None:
        if not info:
            info = {}

        card_present = info.get("card_present", False)
        applets = info.get("applets", [])
        status = info.get("status", "")

        if not isinstance(applets, (list, tuple)):
            applets = []

        if card_present:
            self.card_label.set_text("Card: present")
        else:
            self.card_label.set_text("Card: not detected")

        if applets:
            self.applets_label.set_text("Applets:\n" + "\n".join(["  - " + str(a) for a in applets]))
        else:
            self.applets_label.set_text("Applets: (none detected)")

        if status:
            self.status_label.set_text(str(status))
        else:
            self.status_label.set_text("")

        update()
