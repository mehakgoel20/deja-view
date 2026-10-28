"""Probe the Wayback/Common-Crawl enumerated statuspage.io hostnames.

Wayback's CDX index (matchType=domain) returns every statuspage.io URL it has
ever archived, which yields ~31,700 distinct hostnames - 20x what company-name
guessing found, because Statuspage assigns random subdomain ids.

Writes raw/statuspage_scale<N>_raw.json in the same shape as the other
harvests, skipping hosts already known and dropping SEO-spam pages.
"""
import json
import os
import re
import subprocess
import sys
import glob
import concurrent.futures as cf

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# pirated-media / casino pages abuse free Statuspage accounts: real hosts, but
# their "incidents" are spam text, never real incidents
SPAM = re.compile(
    r'regarder|streaming|vostfr|\bfilm[se]?\b|\bmovie\b|watch online|ganzer|'
    r'pelicula|película|完整版|พากย์|เต็มเรื่อง|online schauen|putlocker|'
    r'123movies|full movie|sub indo|dublado|ver online|cuevana|'
    r'slot|casino|togel|judi|bokep|xnxx|porn|escort|'
    r'crack|keygen|serial key|free download|mod apk|'
    r'\bnonton\b|\bsemua\b|\bterbaru\b', re.I)


def known_hosts():
    seen = set()
    for f in glob.glob('raw/statuspage*_raw.json'):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        seen |= set(d.keys())
    return seen


def probe(h):
    try:
        r = subprocess.run(
            ['curl', '-sL', '--max-time', '14', '--connect-timeout', '5',
             '-A', UA, f'https://{h}/api/v2/incidents.json'],
            capture_output=True, text=True, timeout=24, errors='ignore')
        s = r.stdout.strip()
        if not s.startswith('{'):
            return h, None, 'no-json'
        j = json.loads(s)
        incs = j.get('incidents') or []
        if not incs:
            return h, None, 'no-incidents'
        org = (j.get('page') or {}).get('name') or h
        if SPAM.search(org):
            return h, None, 'spam'
        return h, {'org': org, 'raw': j}, 'ok'
    except Exception:
        return h, None, 'error'


def next_path():
    n = 1
    while os.path.exists(f'raw/statuspage_scale{n}_raw.json'):
        n += 1
    return f'raw/statuspage_scale{n}_raw.json'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'raw/scale_hosts.txt'
    hosts = []
    for l in open(src):
        h = l.strip().lower()
        if not h or h.startswith('*') or not h.endswith('.statuspage.io'):
            continue
        if h.count('.') > 3:
            continue
        hosts.append(h)
    hosts = sorted(set(hosts))
    already = known_hosts()
    hosts = [h for h in hosts if h not in already]
    print(f'candidates: {len(hosts)} (skipped {len(already)} already known)',
          flush=True)

    found, stats, done = {}, {}, 0
    with cf.ThreadPoolExecutor(60) as ex:
        for h, v, why in ex.map(probe, hosts):
            done += 1
            stats[why] = stats.get(why, 0) + 1
            if v:
                found[h] = v
            if done % 2500 == 0:
                inc = sum(len(x['raw'].get('incidents', [])) for x in found.values())
                print(f'  {done}/{len(hosts)} probed | live {len(found)} | '
                      f'incidents {inc}', flush=True)

    out = next_path()
    json.dump(found, open(out, 'w'))
    incs = sum(len(v['raw'].get('incidents', [])) for v in found.values())
    print(f'RESULT live hosts: {len(found)} | incidents: {incs}')
    print('breakdown:', stats)
    print('wrote', out)


if __name__ == '__main__':
    main()
