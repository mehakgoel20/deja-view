"""Scale host discovery via Certificate Transparency, when crt.sh is reachable.

Why this exists
---------------
Atlassian Statuspage gives each page a random subdomain id, e.g.
`027j6zrg2zwb.statuspage.io` is Mixmax and `029txycd4lgb.statuspage.io` is
Zaptec. Guessing company names therefore cannot find most status pages - which
is why the name-guessing hit rate collapsed to ~2% after 44,702 candidates.

CT logs record a certificate for every one of those hostnames, so `crt.sh`
can enumerate them exhaustively. That is the only identified route to a
materially larger dataset. When this was first run, crt.sh returned HTTP 502 on
every attempt, so it is written to be re-run later.

Usage
-----
    python3 expand_via_ct.py            # one attempt, then stop
    python3 expand_via_ct.py --wait     # retry until crt.sh answers, then run

On success it: enumerates hostnames -> probes them for a live Statuspage API
-> harvests incidents into raw/statuspage_ct_<n>_raw.json -> prints the new
pool size. Then run `python3 rebuild_pool.py && bash build.sh`.
"""
import json
import os
import re
import subprocess
import sys
import time
import concurrent.futures as cf

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HOSTS_OUT = 'raw/enumerated_hosts.txt'
# pirated-media SEO pages abuse free Statuspage accounts; they are real hosts
# but carry no real incidents, so they are filtered at discovery time
SPAM = re.compile(
    r'regarder|streaming|vostfr|\bfilm\b|\bmovie\b|watch online|ganzer|'
    r'pelicula|película|完整版|พากย์|เต็มเรื่อง|online schauen|putlocker|'
    r'123movies|full movie|sub indo|dublado', re.I)
CT_URLS = [
    'https://crt.sh/?q=%25.statuspage.io&output=json',
    'https://crt.sh/?q=.statuspage.io&output=json',
]


def curl(url, timeout=180):
    try:
        r = subprocess.run(['curl', '-sS', '--compressed', '--max-time',
                            str(timeout), '-A', UA, url],
                           capture_output=True, text=True,
                           timeout=timeout + 30, errors='ignore')
        return r.stdout or ''
    except Exception:
        return ''


def enumerate_hosts():
    """Return every *.statuspage.io hostname crt.sh knows about."""
    names = set()
    for url in CT_URLS:
        body = curl(url)
        if not body.strip() or body.lstrip().startswith('<'):
            continue
        try:
            recs = json.loads(body)
        except Exception:
            continue
        for r in recs:
            for nm in (r.get('name_value') or '').split('\n'):
                nm = nm.strip().lower().lstrip('*.')
                if nm.endswith('.statuspage.io'):
                    names.add(nm)
        if names:
            break
    return names


def probe_and_harvest(hosts):
    """Fetch the incident API for each host; keep hosts with real incidents."""
    def one(h):
        try:
            r = subprocess.run(['curl', '-sL', '--max-time', '20',
                                '--connect-timeout', '7', '-A', UA,
                                f'https://{h}/api/v2/incidents.json'],
                               capture_output=True, text=True, timeout=32,
                               errors='ignore')
            if not r.stdout.strip().startswith('{'):
                return h, None
            j = json.loads(r.stdout)
            if not j.get('incidents'):
                return h, None
            org = (j.get('page') or {}).get('name') or h
            if SPAM.search(org):
                return h, None
            return h, {'org': org, 'raw': j}
        except Exception:
            return h, None

    found = {}
    done = 0
    with cf.ThreadPoolExecutor(40) as ex:
        for h, v in ex.map(one, hosts):
            done += 1
            if v:
                found[h] = v
            if done % 2000 == 0:
                print(f'   probed {done}/{len(hosts)} -> {len(found)} live',
                      flush=True)
    return found


def next_raw_path():
    n = 1
    while os.path.exists(f'raw/statuspage_ct_{n}_raw.json'):
        n += 1
    return f'raw/statuspage_ct_{n}_raw.json'


def main():
    wait = '--wait' in sys.argv
    attempt = 0
    while True:
        attempt += 1
        print(f'attempt {attempt}: querying crt.sh ...', flush=True)
        names = enumerate_hosts()
        if names:
            break
        if not wait:
            print('crt.sh unavailable (it returns 502 when overloaded). '
                  'Re-run later, or use --wait to keep retrying.')
            return 1
        delay = min(900, 60 * attempt)
        print(f'  unavailable; retrying in {delay}s', flush=True)
        time.sleep(delay)

    prev = set()
    if os.path.exists(HOSTS_OUT):
        prev = {l.strip() for l in open(HOSTS_OUT) if l.strip()}
    allnames = sorted(names | prev)
    open(HOSTS_OUT, 'w').write('\n'.join(allnames) + '\n')
    print(f'enumerated {len(names)} hostnames from CT '
          f'({len(allnames)} total known)', flush=True)

    print('probing for live Statuspage APIs ...', flush=True)
    found = probe_and_harvest(allnames)
    out = next_raw_path()
    json.dump(found, open(out, 'w'))
    incs = sum(len(v['raw'].get('incidents', [])) for v in found.values())
    print(f'live non-spam hosts: {len(found)} | incidents: {incs}')
    print(f'wrote {out}')
    print('now run:  python3 rebuild_pool.py && bash build.sh')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
