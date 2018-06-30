import time
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from typing import List, Optional

from wpcraft.types import WPScope, WPData, WPID, Resolution

BASE_URL = "https://wallpaperscraft.com"

s = requests.Session()


def get_scope_url(scope: WPScope,
                  resolution: Resolution,
                  page_n: Optional[int]=None) -> str:
    t, v = scope.split('/', 1)
    if t in ['tag', 'catalog']:
        url = BASE_URL + "/{}/{}/{}x{}".format(
            t, v, resolution.w, resolution.h)
        if page_n:
            url += '/page{}'.format(page_n + 1)
        return url
    elif t in ['search']:
        url = BASE_URL + "/search/?query={}&size={}x{}".format(
            v, resolution.w, resolution.h)
        if page_n:
            url += "&page={}".format(page_n + 1)
        return url
    exit("Error: Invalid wallpaper scope '{}'".format(scope))


def get_wpids(scope: WPScope,
              resolution: Resolution) -> List[WPID]:
    N = get_npages(scope, resolution)

    def gather_results_from_page_n(n: int) -> List[WPID]:
        page_url = get_scope_url(scope, resolution, n)
        page = s.get(page_url)
        if page.status_code is not 200:
            return []

        soup = BeautifulSoup(page.content, 'html.parser')
        wallpapers = soup.find_all('div', class_='wallpapers')
        if len(wallpapers) == 0:  # graceful 404
            return []
        wallpapers = wallpapers[0].find_all('li', class_='wallpapers__item')

        result = []
        for w in wallpapers:
            href = w.find_all('a')[0]['href']
            identifier = href.split('/')[-2]
            result.append(identifier)
        return result

    with concurrent.futures.ThreadPoolExecutor(50) as executor:
        futures = [executor.submit(gather_results_from_page_n, i)
                   for i in range(N)]

        # Wait for all requests to finish
        finished = 0
        msg = "\rGathering wallpaper list for '%s': {:.0f}%%..." % scope
        while finished < N:
            finished = sum(f.done() for f in futures)
            print(msg.format(100.0*finished/N), end='')
            time.sleep(0.1)
        print(msg.format(100))

    # Gather results
    result = sum((f.result() for f in futures), [])

    # Remove duplicates
    result = list(set(result))

    return result


def get_wpdata(wpid: WPID) -> Optional[WPData]:
    wallpaper_page_url = BASE_URL + "/wallpaper/{}".format(wpid)
    page = s.get(wallpaper_page_url)
    if page.status_code is not 200:
        return None

    soup = BeautifulSoup(page.content, 'html.parser')
    div_tags = soup.find_all('div', class_='wallpaper__tags')
    tags: List[str]
    if len(div_tags) == 0:
        tags = []
    else:
        a_tags = div_tags[0].find_all('a')
        tags = [a.get_text().replace('wallpapers', '').
                replace('backgrounds', '').strip()
                for a in a_tags]

    # TODO: Also pull tags from wallpaper title

    return WPData(wpid, tags)


def get_npages(scope: WPScope, resolution: Resolution) -> int:
    page_url = get_scope_url(scope, resolution)
    page = s.get(page_url)
    if page.status_code is not 200:
        return 0

    soup = BeautifulSoup(page.content, 'html.parser')
    pages_ul = soup.find_all('ul', class_='pager__list')
    if len(pages_ul) == 0:
        return 1

    page_a = pages_ul[0].find_all('a', class_='pager__link')
    if len(page_a) == 0:
        return 1

    lastpage_href = page_a[-1]['href']
    if 'page=' in lastpage_href:
        # Search results
        get_args = (lastpage_href.split('/')[-1])[1:].split('&')
        page_arg = [a[len('page='):]
                    for a in get_args
                    if a.startswith('page=')][0]
        return int(page_arg)
    else:
        # Browsing catalog/tag
        return int(lastpage_href.split('/')[-1][4:])


def get_image_url(id: WPID, resolution: Resolution) -> Optional[str]:
    download_page_url = "https://wallpaperscraft.com/download/{}/{}x{}".format(
        id, resolution.w, resolution.h)
    page = s.get(download_page_url)
    if page.status_code is not 200:
        return None

    soup = BeautifulSoup(page.content, 'html.parser')
    imgs = soup.find_all('img', class_='wallpaper__image')
    if len(imgs) is 0:
        return None
    src = imgs[0]['src']
    return "https://wallpaperscraft.com/image/{}".format(src.split('/')[-1])
