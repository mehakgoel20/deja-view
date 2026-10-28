"""Stage 1: discover incident write-up URLs from engineering-blog indexes.

Fetches each seed index, keeps same-site links whose URL or anchor text looks
like an incident write-up, and saves the candidate list. Stage 2
(extract_blogs.py) fetches and extracts from each article.
"""
import json
import re
import subprocess
import concurrent.futures as cf
import html
from collections import Counter
from urllib.parse import urljoin, urlparse

from blogs_seed import SEEDS

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# URL or anchor text that suggests an incident write-up
INC = re.compile(
    r'outage|post-?mortem|postmortem|incident|\brca\b|root-?cause|downtime|'
    r'degradation|degraded|availability-report|retrospective|'
    r'what-happened|service-disruption|disruption|'
    r'lessons-from|we-broke|went-down|was-down|failure', re.I)
# obvious non-articles
SKIP = re.compile(
    r'/(tag|tags|category|categories|author|authors|page|search|feed|rss|'
    r'subscribe|login|signin|pricing|careers|jobs|contact|legal|privacy|'
    r'terms|cookie|sitemap)(/|$|\?)|\.(png|jpe?g|gif|svg|webp|pdf|zip|css|js)$|'
    r'^mailto:|^tel:|#', re.I)


def fetch(url, timeout=30):
    try:
        r = subprocess.run(['curl', '-sL', '--max-time', str(timeout),
                            '--connect-timeout', '10', '-A', UA, url],
                           capture_output=True, text=True,
                           timeout=timeout + 15, errors='ignore')
        return r.stdout or ''
    except Exception:
        return ''


def links_from(page, base):
    """(absolute_url, anchor_text) for every same-site link on the page."""
    out = []
    host = urlparse(base).netloc
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         page, re.S | re.I):
        href, text = m.group(1), m.group(2)
        text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
        text = re.sub(r'\s+', ' ', text).strip()
        absu = urljoin(base, href)
        p = urlparse(absu)
        if p.scheme not in ('http', 'https'):
            continue
        # medium.com/<pub> and similar shared hosts: keep the publication path
        if p.netloc != host:
            continue
        out.append((absu.split('#')[0], text))
    return out


def main():
    found = {}          # url -> (org, anchor text)
    stats = Counter()

    def one(seed):
        org, idx = seed
        page = fetch(idx)
        if len(page) < 2000:
            return org, idx, []
        hits = []
        for u, t in links_from(page, idx):
            if SKIP.search(urlparse(u).path or '/'):
                continue
            if not (INC.search(u) or INC.search(t)):
                continue
            if len(urlparse(u).path.strip('/')) < 8:
                continue
            hits.append((u, t))
        return org, idx, hits

    with cf.ThreadPoolExecutor(24) as ex:
        for org, idx, hits in ex.map(one, SEEDS):
            stats['index_ok' if hits else 'index_empty'] += 1
            for u, t in hits:
                if u not in found:
                    found[u] = (org, t[:160])

    json.dump({u: v for u, v in found.items()},
              open('raw/blog_candidates.json', 'w'), indent=1)
    print('seed indexes:', len(SEEDS), dict(stats))
    print('candidate article urls:', len(found))
    by_org = Counter(v[0] for v in found.values())
    for o, n in by_org.most_common(30):
        print(f'  {n:>4} {o}')


if __name__ == '__main__':
    main()
