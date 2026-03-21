import lvgl as lv
from binascii import hexlify, unhexlify
from app import BaseApp, AppError
from gui.common import add_button
from gui.decorators import on_release
from gui.screens import Menu, Alert, Prompt


class App(BaseApp):
    button = "JavaCard Manager"
    name = "javacard"

    async def _get_connection(self):
        from keystore.javacard.util import get_connection
        conn = get_connection()
        try:
            conn.disconnect()
        except Exception:
            pass
        import time as _time
        _time.sleep_ms(500)
        conn.connect(conn.T1_protocol)
        return conn

    async def _open_session(self, conn):
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.scp02 import open_session
        return open_session(conn, JCOP4_PROFILE)

    async def _show_card_info(self, show_screen):
        from keystore.javacard.gp.probe import probe_card
        try:
            conn = await self._get_connection()
            result = probe_card(conn)
            try:
                conn.disconnect()
            except Exception:
                pass
        except Exception as e:
            await show_screen(Alert(
                title="Error",
                message="Card probe failed:\n%s" % str(e),
                button_text="Close",
            ))
            return True

        atr = hexlify(result.get("atr", b"")).decode()
        kind = result.get("kind", "unknown")
        mc = result.get("memorycard", False)
        sk = result.get("seedkeeper", False)
        lines = ["Kind: %s" % kind]
        lines.append("ATR: %s" % atr)
        if mc:
            lines.append("MemoryCard: installed")
        if sk:
            lines.append("SeedKeeper: installed")
        if not mc and not sk:
            lines.append("No known applets found")
        await show_screen(Alert(
            title="Card Info",
            message="\n".join(lines),
            button_text="Close",
        ))
        return True

    async def _show_installed_applets(self, show_screen):
        from keystore.javacard.gp.registry import list_all, format_registry
        try:
            conn = await self._get_connection()
            session = await self._open_session(conn)
            registry = list_all(session)
            text = format_registry(registry)
            try:
                conn.disconnect()
            except Exception:
                pass
        except Exception as e:
            await show_screen(Alert(
                title="Error",
                message="Failed to read registry:\n%s" % str(e),
                button_text="Close",
            ))
            return True

        await show_screen(Alert(
            title="Installed Applets",
            message=text,
            button_text="Close",
        ))
        return True

    async def _install_from_sd(self, show_screen):
        import platform
        from keystore.javacard.gp.loader import install_from_dgp
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        try:
            with platform.sdcard as sd:
                if not sd.present():
                    await show_screen(Alert(
                        title="Error",
                        message="No SD card inserted",
                        button_text="Close",
                    ))
                    return True
                gp_files = []
                for fname in sd.ilistdir("/gp"):
                    if fname[0].endswith(".dgp") or fname[0].endswith(".cap"):
                        gp_files.append(fname[0])
                if not gp_files:
                    await show_screen(Alert(
                        title="Error",
                        message="No .dgp or .cap files\nfound in /gp/ on SD card",
                        button_text="Close",
                    ))
                    return True
        except Exception as e:
            await show_screen(Alert(
                title="Error",
                message="SD card error:\n%s" % str(e),
                button_text="Close",
            ))
            return True

        buttons = [(i, f) for i, f in enumerate(gp_files)]
        buttons.append((None, ""))
        buttons.append((255, None))
        idx = await show_screen(Menu(
            buttons,
            last=(255, None),
            title="Select DGP file",
            note="",
        ))
        if idx == 255 or idx is None:
            return True

        filename = gp_files[idx]
        filepath = "/gp/%s" % filename

        await show_screen(Alert(
            title="Installing",
            message="Loading %s..." % filename,
            button_text="Close",
        ))

        try:
            conn = await self._get_connection()
            session = await self._open_session(conn)

            with platform.sdcard as sd:
                with sd.open(filepath, "rb") as f:
                    dgp_data = f.read()

            from binascii import hexlify as _h
            from keystore.javacard.gp.loader import extract_package_aid
            pkg_aid = extract_package_aid(dgp_data)
            pkg_aid_hex = _h(pkg_aid).decode()

            await show_screen(Alert(
                title="Installing",
                message="Package: %s\n%d bytes" % (pkg_aid_hex, len(dgp_data)),
                button_text="Close",
            ))

            sd_aid = JCOP4_PROFILE["isd_aid"]
            installed_aid = install_from_dgp(session, dgp_data, sd_aid)

            await show_screen(Alert(
                title="Success",
                message="%s\n%s installed!" % (filename, _h(installed_aid).decode()),
                button_text="Close",
            ))

            try:
                conn.disconnect()
            except Exception:
                pass
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            await show_screen(Alert(
                title="Install Failed",
                message=str(e),
                button_text="Close",
            ))

        return True

    async def _delete_applet(self, show_screen):
        from keystore.javacard.gp.deleter import delete_aid
        from keystore.javacard.gp.registry import list_all
        try:
            conn = await self._get_connection()
            session = await self._open_session(conn)
            registry = list_all(session)
            try:
                conn.disconnect()
            except Exception:
                pass
        except Exception as e:
            await show_screen(Alert(
                title="Error",
                message="Failed to read registry:\n%s" % str(e),
                button_text="Close",
            ))
            return True

        all_entries = []
        for category in ["apps", "packages", "load_files"]:
            for entry in registry.get(category, []):
                aid = entry.get("aid", b"")
                if aid:
                    all_entries.append(entry)

        if not all_entries:
            await show_screen(Alert(
                title="No Applets",
                message="No applets found\nto delete",
                button_text="Close",
            ))
            return True

        buttons = []
        for i, entry in enumerate(all_entries):
            aid_hex = hexlify(entry["aid"]).decode()
            lc = entry.get("lifecycle")
            label = "%s" % aid_hex
            if lc is not None:
                label += " (LC=%02X)" % lc
            buttons.append((i, label))
        buttons.append((None, ""))
        buttons.append((255, None))

        idx = await show_screen(Menu(
            buttons,
            last=(255, None),
            title="Select applet to delete",
            note="",
        ))
        if idx == 255 or idx is None:
            return True

        entry = all_entries[idx]
        aid_hex = hexlify(entry["aid"]).decode()

        confirm = await show_screen(Prompt(
            "Delete %s?" % aid_hex,
            message="This cannot be undone.",
        ))
        if not confirm:
            return True

        try:
            conn = await self._get_connection()
            session = await self._open_session(conn)
            delete_aid(session, entry["aid"])
            try:
                conn.disconnect()
            except Exception:
                pass
            await show_screen(Alert(
                title="Deleted",
                message="%s deleted" % aid_hex,
                button_text="Close",
            ))
        except Exception as e:
            try:
                conn.disconnect()
            except Exception:
                pass
            await show_screen(Alert(
                title="Delete Failed",
                message=str(e),
                button_text="Close",
            ))

        return True

    async def _show_debug_info(self, show_screen):
        from keystore.javacard.gp.profiles import JCOP4_PROFILE
        from keystore.javacard.gp.probe import probe_card
        from keystore.javacard.gp.registry import list_all, format_registry
        try:
            conn = await self._get_connection()
            result = probe_card(conn)
            session = await self._open_session(conn)
            registry = list_all(session)
            text = format_registry(registry)
            try:
                conn.disconnect()
            except Exception:
                pass
        except Exception as e:
            await show_screen(Alert(
                title="Error",
                message="Debug failed:\n%s" % str(e),
                button_text="Close",
            ))
            return True

        lines = []
        lines.append("SCP: %s" % JCOP4_PROFILE["scp"])
        lines.append("Key version: %d" % JCOP4_PROFILE["key_version"])
        lines.append("Card kind: %s" % result.get("kind", "unknown"))
        lines.append("ATR: %s" % hexlify(result.get("atr", b"")).decode())
        lines.append("")
        lines.append(text)
        await show_screen(Alert(
            title="Debug Info",
            message="\n".join(lines),
            button_text="Close",
        ))
        return True

    async def menu(self, show_screen):
        buttons = [
            (None, "Card Management"),
            (0, "Card Info"),
            (1, "Installed Applets"),
            (2, "Install from SD Card"),
            (3, "Delete Applet"),
            (None, "Developer"),
            (4, "Debug Info"),
        ]

        menuitem = await show_screen(Menu(
            buttons,
            last=(255, None),
            title="JavaCard Manager",
            note="",
        ))

        if menuitem == 255:
            return False

        if menuitem == 0:
            return await self._show_card_info(show_screen)
        elif menuitem == 1:
            return await self._show_installed_applets(show_screen)
        elif menuitem == 2:
            return await self._install_from_sd(show_screen)
        elif menuitem == 3:
            return await self._delete_applet(show_screen)
        elif menuitem == 4:
            return await self._show_debug_info(show_screen)

        return True
