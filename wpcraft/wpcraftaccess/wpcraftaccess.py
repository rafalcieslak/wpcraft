import time
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from typing import NewType, NamedTuple, List, Optional

BASE_URL = "https://wallpaperscraft.com"

s = requests.Session()

WPScope = NewType('WPScope', str)
WPID = NewType('WPID', str)


class WPData(NamedTuple):
    id: WPID
    tags: List[str]


def get_scope_url(scope: WPScope) -> str:
    t, v = scope.split('/', 1)
    if t in ['tag', 'catalog']:
        return BASE_URL + "/" + t + "/" + v
    elif t in ['search']:
        return BASE_URL + "/search/keywords?q=" + v
    exit("Error: Invalid wallpaper scope '{}'".format(scope))


def get_wpids(scope: WPScope) -> List[WPID]:
    N = get_npages(scope)

    def gather_results_from_page_n(n: int) -> List[WPID]:
        page_url = get_scope_url(scope)
        if n > 0:
            page_url += "/page{}".format(n+1)
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
            identifier = href.split('/')[-1]
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


def get_npages(scope: WPScope) -> int:
    page_url = get_scope_url(scope)
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

    return int(page_a[-1]['href'].split('/')[-1][4:])


# TODO: Maybe resolution deserves its own type
def get_image_url(id: WPID, resolution: str) -> Optional[str]:
    download_page_url = "https://wallpaperscraft.com/download/{}/{}".format(
        id, resolution)
    page = s.get(download_page_url)
    if page.status_code is not 200:
        return None

    soup = BeautifulSoup(page.content, 'html.parser')
    imgs = soup.find_all('img', class_='wallpaper__image')
    if len(imgs) is 0:
        return None
    src = imgs[0]['src']
    return "https://wallpaperscraft.com/image/{}".format(src.split('/')[-1])
