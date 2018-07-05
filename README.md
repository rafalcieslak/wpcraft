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

Configure `wpcraft` to only use wallpapers with user score at least 7.5:

```
$ wpcraft min_score 7.5
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

Show your favorite tags (based on your likes/dislikes):

```
$ wpcraft show tags
You seem to like these tags:
city: 21
skyscrapers: 17
building: 12
night: 10
sky: 10
buildings: 9
bridge: 8
new york: 8
top view: 7
usa: 6
chicago: 5
river: 5
clouds: 4
hdr: 4
lights: 4
metropolis: 4
```

Set a specific wallpaper by ID:

```
$ wpcraft wallpaper architecture_city_view_from_above_buildings_river_118446
```

Display wallpaper history:

```
$ wpcraft show history
```


Go back to the previous wallpaper:

```
$ wpcraft prev
```


Configure `wpcraft` to automatically switch to "next" wallpaper every 5 minutes / every 12 hours / every 7 days (`wpcraft` uses cron):

```
$ wpcraft auto minutes 5
$ wpcraft auto hours 12
$ wpcraft auto days 7
```

Stop automatically switching wallpapers:

```
$ wpcraft auto disable
```

Force redownload wallpaper index (there is no need to do use this command manually):

```
$ wpcraft update
```
