"""Debug info screen shown during idle keystore detection.

This screen is displayed in the select_keystore() polling loop when multiple
keystores are available. It provides real-time feedback about:

- Firmware version and git commit information
- Smartcard presence detection
- Detected JavaCard applets (SeedKeeper, MemoryCard)
- Card connection status

The screen refreshes every ~500ms (KEYSTORE_POLL_INTERVAL in specter.py)
while waiting for a keystore to become available.

Spec reference:
    - .sisyphus/plans/seedkeeper-support.md: Debug screen displays firmware
      version, card presence, detected applets during keystore detection.
    - specter.py select_keystore(): Shows this screen in multi-keystore mode.

Usage:
    debug_screen = DebugInfoScreen()
    debug_screen.load()
    # ... later, in polling loop:
    info = scan_card_applets(connection)
    debug_screen.update_info(info)
"""
import lvgl as lv
from .screen import Screen
from ..common import add_label, PADDING
from ..core import update

# Screen layout constant - Y position for bottom hint label
_HINT_LABEL_Y = 700


class DebugInfoScreen(Screen):
    """
    Displays firmware version, card presence, and detected applets.
    Shown during the select_keystore() polling loop.
    Call update_info(info_dict) to refresh displayed data.
    """

    def __init__(self):
        super().__init__()
        self.title = add_label("Specter Debug Info", scr=self, style="title")

        # Firmware info (static - set once)
        self.version_label = add_label("", scr=self, style="hint")
        self.version_label.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        # Card presence
        self.card_label = add_label("Card: checking...", scr=self, style="small")
        self.card_label.align(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        # Applets list
        self.applets_label = add_label("Applets: --", scr=self, style="small")
        self.applets_label.align(self.card_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        # Card status details
        self.status_label = add_label("", scr=self, style="hint")
        self.status_label.align(self.applets_label, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)

        # Waiting hint at bottom
        self.hint_label = add_label(
            "Waiting for keystore...", scr=self, style="hint"
        )
        self.hint_label.set_y(_HINT_LABEL_Y)

        # Set firmware info once
        self._set_firmware_info()

    def _set_firmware_info(self):
        """Set static firmware version info."""
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
        except Exception as e:
            self.version_label.set_text("Firmware: unknown")

    def update_info(self, info: dict) -> None:
        """
        Update displayed debug info.
        
        Args:
            info: dict with optional keys:
                - card_present (bool): Whether a smartcard is inserted
                - applets (list[str]): Names of detected applets  
                - status (str): Additional status message
        
        Note:
            Missing keys are handled with safe defaults. Invalid types
            are coerced to safe values to prevent crashes.
        """
        # Defensive: handle None or invalid input
        if not info:
            info = {}
        
        # Extract values with safe defaults
        card_present = info.get("card_present", False)
        applets = info.get("applets", [])
        status = info.get("status", "")
        
        # Validate applets is iterable
        if not isinstance(applets, (list, tuple)):
            applets = []
        
        # Update card presence
        if card_present:
            self.card_label.set_text("Card: present")
        else:
            self.card_label.set_text("Card: not detected")

        # Update applets list
        if applets:
            # Safely convert each applet name to string
            applets_text = "Applets:\n" + "\n".join(["  - " + str(a) for a in applets])
        else:
            applets_text = "Applets: (none detected)"
        self.applets_label.set_text(applets_text)

        # Update status
        if status:
            self.status_label.set_text(str(status))
        else:
            self.status_label.set_text("")

        # Trigger screen refresh
        update()
