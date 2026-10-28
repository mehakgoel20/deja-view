"""Stage 2: fetch each candidate blog article and extract an entry."""
import json
import os
import re
import html
import hashlib
import subprocess
import concurrent.futures as cf
from collections import Counter

from extract3 import build, cat_of
from polish import validate

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
CACHE = 'raw/blogpages'
MONTHS = ('january|february|march|april|may|june|july|august|september|'
          'october|november|december')
MO = {m: i + 1 for i, m in enumerate(MONTHS.split('|'))}
SEV_CRIT = re.compile(
    r'\b(?:global|complete|total|worldwide)\b.{0,30}\b(?:outage|unavailab)|'
    r'data loss|permanently lost|all (?:customers|users|regions)', re.I)
SEV_HIGH = re.compile(r'\boutage\b|\bunavailable\b|could not|unable to', re.I)


def totext(h):
    h = re.sub(r'(?is)<(script|style|nav|header|footer|svg|noscript|aside|form)'
               r'[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<!--.*?-->', ' ', h)
    h = re.sub(r'(?i)</(p|div|li|h[1-6]|br)\s*/?>', '\n', h)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = html.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()


def date_from(url, text):
    m = re.search(r'/(20\d\d)/(\d{1,2})/(\d{1,2})/', url)
    if m:
        return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = re.search(r'/(20\d\d)/(\d{1,2})/', url)
    if m:
        return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}'
    m = re.search(rf'\b({MONTHS})\s+(\d{{1,2}}),?\s+(20\d\d)\b', text[:4000], re.I)
    if m:
        return (f'{int(m.group(3)):04d}-{MO[m.group(1).lower()]:02d}-'
                f'{int(m.group(2)):02d}')
    m = re.search(rf'\b(\d{{1,2}})\s+({MONTHS})\s+(20\d\d)\b', text[:4000], re.I)
    if m:
        return (f'{int(m.group(3)):04d}-{MO[m.group(2).lower()]:02d}-'
                f'{int(m.group(1)):02d}')
    m = re.search(r'\b(20[0-2]\d)\b', url) or re.search(r'\b(20[0-2]\d)\b', text[:2000])
    return m.group(1) if m else ''


def title_of(page):
    m = re.search(r'(?is)<title>(.*?)</title>', page)
    if not m:
        return ''
    t = html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))
    t = re.sub(r'\s*[|–—-]\s*[^|]{0,40}$', '', t.strip())
    return re.sub(r'\s+', ' ', t).strip()


def main():
    os.makedirs(CACHE, exist_ok=True)
    cands = json.load(open('raw/blog_candidates.json'))
    base = json.load(open('clean_base.json'))
    have = {x['source_url'].rstrip('/') for x in base}

    def grab(item):
        url, (org, anchor) = item
        key = hashlib.md5(url.encode()).hexdigest()[:16]
        p = f'{CACHE}/{key}.html'
        if os.path.exists(p) and os.path.getsize(p) > 2000:
            return url, org, anchor, open(p, errors='ignore').read()
        try:
            r = subprocess.run(['curl', '-sL', '--max-time', '35',
                                '--connect-timeout', '10', '-A', UA, url],
                               capture_output=True, text=True, timeout=55,
                               errors='ignore')
            page = r.stdout or ''
        except Exception:
            page = ''
        if len(page) > 2000:
            open(p, 'w').write(page[:400000])
        return url, org, anchor, page

    out, stats = [], Counter()
    with cf.ThreadPoolExecutor(16) as ex:
        results = list(ex.map(grab, list(cands.items())))

    for url, org, anchor, page in results:
        if url.rstrip('/') in have:
            stats['already_have'] += 1
            continue
        if len(page) < 2000:
            stats['fetch_thin'] += 1
            continue
        text = totext(page)
        if len(text) < 800:
            stats['text_thin'] += 1
            continue
        name = title_of(page) or anchor
        date = date_from(url, text)
        built, why = build(text[:40000], org, date, url, name[:160], None)
        if not built and why == 'no_solution':
            built, why = build(text[:40000], org, date, url, name[:160], None,
                               require_fix=False)
            if built:
                stats['recovered_cause_only'] += 1
        if not built:
            stats['build:' + why] += 1
            continue
        head = text[:8000]
        built['severity'] = ('Critical' if SEV_CRIT.search(head)
                             else 'High' if SEV_HIGH.search(head) else 'Medium')
        built['category'] = cat_of(text[:15000])
        built['provenance'] = 'engineering_blog_postmortem'
        e, why = validate(built)
        if not e:
            stats['polish:' + why] += 1
            continue
        out.append(e)

    json.dump(out, open('raw/extracted_blogs.json', 'w'), indent=1)
    print('candidates:', len(cands), '| extracted:', len(out))
    print('rejections:', dict(stats))
    print('orgs:', Counter(e['org'] for e in out).most_common(15))
    print('categories:', Counter(e['category'] for e in out).most_common())


if __name__ == '__main__':
    main()
