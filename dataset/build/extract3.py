import json,re,html
from collections import Counter

BOILER=re.compile(r'thank you (?:for|all)|we (?:will|\'ll) (?:continue to )?(?:monitor|provide|share|post)|we are (?:investigating|continuing|aware)|stay tuned|please (?:reach out|contact|see|re-?run)|for (?:more|further) (?:information|details)|the original (?:circleci )?status page|subscribe|next update|we apologi[sz]e|if you (?:have|continue|are still)|our (?:team|engineers) (?:is|are) (?:actively )?(?:working|investigating)|monitoring the results|incident (?:has been|is) resolved|^(?:resolved|identified|investigating|monitoring|update|scheduled|in progress|completed)\b[:\s]|all systems (?:are )?operational|service(?:s)? (?:have|has) (?:been )?(?:fully )?restored and|no further (?:action|impact)|we consider this|this incident is now closed|sincerely apologi[sz]e|we recogni[sz]e the impact|any disruption this caused|we remain committed|as always|we (?:deeply )?regret|appreciate your (?:patience|understanding|continued)|value your support|thank you again|we know (?:how|that) (?:important|frustrating)|inconvenience (?:this|caused)',re.I)
# sentences that are timeline rows or meta-structure
STRUCT=re.compile(r'\btimeline\b|\bimpact window\b|^(?:summary|background|what happened|next steps|follow-?up|remediation|action items|lessons learned|duration|services? affected|customer impact began)\b[:\s]*$|—\s*\S+\s*—',re.I)
CAUSE=re.compile(r'root cause|caused by|was caused|due to (?:a|an|the)|because of|stemmed from|resulted from|triggered by|we (?:identified|discovered|determined|found|traced|observed)|introduced (?:a|an|by)|a (?:bug|defect|regression|misconfiguration|race condition|memory leak)|misconfigur|the issue (?:was caused|originated|stemmed|resulted)|this (?:was|occurred) (?:because|when|due)|as a result of (?:a|an)|attribut\w+ to|failure of (?:a|an|the)'
 # additional attribution phrasings found in the rejected pool
 r'|\b(?:identified|determined|found|discovered) that\b'
 r'|root cause\s*[:\-]'
 r'|trace[d]? (?:back )?to\b|narrowed (?:it )?down to\b|pinpointed\b'
 r'|\b(?:a|an|the) (?:bug|defect|fault|flaw|regression|typo)\b'
 r'|\b(?:change|deploy(?:ment)?|release|update|upgrade|migration) (?:that|which)\b'
 r'|\bwhile (?:performing|running|applying|deploying|upgrading)\b'
 r'|\b(?:upstream|third[- ]party|vendor|provider|external)\b[^.]{0,60}\b(?:outage|incident|degrad\w*|failure|failed|disruption)'
 r'|\b(?:exhaust\w*|saturat\w*|overload\w*|overwhelm\w*)\b'
 r'|\blimit (?:was )?(?:reached|hit|exceeded)\b'
 r'|\b(?:certificate|token|credential|lease|license)s? (?:had )?expir\w+'
 ,re.I)
# a root cause must name a mechanism, not just assert one was found
VACUOUS=re.compile(r'^(?:we have |we )?(?:identified|determined|found|discovered|isolated)(?: the)? (?:root )?cause(?: of[^.]{0,40})?(?: and| ,|,|\.|$)|root cause (?:has been|was) identified|we (?:have )?(?:now )?identified the (?:issue|problem|source)|cause (?:is|has been) (?:under|identified)',re.I)
MECHANISM=re.compile(r'config|deploy|releas|migrat|schema|index|quer|database|replica|shard|cache|dns|route|routing|network|load balanc|certificat|tls|ssl|token|auth|permission|quota|rate limit|throttl|capacity|memory|disk|cpu|leak|deadlock|race|lock|timeout|bug|defect|regression|upgrade|patch|version|dependenc|api|queue|worker|pod|node|server|host|cluster|provider|vendor|upstream|firewall|proxy|saturat|exhaust|overload|surge|spike|volume|traffic|limit|threshold|expir|credential|secret|key|flag|code change|data type|null|validation|queu|sqs|kafka|kinesis|pubsub|\bs3\b|storage|pipeline|job|cron|scheduler|gateway|ingress|egress|dependenc|librar|package|parameter|field|serializ|encod|retry|backoff|circuit break|poll|webhook|volume|container|kubernetes|k8s|autoscal|instance|region|availability zone|provider|third[- ]party|rollout|build|artifact|binar|thread|process|garbage collect|connection|socket|handshake|header|payload|request|response|endpoint|service discovery|dns record|zone file|acl|iam|role|policy|scope|session|cookie|crawler|bot|waf|ruleset|lua|script|sql|orm|lock|transaction|isolation|checkpoint|snapshot|backup|restore|failover|quorum|leader|election|consensus|heartbeat|health check|probe|timeout|limit|threshold|bound|overflow|underflow|rounding|precision|unicode|utf|charset|locale|timezone|leap|clock|ntp|drift',re.I)
FIX=re.compile(r'\b(?:we )?(?:rolled back|reverted|redeployed|deployed a fix|applied a fix|restored|mitigated|patched|corrected|disabled|re-?enabled|scaled (?:up|out|back)|failed over|restarted|cleared|rebuilt|rotated|increased (?:capacity|the limit|limits)|remediated|resized|removed|replaced|drained|suspended|throttled|reprocessed|replayed|backfilled)\b'
 r'|fix (?:was|has been) (?:deployed|applied|released|rolled out)'
 r'|mitigated by|resolved by|was addressed by|to prevent (?:this|recurrence|similar)'
 r'|we (?:are|have) (?:added|adding|implemented|implementing) (?:additional |)(?:monitoring|alerting|validation|safeguards|quotas|guardrails)'
    # additional remediation phrasings measured in the rejected pool
 r'|\b(?:re-?deployed|rolled forward|switched (?:over|back|to)|migrated|rebalanced|reindexed|purged|flushed|invalidated|upgraded|downgraded|reconfigured|retuned|provisioned|rebooted|power[- ]?cycled|failed back|re-?ran|re-?queued|re-?synced|resynchronised|resynchronized)\b'
 r'|\b(?:brought|returned)\s+(?:it\s+|them\s+|the\s+\w+\s+)?back\s+(?:online|into service|up)\b'
 r'|\breturned to (?:service|normal operation)\b'
 r'|\b(?:service|services|functionality|operations?) (?:was|were|has been|have been) (?:fully )?(?:restored|recovered|re-?established)\b'
 r'|\b(?:issue|incident|problem) (?:was|has been) (?:resolved|fixed|mitigated|corrected)\b'
 r'|\bresolved (?:the|this) (?:issue|incident|problem)\b'
 r'|\bworkaround (?:was|has been) (?:applied|deployed|put in place)\b'
 r'|\b(?:added|raised|lowered|adjusted|tuned|expanded|extended) (?:the )?(?:capacity|limit|limits|quota|quotas|timeout|timeouts|threshold|thresholds|headroom|instances|replicas|shards|workers|nodes)\b'
 # passive voice: "capacity was expanded", "thresholds were raised"
 r'|\b(?:capacity|limits?|quotas?|timeouts?|thresholds?|headroom|instances|replicas|shards|workers|nodes) (?:was|were|has been|have been) (?:added|raised|increased|expanded|extended|adjusted|tuned|provisioned)\b'
 ,re.I)
PREVENT=re.compile(r'conducting a (?:thorough )?review|we are reviewing|we will be reviewing|thorough review of|to (?:reduce|prevent|avoid) (?:the )?(?:likelihood|risk|recurrence|impact)|going forward|in the future|follow-?up (?:work|items)|we (?:are|will be) (?:adding|improving|implementing)|action items|lessons',re.I)
SYMPTOM=re.compile(r'customers? (?:experienc|were unable|saw|may have|encountered|reported|could not)|users? (?:experienc|were unable|saw|may have|could not)|(?:experienced|observed|saw) (?:elevated|increased|degraded|high|intermittent|partial)|unable to (?:log|sign|access|load|connect|create|view|send)|failed to (?:load|start|process|deliver|complete)|elevated (?:error|latency|failure)|increased (?:error|latency)|error rates?|unavailab|outage|degrad|timeouts?|slow|not (?:load|work|avail|process)|downtime|interrupt|disrupt',re.I)

def clean(t):
    t=html.unescape(t or '')
    t=re.sub(r'\\([()\[\]*_#>`~.+-])',r'\1',t)
    t=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',t)
    t=re.sub(r'https?://\S+','',t)
    t=re.sub(r'#{1,6}\s*','',t); t=re.sub(r'\*\*|__|\*|`','',t)
    t=re.sub(r'\|\|',' ',t)
    t=re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:UTC|utc|GMT|am|pm|AM|PM)?\b','',t)
    t=re.sub(r'\b\d{1,2}\.\d{2}\s*(?:UTC|utc|GMT|am|pm|AM|PM)\b','',t)
    t=re.sub(r'\b(?:from|between|at|until|to)\s+\d{1,2}\.\d{2}\b','',t,flags=re.I)
    t=re.sub(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4}\b','',t)
    t=re.sub(r'\bBetween\s+(?:and|to)\s+','',t)
    t=re.sub(r'\b(?:between|from|at|by|on|until)\s+(?:and|to)\s+',' ',t,flags=re.I)
    t=re.sub(r'\b(?:PDT|PST|EDT|EST|CET|CEST|UTC|GMT)\b','',t)
    t=re.sub(r'\bon\s*,','',t); t=re.sub(r'\s+,',',',t)
    t=re.sub(r'\(\s*\)','',t); t=re.sub(r'\s*,\s*,',',',t)
    t=re.sub(r'\b\d{4}-\d{2}-\d{2}\s*[-–—]\s*','',t)
    t=re.sub(r'\s{2,}',' ',t)
    return t.strip()

def sents(t):
    # cut everything from a Timeline header onward if it is mostly rows
    m=re.search(r'\bTimeline\b',t,re.I)
    body=t[:m.start()] if m and m.start()>200 else t
    tail=t[m.start():] if m and m.start()>200 else ''
    out=[]
    for chunk in (body,tail):
        for s in re.split(r'(?<=[.!?])\s+|\s+•\s+',chunk):
            s=s.strip(' -*•\t|–—')
            if len(s)<45 or len(s)>400: continue
            if BOILER.search(s) or STRUCT.search(s): continue
            if s.count(':')>2: continue
            if sum(ch.isdigit() for ch in s)>len(s)*0.18: continue
            if s.lower().startswith(('timeline','at ','by ','from ')) and sum(ch.isdigit() for ch in s)>6: continue
            out.append(s)
    seen=set(); ded=[]
    for s in out:
        k=s.lower()[:70]
        if k in seen: continue
        seen.add(k); ded.append(s)
    return ded

CAT=[('memory_leak',r'memory leak|out of memory|\boom\b|heap (?:growth|exhaust)|memory (?:growth|exhaustion|pressure|fragmentation)|memory usage (?:grew|climb|increas)'),
 ('concurrency_race_condition',r'race condition|deadlock|lock contention|semaphore|livelock|mutex|thread (?:pool )?(?:exhaust|starv)|lock (?:wait|timeout)|concurren\w+ (?:bug|issue)'),
 ('security_incident',r'security (?:incident|vulnerabilit)|unauthori[sz]ed access|breach|cve-\d|exploit|compromis|malicious|\bddos\b|denial of service|credential (?:leak|theft|expos)'),
 ('payment_processing',r'payment|payout|transaction(?:s)? (?:fail|declin|delay)|card (?:auth|network|issu)|billing|invoice|settlement|refund|\bach\b|direct debit|charge(?:s|d)? (?:fail|declin)'),
 ('authentication',r'authenticat|unable to log ?in|sign-?in|\bsso\b|\bsaml\b|oauth|\bmfa\b|session (?:token|cookie)|authori[sz]ation|access token|api (?:key|token)'),
 ('networking_dns',r'\bdns\b|resolver|\bbgp\b|routing|network (?:connectivity|partition|path|configuration)|load balanc|tls (?:handshake|certificate)|packet loss|\bcdn\b|anycast|firewall|proxy'),
 ('database_issue',r'database|postgres|mysql|replica(?:tion)?|quer(?:y|ies)|\bindex(?:es)?\b|schema (?:change|migration)|table lock|shard|redis|cassandra|mongo|connection pool'),
 ('configuration_deployment',r'deploy|rollout|roll(?:ed)? out|configuration change|misconfigur|feature flag|releas|rollback|helm|terraform|code change|upgrade|version bump'),
 ('api_latency',r'latency|slow(?:ness|down)|timeout|elevated (?:error|response)|throttl|rate limit|degraded performance|p9\d|queue (?:backlog|depth)|saturat|capacity'),
 ('hardware_infra',r'hardware|disk (?:fail|full|space)|power (?:loss|outage|failure)|data ?cent(?:er|re)|physical (?:host|server)|node fail|host (?:fail|degrad)|upstream (?:provider|vendor)|cloud provider|availability zone|third[- ]party (?:hosting |cloud |infrastructure )?(?:provider|vendor|host)|hosting provider|provider (?:experienced|suffered|had) an (?:outage|incident)|upstream (?:outage|incident|failure)|our (?:cloud |infrastructure )?provider|(?:aws|azure|gcp|google cloud|amazon web services) (?:outage|incident|degradation)|colocation|fiber cut|transit provider|power (?:failure|event)'),
]
SEVMAP={'critical':'Critical','major':'High','minor':'Medium','none':'Low'}
def cat_of(t):
    tl=t.lower(); best=('other',0)
    for n,p in CAT:
        k=len(re.findall(p,tl))
        if k>best[1]: best=(n,k)
    return best[0]

def build(rec,org,date,url,name,impact,require_fix=True):
    full=clean(rec)
    ss=sents(full)
    if len(ss)<2: return None,'too_few_sentences'
    used=set()
    rc=[]
    # (a) explicit "Root cause" / "What caused it" section: take that sentence + the next
    for i,s in enumerate(ss):
        # must be a root-cause STATEMENT, not a passing mention
        # ("a fix for the root cause" is not an attribution)
        if re.search(r'^\s*root cause\b|\broot cause (?:was|is|of (?:the|this)[^.]{0,40}(?:was|is)|:|[-–—])'
                     r'|\bwhat caused it\b|\bcause of the (?:incident|outage|issue) (?:was|is)\b',s,re.I):
            if PREVENT.search(s): continue
            cand=[s]
            if not MECHANISM.search(s) and i+1<len(ss) and MECHANISM.search(ss[i+1]) and not PREVENT.search(ss[i+1]):
                cand.append(ss[i+1])
            if MECHANISM.search(' '.join(cand)):
                rc=cand; used|=set(cand); break
    # (b) causal sentence; if it lacks a mechanism, borrow the following sentence
    if not rc:
        for i,s in enumerate(ss):
            if not CAUSE.search(s) or PREVENT.search(s): continue
            if VACUOUS.search(s) and not MECHANISM.search(s):
                if i+1<len(ss) and MECHANISM.search(ss[i+1]) and not PREVENT.search(ss[i+1]) and not FIX.search(ss[i+1]):
                    rc=[s,ss[i+1]]; used|=set(rc); break
                continue
            if MECHANISM.search(s):
                cand=[s]
                if len(s)<110 and i+1<len(ss) and MECHANISM.search(ss[i+1]) and not PREVENT.search(ss[i+1]) and not FIX.search(ss[i+1]):
                    cand.append(ss[i+1])
                rc=cand; used|=set(cand); break
            if i+1<len(ss) and MECHANISM.search(ss[i+1]) and not PREVENT.search(ss[i+1]) and not FIX.search(ss[i+1]):
                rc=[s,ss[i+1]]; used|=set(rc); break
    if not rc: return None,'no_root_cause'
    if len(' '.join(rc))<70: return None,'rc_too_short'
    # solution: fix language, prefer non-prevention first
    fx=[s for s in ss if s not in used and FIX.search(s) and not PREVENT.search(s)][:2]
    if not fx: fx=[s for s in ss if s not in used and FIX.search(s)][:2]
    if not fx:
        if require_fix: return None,'no_solution'
        fx=[]                      # cause-only entry; solution stays unpublished
    used|=set(fx)
    # issue: symptom sentence, not a fix/prevention sentence
    im=[s for s in ss if s not in used and SYMPTOM.search(s) and not FIX.search(s) and not PREVENT.search(s) and not CAUSE.search(s)][:1]
    nm=re.sub(r'^\s*\[(?:minor|major|critical|medium|high|low|resolved|maintenance)\]\s*','',clean(name),flags=re.I)
    issue=f"{nm}. {im[0]}" if im else nm
    if len(issue)<25: return None,'issue_too_short'
    def ddup(lst):
        o=[];seen=set()
        for x in lst:
            k=re.sub(r'[^a-z0-9]','',x.lower())[:60]
            if k in seen: continue
            seen.add(k); o.append(x)
        return o
    rc=ddup(rc); fx=ddup(fx)
    return {'org':org,'incident_date':date,'source_url':url,
      'issue':issue[:400],'root_cause':' '.join(rc)[:600],
      'solution':(' '.join(fx)[:600] if fx else None),
      'severity':SEVMAP.get(impact,'Medium'),'category':cat_of(full),
      'data_type':'real','provenance':'statuspage_postmortem'},None

if __name__=='__main__':
    raw=json.load(open('raw/sp_candidates.json'))
    base=json.load(open('clean_base.json'))
    have={x['source_url'].rstrip('/') for x in base}
    raw=[x for x in raw if x['url'].rstrip('/') not in have]
    out=[];rej=Counter()
    for x in raw:
        e,why=build(x['postmortem'] if x['postmortem'] else x['body'],x['org'],
                    (x['created_at'] or '')[:10],x['url'],x['name'],x['impact'])
        if e: out.append(e)
        else: rej[why]+=1
    json.dump(out,open('raw/extracted.json','w'),indent=1)
    print('usable:',len(out),' rejected:',sum(rej.values()),dict(rej))
    print('orgs:',len(set(o['org'] for o in out)))
    print('categories:',Counter(o['category'] for o in out).most_common())
