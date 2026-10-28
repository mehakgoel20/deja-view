import json,subprocess,concurrent.futures as cf,sys
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
hosts=[h.strip() for h in open('hosts13.txt') if h.strip()]
def get(h):
    try:
        r=subprocess.run(['curl','-sL','--max-time','12','--connect-timeout','5','-A',UA,
                          f'https://{h}/api/v2/incidents.json'],capture_output=True,text=True,timeout=20)
        if not r.stdout.strip().startswith('{'): return h,0,None
        j=json.loads(r.stdout); n=len(j.get('incidents',[]))
        return h,n,(j if n else None)
    except Exception: return h,0,None
found={}
done=0
with cf.ThreadPoolExecutor(70) as ex:
    for h,n,j in ex.map(get,hosts):
        done+=1
        if n: found[h]={'n':n,'raw':j}
print('probed',len(hosts),'-> live statuspages:',len(found),'incidents:',sum(v['n'] for v in found.values()))
json.dump(found,open('raw/statuspage13_raw.json','w'))
for h,v in sorted(found.items(),key=lambda kv:-kv[1]['n'])[:200]: print(f"  {v['n']:>3} {h}")
