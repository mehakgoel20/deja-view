"""Check the synthetic set against the gold schema and for internal sanity."""
import json
import re
from collections import Counter, defaultdict

G = json.load(open('../gold_incidents.json'))
S = json.load(open('../synthetic_incidents.json'))

GOLD_KEYS = ['id', 'issue', 'root_cause', 'solution', 'severity', 'category',
             'org', 'source_url', 'incident_date', 'data_type', 'provenance']
CATS = set(e['category'] for e in G)
SEVS = set(e['severity'] for e in G)
GOLD_ORGS = set(e['org'].lower() for e in G)

fail = Counter()
detail = defaultdict(list)


def bad(code, eid, extra=''):
    fail[code] += 1
    if len(detail[code]) < 3:
        detail[code].append(f'{eid} {extra}'[:140])


# ---- schema parity -------------------------------------------------------
for i, e in enumerate(S, 1):
    if list(e.keys()) != GOLD_KEYS:
        bad('key_order_or_set_differs', e.get('id'), str(list(e.keys())))
    if e.get('id') != f'SYN-{i:04d}':
        bad('id_not_sequential', e.get('id'))
    if e.get('category') not in CATS:
        bad('category_not_in_gold_vocab', e['id'], str(e.get('category')))
    if e.get('severity') not in SEVS:
        bad('severity_not_in_gold_vocab', e['id'], str(e.get('severity')))
    if e.get('data_type') != 'synthetic':
        bad('data_type_not_synthetic', e['id'], str(e.get('data_type')))
    if e.get('source_url') is not None:
        bad('source_url_not_null', e['id'], str(e.get('source_url')))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(e.get('incident_date', ''))):
        bad('bad_date', e['id'], str(e.get('incident_date')))

    # ---- content sanity --------------------------------------------------
    iss, rc, sol = e['issue'], e['root_cause'], e['solution']
    if '{' in iss + rc + sol or '}' in iss + rc + sol:
        bad('unfilled_slot', e['id'])
    for f, v in (('issue', iss), ('root_cause', rc), ('solution', sol)):
        if not v or not (v[0].isupper() or v[0].isdigit()):
            bad('not_capitalised:' + f, e['id'], v[:50])
        if not re.search(r'[.!?]$', v.strip()):
            bad('no_terminal_punctuation:' + f, e['id'], v[-40:])
        if re.search(r'\s{2,}|\s[.,;:]', v):
            bad('whitespace_artifact:' + f, e['id'], v[:60])
    if rc == iss or sol == rc or sol == iss:
        bad('fields_identical', e['id'])
    if len(rc) < 70 or len(sol) < 45 or len(iss) < 25:
        bad('field_too_short', e['id'])
    # The cause must add information beyond the symptom rather than restate it.
    # A verb whitelist is the wrong tool (real causes use "took", "concentrated",
    # "coincided", ...), so measure token overlap with the issue instead.
    def toks(x):
        return set(re.sub(r'[^a-z0-9 ]', '', x.lower()).split())
    ti, tr = toks(iss), toks(rc)
    # a terse title legitimately shares all its few tokens with the cause,
    # so only judge overlap once the issue carries enough content to compare
    if len(ti) >= 9 and tr and len(ti & tr) / float(len(ti)) > 0.85:
        bad('cause_restates_issue', e['id'], rc[:70])

# ---- no real-company attribution ----------------------------------------
syn_orgs = set(e['org'].lower() for e in S)
overlap = syn_orgs & GOLD_ORGS
if overlap:
    fail['org_collides_with_real_company'] += len(overlap)
    detail['org_collides_with_real_company'] = sorted(overlap)[:5]

# ---- duplicates ----------------------------------------------------------
trip = Counter((e['issue'], e['root_cause'], e['solution']) for e in S)
dups = sum(v - 1 for v in trip.values() if v > 1)
if dups:
    fail['duplicate_entries'] += dups
rc_dups = sum(v - 1 for v in Counter(e['root_cause'] for e in S).values() if v > 1)
if rc_dups:
    fail['duplicate_root_cause'] += rc_dups

# ---- id collision with gold ---------------------------------------------
if set(e['id'] for e in S) & set(e['id'] for e in G):
    fail['id_collides_with_gold'] += 1

print('gold entries :', len(G))
print('synth entries:', len(S))
print('gold key order matches:', list(S[0].keys()) == GOLD_KEYS)
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
print('distinct root_cause texts:', len(set(e['root_cause'] for e in S)))
print('distinct issue texts     :', len(set(e['issue'] for e in S)))
print('distinct solution texts  :', len(set(e['solution'] for e in S)))
print('distinct orgs            :', len(syn_orgs))
