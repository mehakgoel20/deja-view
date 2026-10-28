import re, html, os, json
from collections import Counter
from extract3 import cat_of, build
from polish import validate

idx = {}
for line in open('raw/aws/index.txt', errors='ignore'):
    p = line.rstrip('\n').split(' ', 1)
    if len(p) == 2:
        idx[p[0]] = p[1]


def totext(h):
    h = re.sub(r'(?is)<(script|style|nav|footer|svg|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<!--.*?-->', ' ', h)
    h = re.sub(r'(?i)</(p|div|li|h[1-6]|br)>', '\n', h)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = html.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()


MONTHS = ('january|february|march|april|may|june|july|august|september|'
          'october|november|december')
MO = {m: i + 1 for i, m in enumerate(MONTHS.split('|'))}
SEVW = re.compile(r'\b(?:all|entire|every)\b.{0,30}\b(?:region|customers)\b|'
                  r'complete (?:outage|loss)|data loss|unavailable for', re.I)

out, stats = [], Counter()
for k, url in sorted(idx.items()):
    p = f'raw/aws/{k}.html'
    if not os.path.exists(p) or os.path.getsize(p) < 2000:
        stats['missing'] += 1
        continue
    t = totext(open(p, errors='ignore').read())
    if len(t) < 600:
        stats['thin'] += 1
        continue
    # service name from the page title / first heading
    title = ''
    mt = re.search(r'(?is)<title>(.*?)</title>', open(p, errors='ignore').read())
    if mt:
        title = html.unescape(re.sub(r'<[^>]+>', '', mt.group(1))).strip()
    # date: AWS message pages state e.g. "July 30, 2024"
    date = ''
    md = re.search(rf'\b({MONTHS})\s+(\d{{1,2}}),?\s+(20\d\d)\b', t, re.I)
    if md:
        date = f"{int(md.group(3)):04d}-{MO[md.group(1).lower()]:02d}-{int(md.group(2)):02d}"
    else:
        my = re.search(r'\b(20\d\d)\b', t)
        date = my.group(1) if my else ''
    built, why = build(t[:25000], 'AWS', date, url, title[:120], None)
    if not built:
        stats['build:' + why] += 1
        continue
    built['severity'] = 'Critical' if SEVW.search(t[:6000]) else 'High'
    built['category'] = cat_of(t[:12000])
    built['provenance'] = 'aws_post_event_summary'
    ee, why = validate(built)
    if not ee:
        stats['polish:' + why] += 1
        continue
    out.append(ee)

json.dump(out, open('raw/extracted_aws.json', 'w'), indent=1)
print('aws summaries extracted:', len(out), dict(stats))
print('categories:', Counter(o['category'] for o in out).most_common())
print('dates:', sorted(o['incident_date'] for o in out))
