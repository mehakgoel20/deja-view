import re, html, os, json
from collections import Counter
from extract3 import cat_of, build
from polish import validate

MO = {m: i + 1 for i, m in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july',
     'august', 'september', 'october', 'november', 'december'])}
MONTHS = '|'.join(MO)

idx = {}
for line in open('raw/gh/index.txt', errors='ignore'):
    p = line.rstrip('\n').split('\t')
    if len(p) == 2:
        idx[p[0]] = p[1]

# incident header, e.g. "May 16 07:17 UTC (lasting 9 hours 48 minutes)"
HDR = re.compile(rf'\b({MONTHS})\s+(\d{{1,2}})\s+(\d{{2}}):(\d{{2}})\s*UTC\s*\(([^)]{{0,80}})\)', re.I)
# trailing sections of the post we must not read as incident prose
TAIL = re.compile(r'\b(?:In summary|Tags:|Written by|More on GitHub|Related posts|'
                  r'Explore more from GitHub|We do newsletters|Site-wide Links|'
                  r'Subscribe to|Learn more about)\b', re.I)
DUR_H = re.compile(r'(\d+)\s*hour', re.I)
DUR_M = re.compile(r'(\d+)\s*minute', re.I)


def totext(h):
    h = re.sub(r'(?is)<(script|style|nav|footer|svg|noscript)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?s)<!--.*?-->', ' ', h)
    h = re.sub(r'(?i)</(p|div|li|h[1-6])>', '\n', h)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = html.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t)
    return re.sub(r'\n\s*\n+', '\n', t).strip()


out, seen, stats = [], set(), Counter()
seen_reports = set()

for k, url in sorted(idx.items()):
    p = f'raw/gh/{k}.html'
    if not os.path.exists(p):
        continue
    m = re.search(r'availability-report-([a-z]+)-(\d{4})', url)
    if not m:
        continue
    rep_mo, year = m.group(1).lower(), int(m.group(2))
    # the same report was fetched under two URL patterns - keep one
    if (rep_mo, year) in seen_reports:
        continue
    seen_reports.add((rep_mo, year))

    t = totext(open(p, errors='ignore').read())
    hits = list(HDR.finditer(t))
    if not hits:
        stats['no_incident_headers'] += 1
        continue
    for i, h in enumerate(hits):
        start = h.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(t)
        prose = t[start:end]
        cut = TAIL.search(prose)
        if cut:
            prose = prose[:cut.start()]
        prose = prose.strip()
        if len(prose) < 150:
            stats['prose_thin'] += 1
            continue

        mon, day = MO[h.group(1).lower()], int(h.group(2))
        yr = year
        if rep_mo == 'january' and mon == 12:
            yr = year - 1
        elif MO[rep_mo] < mon and not (rep_mo == 'january' and mon == 12):
            # report month earlier than incident month -> incident is from prior year
            yr = year - 1
        date = f"{yr:04d}-{mon:02d}-{day:02d}"

        dur = h.group(5)
        hh = DUR_H.search(dur)
        mm2 = DUR_M.search(dur)
        mins = (int(hh.group(1)) * 60 if hh else 0) + (int(mm2.group(1)) if mm2 else 0)
        sev = ('Critical' if mins >= 360 else 'High' if mins >= 120
               else 'Medium' if mins >= 30 else 'Low')

        built, why = build(prose, 'GitHub', date, url, '', None)
        if not built and why == 'no_solution':
            built, why = build(prose, 'GitHub', date, url, '', None,
                               require_fix=False)
            if built:
                stats['recovered_cause_only'] += 1
        if not built:
            stats['build:' + why] += 1
            continue
        built['severity'] = sev
        built['category'] = cat_of(prose)
        built['provenance'] = 'github_availability_report'
        ee, why = validate(built)
        if not ee:
            stats['polish:' + why] += 1
            continue
        key = re.sub(r'[^a-z0-9]', '', ee['root_cause'].lower())[:70]
        if key in seen:
            stats['dupe'] += 1
            continue
        seen.add(key)
        out.append(ee)

json.dump(out, open('raw/extracted_gh.json', 'w'), indent=1)
print('unique reports parsed:', len(seen_reports))
print('github incidents extracted:', len(out))
print('rejections:', dict(stats))
print('categories:', Counter(o['category'] for o in out).most_common())
print('years:', sorted(Counter(o['incident_date'][:4] for o in out).items()))
print('severity:', Counter(o['severity'] for o in out).most_common())
