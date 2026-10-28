"""Enumerate statuspage.io subdomains from Certificate Transparency and
passive-DNS sources, instead of guessing company names.

Statuspage assigns each page a random subdomain id (e.g.
`027j6zrg2zwb.statuspage.io` is Mixmax), so name-guessing can never find most
pages. CT logs record every certificate issued for those hostnames, which makes
them enumerable.

Writes raw/enumerated_hosts.txt.
"""
import json
import re
import subprocess
import time
import sys

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
OUT = 'raw/enumerated_hosts.txt'


def fetch(url, timeout=120, tries=4, sleep=6):
    """CT front-ends are frequently overloaded; retry with backoff."""
    for i in range(tries):
        try:
            r = subprocess.run(['curl', '-sS', '--max-time', str(timeout),
                                '--compressed', '-A', UA, url],
                               capture_output=True, text=True,
                               timeout=timeout + 20, errors='ignore')
            body = r.stdout or ''
            if body.strip() and not body.lstrip().startswith('<'):
                return body
            if '502' in body or '503' in body or 'Offline' in body:
                pass
        except Exception:
            pass
        if i < tries - 1:
            time.sleep(sleep * (i + 1))
    return ''


def names_from_crtsh(body):
    out = set()
    try:
        d = json.loads(body)
    except Exception:
        return out
    for r in d:
        for nm in (r.get('name_value') or '').split('\n'):
            nm = nm.strip().lower().lstrip('*.')
            if nm.endswith('.statuspage.io'):
                out.add(nm)
    return out


def names_from_certspotter(body):
    out = set()
    try:
        d = json.loads(body)
    except Exception:
        return out
    if not isinstance(d, list):
        return out
    for r in d:
        for nm in r.get('dns_names', []) or []:
            nm = nm.strip().lower().lstrip('*.')
            if nm.endswith('.statuspage.io'):
                out.add(nm)
    return out


def names_from_lines(body):
    out = set()
    for line in body.splitlines():
        nm = re.split(r'[,\s]', line.strip())[0].lower()
        if nm.endswith('.statuspage.io'):
            out.add(nm)
    return out


SOURCES = [
    ('crt.sh json', 'https://crt.sh/?q=%25.statuspage.io&output=json', names_from_crtsh),
    ('crt.sh json alt', 'https://crt.sh/?q=.statuspage.io&output=json', names_from_crtsh),
    ('certspotter', 'https://api.certspotter.com/v1/issuances?domain=statuspage.io'
                    '&include_subdomains=true&expand=dns_names', names_from_certspotter),
    ('hackertarget', 'https://api.hackertarget.com/hostsearch/?q=statuspage.io', names_from_lines),
    ('rapiddns', 'https://rapiddns.io/subdomain/statuspage.io?full=1&down=1', names_from_lines),
    ('alienvault', 'https://otx.alienvault.com/api/v1/indicators/domain/statuspage.io/passive_dns',
     lambda b: {r.get('hostname', '').lower() for r in (json.loads(b).get('passive_dns', []) if b.strip().startswith('{') else [])
                if str(r.get('hostname', '')).endswith('.statuspage.io')}),
]


def main():
    found = set()
    for label, url, parser in SOURCES:
        body = fetch(url)
        got = set()
        if body:
            try:
                got = parser(body) or set()
            except Exception as e:
                print(f'  {label}: parse failed {type(e).__name__}')
        new = got - found
        found |= got
        print(f'  {label:<18} returned {len(got):>6} hostnames ({len(new)} new)')
        sys.stdout.flush()

    # keep anything previously discovered too
    try:
        found |= {l.strip() for l in open(OUT) if l.strip()}
    except FileNotFoundError:
        pass

    with open(OUT, 'w') as f:
        f.write('\n'.join(sorted(found)) + '\n')
    print('TOTAL enumerated statuspage.io hostnames:', len(found))


if __name__ == '__main__':
    main()
