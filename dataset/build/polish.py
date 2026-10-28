import re
JUNK_START=re.compile(r'^(?:on|at|by|from|between|during|as of|around|by approximately)\s*[,:]?\s*',re.I)
LISTTAIL=re.compile(r'(?:\b\d{1,2}\.|\b\d{1,2}\)|[:;,]|\band\b|\bthe\b|\bof\b|\bto\b|\ba\b|\ban\b)\s*$',re.I)
TIMEROW=re.compile(r'^\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\b.{0,40}[–—-]',re.I)
QUESTION=re.compile(r'\?\s*$')
HEADERY=re.compile(r'^(?:what|why|how|who|when)\b.{0,60}\?$',re.I)

def tidy(t, _rounds=4):
    """Clean text. Applied repeatedly: removing one fragment can strand another
    (dropping a timestamp leaves a dangling preposition, which the
    trailing-period rule then re-terminates), so run to a fixpoint."""
    prev = None
    for _ in range(_rounds):
        t = _tidy_once(t)
        if t == prev: break
        prev = t
    return t


def _tidy_once(t):
    if not t: return ''
    t=re.sub(r'\s+',' ',t).strip()
    # a stripped timestamp can leave a leading preposition before a
    # lowercase word: "At we observed ..."
    t=re.sub(r'^(?:At|On|From|By|Between|During|Around|Until)\s+(?=[a-z])','',t)
    t=re.sub(r'\bOn\s*,\s*','',t)
    t=re.sub(r'\bOn\s*,?\s*at\s*,\s*','',t)
    # residue left behind when timestamps were stripped, e.g. "between approximately and,"
    t=re.sub(r'\b(?:between|from)\s+(?:approximately\s+)?and\s*,?\s*','',t,flags=re.I)
    # "from to," / "between and ." - both endpoints were stripped timestamps
    t=re.sub(r'\b(?:between|from|at|on|by|during|around|until)\s+(?:approximately\s+)?(?:and|to)\s*,?\s*',' ',t,flags=re.I)
    t=re.sub(r'\bapproximately\s*(?:and|to|,)\s*','',t,flags=re.I)
    t=re.sub(r'\b(?:between|from|at|on|by|during|around)\s*,\s*','',t,flags=re.I)
    # "On at <org>" / "~ -" : both ends of a time range were stripped
    t=re.sub(r'\b(?:on|at|from|between)\s+(?:on|at|to|and)\b\s*',' ',t,flags=re.I)
    t=re.sub(r'~\s*[\u2013\u2014-]\s*',' ',t)
    # a date range whose second endpoint was stripped: "2026-04-16 to,"
    t=re.sub(r'\s+(?:to|and|until|through)\s*(?=[,.)])','',t,flags=re.I)
    t=re.sub(r'[,:]\s*~\s*(?=[.,:]|$)','',t)
    t=re.sub(r'\s*~\s*(?=[.,:]|$)','',t)
    # a time range whose endpoints were stripped leaves dashes and
    # dangling prepositions, e.g. "during two periods: -and -on."
    t=re.sub(r'(?:(?<=\s)|^)[\u2013\u2014-]\s*(?:and|to|on|at|from)\b','',t,flags=re.I)
    t=re.sub(r':\s*(?=[.,;]|$)','',t)
    t=re.sub(r'\s*\(\s*\)\s*',' ',t)
    t=t.replace('‌','').replace('​','').replace('­','')
    # markdown links and footnote refs -> their visible text
    t=re.sub(r'\[\[?ref\]?\]\([^)]*\)','',t,flags=re.I)
    t=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',t)
    t=re.sub(r'\(https?://[^)]*\)','',t)
    t=re.sub(r'https?://\S+','',t)
    # placeholder tokens and orphaned brackets left by templating / markdown
    t=re.sub(r'\[[A-Z_ ]{2,30}\]','',t)
    t=re.sub(r'^\s*[\]\)\}]\s*','',t)
    t=re.sub(r'\s*[\[\(\{]\s*$','',t)
    t=re.sub(r'[\[\]]','',t)
    # a trailing date/time fragment whose timestamp was stripped out
    t=re.sub(r'\s+on\s+\w+\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:at|by|from)\s*(?=[.,]|$)','',t,flags=re.I)
    t=re.sub(r'\s+(?:at|by|on|around|from|until)\s+approximately\s*(?=[.,]|$)','',t,flags=re.I)
    t=re.sub(r'\s+(?:on|at|by|from|between|during|around|until|through)\s*(?=[.,]|$)','',t,flags=re.I)
    t=re.sub(r'\s+([.,;:])',r'\1',t)
    t=re.sub(r'([.,;:]){2,}',r'\1',t)
    t=re.sub(r'^\W+','',t)
    t=re.sub(r'\s{2,}',' ',t).strip()
    # drop a trailing dangling clause ending in a list marker
    t=re.sub(r'(?<![\d.])\s\d{1,2}\.\s*$','',t)
    if t and t[-1] not in '.!?': t=t.rstrip(' ,;:–—-')+'.'
    # extracted sentences often begin mid-clause ("we deployed a fix ...")
    if t and t[0].islower(): t=t[0].upper()+t[1:]
    return t

def ok_sentence(t,kind):
    if not t or len(t)<45: return False
    if QUESTION.search(t) or HEADERY.match(t): return False
    if TIMEROW.match(t): return False
    if kind=='rc':
        if len(t)<70: return False
        if LISTTAIL.search(t.rstrip('.')): return False
        # a downstream-impact statement is not a root cause
        if re.search(r'(?:also|were|was) (?:impacted|affected)\b.{0,40}\bdue to (?:their|its|a) depend',t,re.I): return False
        if re.search(r'^[A-Z][\w .,&-]{0,160}\bwere also (?:impacted|affected)\b',t): return False
        # "we identified the root cause" without ever naming it is not a cause
        asserts = re.search(r'identified the (?:root )?cause|root cause (?:has been|was|is) '
                            r'(?:identified|found|determined)|(?:are|is) (?:actively )?'
                            r'working on a fix|investigating the (?:root )?cause', t, re.I)
        # A cause must be attributed to something concrete. "due to an ongoing
        # issue" is a restatement, not a mechanism, so vague objects don't count.
        names = re.search(r'\b(?:caused by|due to|because of|because|resulted from|stemmed from|'
                          r'triggered by|attributable to|as a result of|originated (?:in|from)|'
                          r'was (?:a|an|the)|were (?:a|an)|introduced (?:a|an|by))\s+'
                          r'(?:a |an |the )?'
                          r'(?:(?:ongoing|unexpected|unknown|temporary|brief|intermittent|'
                          r'minor|major|partial|recent)\s+)*'
                          r'(?!(?:issue|problem|error|outage|incident|degradation|disruption|'
                          r'fault|condition|failure|unknown|something|ongoing|unexpected|'
                          r'temporary|brief|intermittent|minor|major|partial)\b)\w{3,}', t, re.I)
        if asserts and not names: return False
        # pure impact description (duration / share of users) is not a cause
        if (re.search(r'^(?:quality |service |performance )?was degraded|'
                      r'^[^.]{0,40}\bfor a total duration of|'
                      r'^no more than \d+%|^approximately \d+% of', t, re.I)
                and not names):
            return False
        # a progress/status update is not a cause - unless it also names one
        if not names and re.search(
                r'^(?:we (?:are|have|will|continue)|the team (?:is|are|has)|'
                r'our (?:\w+ ){0,2}team (?:is|are|has)|'
                r'(?:a|the) fix (?:is|has been|will be))\b'
                r'|working with urgency|to identify the root cause|'
                r'another update|more information becomes available|'
                r'investigation (?:is|remains) (?:ongoing|underway)'
                r'|\b(?:are|is) seeing (?:gradual )?recovery|continue to monitor|'
                r'deploy(?:ing)? a fix for|working to (?:restore|resolve|identify)', t, re.I):
            return False
        # "a potential root cause", "still investigating", "current status: ..."
        # are only acceptable if the same text also names a concrete mechanism.
        hedged = re.search(
            r'identified a (?:potential|possible|likely)|(?:potential|possible) root cause'
            r'|(?:continuing|continues) to investigate|still investigating'
            r'|\bare investigating\b|investigation (?:is|remains) ongoing'
            r'|working (?:to|on) (?:implement|deploy|develop|roll out)'
            r'|working on a (?:fix|resolution)'
            r'|current status\b|currently experiencing|we are currently'
            r'|monitoring (?:the )?(?:situation|services)', t, re.I)
        if hedged and not names:
            return False
        # a contentless attribution ("due to an issue", "because of a problem")
        # is a restatement, not a cause, unless it points at something concrete
        if re.search(r'\b(?:due to|because of|owing to)\s+(?:a|an|the)\s+'
                     r'(?:issue|problem|error|fault|incident|condition)\b'
                     r'(?!\s+(?:with|in|on|at|affecting)\s+\S)', t, re.I):
            return False
        # "we observed elevated failure rates" restates the symptom
        if (re.search(r'\bwe (?:observed|saw|noticed|detected)\b', t, re.I)
                and re.search(r'elevated|increased|degraded|failure rates?|'
                              r'error rates?|latency|timeouts?', t, re.I)
                and not names):
            return False
        # retrospective framing is not a cause
        if re.search(r'reinforced the importance|highlighted the need|lessons? learned|'
                     r'\bkey takeaway|going forward we|importance of (?:clear|having)|'
                     r'underscored the', t, re.I):
            return False
        # a recovery confirmation is not a cause
        if re.search(r'operating normally|back to normal|fully restored|have been restored|'
                     r'has been resolved|returned to (?:normal|baseline)|'
                     r'confirmed that .{0,60}(?:normal|restored|resolved|healthy)|'
                     r'no further impact|services? (?:are|is) (?:now )?(?:stable|healthy)',
                     t, re.I) and not re.search(
                     r'\b(?:caused by|due to a|due to an|because|resulted from|stemmed from|'
                     r'triggered by|root cause)\b', t, re.I):
            return False
        # apology / sympathy text is not a cause
        if re.search(r'regret the inconvenience|appreciate your (?:patience|understanding)|'
                     r'value your support|we (?:deeply )?regret|we apologi[sz]e', t, re.I): return False
        # responders being paged is not a cause
        if re.search(r'\b(?:operators?|engineers?|team|on-?call|responders?)\b[^.]{0,60}'
                     r'\b(?:were|was|had been)\s+(?:already\s+)?'
                     r'(?:engaged|paged|alerted|notified|investigating|mobili[sz]ed)', t, re.I): return False
        # must read as a sentence, not a noun-phrase fragment. A verb whitelist
        # is too narrow here (causes use "allowed", "revealed", "reset",
        # "depended", ...), so require sentence shape instead.
        if len(t.split())<10: return False
        if not re.search(r'[.!?]$',t.strip()): return False
    return True

# editorial commentary from a curated index, not incident text
# Only unambiguous index-author asides. Words like "presumably" are ordinary
# descriptive prose and must not disqualify an entry.
META=re.compile(r"postmortem is (?:pretty )?thin|i'?m not sure|it sounds like|"
                r"not sure what happened|this is a (?:good|great|classic) (?:one|example)|"
                r"worth reading|^also\s+this\b|"
                r"no (?:real )?(?:postmortem|details) (?:is |are )?(?:available|published)",re.I)
# a mid-sentence fragment opens with a closing bracket
FRAGMENT=re.compile(r'^\s*[\)\]\}]')


def unbalanced(v):
    """More closers than openers means the sentence was cut mid-parenthesis."""
    return v.count(')') > v.count('(') or v.count('}') > v.count('{')
# markdown leftovers that survive tidy() and signal a mangled field
MDLEFT=re.compile(r'\[\[?ref\]?\]|\]\(')
# an impact statement masquerading as a fix
IMPACT_AS_FIX=re.compile(r'^(?:some|all|no)?\s*(?:user |customer )?data was (?:permanently )?lost'
                         r'|^[^.]{0,60}\bwas (?:unavailable|down|lost)\b[^.]{0,30}\.?$'
                         r'|^an attempt to [^.]{0,60}caused more',re.I)


def structural_ok(e):
    """Checks that apply to every entry regardless of how it was built."""
    for k in ('issue','root_cause','solution'):
        v=e.get(k) or ''
        if META.search(v): return 'editorial_commentary'
        if MDLEFT.search(v): return 'markdown_leftover'
    for k in ('issue','root_cause','solution'):
        v=e.get(k) or ''
        if FRAGMENT.match(v) or unbalanced(v): return 'sentence_fragment:'+k
    if IMPACT_AS_FIX.search(e.get('solution') or ''): return 'impact_as_solution'
    # computing-era incidents only (keeps ARPANET/Apollo, drops e.g. a 1628 shipwreck)
    y=str(e.get('incident_date',''))[:4]
    if y.isdigit() and int(y)<1960: return 'out_of_scope_era'
    return None


def validate(e):
    """returns (entry, None) or (None, reason)"""
    e=dict(e)
    for k in ('issue','root_cause','solution'):
        if k=='solution' and e.get('solution') is None:
            continue              # remediation was never published
        e[k]=tidy(e.get(k,''))
    why=structural_ok(e)
    if why: return None,why
    if not ok_sentence(e['root_cause'],'rc'): return None,'rc_invalid'
    if e.get('solution') is not None:
        sol=e['solution']
        if not ok_sentence(sol,'sol'): return None,'sol_invalid'
        # "Summary On Nov 9th the certificate was replaced with a dummy cert"
        # describes the fault, not the remediation
        if re.search(r'^(?:summary|background|timeline|what happened|'
                     r'impact summary|incident summary)\b', sol, re.I):
            return None,'sol_is_section_header'
    if len(e['issue'])<25: return None,'issue_invalid'
    # rc and solution must not be the same text
    a=re.sub(r'[^a-z0-9]','',e['root_cause'].lower())
    if e.get('solution') is not None:
        b=re.sub(r'[^a-z0-9]','',e['solution'].lower())
        if a==b or a in b or b in a: return None,'rc_eq_sol'
    # issue must not duplicate rc
    i=re.sub(r'[^a-z0-9]','',e['issue'].lower())
    if i and (i in a or a in i): return None,'issue_eq_rc'
    if not re.fullmatch(r'\d{4}(-\d{2}(-\d{2})?)?',str(e.get('incident_date',''))): return None,'bad_date'
    return e,None
