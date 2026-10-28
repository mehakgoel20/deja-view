"""Assemble the final gold dataset: merge sources, dedupe, verify URLs, renumber."""
import json, re, os, subprocess, difflib, concurrent.futures as cf
from collections import Counter, defaultdict
from polish import validate

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
FIELDS = ['id', 'issue', 'root_cause', 'solution', 'severity', 'category',
          'org', 'source_url', 'incident_date', 'data_type', 'provenance', 'note']
CATS = {'database_issue', 'configuration_deployment', 'api_latency', 'networking_dns',
        'hardware_infra', 'security_incident', 'concurrency_race_condition',
        'memory_leak', 'authentication', 'payment_processing', 'other'}
SEVS = {'Critical', 'High', 'Medium', 'Low'}


def load(path, prov=None):
    if not os.path.exists(path):
        return []
    d = json.load(open(path))
    for x in d:
        x.setdefault('provenance', prov or 'unknown')
        x.setdefault('data_type', 'real')
    return d


def norm(t):
    return re.sub(r'[^a-z0-9 ]', '', str(t).lower())


def main():
    raw_base = load('clean_base.json', 'original_curated')
    # The curated base is held to the same standard as everything else: parts of
    # it were machine-generated and carry split sentences, index commentary and
    # impact text in the solution field.
    base, bdrop = [], Counter()
    for x in raw_base:
        e, why = validate(x)
        if not e:
            bdrop[why] += 1
            continue
        base.append(e)
    print('curated base:', len(raw_base), '->', len(base), dict(bdrop), flush=True)

    # dedupe the base against itself (same incident filed twice)
    seen_u, seen_s, dd = set(), [], Counter()
    deduped = []
    for x in base:
        u = x['source_url'].rstrip('/')
        sig = norm(x['root_cause'])[:160]
        if u in seen_u:
            dd['dup_url'] += 1
            continue
        if any(difflib.SequenceMatcher(None, sig, s).ratio() > 0.80 for s in seen_s):
            dd['dup_text'] += 1
            continue
        seen_u.add(u)
        seen_s.append(sig)
        deduped.append(x)
    print('base self-dedupe:', len(base), '->', len(deduped), dict(dd), flush=True)
    base = deduped
    new = (load('raw/extracted.json', 'statuspage_postmortem')
           + load('raw/extracted_gh.json', 'github_availability_report')
           + load('raw/extracted_aws.json', 'aws_post_event_summary')
           + load('raw/extracted_danluu.json', 'curated_index+source_page')
           + load('raw/extracted_blogs.json', 'engineering_blog_postmortem'))
    print(f'base={len(base)} new={len(new)}')

    # ---- 1. dedupe new against base and against itself -------------------
    # Shingle-indexed Jaccard: only compare entries that share a 4-gram, so this
    # stays near-linear instead of comparing every pair.
    def shingles(t, n=4):
        w = norm(t).split()
        return {' '.join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}

    seen_url = {x['source_url'].rstrip('/') for x in base}
    index = defaultdict(list)          # shingle -> list of shingle-set ids
    sets = []

    def add_sig(sh):
        sid = len(sets)
        sets.append(sh)
        for g in sh:
            index[g].append(sid)
        return sid

    for x in base:
        add_sig(shingles(x['root_cause']))

    kept, drop = [], Counter()
    for x in new:
        u = x['source_url'].rstrip('/')
        # a monthly availability report legitimately holds several incidents
        if u in seen_url and x.get('provenance') != 'github_availability_report':
            drop['dup_url'] += 1
            continue
        sh = shingles(x['root_cause'])
        if not sh:
            drop['empty_rc'] += 1
            continue
        cand = Counter()
        for g in sh:
            for sid in index.get(g, ()):
                cand[sid] += 1
        hit = False
        for sid, shared in cand.most_common(12):
            other = sets[sid]
            j = shared / float(len(sh | other))
            if j > 0.55:
                hit = True
                break
        if hit:
            drop['dup_text'] += 1
            continue
        seen_url.add(u)
        add_sig(sh)
        kept.append(x)
    print('after dedupe:', len(kept), dict(drop), flush=True)

    # ---- 2. verify every new URL resolves --------------------------------
    urls = sorted({x['source_url'] for x in kept})
    print('verifying', len(urls), 'urls ...')

    def chk(u):
        try:
            r = subprocess.run(['curl', '-sL', '-o', '/dev/null', '-w', '%{http_code}',
                                '--max-time', '25', '-A', UA, u],
                               capture_output=True, text=True, timeout=40)
            return u, r.stdout.strip() or '000'
        except Exception:
            return u, 'ERR'
    # reuse earlier verdicts so repeated builds do not re-hit every host
    cache = {}
    if os.path.exists('raw/newurlstatus.json'):
        cache = json.load(open('raw/newurlstatus.json'))
    todo = [u for u in urls if cache.get(u) not in ('200', '429', '403', '301', '302')]
    print('  cached:', len(urls) - len(todo), '| to check:', len(todo), flush=True)
    status = {u: cache[u] for u in urls if u in cache}
    with cf.ThreadPoolExecutor(30) as ex:
        for u, c in ex.map(chk, todo):
            status[u] = c
    cache.update(status)
    json.dump(cache, open('raw/newurlstatus.json', 'w'), indent=1)
    print('url status:', Counter(status.values()).most_common())
    # A source URL that a reader cannot open is not a citation. Many retired
    # or restricted Statuspage pages answer 403 on every URL form, so require
    # a clean 200 (after redirects) rather than merely "not 404".
    live = [x for x in kept if status.get(x['source_url'], '000') == '200']
    from collections import Counter as _C
    print('entries with a 200 source url:', len(live),
          '(dropped', len(kept) - len(live), ')')
    print('  dropped by status:',
          dict(_C(status.get(x['source_url'], '000') for x in kept
                  if status.get(x['source_url'], '000') != '200')))

    # ---- 3. field validation --------------------------------------------
    final_new, bad = [], Counter()
    for x in live:
        if x.get('category') not in CATS:
            x['category'] = 'other'
        if x.get('severity') not in SEVS:
            x['severity'] = 'Medium'
        if not re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?', str(x.get('incident_date', ''))):
            bad['bad_date'] += 1
            continue
        if not x.get('org') or len(str(x['org'])) < 2:
            bad['no_org'] += 1
            continue
        # `issue` is a symptom label and is legitimately terse
        # ("Delays starting Gen 2 Docker Jobs."); cause and fix must carry detail.
        if len(x['issue']) < 25:
            bad['issue_too_short'] += 1
            continue
        if len(x['root_cause']) < 45:
            bad['cause_too_short'] += 1
            continue
        # solution is None when the publisher never stated a remediation
        if x.get('solution') is not None and len(x['solution']) < 45:
            bad['fix_too_short'] += 1
            continue
        final_new.append(x)
    print('new entries passing validation:', len(final_new), dict(bad))

    # ---- 4. merge, order, renumber --------------------------------------
    allx = base + final_new
    allx.sort(key=lambda x: (0 if x['provenance'] == 'original_curated' else 1,
                             str(x.get('incident_date', '')), str(x.get('org', ''))))
    out = []
    for i, x in enumerate(allx, 1):
        e = {k: x.get(k, '') for k in FIELDS}
        e['id'] = f'GOLD-{i:04d}'
        out.append(e)
    return out


if __name__ == '__main__':
    out = main()
    json.dump(out, open('final_candidate.json', 'w'), indent=2)
    print()
    print('TOTAL:', len(out))
    print('categories:', Counter(o['category'] for o in out).most_common())
    print('severity:', Counter(o['severity'] for o in out).most_common())
    print('provenance:', Counter(o['provenance'] for o in out).most_common())
    print('orgs:', len(set(o['org'] for o in out)))
