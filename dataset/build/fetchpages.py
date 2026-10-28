import json,subprocess,concurrent.futures as cf,re,html,os,hashlib
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
ents=json.load(open('raw/danluu_entries.json'))
def totext(h):
    h=re.sub(r'(?is)<(script|style|nav|header|footer|svg|noscript)[^>]*>.*?</\1>',' ',h)
    h=re.sub(r'(?s)<!--.*?-->',' ',h)
    h=re.sub(r'<br\s*/?>|</p>|</div>|</li>|</h[1-6]>','\n',h,flags=re.I)
    t=re.sub(r'<[^>]+>',' ',h); t=html.unescape(t)
    t=re.sub(r'[ \t]+',' ',t); t=re.sub(r'\n\s*\n+','\n',t)
    return t.strip()
def one(e):
    key=hashlib.md5(e['url'].encode()).hexdigest()[:16]
    p=f'raw/pages/{key}.txt'
    if os.path.exists(p) and os.path.getsize(p)>500: return e['url'],'cached',os.path.getsize(p)
    try:
        r=subprocess.run(['curl','-sL','--max-time','35','--connect-timeout','10','-A',UA,e['url']],
                         capture_output=True,text=True,timeout=55,errors='ignore')
        t=totext(r.stdout)
        if len(t)<400: return e['url'],'thin',len(t)
        open(p,'w').write(t[:60000]); return e['url'],'ok',len(t)
    except Exception as ex: return e['url'],'err',0
res=[]
with cf.ThreadPoolExecutor(25) as ex:
    for u,s,n in ex.map(one,ents): res.append((u,s,n))
from collections import Counter
print(Counter(s for _,s,_ in res).most_common())
json.dump({hashlib.md5(e['url'].encode()).hexdigest()[:16]:e for e in ents},open('raw/danluu_index.json','w'),indent=1)
