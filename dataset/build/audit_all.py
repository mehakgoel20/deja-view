"""Independent audit of the shipped dataset. Re-checks every stated guarantee."""
import json, re, subprocess, random, concurrent.futures as cf
from collections import Counter, defaultdict

PATH = "../gold_incidents_all.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
REQUIRED = ['id', 'issue', 'root_cause', 'solution', 'severity', 'category',
            'org', 'source_url', 'incident_date', 'data_type', 'provenance']
CATS = {'database_issue', 'configuration_deployment', 'api_latency', 'networking_dns',
        'hardware_infra', 'security_incident', 'concurrency_race_condition',
        'memory_leak', 'authentication', 'payment_processing', 'other'}
SEVS = {'Critical', 'High', 'Medium', 'Low'}

d = json.load(open(PATH))
fail = Counter()
detail = defaultdict(list)


def bad(code, eid, extra=''):
    fail[code] += 1
    if len(detail[code]) < 4:
        detail[code].append(f'{eid} {extra}'[:150])


# ---- schema, ids, enums, dates ------------------------------------------
ids = [e.get('id') for e in d]
if len(set(ids)) != len(ids):
    fail['duplicate_id'] += len(ids) - len(set(ids))
for i, e in enumerate(d, 1):
    if e.get('id') != f'GOLD-{i:04d}':
        bad('id_not_sequential', e.get('id'))
    for k in REQUIRED:
        if k not in e:
            bad('missing_field:' + k, e.get('id'))
        elif e[k] in (None, ''):
            # gold_incidents.json ships complete entries only, so `solution`
            # must be populated here. Cause-only rows live in
            # gold_incidents_all.json and are audited by audit_all.py.
            if k != 'solution':
                bad('empty_field:' + k, e.get('id'))
    if e.get('category') not in CATS:
        bad('bad_category', e.get('id'), str(e.get('category')))
    if e.get('severity') not in SEVS:
        bad('bad_severity', e.get('id'), str(e.get('severity')))
    if e.get('data_type') != 'real':
        bad('bad_data_type', e.get('id'))
    if not re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?', str(e.get('incident_date', ''))):
        bad('bad_date', e.get('id'), str(e.get('incident_date')))
    else:
        y = int(str(e['incident_date'])[:4])
        if y < 1960 or y > 2026:
            bad('implausible_year', e.get('id'), str(e['incident_date']))
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(e['incident_date'])):
            mo, dy = int(e['incident_date'][5:7]), int(e['incident_date'][8:10])
            if not (1 <= mo <= 12 and 1 <= dy <= 31):
                bad('impossible_date', e.get('id'), e['incident_date'])
    if not str(e.get('source_url', '')).startswith('http'):
        bad('bad_url', e.get('id'))
    # degenerate text
    iss, rc = (str(e.get(k, '')).strip() for k in ('issue', 'root_cause'))
    sol = e.get('solution')
    sol = sol.strip() if isinstance(sol, str) else None
    if rc == iss:
        bad('rc_eq_issue', e.get('id'))
    if sol is not None and sol == rc:
        bad('sol_eq_rc', e.get('id'))
    if len(rc) < 45:
        bad('rc_short', e.get('id'), rc[:60])
    if sol is not None and len(sol) < 45:
        bad('sol_short', e.get('id'), (sol or 'None')[:60])
    if len(iss) < 25:
        bad('issue_short', e.get('id'), iss[:60])
    # leftover artifacts
    if re.search(r'\bOn\s*,|\bat\s+and\b|\bfrom\s+to\b|\(\s*\)|  |[\[\]]'
                 r'|\b(?:on|at|from|between)\s+(?:on|at|to|and)\b'
                 r'|~\s*[–—-]|~\s*[.,:]'
                 r'|\s(?:to|and|until|through)\s*[,.)]'
                 r'|(?<![-\w])(?:between|from|at|on|by|during|around|until)\s*[.,]',
                 iss + ' ' + rc + ' ' + (sol or '')):
        bad('text_artifact', e.get('id'))
    if re.search(r'we (?:deeply )?regret|apologi[sz]e|appreciate your patience', rc, re.I):
        bad('apology_as_cause', e.get('id'))

# ---- duplicate detection ------------------------------------------------
by_url = defaultdict(list)
for e in d:
    by_url[e['source_url'].rstrip('/')].append(e)
def rcwords(e):
    return set(re.sub(r'[^a-z0-9 ]', '', e['root_cause'].lower()).split())


for u, grp in by_url.items():
    if len(grp) < 2:
        continue
    # One report page can legitimately document several incidents (GitHub's
    # monthly availability reports do). Only flag entries whose causes overlap.
    for i in range(len(grp)):
        for j in range(i + 1, len(grp)):
            a_, b_ = rcwords(grp[i]), rcwords(grp[j])
            if not a_ or not b_:
                continue
            if len(a_ & b_) / float(len(a_ | b_)) > 0.5:
                bad('shared_url_same_cause', grp[i]['id'],
                    f"vs {grp[j]['id']} {u}")


def shingles(t, n=4):
    w = re.sub(r'[^a-z0-9 ]', '', str(t).lower()).split()
    return {' '.join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


index = defaultdict(list)
sets = []
for e in d:
    sh = shingles(e['root_cause'])
    cand = Counter()
    for g in sh:
        for sid in index.get(g, ()):
            cand[sid] += 1
    for sid, shared in cand.most_common(8):
        if shared / float(len(sh | sets[sid][0])) > 0.55:
            bad('near_dup_rc', e['id'], 'vs ' + sets[sid][1])
            break
    sets.append((sh, e['id']))
    for g in sh:
        index[g].append(len(sets) - 1)

# ---- live URL spot-check ------------------------------------------------
random.seed(0)
sample = random.sample([e['source_url'] for e in d], min(120, len(d)))


def chk(u):
    try:
        r = subprocess.run(['curl', '-sL', '-o', '/dev/null', '-w', '%{http_code}',
                            '--max-time', '25', '-A', UA, u],
                           capture_output=True, text=True, timeout=40)
        return u, r.stdout.strip() or '000'
    except Exception:
        return u, 'ERR'


codes = Counter()
with cf.ThreadPoolExecutor(25) as ex:
    for u, c in ex.map(chk, sample):
        codes[c] += 1
        if c in ('404', '410', '000', 'ERR'):
            fail['dead_url_in_sample'] += 1
            detail['dead_url_in_sample'].append(u)

# ---- report -------------------------------------------------------------
print('AUDIT of', PATH)
print('entries:', len(d))
print('url spot-check (n=%d):' % len(sample), dict(codes))
print()
if not fail:
    print('PASS - no problems found')
else:
    print('FINDINGS:')
    for k, v in fail.most_common():
        print(f'  {v:>5}  {k}')
        for x in detail[k][:3]:
            print(f'           e.g. {x}')
print()
print('categories:', Counter(e['category'] for e in d).most_common())
print('orgs:', len(set(e['org'] for e in d)))
print('years:', sorted(Counter(str(e['incident_date'])[:4] for e in d).items()))
