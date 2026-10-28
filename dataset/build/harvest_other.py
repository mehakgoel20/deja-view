"""Harvest incidents from status platforms other than Atlassian Statuspage.

Statuspage is roughly half the market. These are the rest that expose a usable
public JSON endpoint:

* Better Stack  - GET https://<host>/index.json
    JSON:API. `included[]` holds `status_report` records (the incidents) and
    `status_update` records (the narrative text), linked by relationships.
* Statuspal     - GET https://statuspal.io/api/v2/status_pages/<slug>/incidents
    `incidents[]`, each with `updates[].description`.

Instatus was examined and rejected: every path returns the SPA shell, with the
data only in a React Server Components payload.

Output shape matches the Statuspage pool so the same extractor can consume it.
"""
import json
import re
import html
import subprocess
import concurrent.futures as cf
from collections import Counter

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def strip_html(h):
    t = re.sub(r'<[^>]+>', ' ', h or '')
    t = html.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()


def get(url, timeout=20):
    try:
        r = subprocess.run(['curl', '-sL', '--max-time', str(timeout),
                            '--connect-timeout', '7', '-A', UA, url],
                           capture_output=True, text=True,
                           timeout=timeout + 12, errors='ignore')
        s = r.stdout.strip()
        return json.loads(s) if s.startswith(('{', '[')) else None
    except Exception:
        return None


def nice_org(host, fallback=''):
    if fallback:
        return fallback
    h = re.sub(r'^(www|status)\.', '', host.lower())
    h = re.sub(r'\.(betteruptime|betterstack|statuspal|com|io|co|net|dev|ai|app)$', '', h)
    h = h.split('.')[0]
    return h.capitalize()


# ---------------------------------------------------------------- Better Stack
def harvest_betterstack(host):
    d = get(f'https://{host}/index.json', 25)
    if not isinstance(d, dict) or 'included' not in d:
        return []
    attrs = (d.get('data') or {}).get('attributes') or {}
    org = attrs.get('company_name') or nice_org(host)
    inc_map = {x['id']: x for x in d['included'] if x.get('type') == 'status_report'}
    upd_map = {x['id']: x for x in d['included'] if x.get('type') == 'status_update'}
    out = []
    for rid, rep in inc_map.items():
        a = rep.get('attributes') or {}
        rels = ((rep.get('relationships') or {}).get('status_updates') or {}).get('data') or []
        msgs = []
        for ref in rels:
            u = upd_map.get(ref.get('id'))
            if not u:
                continue
            m = strip_html((u.get('attributes') or {}).get('message'))
            if m:
                msgs.append(m)
        if not msgs:
            continue
        body = ' || '.join(msgs)
        out.append({
            'org': org, 'host': host, 'inc_id': f'bs-{rid}',
            'name': a.get('title') or '', 'impact': a.get('aggregate_state'),
            'created_at': a.get('starts_at') or '', 'resolved_at': a.get('ends_at') or '',
            'url': f'https://{host}/incident/{rid}',
            'postmortem': '', 'body': body[:8000],
        })
    return out


# ------------------------------------------------------------------- Statuspal
def harvest_statuspal(slug):
    d = get(f'https://statuspal.io/api/v2/status_pages/{slug}/incidents', 25)
    if not isinstance(d, dict):
        return []
    out = []
    for inc in d.get('incidents', []) or []:
        msgs = [strip_html(u.get('description')) for u in (inc.get('updates') or [])
                if u.get('description')]
        if not msgs:
            continue
        out.append({
            'org': slug.capitalize(), 'host': 'statuspal.io',
            'inc_id': f"sp-{slug}-{inc.get('id')}",
            'name': inc.get('title') or '', 'impact': inc.get('type'),
            'created_at': (inc.get('starts_at') or inc.get('inserted_at') or ''),
            'resolved_at': inc.get('ends_at') or '',
            'url': f'https://statuspal.io/{slug}',
            'postmortem': '', 'body': ' || '.join(msgs)[:8000],
        })
    return out


def main(bs_hosts, sp_slugs, outfile='raw/other_platforms.json'):
    pool, stats = {}, Counter()

    def run(fn, items, label):
        with cf.ThreadPoolExecutor(20) as ex:
            for res in ex.map(fn, items):
                if res:
                    stats[label + '_hosts'] += 1
                for inc in res:
                    pool.setdefault(inc['inc_id'], inc)

    run(harvest_betterstack, bs_hosts, 'betterstack')
    run(harvest_statuspal, sp_slugs, 'statuspal')

    json.dump(list(pool.values()), open(outfile, 'w'))
    print('other-platform incidents:', len(pool), dict(stats))
    print('orgs:', len({p['org'] for p in pool.values()}))
    return pool


if __name__ == '__main__':
    import sys
    bs = [l.strip() for l in open(sys.argv[1])] if len(sys.argv) > 1 else []
    sp = [l.strip() for l in open(sys.argv[2])] if len(sys.argv) > 2 else []
    main([h for h in bs if h], [s for s in sp if s])
