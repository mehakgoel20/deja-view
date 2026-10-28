"""Collect the full acquisition funnel into one machine-checked record.

Everything in DATA_PROVENANCE.md is generated from this, so the numbers in the
write-up are measured from the artefacts on disk rather than recalled.
"""
import json
import os
import glob
import re
from collections import Counter, defaultdict

OUT = 'raw/provenance.json'


def jload(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default if default is not None else {}


def main():
    rec = {}

    # ---- 1. host discovery -------------------------------------------------
    rounds = []
    for nf in sorted(glob.glob('names*.txt')) + ['names_big.txt']:
        if not os.path.exists(nf):
            continue
        names = [n for n in open(nf).read().split() if n.strip()]
        rounds.append({'names_file': nf, 'company_slugs': len(names)})
    hostfiles = []
    for hf in sorted(glob.glob('hosts*.txt')):
        hostfiles.append({'hosts_file': hf,
                          'candidate_hosts': sum(1 for _ in open(hf))})
    rec['host_discovery'] = {
        'name_lists': rounds,
        'candidate_host_files': hostfiles,
        # de-duplicated: rounds overlap, so summing the files overcounts
        'total_candidate_hosts_probed': len({l.strip() for hf in glob.glob('hosts*.txt')
                                             for l in open(hf) if l.strip()}),
        'candidate_host_lines_incl_overlap': sum(h['candidate_hosts'] for h in hostfiles),
    }

    # ---- 2. live hosts + harvest ------------------------------------------
    harvests = []
    live_hosts = set()
    for f in sorted(glob.glob('raw/statuspage*_raw.json'),
                    key=lambda p: int(re.search(r'(\d+)_raw', p).group(1))
                    if re.search(r'(\d+)_raw', p) else 0):
        d = jload(f, {})
        hosts, incs = 0, 0
        for h, v in d.items():
            if not isinstance(v, dict):
                continue
            raw = v.get('raw') or {}
            n = len(raw.get('incidents', []) or v.get('incidents', []) or [])
            if n:
                hosts += 1
                incs += n
                live_hosts.add(h)
        harvests.append({'file': os.path.basename(f), 'live_hosts': hosts,
                         'incidents_returned': incs})
    # harvest 1 has a different shape
    h1 = jload('raw/statuspage.json', {})
    if h1:
        hosts = sum(1 for v in h1.values() if v.get('n'))
        live_hosts |= {h for h, v in h1.items() if v.get('n')}
        harvests.insert(0, {'file': 'statuspage.json', 'live_hosts': hosts,
                            'incidents_returned': sum(v.get('n', 0) for v in h1.values())})

    # how many hosts hit the API's 50-incident ceiling (hidden older history)
    per_host = Counter()
    for f in glob.glob('raw/statuspage*_raw.json'):
        d = jload(f, {})
        for h, v in d.items():
            if not isinstance(v, dict):
                continue
            raw = v.get('raw') or {}
            cnt = len(raw.get('incidents', []) or v.get('incidents', []) or [])
            if cnt:
                per_host[h] = max(per_host[h], cnt)
    rec['capped_hosts'] = sum(1 for n in per_host.values() if n >= 50)
    rec['live_hosts_total'] = len(per_host)
    rec['per_host_histogram'] = {
        '50 (API cap)': sum(1 for n in per_host.values() if n >= 50),
        '25-49': sum(1 for n in per_host.values() if 25 <= n < 50),
        '10-24': sum(1 for n in per_host.values() if 10 <= n < 25),
        '1-9': sum(1 for n in per_host.values() if n < 10),
    }

    pool = jload('raw/pool_all.json', [])
    rec['harvest'] = {
        'rounds': harvests,
        'distinct_live_status_hosts': len(live_hosts),
        'pool_unique_incidents': len(pool),
        'pool_distinct_orgs': len(set(p['org'] for p in pool)) if pool else 0,
        'pool_with_explicit_postmortem_update':
            sum(1 for p in pool if p.get('postmortem')) if pool else 0,
    }

    # ---- 3. other sources --------------------------------------------------
    rec['other_sources'] = {
        'danluu_index_entries': len(jload('raw/danluu_entries.json', [])),
        'danluu_pages_fetched': len(glob.glob('raw/pages/*.txt')),
        'github_availability_reports_fetched': len(glob.glob('raw/gh/*.html')),
        'aws_post_event_summaries_fetched': len(glob.glob('raw/aws/*.html')),
        'blog_index_seeds': 0,
        'blog_candidate_articles': len(jload('raw/blog_candidates.json', {})),
        'blog_pages_fetched': len(glob.glob('raw/blogpages/*.html')),
    }
    try:
        from blogs_seed import SEEDS
        rec['other_sources']['blog_index_seeds'] = len(SEEDS)
    except Exception:
        pass

    # ---- 4. extraction yield per source -----------------------------------
    rec['extraction'] = {
        'statuspage_entries': len(jload('raw/extracted.json', [])),
        'github_entries': len(jload('raw/extracted_gh.json', [])),
        'blog_entries': len(jload('raw/extracted_blogs.json', [])),
        'danluu_entries': len(jload('raw/extracted_danluu.json', [])),
        'aws_entries': len(jload('raw/extracted_aws.json', [])),
    }

    # ---- 5. url verification ----------------------------------------------
    us = jload('raw/newurlstatus.json', {})
    rec['url_verification'] = {
        'urls_checked': len(us),
        'status_counts': dict(Counter(us.values())),
    }
    # original seed audit
    seed = jload('urlstatus.json', None) or jload('raw/urlstatus.json', None)
    if seed:
        rec['original_seed_url_audit'] = dict(Counter(r[1] for r in seed))
    dropped = jload('raw/dropped.json', {})
    if dropped:
        rec['original_seed_drop_reasons'] = dict(
            Counter(r for rs in dropped.values() for r in rs))

    # ---- 6. final dataset composition -------------------------------------
    final = jload('../gold_incidents.json', [])
    if final:
        cause_only = [e for e in final if e.get('solution') is None]
        rec['final'] = {
            'entries': len(final),
            'distinct_orgs': len(set(e['org'] for e in final)),
            'provenance': dict(Counter(e['provenance'] for e in final)),
            'category': dict(Counter(e['category'] for e in final)),
            'severity': dict(Counter(e['severity'] for e in final)),
            'year': dict(sorted(Counter(str(e['incident_date'])[:4] for e in final).items())),
            'date_precision': dict(Counter(
                'YYYY-MM-DD' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(e['incident_date']))
                else 'YYYY-MM' if re.fullmatch(r'\d{4}-\d{2}', str(e['incident_date']))
                else 'YYYY' for e in final)),
            'with_published_solution': len(final) - len(cause_only),
            'cause_only_no_published_solution': len(cause_only),
            'top_orgs': dict(Counter(e['org'] for e in final).most_common(25)),
            'mean_len': {
                f: sum(len(e[f] or '') for e in final) // len(final)
                for f in ('issue', 'root_cause', 'solution')},
            'mean_len_solution_where_present': (
                sum(len(e['solution']) for e in final if e.get('solution'))
                // max(1, len(final) - len(cause_only))),
        }

    json.dump(rec, open(OUT, 'w'), indent=2)
    print('WROTE', OUT)
    for k, v in rec.items():
        if isinstance(v, dict) and 'entries' not in v:
            print(f'{k}: {len(v)} keys')
        else:
            print(f'{k}: {v if not isinstance(v, dict) else list(v)[:6]}')


if __name__ == '__main__':
    main()
