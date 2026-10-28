import json
from collections import Counter
from extract3 import build
from polish import validate
pool=json.load(open('raw/pool_all.json'))
base=json.load(open('clean_base.json')); have={x['source_url'].rstrip('/') for x in base}
out=[];rej=Counter()
for x in pool:
    if x['url'].rstrip('/') in have: continue
    raw = x['postmortem'] if x['postmortem'] else x['body']
    args = (raw, x['org'], (x.get('created_at') or '')[:10], x['url'],
            x.get('name') or '', x.get('impact'))
    e, why = build(*args)
    if not e and why == 'no_solution':
        # the cause is the RCA label; a published remediation is a bonus, so
        # keep the incident with solution=None rather than discarding it
        e, why = build(*args, require_fix=False)
        if e: rej['recovered_cause_only'] += 1
    if not e: rej[why]+=1; continue
    e,why=validate(e)
    if not e: rej['polish:'+why]+=1; continue
    out.append(e)
json.dump(out,open('raw/extracted.json','w'),indent=1)
print('usable after polish:',len(out))
print('rejections:',dict(rej))
print('categories:',Counter(o['category'] for o in out).most_common())
