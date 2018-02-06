wpcraft
===

This tool automatically downloads images from https://wallpaperscraft.com/ . The user can choose an image catalog or tag, and `wpcraft` will randomly pick images that match these settings, download the image in the right resolution, and set their desktop wallpaper to the new image.

Wallpapers can be marked as "liked", you can instruct `wpcraft` to only pick wallpapers from the "liked" set.

You can also configure `wpcraft` to automatically switch wallpapers e.g. every 6 hours.

Created 2017-2018 by Rafał Cieślak and published under the terms of the GNU General Public License version 3, see full text in LICENSE.txt.

Installation
===

```
sudo pip3 install wpcraft
```

Usage
===

Switch to another randomly selected wallpaper:

```
$ wpcraft next
```

Display detailed information about current wallpaper:

```
$ wpcraft status
Current wallpaper: night_city_top_view_buildings_clouds_118603
You like this wallpaper.
Tags: night city, top view, buildings, clouds
Image URL: https://wallpaperscraft.com/image/night_city_top_view_buildings_clouds_118603_1920x1080.jpg
Using images from catalog 'city', 3638 wallpapers available.
Automatically switching every 12 hours.
```

Configure `wpcraft` to pick wallpapers from "nature" collection:

```
$ wpcraft use catalog nature
Found 9706 wallpapers from catalog 'nature'.
```

Configure `wpcraft` to choose wallpapers by their tag:

```
$ wpcraft use tag "hong kong"
Found 15 wallpapers with tag 'hong kong'.
```

Configure `wpcraft` to use search results for choosing wallpapers:

```
$ wpcraft use search ferrari
Found 169 wallpapers in search results for 'ferrari'
```

Mark a wallpaper as liked or disliked:

```
$ wpcraft like
$ wpcraft dislike
```

Unmark a liked or disliked wallpaper:

```
$ wpcraft unlike
```

Configure `wpcraft` to pick wallpapers marked as "liked":

```
$ wpcraft use liked
```

Show liked/disliked wallpapers:

```
$ wpcraft show liked
$ wpcraft show disliked
```

Set a specific wallpaper by ID:

```
$ wpcraft wallpaper architecture_city_view_from_above_buildings_river_118446
```

Configure `wpcraft` to automatically switch to "next" wallpaper every 5 minutes / every 12 hours (`wpcraft` uses cron):

```
$ wpcraft auto minutes 5
$ wpcraft auto hours 12
```

Stop automatically switching wallpapers:

```
$ wpcraft auto disable
```

Force redownload wallpaper index (there is no need to do use this command manually):

```
$ wpcraft update
```
