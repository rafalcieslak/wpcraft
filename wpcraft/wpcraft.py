#!/usr/bin/env python3

import os
import sys
import json
import time
import shutil
import random
import requests
import datetime
import argparse
import subprocess
from contextlib import contextmanager
from typing import Dict, Any, Optional, List, Set

from crontab import CronTab

from wpcraft.wpcraftaccess import wpcraftaccess as wpa
from wpcraft.utils import utils
from wpcraft.types import WPScope, WPID, WPData, Resolution

CONFIG_FILE_PATH = (os.getenv("WPCRAFT_CONFIG") or
                    "~/.local/share/wpcraft/config.json")

# TODO: These dictionaries could be TypedDicts instead.
DEFAULT_CONFIG: Dict[str, Any] = {
    "state-path": "~/.local/share/wpcraft/state.json",
    "preferences-path": "~/.local/share/wpcraft/preferences.json",
    "cache-dir": "~/.cache/wpcraft",
    "scope": "catalog/city",
    "resolution": "default",
    "history-size": 20,
    "min-score": 0.0
}
DEFAULT_STATE: Dict[str, Any] = {}
DEFAULT_PREFERENCES: Dict[str, Any] = {
    "liked": [],
    "disliked": []
}

SET_VOTES = {
    'liked': 1,
    'disliked': -1
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
            data = default.copy()

    yield data

    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    json.dump(data, open(fullpath, 'w'), indent=4)


@contextmanager
def user_crontab():
    cron = CronTab(user=True)
    yield cron
    cron.write_to_user(user=True)


class WPCraft:
    def __init__(self, config_path: str) -> None:
        self.config_path = os.path.expanduser(config_path)

        # Load config
        try:
            self.config = json.load(open(self.config_path, 'r'))
        except (FileNotFoundError, json.decoder.JSONDecodeError) as e:
            print("Config file is missing or corrupted, using default.")
            self.config = DEFAULT_CONFIG

        # Load state
        state_file_path = self.config_get_filesystem_path("state-path")
        try:
            self.state = json.load(open(state_file_path, 'r'))
        except (FileNotFoundError, json.decoder.JSONDecodeError) as e:
            print("State file is missing or corrupted, using default.")
            self.state = DEFAULT_STATE

        preferences_file_path = self.config_get_filesystem_path("preferences-path")
        try:
            self.preferences = json.load(open(preferences_file_path, 'r'))
        except (FileNotFoundError, json.decoder.JSONDecodeError) as e:
            print("Preferences file is missing or corrupted, using default.")
            self.preferences = DEFAULT_PREFERENCES

        # Initialize tag votes, if they are missing from the preferences file.
        if ('votes' not in self.preferences
           or self.preferences['votes'] is None):
            if (self.preferences.get("liked", [])
               or self.preferences.get("disliked", [])):
                print("Recomputing tag votes, please wait...")
                self.recompute_all_tags()

    def save(self) -> None:
        # If the state contains preferences, move them to the preferences
        # file. This is to support legacy configs where preferences were
        # stored in the state file.
        if 'liked' in self.state:
            self.preferences['liked'].extend(self.state['liked'])
            del self.state['liked']
        if 'disliked' in self.state:
            self.preferences['disliked'].extend(self.state['disliked'])
            del self.state['disliked']

        # Save state
        state_file = self.config_get_filesystem_path("state-path")
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        json.dump(self.state, open(state_file, 'w'), indent=4)

        # Save preferences
        preferences_file = self.config_get_filesystem_path("preferences-path")
        os.makedirs(os.path.dirname(preferences_file), exist_ok=True)
        json.dump(self.preferences, open(preferences_file, 'w'), indent=4,
                  sort_keys=True)

        # Save config
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        json.dump(self.config, open(self.config_path, 'w'), indent=4)

    def config_get(self, path: str):
        if path in self.config:
            return self.config[path]
        return DEFAULT_CONFIG[path]

    def config_get_filesystem_path(self, path: str):
        return os.path.abspath(os.path.expanduser(self.config_get(path)))

    def get_wpdata(self, id: WPID) -> Optional[WPData]:
        # TODO: Maybe cache wpdata, or is it unnecessary?
        return wpa.get_wpdata(id)

    def get_wpids(self, scope: WPScope=None,
                  clear_cache=False) -> List[WPID]:
        if scope is None:
            scope = WPScope(self.config_get("scope"))
        if scope == "liked":
            return self.preferences.get("liked", [])
        if scope == "disliked":
            return self.preferences.get("disliked", [])
        cache_dir = self.config_get_filesystem_path("cache-dir")
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, "by_scope", str(scope) + ".json")
        with data_in_json_file(path, {}) as data:
            if clear_cache:
                data.clear()
            if 'ids' in data:
                return data['ids']
            min_score = self.config_get('min-score')
            data['ids'] = wpa.get_wpids(
                scope, self.get_resolution(), min_score)
            return data['ids']

    def invalidate_scope_cache(self) -> None:
        cache_dir = self.config_get_filesystem_path("cache-dir")
        shutil.rmtree(os.path.join(cache_dir, "by_scope"))

    def get_resolution(self) -> Resolution:
        resolution = self.config_get("resolution")
        if resolution == "default":
            return utils.get_screen_resolution()
        w, h = resolution.split('x')[0:2]
        return Resolution(w, h)

    def get_wallpaper_cache_path(self, id: WPID, image_url: str) -> str:
        return "{}/{}.{}".format(
            self.config_get_filesystem_path("cache-dir"),
            id, image_url.split('.')[-1])

    def download_image(self, source, target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        s = requests.Session()
        image = s.get(source, stream=True)
        with open(target, 'wb') as out_file:
            shutil.copyfileobj(image.raw, out_file)

    def get_current(self) -> WPID:
        # TODO: Maybe we could avoid storing the wallpaper name in the
        # state file and fetch it from DE config instead?
        return self.state.get("current", None)

    # Returns true iff the wallpaper was actually changed
    def switch_to_wallpaper(self, id: WPID, dry_run: bool=False) -> bool:
        resolution = self.get_resolution()
        image_url = wpa.get_image_url(id, resolution)
        if not image_url:
            print("Wallpaper {} not found in requested resolution ({}x{}).".
                  format(id, resolution.w, resolution.h))
            return False

        print("Switching to wallpaper: {}{}".format(
            (id), " (dry run)" if dry_run else ""))

        target_file = self.get_wallpaper_cache_path(id, image_url)
        if not os.path.exists(target_file):
            self.download_image(image_url, target_file)

        if dry_run:
            return True  # Pretend the change was performed.

        # TODO: Detect desktop environment
        utils.set_wallpaper_gnome3(target_file)

        # Record the change in state file
        previous = self.get_current()
        history = self.state.get("history", [])
        if previous:
            history_size = self.config_get('history-size')
            self.state["history"] = ([previous] + history)[:history_size]
        self.state["current"] = str(id)
        self.state["current-url"] = image_url
        self.state["last-changed"] = time.time()

        return True

    def get_current_scope_name(self) -> str:
        scope = self.config_get("scope").split("/", 1)
        return {
            "tag": "with tag '{param}'",
            "catalog": "from catalog '{param}'",
            "search": "in search results for '{param}'",
            "liked": "marked as liked",
            "disliked": "marked as disliked",
        }[scope[0]].format(
            param=(scope[1] if len(scope) >= 2 else None))

    def is_liked(self, wpid: WPID) -> bool:
        return wpid in self.preferences.get("liked", [])

    def is_disliked(self, wpid: WPID) -> bool:
        return wpid in self.preferences.get("disliked", [])

    def mark(self, wpid: WPID, set_name: str, val: bool=True) -> None:
        wpset: Set[WPID] = set(self.preferences.get(set_name, []))
        if val and wpid not in wpset:
            wpset.add(wpid)
            # Update tag votes
            for t in self.get_tags(wpid):
                self.vote_tag(t, SET_VOTES.get(set_name, 0))
        elif not val and wpid in wpset:
            wpset.remove(wpid)
            # Update tag votes
            for t in self.get_tags(wpid):
                self.vote_tag(t, -1 * SET_VOTES.get(set_name, 0))
        self.preferences[set_name] = list(wpset)

    def get_tags(self, wpid: WPID) -> List[str]:
        wpdata = wpa.get_wpdata(wpid)
        return wpdata.tags if wpdata else []

    def vote_tag(self, tag: str, change: int) -> None:
        if change == 0:
            return
        v = self.preferences['votes'].get(tag, 0)
        self.preferences['votes'][tag] = v + change

    def recompute_all_tags(self):
        # This function disregards current tag votes and initializes them from
        # liked and disliked sets.
        self.preferences['votes'] = {}
        for wpid in self.preferences.get("liked", []):
            for t in self.get_tags(wpid):
                self.vote_tag(t, SET_VOTES['liked'])
        for wpid in self.preferences.get("disliked", []):
            for t in self.get_tags(wpid):
                self.vote_tag(t, SET_VOTES['disliked'])

    def show_details(self, wpid: WPID) -> None:
        wpdata = self.get_wpdata(wpid)
        if wpdata:
            # TODO: Check if this wallpaper matches system config.
            print("Tags: {}".format(', '.join(wpdata.tags)))

            if wpdata.score:
                print("User score: {}".format(wpdata.score))

            if wpdata.author:
                print("Author: {}".format(wpdata.author))
            if wpdata.license:
                print("License: {}".format(wpdata.license))
            if wpdata.source:
                print("Source link: {}".format(wpdata.source))

            print("Image URL: {}".format(
                self.state.get('current-url', "(unknown)")))

            if self.is_liked(wpid):
                print("You like this wallpaper.")
            elif self.is_disliked(wpid):
                print("You dislike this wallpaper.")

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
        changed = False
        while not changed:
            newwpid = random.choice(wpids)
            changed = self.switch_to_wallpaper(newwpid, dry_run=args.dry_run)

        current = self.get_current()
        self.show_details(current)

    def cmd_next_cron(self, args) -> None:
        # cron rules use this command instead of next. This is because some
        # extra variables need to be added to the environment.

        # Determine whether the time is right to switch the wallpaper.
        last_changed = datetime.datetime.utcfromtimestamp(
            int(self.state.get('last-changed', 0)))
        delta = datetime.datetime.utcnow() - last_changed

        if 'auto' not in self.state:
            return
        n, per = self.state['auto'].split(' ')
        n = int(n)
        if per == 'minutes':
            target_delta = datetime.timedelta(minutes=n)
        elif per == 'hours':
            target_delta = datetime.timedelta(hours=n)
        elif per == 'days':
            target_delta = datetime.timedelta(days=n)
        else:
            return

        print("Time since last switch: {}".format(delta))
        print("Configured time between automatic switches: {}".format(
            target_delta))

        # Account for the time it might have taken the last cron change to
        # download and set the wallpaper. Otherwise we would fall for
        # discretization error and switch wallpapers every n+1 minutes instead
        # of n.
        delta += datetime.timedelta(seconds=10)

        if delta < target_delta:
            print("Skipping, not enough time has elapsed since last switch.")
            return

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

    def cmd_prev(self, args) -> None:
        history = self.state.get("history", [])
        if len(history) is 0:
            print("No previous wallpaper")
            return
        prev = WPID(history[0])
        self.switch_to_wallpaper(prev, dry_run=args.dry_run)

    def cmd_status(self, args) -> None:
        wpid = self.get_current()
        print("Current wallpaper: {}".format(wpid))

        if wpid is not None:
            self.show_details(wpid)
            print("-"*32)

        wpids = self.get_wpids()
        scope = self.get_current_scope_name()
        print("Using images {}.".format(scope))

        filtered_scope = self.config_get("scope").split("/", 1)[0] in [
            'catalog', 'tag', 'search']
        min_score = self.config_get('min-score')
        if min_score and filtered_scope:
            print("Picking only wallpapers with user score at least {}".format(
                min_score))

        print("{} wallpapers match these criteria.".format(len(wpids)))

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
        self.show_details(self.get_current())

    def cmd_show_liked(self, args) -> None:
        liked = self.preferences.get("liked", [])
        if len(liked) is 0:
            print("No liked wallpapers")
        else:
            print("\n".join(liked))

    def cmd_show_disliked(self, args) -> None:
        disliked = self.preferences.get("disliked", [])
        if len(disliked) is 0:
            print("No disliked wallpapers")
        else:
            print("\n".join(disliked))

    def cmd_show_history(self, args) -> None:
        history = self.state.get("history", [])
        if len(history) is 0:
            print("History is empty")
        else:
            print("\n".join(history))

    def cmd_show_tags(self, args) -> None:
        TAGS_MAX = 15
        print("You seem to like these tags the most:")
        votes = self.preferences.get("votes", {})
        result = sorted(votes.items(), key=lambda q: -q[1])
        if len(result) is 0:
            print("No tag preferences to display, mark more wallpapers as "
                  "liked using `wpcraft like`.")
        if len(result) > TAGS_MAX:
            cutoff_v = result[TAGS_MAX][1]
            result = [(t, v) for t, v in result if v >= cutoff_v]

        print("\n".join("{}: {}".format(t, v) for t, v in result))

    def cmd_like(self, args) -> None:
        current = self.get_current()

        if self.is_liked(current):
            print("Current wallpaper is already marked as liked.")
            return

        self.mark(current, "disliked", False)
        self.mark(current, "liked", True)

        print("Marked current wallpaper as liked.")
        wpa.vote(current, up=True)

    def cmd_dislike(self, args) -> None:
        current = self.get_current()

        if self.is_disliked(current):
            print("Wallpaper is already marked as disliked.")
            return

        self.mark(current, "liked", False)
        self.mark(current, "disliked", True)

        print("Marked current wallpaper as disliked.")
        wpa.vote(current, up=False)

        print("Use '{} next' to switch to a different wallpaper.".format(
            args.program))

    def cmd_unlike(self, args) -> None:
        wpid = self.get_current()
        self.mark(wpid, "liked", False)
        self.mark(wpid, "disliked", False)
        print("Removed like/dislike mark for current wallpaper.")

    def cmd_auto_disable(self, args) -> None:
        with user_crontab() as cron:
            cron.remove_all(comment=CRONTAB_COMMENT)
        self.state["auto"] = None

    def cron_enable(self) -> None:
        with user_crontab() as cron:
            cron.remove_all(comment=CRONTAB_COMMENT)
            job = cron.new(command=CRON_COMMAND + " next_cron")
            job.set_comment(CRONTAB_COMMENT)
            job.env["DISPLAY"] = os.getenv("DISPLAY")
            job.every(1).minutes()

    def cmd_auto_minutes(self, args) -> None:
        self.state["auto"] = "{} minutes".format(args.minutes)
        self.cron_enable()

    def cmd_auto_hours(self, args) -> None:
        self.state["auto"] = "{} hours".format(args.hours)
        self.cron_enable()

    def cmd_auto_days(self, args) -> None:
        self.state["auto"] = "{} days".format(args.days)
        self.cron_enable()

    def cmd_min_score(self, args) -> None:
        self.config['min-score'] = args.min_score
        self.invalidate_scope_cache()
        self.cmd_update(args)

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
        'next_cron')
    parser_next_cron.set_defaults(func=WPCraft.cmd_next_cron)

    parser_prev = subparsers.add_parser(
        'prev', help="Go back to the previous wallpaper.")
    parser_prev.set_defaults(func=WPCraft.cmd_prev)

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

    parser_show_history = show_subparsers.add_parser(
        'history', help="Show the history of previously used wallpapers.")
    parser_show_history.set_defaults(func=WPCraft.cmd_show_history)

    parser_show_tags = show_subparsers.add_parser(
        'tags', help="Show summary of tags you liked with `wpcraft like`.")
    parser_show_tags.set_defaults(func=WPCraft.cmd_show_tags)

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

    parser_auto_days = auto_subparsers.add_parser(
        'days', help="Automatically switch to next wallpaper every N days.")
    parser_auto_days.set_defaults(func=WPCraft.cmd_auto_days)
    parser_auto_days.add_argument('days', metavar='N', type=int)

    parser_min_score = subparsers.add_parser(
        'min_score', help="Ignore wallpapers with user score lower than X. "
        "This helps in filtering out low-quality images. "
        "Set to '0' (default) to disable filtering.")
    parser_min_score.add_argument('min_score', metavar='X', type=float)
    parser_min_score.set_defaults(func=WPCraft.cmd_min_score)

    args = parser.parse_args()
    args.program = sys.argv[0]

    wpcraft = WPCraft(CONFIG_FILE_PATH)

    args.func(wpcraft, args)

    wpcraft.save()


if __name__ == "__main__":
    main()
