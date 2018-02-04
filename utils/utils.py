import os
import subprocess

from typing import Tuple


def set_wallpaper_gnome3(path) -> None:
    command = ("gsettings set org.gnome.desktop.background "
               "picture-uri file://{}".format(path))
    os.system(command)


def get_screen_resolution() -> Tuple[int, int]:
    # There are various ways to query screen resolution, but most of them
    # require a specific tool to be available on the target system.

    # First, try pygtk.
    try:
        import gtk
        return gtk.gdk.screen_width(), gtk.gdk.screen_height()
    except (ImportError, ModuleNotFoundError):
        pass

    # Then, try xrandr.
    try:
        cmd = ['xrandr']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        xrandr, _ = p.communicate()
        resolution_lines = [l for l in xrandr.decode('ascii').split('\n')
                            if '*' in l]

        # TODO: What if there are multiple displays with different resolutions?
        resolution = resolution_lines[0].split()[0]
        w, h = resolution.split('x', 1)

        return int(w), int(h)
    except FileNotFoundError:
        pass

    exit("Unable to determine screen resolution.")
