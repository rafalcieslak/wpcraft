import time
import requests
import threading
import collections
import concurrent.futures
from bs4 import BeautifulSoup
from typing import List, Optional

from wpcraft.types import WPScope, WPData, WPID, Resolution

BASE_URL = "https://wallpaperscraft.com"
REQ_PER_SECOND_LIMIT = 0.2

s = requests.Session()


class RateLimiter(collections.Iterator):
    """Iterator that yields a value at most once every 'interval' seconds."""
    def __init__(self, interval):
        self.lock = threading.Lock()
        self.interval = interval
        self.next_yield = 0

    def __next__(self):
        with self.lock:
            t = time.monotonic()
            if t < self.next_yield:
                time.sleep(self.next_yield - t)
                t = time.monotonic()
            self.next_yield = t + self.interval


wallpaperscraft_rate_limit = RateLimiter(REQ_PER_SECOND_LIMIT)


def throttled_get(*args):
    next(wallpaperscraft_rate_limit)
    return s.get(*args)


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
              resolution: Resolution,
              min_score: Optional[float]=None) -> List[WPID]:
    N = get_npages(scope, resolution)

    def gather_results_from_page_n(n: int) -> List[WPID]:
        page_url = get_scope_url(scope, resolution, n)
        page = throttled_get(page_url)
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
            score_s = w.find_all('span', class_="wallpapers__info-rating")[0]
            score_t = score_s.text.strip()
            score = float(score_t or 0)
            if not min_score or (score >= min_score):
                result.append(identifier)
        return result

    with concurrent.futures.ThreadPoolExecutor(50) as executor:
        futures = [executor.submit(gather_results_from_page_n, i)
                   for i in range(N)]

        # Wait for all requests to finish
        finished = 0
        score_msg = (" (min_score: {})".format(min_score)
                     if min_score else "")
        msg = "\rGathering wallpaper list for '{}'{}: ".format(
            scope, score_msg)
        while finished < N:
            finished = sum(f.done() for f in futures)
            print((msg + "{:.0f}%...").format(100.0*finished/N), end='')
            time.sleep(0.1)
        print(msg.format(100))

    # Gather results
    result = sum((f.result() for f in futures), [])

    # Remove duplicates
    result = list(set(result))

    return result


def get_wpdata(wpid: WPID) -> Optional[WPData]:
    wallpaper_page_url = BASE_URL + "/wallpaper/{}".format(wpid)
    page = throttled_get(wallpaper_page_url)
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

    author = license_ = source = None
    div_authors = soup.find_all('div', class_='author__block')
    if div_authors:
        div_authors = div_authors[0]
        arows = div_authors.find_all('div', class_="author__row")
        for row in arows:
            text = row.text.strip()
            if text.startswith('Author: '):
                author = text[8:].strip()
            if text.startswith('License: '):
                license_ = text[9:].strip()
        sources = soup.find_all('a', class_="author__link")
        if sources:
            source = sources[0]['href']

    if license_ and (license_.startswith("No licence") or
                     license_.startswith("No license")):
        license_ = None

    score = 0.0
    span_scores = soup.find_all('span', {
        'class': lambda x: x and x.startswith('wallpaper-votes__rate')})
    if span_scores:
        if span_scores[0].text:
            score = float(span_scores[0].text)

    return WPData(wpid, tags, score, author, license_, source)


def get_npages(scope: WPScope, resolution: Resolution) -> int:
    page_url = get_scope_url(scope, resolution)
    page = throttled_get(page_url)
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
    page = throttled_get(download_page_url)
    if page.status_code is not 200:
        return None

    soup = BeautifulSoup(page.content, 'html.parser')
    imgs = soup.find_all('img', class_='wallpaper__image')
    if len(imgs) is 0:
        return None
    src = imgs[0]['src']
    return "https://wallpaperscraft.com/image/{}".format(src.split('/')[-1])


# If @up is true, you're voting UP. Otherwise you are voting DOWN.
def vote(id: WPID, up: bool) -> None:
    id_n = id.split('_')[-1]
    vote_url = "https://wallpaperscraft.com/ajax/votes/vote.json?image_id={}"

    data = b"vote=yes" if up else b"vote=no"

    res = s.post(vote_url.format(id_n), data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    })

    if res.status_code is not 200:
        # print("Failed to share your vote with wallpaperscraft.com")
        pass  # Errors here do not matter much.
