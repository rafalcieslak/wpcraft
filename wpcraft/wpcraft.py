#!/usr/bin/env python3

import os
import sys
import json
import shutil
import random
import requests
import argparse
import subprocess
from contextlib import contextmanager
from typing import Dict, Any, Optional, List, Set

from crontab import CronTab

from wpcraft.wpcraftaccess import wpcraftaccess as wpa
from wpcraft.utils import utils

CONFIG_FILE_PATH = (os.getenv("WPCRAFT_CONFIG") or
                    "~/.local/share/wpcraft/config.yml")

DEFAULT_CONFIG: Dict[str, str] = {
    "state-path": "~/.local/share/wpcraft/state.json",
    "cache-dir": "~/.cache/wpcraft",
    "scope": "catalog/city",
    "resolution": "default"
}

CRONTAB_COMMENT = 'wpcraft_automatically_generated'

THIS_FILE = os.path.realpath(__file__)
CRON_COMMAND = "python3 -m wpcraft.wpcraft"


@contextmanager
def data_in_json_file(path: str, default: Dict[str, Any]):
    fullpath = os.path.expanduser(path)
    if not os.path.exists(fullpath):
        data = default.copy()
    else:
        if os.path.exists(fullpath):
            try:
                data = json.load(open(fullpath, 'r'))
            except json.decoder.JSONDecodeError:
                data = default.copy()
        else:
            os.makedirs(os.path.dirname(fullpath))
            data = default.copy

    yield data

    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    json.dump(data, open(fullpath, 'w'), indent=4)


@contextmanager
def user_crontab():
    cron = CronTab(user=True)
    yield cron
    cron.write_to_user(user=True)


class WPCraft:
    config_path: str
    config: Dict[str, str]
    state: Dict[str, Any]

    def __init__(self, config_path: str) -> None:
        self.config_path = os.path.expanduser(config_path)

        # Load config
        if not os.path.exists(self.config_path):
            self.config = DEFAULT_CONFIG
        if os.path.exists(self.config_path):
            data = json.load(open(self.config_path, 'r'))
        else:
            os.makedirs(os.path.dirname(self.config_path))
            data = {}
        if not data:
            data = DEFAULT_CONFIG
        self.config = data

        # Load state
        state_file = self.config_get_filesystem_path("state-path")
        if not os.path.exists(state_file):
            self.state = {}
        else:
            try:
                self.state = json.load(open(state_file, 'r'))
            except json.decoder.JSONDecodeError:
                print("State file is broken, restoring default")
                self.state = {}

    def save(self) -> None:
        # Save state
        state_file = self.config_get_filesystem_path("state-path")
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        json.dump(self.state, open(state_file, 'w'))

        # Save config
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        json.dump(self.config, open(self.config_path, 'w'), indent=4)

    def config_get(self, path: str):
        if path in self.config:
            return self.config[path]
        return DEFAULT_CONFIG[path]

    def config_get_filesystem_path(self, path: str):
        return os.path.abspath(os.path.expanduser(self.config_get(path)))

    def get_wpdata(self, id: wpa.WPID) -> Optional[wpa.WPData]:
        # TODO: Maybe cache wpdata, or is it unnecessary?
        return wpa.get_wpdata(id)

    def get_wpids(self, scope: wpa.WPScope=None,
                  clear_cache=False) -> List[wpa.WPID]:
        if scope is None:
            scope = wpa.WPScope(self.config_get("scope"))
        if scope == "liked":
            return self.state.get("liked", [])
        if scope == "disliked":
            return self.state.get("disliked", [])
        cache_dir = self.config_get_filesystem_path("cache-dir")
        path = os.path.join(cache_dir, "by_scope", str(scope) + ".json")
        with data_in_json_file(path, {}) as data:
            if clear_cache:
                data.clear()
            if 'ids' in data:
                return data['ids']
            data['ids'] = wpa.get_wpids(scope)
            return data['ids']

    def get_resolution(self) -> str:
        resolution = self.config_get("resolution")
        if resolution == "default":
            w, h = utils.get_screen_resolution()
            return '{}x{}'.format(w, h)
        return resolution

    def get_wallpaper_cache_path(self, id: wpa.WPID, image_url: str) -> str:
        return "{}/{}.{}".format(
            self.config_get_filesystem_path("cache-dir"),
            id, image_url.split('.')[-1])

    def download_image(self, source, target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        s = requests.Session()
        image = s.get(source, stream=True)
        with open(target, 'wb') as out_file:
            shutil.copyfileobj(image.raw, out_file)

    def switch_to_wallpaper(self, id: wpa.WPID, dry_run: bool=False) -> None:
        # TODO: Handle missing resolutions
        image_url = wpa.get_image_url(id, self.get_resolution())
        if not image_url:
            print("Wallpaper {} not found.".format(id))
            return

        print("Switching to wallpaper {}{}".format(
            (id), " (dry run)" if dry_run else ""))

        target_file = self.get_wallpaper_cache_path(id, image_url)
        if not os.path.exists(target_file):
            self.download_image(image_url, target_file)

        if not dry_run:
            # TODO: Detect desktop environment
            utils.set_wallpaper_gnome3(target_file)

            # Record the change in state file
            current = self.state.get("current", None)
            history = self.state.get("history", [])
            if current:
                self.state["history"] = [current] + history
            self.state["current"] = str(id)

    def get_current_scope_name(self) -> str:
        scope = self.config_get("scope").split("/", 1)
        return {
            "tag": "with tag '{param}'",
            "catalog": "from catalog '{param}'",
            "search": "in search results for '{param}'",
            "liked": "marked as liked.",
            "disliked": "marked as disliked.",
        }[scope[0]].format(
            param=(scope[1] if len(scope) >= 2 else None))

    def is_liked(self, wpid: wpa.WPID) -> bool:
        return wpid in self.state.get("liked", [])

    def is_disliked(self, wpid: wpa.WPID) -> bool:
        return wpid in self.state.get("disliked", [])

    def mark(self, wpid: wpa.WPID, set_name: str, val: bool=True) -> None:
        wpset: Set[wpa.WPID] = set(self.state.get(set_name, []))
        if val:
            wpset.add(wpid)
        elif not val and wpid in wpset:
            wpset.remove(wpid)
        self.state[set_name] = list(wpset)

    def cmd_next(self, args) -> None:
        # Increment counter
        counter = self.state.get("counter", 0)
        counter = counter + 1
        self.state["counter"] = counter

        wpids = self.get_wpids()
        if len(wpids) is 0:
            print("No wallpapers {} were found.".format(
                self.get_current_scope_name()))
            return
        # TODO: Maybe avoid selecting the same wp in a row if there are not too
        # many to choose from.
        newwpid = random.choice(wpids)
        self.switch_to_wallpaper(newwpid, dry_run=args.dry_run)

    def cmd_next_cron(self, args) -> None:
        # cron rules use this command instead of next. This is because some
        # extra variables need to be added to the environment.

        # Find a PID of a process running inside desktop session
        pidlist = [int(s.strip()) for s in subprocess.check_output(
            ["ps", "-o", "pid=", "U", str(os.getuid())]
        ).decode('ascii').splitlines() if s != '']

        # Look for a process that has DBUS_SESSION_BUS_ADDRESS env var set.
        KEY = "DBUS_SESSION_BUS_ADDRESS"
        dbus_address = ""
        for pid in pidlist:
            try:
                env = open('/proc/{}/environ'.format(pid)).read().split('\0')
            except (PermissionError, FileNotFoundError):
                continue
            values = [e[len(KEY) + 1:] for e in env if e.startswith(KEY)]
            if len(values) > 0:
                dbus_address = values[0]
                break

        print("Using dbus address: " + dbus_address)
        # Now, let's copy that value for ourselves.
        os.environ[KEY] = dbus_address
        # Continue as normal 'next'.
        self.cmd_next(args)

    def cmd_status(self, args) -> None:
        wpid = self.state.get("current", None)
        print("Current wallpaper: {}".format(wpid))
        if wpid is not None:
            if self.is_liked(wpid):
                print("You like this wallpaper.")
            elif self.is_disliked(wpid):
                print("You dislike this wallpaper.")

            wpdata = self.get_wpdata(wpid)
            if wpdata:
                # TODO: Check if this wallpaper matches system config.
                print("Tags: {}".format(', '.join(wpdata.tags)))
                print("Image URL: {}".format(
                    wpa.get_image_url(wpid, self.get_resolution())))

        wpids = self.get_wpids()
        print("Using images {}, {} wallpapers available.".format(
            self.get_current_scope_name(), len(wpids)))

        if self.state.get("auto", None):
            print("Automatically switching every {}.".format(
                self.state["auto"]))

    def cmd_update(self, args) -> None:
        idlist = self.get_wpids(clear_cache=True)

        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_use_tag(self, args) -> None:
        # TODO: Verify whether this tag exists
        self.config["scope"] = "tag/{}".format(args.tag.lower())

        idlist = self.get_wpids()
        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_use_catalog(self, args) -> None:
        # TODO: Verify whether this catalog exists
        self.config["scope"] = "catalog/{}".format(args.catalog.lower())

        idlist = self.get_wpids()
        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_use_search(self, args) -> None:
        self.config["scope"] = "search/{}".format(args.search.lower())

        idlist = self.get_wpids()
        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_use_liked(self, args) -> None:
        self.config["scope"] = "liked"

        idlist = self.get_wpids()
        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_use_disliked(self, args) -> None:
        self.config["scope"] = "disliked"

        idlist = self.get_wpids()
        print("Found {} wallpapers {}".format(
            len(idlist), self.get_current_scope_name()))

    def cmd_wallpaper(self, args) -> None:
        self.switch_to_wallpaper(args.wallpaper)

    def cmd_show_liked(self, args) -> None:
        liked = self.state.get("liked", [])
        if len(liked) is 0:
            print("No liked wallpapers")
        else:
            print("\n".join(liked))

    def cmd_show_disliked(self, args) -> None:
        disliked = self.state.get("disliked", [])
        if len(disliked) is 0:
            print("No disliked wallpapers")
        else:
            print("\n".join(disliked))

    def cmd_like(self, args) -> None:
        wpid = self.state.get("current", None)

        if self.is_liked(wpid):
            print("Current wallpaper is already marked as liked.")
            return

        self.mark(wpid, "disliked", False)
        self.mark(wpid, "liked", True)

        # TODO: Vote on wallpaperscraft
        # TODO: Update tag opinions
        print("Marked current wallpaper as liked.")

    def cmd_dislike(self, args) -> None:
        wpid = self.state.get("current", None)

        if self.is_disliked(wpid):
            print("Wallpaper is already marked as disliked.")
            return

        self.mark(wpid, "liked", False)
        self.mark(wpid, "disliked", True)

        # TODO: Vote on wallpaperscraft
        # TODO: Update tag opinions
        print("Marked current wallpaper as disliked.")

        print("Use '{} next' to switch to a different wallpaper.".format(
            args.program))

    def cmd_unlike(self, args) -> None:
        wpid = self.state.get("current", None)
        self.mark(wpid, "liked", False)
        self.mark(wpid, "disliked", False)
        print("Removed like/dislake mark for current wallpaper.")

    def cmd_auto_disable(self, args) -> None:
        with user_crontab() as cron:
            cron.remove_all(comment=CRONTAB_COMMENT)
        self.state["auto"] = None

    # TODO: Do not rely on cron timing. Instead, save the "last-changed"
    # timestamp, and call cron every minute with a special command that
    # switches wallpaper only if now-timestamp>threshold.
    def cmd_auto_hours(self, args) -> None:
        with user_crontab() as cron:
            cron.remove_all(comment=CRONTAB_COMMENT)
            job = cron.new(command=CRON_COMMAND + " next_cron")
            job.set_comment(CRONTAB_COMMENT)
            job.env["DISPLAY"] = os.getenv("DISPLAY")
            job.every(args.hours).hours()
        self.state["auto"] = "{} hours".format(args.hours)

    def cmd_auto_minutes(self, args) -> None:
        with user_crontab() as cron:
            cron.remove_all(comment=CRONTAB_COMMENT)
            job = cron.new(command=CRON_COMMAND + " next_cron")
            job.set_comment(CRONTAB_COMMENT)
            job.env["DISPLAY"] = os.getenv("DISPLAY")
            job.every(args.minutes).minutes()
        self.state["auto"] = "{} minutes".format(args.minutes)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="wpcraft",
        description="Browse wallpapercraft images from command-line.")
    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    parser.add_argument('--dry-run', '-n', action="store_true",
                        help="Never change current wallpaper.")

    parser_status = subparsers.add_parser(
        'status', help="Display information about the current wallpaper.")
    parser_status.set_defaults(func=WPCraft.cmd_status)

    parser_next = subparsers.add_parser(
        'next', help="Switch to the next wallpaper.")
    parser_next.set_defaults(func=WPCraft.cmd_next)
    parser_next_cron = subparsers.add_parser(
        'next_cron', help=argparse.SUPPRESS)
    parser_next_cron.set_defaults(func=WPCraft.cmd_next_cron)

    parser_update = subparsers.add_parser(
        'update', help="Refresh the list of available wallpapers.")
    parser_update.set_defaults(func=WPCraft.cmd_update)

    parser_use = subparsers.add_parser(
        'use', help="Selects which wallpapers to use.")
    use_subparsers = parser_use.add_subparsers(dest='use')
    use_subparsers.required = True

    parser_use_tag = use_subparsers.add_parser(
        'tag', help="Wallpaper tag to choose from.")
    parser_use_tag.set_defaults(func=WPCraft.cmd_use_tag)
    parser_use_tag.add_argument('tag', type=str)

    parser_use_catalog = use_subparsers.add_parser(
        'catalog', help="Wallpaper catalog to choose from.")
    parser_use_catalog.set_defaults(func=WPCraft.cmd_use_catalog)
    parser_use_catalog.add_argument('catalog', type=str)

    parser_use_search = use_subparsers.add_parser(
        'search', help="Search query to pick wallpapers from.")
    parser_use_search.set_defaults(func=WPCraft.cmd_use_search)
    parser_use_search.add_argument('search', type=str)

    parser_use_liked = use_subparsers.add_parser(
        'liked', help="Use wallpapers marked as 'liked'.")
    parser_use_liked.set_defaults(func=WPCraft.cmd_use_liked)

    parser_use_disliked = use_subparsers.add_parser(
        'disliked', help="Use wallpapers marked as 'disliked'.")
    parser_use_disliked.set_defaults(func=WPCraft.cmd_use_disliked)

    parser_wallpaper = subparsers.add_parser(
        'wallpaper', aliases=['wp'],
        help="Immediately set a wallpaper with the ID.")
    parser_wallpaper.set_defaults(func=WPCraft.cmd_wallpaper)
    parser_wallpaper.add_argument('wallpaper', type=str)

    parser_like = subparsers.add_parser(
        'like', help="Mark the wallpaper as liked.")
    parser_like.set_defaults(func=WPCraft.cmd_like)

    parser_dislike = subparsers.add_parser(
        'dislike', help="Mark the wallpaper as disliked.")
    parser_dislike.set_defaults(func=WPCraft.cmd_dislike)

    parser_unlike = subparsers.add_parser(
        'unlike', help="Unmark the wallpaper as liked or unliked.")
    parser_unlike.set_defaults(func=WPCraft.cmd_unlike)

    parser_show = subparsers.add_parser(
        'show', help="Displays liked/disliked wallpapers and tag statistics")
    show_subparsers = parser_show.add_subparsers(dest='show')
    show_subparsers.required = True

    parser_show_liked = show_subparsers.add_parser(
        'liked', help="Show the list of liked wallpapers.")
    parser_show_liked.set_defaults(func=WPCraft.cmd_show_liked)

    parser_show_disliked = show_subparsers.add_parser(
        'disliked', help="Show the list of liked wallpapers.")
    parser_show_disliked.set_defaults(func=WPCraft.cmd_show_disliked)

    parser_auto = subparsers.add_parser(
        'auto', help="Automatically switch wallpapers every X hours/minutes.")
    auto_subparsers = parser_auto.add_subparsers(dest='auto')
    auto_subparsers.required = True

    parser_auto_disable = auto_subparsers.add_parser(
        'disable', help="Disable automatic wallpaper switching.")
    parser_auto_disable.set_defaults(func=WPCraft.cmd_auto_disable)

    parser_auto_hours = auto_subparsers.add_parser(
        'hours', help="Automatically switch to next wallpaper every N hours.")
    parser_auto_hours.set_defaults(func=WPCraft.cmd_auto_hours)
    parser_auto_hours.add_argument('hours', metavar='N', type=int)

    parser_auto_minutes = auto_subparsers.add_parser(
        'minutes',
        help="Automatically switch to next wallpaper every N minutes.")
    parser_auto_minutes.set_defaults(func=WPCraft.cmd_auto_minutes)
    parser_auto_minutes.add_argument('minutes', metavar='N', type=int)

    args = parser.parse_args()
    args.program = sys.argv[0]

    wpcraft = WPCraft(CONFIG_FILE_PATH)

    args.func(wpcraft, args)

    wpcraft.save()


if __name__ == "__main__":
    main()
