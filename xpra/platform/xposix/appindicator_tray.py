# This file is part of Xpra.
# Copyright (C) 2011-2022 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

# Ubuntu's "tray" is not very useful:
# - we can't know its position
# - we can't get pointer motion events
# - we can't set the icon using a path (not easily anyway)
# - we can only show a menu and nothing else
# - that menu looks bloody awful
# etc

import os
import sys
import tempfile
from time import monotonic

from xpra.util import envbool
from xpra.os_util import osexpand
from xpra.client.tray_base import TrayBase
from xpra.platform.paths import get_icon_dir, get_icon_filename, get_xpra_tmp_dir
from xpra.log import Logger

log = Logger("tray", "posix")

import gi
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")  # @UndefinedVariable
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3 #pylint: disable=wrong-import-order, wrong-import-position, ungrouped-imports
except (ImportError, ValueError):
    try:
        gi.require_version("AppIndicator3", "0.1")  # @UndefinedVariable
        from gi.repository import AppIndicator3 #pylint: disable=wrong-import-order, wrong-import-position, ungrouped-imports
        log("loaded AppIndicator3")
    except ValueError as e:
        raise ImportError(f"failed to load `AppIndicator3`: {e}")

DELETE_TEMP_FILE = envbool("XPRA_APPINDICATOR_DELETE_TEMP_FILE", True)

PASSIVE = AppIndicator3.IndicatorStatus.PASSIVE
ACTIVE = AppIndicator3.IndicatorStatus.ACTIVE
APPLICATION_STATUS = AppIndicator3.IndicatorCategory.APPLICATION_STATUS
def Indicator(tooltip, filename, status):
    return AppIndicator3.Indicator.new(tooltip, filename, status)


class AppindicatorTray(TrayBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        filename = get_icon_filename(self.default_icon_filename) or "xpra.png"
        self._has_icon = False
        self.tmp_filename = None
        self.tray_widget = Indicator(self.tooltip, filename, APPLICATION_STATUS)
        if hasattr(self.tray_widget, "set_icon_theme_path"):
            self.tray_widget.set_icon_theme_path(get_icon_dir())
        try:
            self.tray_widget.set_attention_icon_full("xpra.png", self.tooltip)
        except AttributeError:
            self.tray_widget.set_attention_icon("xpra.png")
        if filename:
            self.set_icon_from_file(filename)
        if not self._has_icon:
            self.tray_widget.set_label("Xpra")
        if self.menu:
            self.tray_widget.set_menu(self.menu)

    def get_geometry(self):
        #no way to tell :(
        return None

    def hide(self):
        self.tray_widget.set_status(PASSIVE)

    def show(self):
        self.tray_widget.set_status(ACTIVE)

    def set_blinking(self, on):
        #"I'm Afraid I Can't Do That"
        pass

    def set_tooltip(self, tooltip=None):
        #we only use this if we haven't got an icon
        #as with appindicator this creates a large text label
        #next to where the icon is/should be
        if not self._has_icon:
            self.tray_widget.set_label(tooltip or "Xpra")

    def set_icon_from_data(self, pixels, has_alpha, w, h, rowstride, _options=None):
        #use a temporary file (yuk)
        self.clean_last_tmp_icon()
        # pylint: disable=import-outside-toplevel
        from xpra.gtk_common.gtk_util import pixbuf_save_to_memory, get_pixbuf_from_data
        tray_icon = get_pixbuf_from_data(pixels, has_alpha, w, h, rowstride)
        png_data = pixbuf_save_to_memory(tray_icon)
        tmp_dir = osexpand(get_xpra_tmp_dir())
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir, 0o755)
        fd = None
        try:
            fd, self.tmp_filename = tempfile.mkstemp(prefix="tray", suffix=".png", dir=tmp_dir)
            log("set_icon_from_data%s using temporary file %s",
                (f"{len(pixels)} pixels", has_alpha, w, h, rowstride), self.tmp_filename)
            os.write(fd, png_data)
        except OSError as e:
            log("error saving temporary file", exc_info=True)
            log.error("Error saving icon data to temporary file")
            log.estr(e)
            return
        finally:
            if fd:
                os.fchmod(fd, 0o644)
                os.close(fd)
        self.do_set_icon_from_file(self.tmp_filename)

    def do_set_icon_from_file(self, filename):
        if not hasattr(self.tray_widget, "set_icon_theme_path"):
            self.tray_widget.set_icon(filename)
            self._has_icon = True
            return
        head, icon_name = os.path.split(filename)
        if head:
            log(f"do_set_icon_from_file({filename!r}) setting icon theme path={head!r}")
            self.tray_widget.set_icon_theme_path(head)
        #remove extension (wtf?)
        noext = os.path.splitext(icon_name)[0]
        log(f"do_set_icon_from_file({filename!r}) setting icon={noext}")
        try:
            self.tray_widget.set_icon_full(noext, self.tooltip)
        except AttributeError:
            self.tray_widget.set_icon(noext)
        self._has_icon = True
        self.icon_timestamp = monotonic()

    def clean_last_tmp_icon(self):
        if self.tmp_filename and DELETE_TEMP_FILE:
            try:
                os.unlink(self.tmp_filename)
            except OSError:
                log("failed to remove tmp icon", exc_info=True)
            self.tmp_filename = None

    def cleanup(self):
        self.clean_last_tmp_icon()
        super().cleanup()


def main(): # pragma: no cover
    # pylint: disable=import-outside-toplevel
    from xpra.platform import program_context
    with program_context("AppIndicator-Test", "AppIndicator Test"):
        if "-v" in sys.argv:
            from xpra.log import enable_debug_for
            enable_debug_for("tray")

        from xpra.gtk_common.gobject_compat import register_os_signals

        from gi.repository import Gtk
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="Top Menu Item 1")
        submenu = Gtk.Menu()
        item.set_submenu(submenu)
        sub = Gtk.MenuItem(label="Sub Menu Item 1")
        subsubmenu = Gtk.Menu()
        sub.set_submenu(subsubmenu)
        for n in range(1, 1000):
            subsubmenu.append(Gtk.MenuItem(label="Sub Sub Menu Item "+str(n)))
        submenu.append(sub)
        sub = Gtk.MenuItem(label="Sub Menu Item 2")
        submenu.append(sub)
        menu.append(item)
        item = Gtk.MenuItem(label="Top Menu Item 2")
        menu.append(item)
        menu.show_all()
        a = AppindicatorTray(None, None, menu, "test", "xpra.png", None, None, None, Gtk.main_quit)
        a.show()
        register_os_signals(Gtk.main_quit)
        Gtk.main()


if __name__ == "__main__":  # pragma: no cover
    main()
