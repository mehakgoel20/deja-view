import json,re,os,hashlib
from collections import Counter
from extract3 import clean,sents,cat_of,FIX,SYMPTOM,PREVENT,CAUSE,MECHANISM,BOILER
from polish import validate
idx=json.load(open('raw/danluu_index.json'))
base=json.load(open('clean_base.json'))
have={x['source_url'].rstrip('/') for x in base}
SEV=re.compile(r'global outage|complete outage|entire|all (?:customers|users|services)|total loss|data loss|permanently lost|catastroph',re.I)
SEVH=re.compile(r'outage|unavailab|down for|could not|unable to|failed',re.I)
out=[];rej=Counter()
for key,e in idx.items():
    url=e['url']
    if url.rstrip('/') in have: rej['already_have']+=1; continue
    desc=clean(e['desc'])
    if len(desc)<60: rej['desc_thin']+=1; continue
    p=f'raw/pages/{key}.txt'
    page=open(p,errors='ignore').read() if os.path.exists(p) else ''
    ss=sents(clean(page[:30000])) if page else []
    # solution: fix sentence from page
    fx=[s for s in ss if FIX.search(s) and not PREVENT.search(s)][:2]
    if not fx: fx=[s for s in ss if FIX.search(s)][:2]
    # issue: symptom sentence from page, else synthesize from desc
    im=[s for s in ss if SYMPTOM.search(s) and not FIX.search(s) and not CAUSE.search(s) and not PREVENT.search(s)][:1]
    if not fx and not im: rej['no_page_signal']+=1; continue
    sev='Critical' if SEV.search(desc+' '+' '.join(im)) else ('High' if SEVH.search(desc+' '+' '.join(im)) else 'Medium')
    issue=im[0] if im else f"Service disruption at {e['org']} (see incident report)."
    sol=' '.join(fx) if fx else ''
    if not sol: rej['no_solution']+=1; continue
    # date from url if present
    m=re.search(r'/(20\d\d)[/-](\d{2})[/-](\d{2})',url) or re.search(r'/(20\d\d)/(\d{2})/',url)
    if m and len(m.groups())==3: date=f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    elif m: date=f"{m.group(1)}-{m.group(2)}"
    else:
        m2=re.search(r'(20\d\d)',url); date=m2.group(1) if m2 else ''
    cand={'org':e['org'],'incident_date':date,'source_url':url,'issue':issue[:400],
      'root_cause':desc[:600],'solution':sol[:600],'severity':sev,
      'category':cat_of(desc+' '+page[:6000]),'data_type':'real','provenance':'curated_index+source_page'}
    ee,why=validate(cand)
    if not ee: rej['polish:'+why]+=1; continue
    out.append(ee)
json.dump(out,open('raw/extracted_danluu.json','w'),indent=1)
print('usable:',len(out),'rejected:',dict(rej))
print('categories:',Counter(o['category'] for o in out).most_common())
print('date coverage:',Counter('has-date' if o['incident_date'] else 'NO-DATE' for o in out))
print('orgs:',len(set(o['org'] for o in out)))
