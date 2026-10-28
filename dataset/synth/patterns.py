"""Failure patterns for synthetic RCA generation.

Each pattern bundles a symptom, the mechanism that explains it, and a fix that
addresses that mechanism, so every generated entry is internally coherent:
the root cause actually accounts for the issue, and the solution actually
targets the root cause. Slots in {braces} are filled from vocab.SLOTS and stay
consistent within a single entry.

Target field lengths mirror the gold set (issue ~126, root_cause ~171,
solution ~158 characters).
"""

P = {}

# ----------------------------------------------------- configuration_deployment
P['configuration_deployment'] = [
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "{surface} began returning errors for {pct} of requests minutes after a routine deploy, with no code change to {svc} itself.",
        "Requests to {svc} failed across {env} immediately following a scheduled configuration rollout.",
     ],
     'cause': [
        "A configuration change intended for one environment was applied to {env} because the rollout tooling resolved the target by name prefix rather than exact match, so {svc} started with settings it could not validate.",
        "A release changed a default in the shared configuration bundle for {svc}. The new default disagreed with {comp}, which rejected every request it could not map to a known setting.",
     ],
     'fix': [
        "Rolled the configuration bundle back to the previous known-good revision, which restored {svc} within minutes, then changed the rollout tooling to require an exact environment match before applying.",
        "Reverted the changed default and added a pre-apply validation step that rejects a configuration bundle {comp} cannot parse before it reaches {env}.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "New deployments of {svc} hung in a pending state for {dur}, and no new instances joined the pool.",
        "{svc} could not scale out during a traffic increase even though spare capacity was available in {region}.",
     ],
     'cause': [
        "A resource request in the deployment manifest for {svc} was raised past what any node in {region} could satisfy, so the scheduler had nowhere to place new instances and left them pending indefinitely.",
        "An admission policy added earlier in the week required a label that the deployment template for {svc} did not set, so {comp} silently rejected every new instance.",
     ],
     'fix': [
        "Lowered the resource request back to a schedulable value and added a check that fails the pipeline when a request exceeds the largest available node in the target region.",
        "Added the required label to the deployment template and changed {comp} to surface rejected instances as a deploy failure instead of leaving them pending without an alert.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "A feature intended for internal testing became active for {pct} of customers on {surface} without an announcement.",
        "{pct} of users on {surface} saw an unreleased interface for {dur} before it was withdrawn.",
     ],
     'cause': [
        "A feature flag for {svc} was created with a default-on value rather than default-off. The flag service treats an absent per-tenant override as the default, so every tenant without an explicit override received the new behaviour.",
        "A targeting rule meant to match a single internal tenant used a prefix comparison, so it matched a large set of production tenant identifiers that shared the same prefix.",
     ],
     'fix': [
        "Set the flag to default-off and re-enabled it only for the intended internal tenants, then made the flag service require an explicit default at creation time.",
        "Corrected the targeting rule to an exact-match comparison and added a dry-run report that lists which tenants a rule will match before it is saved.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "A rollback intended to resolve an earlier problem with {svc} made the incident worse and extended impact by {dur}.",
        "Reverting a deploy of {svc} did not restore service and left {store} in a state neither version could read.",
     ],
     'cause': [
        "The deploy had already written records to {store} in a new format. Rolling the code back left the older version reading rows it had no schema for, so {svc} failed on a larger share of requests than before the rollback.",
        "The forward deploy performed a one-way data change in {store}, so the previous release could not interpret rows written after the cutover and rejected them during normal reads.",
     ],
     'fix': [
        "Rolled forward to a build that tolerated both record formats, backfilled the affected rows, and added a rule that a deploy touching a stored format must ship its reader before its writer.",
        "Deployed a reader that accepted both formats, reconciled the affected rows in {store}, and made backward-incompatible data changes require a two-phase rollout.",
     ]},
    {'sev': {'Critical': 1, 'High': 2, 'Medium': 4, 'Low': 3},
     'issue': [
        "{svc} ran with configuration from the previous release for {dur} even though the deploy reported success.",
        "A configuration change applied cleanly but had no effect on the behaviour of {svc} in {env}.",
     ],
     'cause': [
        "The configuration was delivered to {comp} but {svc} reads its settings only at process start, and the rollout did not restart the running instances, so they continued serving with the previous values.",
        "The change was written to a configuration path that {svc} stopped reading in an earlier refactor. Nothing validated that the path was still consumed, so the apply reported success while changing nothing.",
     ],
     'fix': [
        "Restarted the affected instances to pick up the new configuration, then added a post-apply check that reads the live value back from each instance before the rollout is marked complete.",
        "Pointed the change at the configuration path {svc} actually reads and added a test that fails when a documented setting is not consumed by the service that owns it.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Legitimate traffic to {surface} was blocked for {dur} with no recent deploy to explain it.",
        "{pct} of requests to {svc} were rejected at the edge while the service itself reported healthy.",
     ],
     'cause': [
        "A filtering rule was changed directly on the edge tier outside the normal pipeline, so the change did not appear in deployment history. Responders spent most of the incident examining recent releases before drift detection surfaced the untracked edit.",
        "A protective rule intended to block a single abusive client was written with a pattern broad enough to match normal traffic to {svc}, and the rule applied to {env} rather than a single tenant.",
     ],
     'fix': [
        "Reverted the out-of-band edge change and restricted write access so edits outside the pipeline are blocked, with drift detection alerting on any that still occur.",
        "Narrowed the rule to the intended client, scoped it to a single tenant, and added a staged rollout for edge filtering changes with an automatic revert on a traffic drop.",
     ]},
    {'sev': {'Critical': 2, 'High': 3, 'Medium': 4, 'Low': 1},
     'issue': [
        "{svc} failed to start in {region} after a dependency upgrade, and {pct} of requests to {surface} returned errors.",
        "A routine library upgrade left {svc} unable to serve traffic in {env}.",
     ],
     'cause': [
        "A transitive dependency was upgraded across a minor version that changed a default serialisation setting. {comp} had relied on the previous default, so it could no longer read payloads written by its own earlier version.",
        "A dependency upgrade removed a method {comp} still called. The build succeeded because the call sits on a path exercised only at runtime, so the failure appeared first in {env}.",
     ],
     'fix': [
        "Pinned the dependency to the previous version to restore service, then updated {comp} to set the serialisation option explicitly rather than relying on a library default.",
        "Rolled back the upgrade, added the missing call path to the integration test suite, and enabled dependency pinning with an explicit review step for minor-version bumps.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} was removed from rotation in {region} despite being healthy, dropping capacity by {pctn}.",
        "Healthy instances of {svc} were ejected from the load balancer pool over a {dur} window.",
     ],
     'cause': [
        "A configuration change altered how {svc} responded to health probes. The response was still successful but no longer matched the string {comp} expected, so every instance was marked unhealthy and pulled from rotation.",
        "An outlier-detection threshold was tightened so a single transient error was enough to eject an instance, and no cap limited how much of the fleet could be removed at once.",
     ],
     'fix': [
        "Reverted the health-probe change so responses matched again, and decoupled the probe contract from the response body so a formatting change cannot mark a healthy instance down.",
        "Restored the previous thresholds and added a ceiling on the share of a fleet that outlier detection may eject at one time.",
     ]},
]

# ------------------------------------------------------------- database_issue
P['database_issue'] = [
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "Queries against {tbl} slowed from milliseconds to several seconds, and {svc} began timing out for {pct} of requests.",
        "{svc} degraded sharply with no deploy to explain it, and {metric} on {store} rose steadily for {dur}.",
     ],
     'cause': [
        "A schema migration on {tbl} was applied as a drop-then-create rather than a single modification. For the window where the index did not exist, queries that depended on it fell back to full scans and saturated {store}.",
        "A new query against {tbl} shipped without a supporting index. Volume was low enough in testing to hide the cost, but at production volume each call scanned the whole table and exhausted the read capacity of {store}.",
     ],
     'fix': [
        "Recreated the index to restore query plans, then changed the migration tool to treat an index modification as one atomic operation instead of a drop followed by a create.",
        "Added the supporting index and introduced a review step that rejects a new query path without an index backing its filter columns.",
     ]},
    {'sev': {'Critical': 3, 'High': 4, 'Medium': 2, 'Low': 1},
     'issue': [
        "{svc} was unavailable for {dur} and some records written shortly before the incident could not be recovered.",
        "{store} became unreachable and recovery required restoring from an older snapshot than expected.",
     ],
     'cause': [
        "A maintenance procedure intended to clear a lagging replica was executed against the primary node of {store}. Snapshot jobs had been failing silently for weeks, so the newest usable backup was considerably older than the retention policy implied.",
        "A cleanup task matched on a hostname pattern that also matched the primary node of {store}. Nothing required a second approval for a destructive operation, so it ran unchecked.",
     ],
     'fix': [
        "Restored from the newest usable snapshot, accepting the resulting data loss, then required a second engineer to confirm any destructive database operation and added alerting on backup success rather than only on failure.",
        "Rebuilt the primary from a replica, added an explicit allow-list for destructive automation, and introduced regular restore drills to verify snapshots are usable.",
     ]},
    {'sev': {'Critical': 1, 'High': 4, 'Medium': 4, 'Low': 1},
     'issue': [
        "Writes to {tbl} began failing with a constraint error, blocking new records in {svc} for {dur}.",
        "{svc} could not create new records, returning a database-level error unrelated to any application change.",
     ],
     'cause': [
        "A foreign key column on {tbl} was declared with a narrower integer type than the primary key it referenced. Once the referenced values exceeded the narrower range, every insert failed with an overflow.",
        "A uniqueness constraint added to {tbl} during a migration did not account for historical rows that legitimately shared a value, so inserts touching those keys were rejected.",
     ],
     'fix': [
        "Widened the foreign key column to match the referenced key and added a schema check that compares column types across a reference before a migration is accepted.",
        "Dropped the constraint, de-duplicated the historical rows, and re-applied it as a partial constraint scoped to records created after the cutover.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Reads from {svc} returned stale data for {dur} while writes continued to succeed normally.",
        "{pct} of reads served by {svc} reflected data minutes behind the primary.",
     ],
     'cause': [
        "Replication from the primary to the read replicas in {store} stalled without raising an error. Monitoring tracked replica availability but not replication lag, so the stall was invisible until customers reported inconsistency.",
        "A long-running analytical query held a lock that blocked replication apply on {store}, so replicas stayed available while falling progressively further behind.",
     ],
     'fix': [
        "Restarted replication to clear the stall and added an explicit lag metric with alerting, rather than treating replica availability as a proxy for freshness.",
        "Terminated the blocking query, moved analytical workloads to a dedicated replica, and added a lag threshold that removes a replica from the read pool automatically.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} exhausted its database connections during a traffic increase and rejected {pct} of requests.",
        "Requests to {svc} queued and timed out while {store} itself remained lightly loaded.",
     ],
     'cause': [
        "A code change moved connection acquisition outside the request scope, so connections were held for the lifetime of a worker instead of a single query. The pool reached {limit} well below the load it had previously handled.",
        "The connection pool for {svc} was sized for a previous instance count. After a scale-out, the combined pools exceeded what {store} would accept and new connections were refused.",
     ],
     'fix': [
        "Returned connection acquisition to request scope so connections are released promptly, and added a pool-saturation metric with alerting before exhaustion.",
        "Reduced the per-instance pool size so the fleet total stays within the server limit, and tied pool sizing to instance count rather than a fixed value.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Background jobs in {svc} stopped being picked up after a deploy, and a backlog of {num} thousand items accumulated.",
        "{svc} stopped processing queued work silently; no errors were logged for {dur}.",
     ],
     'cause': [
        "A deploy changed the stored type of a field in {tbl}. Rows written before and after the change had different types, and the strict validation in {comp} rejected every row it scanned, so it stopped claiming work without reporting an error.",
        "A migration renamed a column {comp} selects on. The query returned an empty result rather than failing, so the dispatcher concluded there was no work to do.",
     ],
     'fix': [
        "Shipped a build that tolerated both field types, drained the backlog with temporary additional capacity, and changed {comp} to treat an unreadable row as an error rather than a skip.",
        "Restored the expected column name, replayed the backlog, and added an alert on a dispatcher reporting zero available work while the queue is non-empty.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "A migration on {tbl} that had run cleanly for weeks caused a sharp availability drop in its final step.",
        "{svc} availability fell by {pctn} during the last stage of a long-running schema change.",
     ],
     'cause': [
        "The final rename step of the migration took a lock that conflicted with ongoing reads on a large share of the replicas in {store}. The affected replicas entered recovery, which pushed their load onto the remainder and cascaded into a broader capacity shortfall.",
        "The concluding step rewrote {tbl} in place rather than swapping a prepared copy, so every replica applied the rewrite simultaneously and fell out of the read pool together.",
     ]
     ,
     'fix': [
        "Recovered the affected replicas and restored capacity, then changed the final migration step to swap a prepared table rather than take a conflicting lock.",
        "Brought replicas back in a staggered sequence and reworked the migration to apply the final step to one replica at a time.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{metric} on {store} rose steadily over {dur} and {svc} began shedding requests, with no change in traffic volume.",
        "{svc} degraded gradually rather than failing outright, and {pct} of queries exceeded their timeout.",
     ],
     'cause': [
        "An index on {tbl} concentrated a frequently-read key range onto a small number of shards in {store}. A short cache expiry forced frequent refreshes, so read contention on those shards grew disproportionately as traffic rose.",
        "A query plan on {tbl} flipped from an index scan to a sequential scan once the table crossed a size threshold, and the planner had no statistics recent enough to choose correctly.",
     ],
     'fix': [
        "Redistributed the hot key range across more shards and lengthened the cache expiry to cut refresh frequency, which brought read contention back to normal.",
        "Refreshed planner statistics and added a hint pinning the intended index, with a scheduled statistics job to prevent the plan from flipping again.",
     ]},
]

# ----------------------------------------------------------------- api_latency
P['api_latency'] = [
    {'sev': {'Critical': 1, 'High': 4, 'Medium': 4, 'Low': 1},
     'issue': [
        "{metric} on {svc} rose from normal to several seconds, and {pct} of calls to {surface} exceeded their timeout.",
        "Callers of {svc} saw response times multiply for {dur} under ordinary traffic.",
     ],
     'cause': [
        "A traffic increase coincided with a reduced number of available workers in {svc}. As requests queued, client retries added further load to the same saturated path and amplified the delay well beyond the original shortfall.",
        "{comp} began synchronously calling {dep} on a path that had previously been asynchronous. Each request inherited the dependency latency, and the thread pool filled with waiting work.",
     ],
     'fix': [
        "Restored worker capacity and separated retry traffic from first-attempt requests so a retry storm can no longer crowd out new work, then added backoff with jitter on the client.",
        "Moved the call to {dep} back off the request path, added a timeout and circuit breaker around it, and sized the thread pool against measured dependency latency.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} slowed progressively over {dur}, with {metric} degrading while CPU and memory stayed within normal bounds.",
        "Latency on {surface} crept upward across the day with no corresponding rise in traffic.",
     ],
     'cause': [
        "A cache in front of {store} was configured with an expiry short enough that most reads missed. Each miss fell through to {store}, so the cache added overhead without absorbing load.",
        "A cache key for {svc} included a request-unique value, so entries were never reused and every call was effectively a cold read against {store}.",
     ],
     'fix': [
        "Lengthened the cache expiry to a value matched to how often the underlying data actually changes, which raised the hit rate and returned latency to normal.",
        "Removed the request-unique component from the cache key so entries are shared across equivalent requests, and added a hit-rate metric with alerting.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Calls to {svc} were rate-limited far more often than usual after a maintenance window, affecting {pct} of clients.",
        "{pct} of API clients received throttling responses from {svc} despite being well under their quota.",
     ],
     'cause': [
        "Maintenance on the token service changed how {comp} identified a caller. Requests that previously counted against a per-tenant quota began counting against a single shared bucket, so unrelated clients exhausted each other's allowance.",
        "A rate-limit counter was keyed on a value that reset during the maintenance window, so {comp} treated long-standing clients as new and applied the stricter unestablished-client limit.",
     ],
     'fix': [
        "Restored per-tenant identification in {comp} so quotas are counted separately again, and added an alert on a sudden rise in throttling rate rather than relying on customer reports.",
        "Re-seeded the counters from the previous values and changed the limiter to fail open for established clients when its key is missing.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "{svc} returned elevated errors for {dur} after a sudden increase in inbound volume.",
        "A traffic spike on {surface} pushed {svc} past its capacity and {pct} of requests failed.",
     ],
     'cause': [
        "Incoming volume rose sharply and {svc} had no admission control, so it accepted more work than it could complete. Queues grew past {limit} and requests began failing after already consuming capacity.",
        "A single tenant sent a concentrated burst that saturated a shared worker pool. Nothing isolated tenants from one another, so the burst degraded {svc} for every caller.",
     ],
     'fix': [
        "Added admission control so {svc} rejects work it cannot complete within its deadline instead of accepting and failing it, and provisioned headroom for bursts of this size.",
        "Introduced per-tenant concurrency limits so one caller's burst cannot consume the shared pool, and added autoscaling keyed on queue depth.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} became slow in {region} only, while the same service performed normally elsewhere.",
        "Latency on {svc} was {pctn} higher in one region for {dur} with no configuration difference.",
     ],
     'cause': [
        "Instances of {svc} in {region} were routed to {store} in a different region after a failover, so every query crossed a regional boundary and paid the round-trip cost.",
        "A capacity reduction in {region} left {svc} running on fewer instances than its load required, and the regional router continued sending a full share of traffic.",
     ],
     'fix': [
        "Repointed {svc} at the local replica of {store} and added an alert when a service's data path crosses a region boundary unexpectedly.",
        "Restored the instance count in {region} and changed the router to weight traffic by healthy capacity rather than by a fixed regional share.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{surface} became slow for {pct} of users while backend services reported normal {metric}.",
        "Users reported {svc} being unresponsive although every backend dashboard looked healthy.",
     ],
     'cause': [
        "A client-side change in {surface} issued one request per item rather than a single batched call. Each individual request was fast, so backend metrics stayed normal while the aggregate page load grew to several seconds.",
        "{surface} began requesting an uncached resource on every navigation. Server-side timings remained flat because the cost was in the number of round trips rather than in any single response.",
     ],
     'fix': [
        "Restored the batched call so a page issues one request instead of many, and added a client-side latency metric so user-visible slowness is visible even when backend timings look normal.",
        "Made the resource cacheable with an appropriate expiry and added synthetic monitoring that measures end-to-end page load rather than only server response time.",
     ]},
]

# -------------------------------------------------------------- networking_dns
P['networking_dns'] = [
    {'sev': {'Critical': 3, 'High': 4, 'Medium': 2, 'Low': 1},
     'issue': [
        "Internal name resolution failed across {env} and services could no longer reach one another for {dur}.",
        "{pct} of service-to-service calls failed with resolution errors after an infrastructure change.",
     ],
     'cause': [
        "A DNS configuration change was deployed to the infrastructure hosting {env}. The defect was not caught in pre-production because the test environment resolved names through a different path, so it first appeared in production.",
        "Two automation components raced to update the same DNS record for {svc} and overwrote each other, ultimately leaving the record empty. Everything that depended on that name began failing resolution.",
     ],
     'fix': [
        "Rolled the DNS configuration change back to restore resolution, then extended pre-production testing to exercise the same resolution path used in production.",
        "Restored the records manually and disabled the conflicting automation until it was serialised behind a single writer with a lock.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "Resolution for {svc} failed intermittently for {pct} of clients, and the first remediation attempt made it worse.",
        "Name lookups for {surface} returned errors for {dur}, with a period of total failure during recovery.",
     ],
     'cause': [
        "A script restarted only the authoritative resolver after an address change and left the caching resolver untouched, so cached lookups began timing out. The subsequent repair rebuilt the zone using a tool that itself depended on working DNS, producing a zone that returned not-found for many names.",
        "A zone update removed a record set that {svc} still relied on. Negative responses were cached downstream, so the failure persisted after the record was restored.",
     ],
     'fix': [
        "Rebuilt and republished a correct zone by hand, restarted both resolvers, and added a rule that DNS-dependent tooling may not be used to repair a DNS outage.",
        "Restored the record set and shortened the negative-response cache lifetime so a corrected record propagates promptly after a mistake.",
     ]},
    {'sev': {'Critical': 3, 'High': 4, 'Medium': 2, 'Low': 1},
     'issue': [
        "{env} lost external connectivity for {dur}, including the remote access paths needed to diagnose the problem.",
        "All inbound traffic to {svc} stopped and remote management tooling was also unreachable.",
     ],
     'cause': [
        "A routing policy change intended to assess available capacity withdrew the routes that connect {env} to the outside world. The same change removed the paths engineers would have used to reach the equipment remotely.",
        "An automated policy update removed prefix filters from the route export configuration, so the edge advertised internal ranges externally and traffic for {svc} was drawn away from its intended path.",
     ],
     'fix': [
        "Restored the routing configuration through out-of-band access, which required physical presence at the facility, then added a separate management path that does not depend on the production routing plane.",
        "Reinstated the prefix filters and added a validation step that blocks a route export policy which would advertise internal ranges.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Requests to {surface} failed TLS negotiation for {pct} of clients starting at a fixed time of day.",
        "{svc} became unreachable for external clients while internal callers were unaffected.",
     ],
     'cause': [
        "The certificate presented by the edge tier for {svc} expired. Renewal was automated but the automation had been failing quietly for several weeks because its credential had been rotated without updating the job.",
        "A certificate chain was deployed without its intermediate, so clients with a strict trust store rejected the connection while clients that cached the intermediate succeeded.",
     ],
     'fix': [
        "Issued and deployed a replacement certificate, repaired the renewal job's credential, and added alerting on certificate expiry that pages well before the deadline rather than reporting silently.",
        "Redeployed the full chain including the intermediate and added a verification step that validates the served chain against a strict trust store after each deploy.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "Routing for {svc} sent requests to the wrong backend after an edge configuration change, affecting {pct} of traffic.",
        "{pct} of requests to {surface} were served by an unintended backend for {dur}.",
     ],
     'cause': [
        "An edge configuration set the backend target inside a request handler, but a later step in the same configuration restarted request processing, which reset the target to the first entry in the list rather than the intended one.",
        "A routing rule matched on a path prefix that overlapped with another service's namespace, so requests intended for {svc} were dispatched to a neighbouring backend.",
     ],
     'fix': [
        "Corrected the configuration so the backend target survives the restart step, and added a test that asserts backend selection after a mid-request restart.",
        "Made the matching rule specific enough to exclude the overlapping namespace and added a conflict check that rejects two rules matching the same path.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Service discovery data stopped reaching {svc}, which continued operating on information that grew progressively more stale.",
        "{pct} of requests from {svc} were sent to instances that no longer existed.",
     ],
     'cause': [
        "A static routing configuration had not kept pace with infrastructure growth, so updated discovery information could not reach every consumer. Clients continued working from a stale view and sent traffic to instances that had been replaced.",
        "The discovery agent on {svc} failed to reconnect after a restart of {comp} and kept serving its last known snapshot rather than reporting that it had no fresh data.",
     ],
     'fix': [
        "Restored discovery data to the affected consumers and changed the routing configuration to scale with the fleet rather than being maintained as a fixed value.",
        "Fixed the reconnect path and changed the agent to report an error and fail closed when its snapshot exceeds a maximum age.",
     ]},
]

# --------------------------------------------------------------- hardware_infra
P['hardware_infra'] = [
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "{svc} degraded in {region} for {dur} and automated failover did not fully restore capacity.",
        "Capacity in {region} fell by {pctn} and {svc} began shedding requests.",
     ],
     'cause': [
        "A hardware failure in network equipment reduced available capacity in {region} below what was needed to serve normal traffic. Automated failover moved some load but could not compensate for the size of the shortfall.",
        "A failing component presented inconsistent state to different members of the cluster behind {svc}, so health checks disagreed about which nodes were usable and repeated leadership changes left the cluster read-only.",
     ],
     'fix': [
        "Rerouted traffic manually and replaced the failed equipment, then provisioned additional headroom so a single component failure cannot push the region below serviceable capacity.",
        "Removed the partially-failed component from service so a stable leader could be elected, then reviewed how the cluster handles conflicting information from a component that is neither fully up nor fully down.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} became unavailable in {region} following a disk failure on a node that continued reporting itself healthy.",
        "Work assigned to one node in {region} stalled for {dur} while the node remained in rotation.",
     ],
     'cause': [
        "A disk on a node hosting {svc} failed in a way that prevented writes while the node continued to pass its health probe, so the orchestrator left it in service and kept scheduling work that could not complete.",
        "A node in {region} entered a degraded state where it accepted connections but could not complete disk operations. The probe tested process liveness rather than the ability to do useful work.",
     ],
     'fix': [
        "Drained and replaced the failed node, then extended the health probe to exercise a real write so a node that cannot do useful work is removed automatically.",
        "Removed the node from rotation and changed the probe to verify end-to-end operation rather than process liveness alone.",
     ]},
    {'sev': {'Critical': 3, 'High': 4, 'Medium': 2, 'Low': 1},
     'issue': [
        "{svc} was offline for {dur} after a power event at the facility hosting {env}.",
        "A power interruption took {env} offline and recovery took considerably longer than planned.",
     ],
     'cause': [
        "A utility power interruption at the facility hosting {env} was expected to be covered by backup generation, which did not engage as designed. Key details of the provider's failover arrangement had not been documented in advance, which slowed diagnosis.",
        "Redundant power feeds into the rack hosting {svc} were found to share an upstream component. When that component failed, both feeds dropped together despite the design being described as redundant.",
     ],
     'fix': [
        "Worked with the facility provider to restore power and bring systems back, then obtained full documentation of the failover design and agreed explicit communication commitments for future events.",
        "Moved the affected equipment onto genuinely independent feeds and audited the remaining racks for shared upstream components behind nominally redundant paths.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} was degraded for {dur} because of an outage at {dep}.",
        "{pct} of requests to {svc} failed due to a fault outside the organisation's own infrastructure.",
     ],
     'cause': [
        "{dep} experienced an outage in {region}. {svc} called it synchronously with no fallback, so the upstream failure became a full failure of the dependent feature rather than a degraded one.",
        "{dep} began returning errors for a subset of requests. {comp} retried aggressively without backoff, which both prolonged recovery and amplified load on the recovering dependency.",
     ],
     'fix': [
        "Served a degraded response while {dep} recovered, then added a circuit breaker and a cached fallback so an upstream outage reduces functionality instead of removing it.",
        "Throttled retries to break the amplification loop and added exponential backoff with jitter plus a cap on concurrent calls to {dep}.",
     ]},
    {'sev': {'Critical': 1, 'High': 2, 'Medium': 4, 'Low': 3},
     'issue': [
        "Batch workloads on {svc} ran at reduced throughput for {dur} while interactive traffic was unaffected.",
        "Lower-priority processing in {region} was delayed by {dur} during planned maintenance.",
     ],
     'cause': [
        "Planned repair work coincided with a rolling software upgrade across the fleet in {region}, reducing capacity available to lower-priority traffic classes. The system correctly protected interactive requests, which meant sustained degradation for batch work until both activities completed.",
        "Capacity removed for maintenance was not replaced before the upgrade began, so the two activities overlapped and the remaining headroom was consumed by higher-priority work.",
     ],
     'fix': [
        "Allowed both activities to complete, after which capacity for lower-priority classes returned to normal, and added a scheduling rule preventing maintenance and fleet upgrades from overlapping in one region.",
        "Paused the upgrade until repair work finished and added a capacity check that must pass before a rolling upgrade starts.",
     ]},
]

# --------------------------------------------------------------- authentication
P['authentication'] = [
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "{pct} of users could not sign in to {surface} for {dur}, with no clear pattern by region or account type.",
        "Sign-in to {surface} failed intermittently while other functionality remained available.",
     ],
     'cause': [
        "An access policy changed during a routine security review blocked a resource beyond its intended scope, which included the path {comp} uses to validate credentials for {svc}.",
        "A signing key used by {comp} was rotated without updating every validator, so tokens issued after the rotation were rejected by the services still holding the previous key.",
     ],
     'fix': [
        "Rolled the policy change back to its intended narrower scope, restoring sign-in, then added a pre-apply check that lists the resources a policy change will affect.",
        "Distributed the new key to all validators and changed rotation to publish the new key and accept both for an overlap window before retiring the old one.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "Users were unable to sign in or load {surface} platform-wide, with error rates climbing for {dur}.",
        "Authentication requests to {svc} timed out for {pct} of attempts after a scheduled change.",
     ],
     'cause': [
        "A caching change caused the session lookup to scan far more data than intended on each miss, driving load on {store} past what it could serve. The automated protective throttle was initially tuned too aggressively and had to be corrected in smaller steps.",
        "Session records in {store} were keyed differently after a deploy, so existing sessions could not be found and every request fell through to a full re-authentication against {comp}.",
     ],
     'fix': [
        "Reduced load with a connection throttle, adjusted it in careful increments to avoid overshooting, and rewrote the lookup to read only the missing entries rather than scanning whole partitions.",
        "Restored the previous key format and added a dual-read path so a key change can no longer invalidate every existing session at once.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Single sign-on to {surface} failed for {pct} of enterprise tenants for {dur}.",
        "Federated login to {svc} broke for a subset of tenants while local accounts worked normally.",
     ],
     'cause': [
        "A stricter assertion-validation rule was enabled in {comp}. Identity providers that sent an optional attribute in a non-canonical form had previously been accepted and were now rejected, so their tenants could not complete sign-in.",
        "A clock drift of several minutes on {comp} caused assertions to fall outside their validity window, and the resulting rejection was reported to users as an invalid credential.",
     ],
     'fix': [
        "Relaxed the rule to accept both forms of the attribute while affected providers were contacted, then staged future validation changes behind a per-tenant warning period.",
        "Corrected time synchronisation on {comp}, added monitoring on clock drift, and made the error message distinguish a timing rejection from a bad credential.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "API tokens for {svc} were rejected as invalid for {dur} even though they had not expired.",
        "{pct} of programmatic clients lost access to {surface} without any credential change on their side.",
     ],
     'cause': [
        "A migration of the token store to {store} did not carry across tokens issued before a certain date, so {comp} could not find them and treated them as invalid rather than reporting a lookup failure.",
        "A change to token hashing in {comp} was deployed without a compatibility path, so previously-issued tokens no longer matched their stored representation.",
     ],
     'fix': [
        "Backfilled the missing tokens into {store} and changed {comp} to distinguish a lookup failure from an invalid credential so the next occurrence is diagnosed faster.",
        "Added a compatibility path that verifies against both the old and new representations, and scheduled re-hashing as a background migration rather than a cutover.",
     ]},
]

# ------------------------------------------------------------ payment_processing
P['payment_processing'] = [
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "Checkout on {surface} failed for {pct} of attempts during a promotional traffic peak.",
        "{pct} of payment attempts on {surface} timed out for {dur} during a demand surge.",
     ],
     'cause': [
        "{svc} could not scale out to meet the surge because its resource configuration prevented new instances from being placed, even though spare capacity existed. Incoming payment requests queued and began exceeding their deadline.",
        "A synchronous call from {svc} to {dep} became the bottleneck under peak load. With no concurrency limit, queued payment attempts consumed worker capacity and timed out before reaching the processor.",
     ],
     'fix': [
        "Corrected the resource configuration so instances could be scheduled onto available capacity, and added load testing ahead of promotional events to surface scaling limits in advance.",
        "Added a concurrency limit and queue with a deadline so payment attempts fail fast rather than consuming capacity, and provisioned headroom sized against peak forecasts.",
     ]},
    {'sev': {'Critical': 1, 'High': 4, 'Medium': 4, 'Low': 1},
     'issue': [
        "Payment confirmations stopped reaching merchants for {dur}, while the payments themselves completed normally.",
        "{pct} of merchants did not receive delivery callbacks from {svc} and were unaware of completed transactions.",
     ],
     'cause': [
        "A change to the queue infrastructure behind {svc} caused a subset of delivery workers to lose their connection without raising an error. Callbacks queued for those workers were never delivered and the absence of errors was read as healthy.",
        "A serialisation change in {comp} made some callback payloads unencodable. The failures were counted as successful dequeues, so the backlog drained without anything being delivered.",
     ],
     'fix': [
        "Replayed the undelivered callbacks once identified, then added active health checks on delivery workers rather than inferring health from an absence of errors.",
        "Fixed the serialisation path, replayed the affected callbacks, and changed {comp} to treat an encoding failure as a delivery failure that retries.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "A subset of transactions in {svc} were recorded twice over a {dur} window.",
        "{num} hundred payments were double-counted in {tbl} before the discrepancy was detected.",
     ],
     'cause': [
        "A retry in {comp} re-sent a payment authorisation that had in fact succeeded but whose response was lost. Without an idempotency key, {dep} treated the retry as a new transaction.",
        "A failover of {store} mid-transaction left a partial record. The reconciliation job treated the partial row as missing and re-submitted it, producing a duplicate.",
     ],
     'fix': [
        "Reconciled and reversed the duplicate transactions, then required an idempotency key on every call to {dep} so a retry can no longer create a second payment.",
        "Reversed the duplicates, and changed reconciliation to resolve a partial record against the processor's ledger before re-submitting anything.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Payouts from {svc} were delayed by {dur} for {pct} of recipients.",
        "Scheduled disbursements in {svc} did not execute on their intended date.",
     ],
     'cause': [
        "A timezone change in the scheduling configuration for {svc} moved the payout cutoff past the window during which {dep} accepts same-day instructions, so batches were held until the next cycle.",
        "A validation rule added to {comp} rejected recipient records missing a newly-required field. Those payouts were queued rather than failed, so they accumulated silently until the delay was noticed.",
     ],
     'fix': [
        "Restored the scheduling configuration to the correct timezone and pinned the cutoff to the processor's stated window rather than a local time.",
        "Backfilled the missing field, released the held payouts, and changed {comp} to surface a rejected record as an alert instead of an indefinite queue.",
     ]},
]

# ------------------------------------------------------------- security_incident
P['security_incident'] = [
    {'sev': {'Critical': 3, 'High': 4, 'Medium': 2, 'Low': 1},
     'issue': [
        "Credentials held by {svc} may have been exposed after a compromise at {dep}.",
        "An unauthorised party obtained access to secrets used by {svc}, affecting {pct} of integrations.",
     ],
     'cause': [
        "{dep} was itself compromised, and the data it held on behalf of the organisation included access tokens and keys issued for customer integrations with {svc}.",
        "A credential with broader permissions than it needed was stored in {store} in recoverable form. An attacker who reached {store} could therefore pivot into systems unrelated to the original entry point.",
     ],
     'fix': [
        "Suspended affected integrations immediately, then coordinated with each provider to revoke and reissue every token and key that had been held, rotating internal credentials before resuming service.",
        "Revoked the exposed credential, reissued it with least-privilege scope, moved secret storage to a managed service with audited access, and audited remaining credentials for excessive permissions.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "An unused host was found to be an entry point through which an attacker reached {env}.",
        "A forgotten system retained access to {env} and was used to reach production data.",
     ],
     'cause': [
        "A prototype machine had never been decommissioned and was still running software with a known unpatched vulnerability. It also still held valid credentials, which allowed the attacker to move from the prototype into {env}.",
        "A host removed from active service retained its network access and service account. Nothing reconciled the inventory against issued credentials, so the stale access went unnoticed.",
     ],
     'fix': [
        "Took the affected systems offline, rotated every credential the host had held, and introduced a decommissioning process that revokes credentials and network access as part of retirement.",
        "Revoked the stale access and added periodic reconciliation between the host inventory and issued credentials so orphaned access is detected automatically.",
     ]},
    {'sev': {'Critical': 1, 'High': 4, 'Medium': 4, 'Low': 1},
     'issue': [
        "{surface} was unavailable for {dur} under a volumetric attack that saturated the edge tier.",
        "{pct} of legitimate requests to {surface} were dropped during a sustained attack.",
     ],
     'cause': [
        "A distributed attack saturated the edge capacity serving {surface}. Mitigation rules existed but were scoped to a traffic profile the attack did not match, so they did not engage automatically.",
        "An attack targeted an endpoint on {svc} whose responses were expensive to generate and not cached, so a modest request rate was enough to exhaust backend capacity.",
     ],
     'fix': [
        "Applied mitigation manually to absorb the attack, then broadened the automatic rules to cover this traffic profile and raised edge capacity headroom.",
        "Added caching and a strict rate limit to the expensive endpoint, and placed it behind authentication so it cannot be reached anonymously at volume.",
     ]},
    {'sev': {'Critical': 2, 'High': 4, 'Medium': 3, 'Low': 1},
     'issue': [
        "A change to {svc} introduced a flaw that allowed data to be read across tenant boundaries.",
        "{pct} of API responses from {svc} could return records belonging to another tenant.",
     ],
     'cause': [
        "A large change was labelled internally as a routine update and received far less review than its scope warranted. It removed a tenant filter from a query path in {svc}, so results were no longer scoped to the caller.",
        "A caching layer added in front of {svc} keyed entries without the tenant identifier, so a response generated for one tenant could be served to another.",
     ],
     'fix': [
        "Reverted the change, audited access logs for cross-tenant reads, and introduced risk-proportional review requirements so a change of that size cannot be labelled routine.",
        "Added the tenant identifier to the cache key, invalidated the cache entirely, and added a test asserting that a response generated for one tenant is never served to another.",
     ]},
]

# ----------------------------------------------- concurrency_race_condition
P['concurrency_race_condition'] = [
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} stopped processing requests for {dur} with no error logged and no rise in load.",
        "{pct} of workers in {svc} became permanently stuck while the process stayed alive.",
     ],
     'cause': [
        "Two code paths in {comp} acquired the same pair of locks in opposite orders. Under a particular interleaving each held one lock and waited for the other, so the workers stopped making progress without crashing or logging an error.",
        "An increase in inbound volume triggered a latent defect in the client library used by {comp}, which deadlocked while holding a connection, exhausting the pool without reporting a failure.",
     ],
     'fix': [
        "Restarted the affected workers to clear the deadlock, then imposed a single global lock-ordering rule in {comp} and added a watchdog that restarts a worker making no progress.",
        "Patched the library defect, added a timeout on lock acquisition so a stall surfaces as an error, and added an alert on workers that stop advancing.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "A small number of records in {tbl} held inconsistent values after concurrent updates.",
        "{num} hundred records in {tbl} were left in a state the application considered impossible.",
     ],
     'cause': [
        "{comp} read a value, computed a new one and wrote it back without a transaction or compare-and-set. Concurrent requests for the same record interleaved between the read and the write, so one update silently overwrote the other.",
        "A uniqueness check in {svc} was performed as a read followed by an insert. Two concurrent requests both passed the read before either inserted, producing duplicate records that later code assumed could not exist.",
     ],
     'fix': [
        "Repaired the affected records and changed the update to a single conditional write so a concurrent modification fails and retries rather than being lost.",
        "De-duplicated the records and enforced uniqueness with a database constraint rather than an application-level check, so the guarantee holds under concurrency.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} briefly ran two active leaders in {region}, and conflicting writes reached {store}.",
        "Leadership for {svc} changed repeatedly over {dur}, and some work was executed twice.",
     ],
     'cause': [
        "A lease renewal in {comp} was slow enough to let the lease expire while the original holder still believed it was leader. A second instance acquired the lease before the first stepped down, so both acted as leader simultaneously.",
        "Health checks in {region} disagreed about which instances were reachable, so repeated elections occurred and each new leader began work the previous one had not finished.",
     ],
     'fix': [
        "Added a fencing token so writes from a superseded leader are rejected by {store}, and shortened the renewal interval relative to the lease duration.",
        "Stabilised the health checks and required a quorum before an election proceeds, then made the work idempotent so a repeated execution is harmless.",
     ]},
    {'sev': {'Critical': 1, 'High': 2, 'Medium': 4, 'Low': 3},
     'issue': [
        "A new code path in {svc} caused intermittent hangs and crashes that could not be reproduced reliably.",
        "{pct} of test runs against {svc} failed unpredictably after a performance change.",
     ],
     'cause': [
        "A rewrite of the input handling in {comp} introduced a low-level synchronisation path with an incorrect ordering assumption. It only misbehaved under specific timing, so it hung or crashed unpredictably rather than failing consistently.",
        "Shared state in {comp} was accessed without synchronisation from a callback that could run on a different thread, so corruption appeared only when the callback overlapped with a request.",
     ],
     'fix': [
        "Corrected the synchronisation ordering in the rewritten path and added a stress test that runs the affected code under deliberately adverse timing.",
        "Confined the shared state behind a single owner and added a race detector to the test pipeline so this class of defect fails the build.",
     ]},
]

# ------------------------------------------------------------------ memory_leak
P['memory_leak'] = [
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Memory use by {svc} climbed steadily under sustained load until the process was terminated and restarted.",
        "Instances of {svc} were restarted every {dur} as memory grew without bound.",
     ],
     'cause': [
        "{comp} registered a listener for each request but never removed it, so the registry grew for the lifetime of the process. Every entry remained reachable, which is why heap analysis showed no conventional leak.",
        "An unbounded in-process cache in {comp} had no eviction policy. It grew in proportion to the number of distinct keys seen, which rose continuously with traffic.",
     ],
     'fix': [
        "Removed the listener when a request completes and added a bound on the registry size, after which memory stabilised under sustained load.",
        "Added a size limit and least-recently-used eviction to the cache, and added an alert on memory growth over a rolling window rather than only on process restarts.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} consumed increasing memory in one environment only, while the same build was stable elsewhere.",
        "Memory growth in {svc} appeared exclusively in {region} and could not be reproduced locally.",
     ],
     'cause': [
        "Memory was lost to fragmentation rather than a genuine leak. An aligned-allocation pattern in {comp} interacted poorly with the system allocator in that environment, permanently fragmenting the pool even though every allocation was correctly freed.",
        "A single large buffer request fragmented the heap under the specific runtime configuration used in {region}. The fragmented space was not reclaimed unless the process came under memory pressure, so usage crept upward.",
     ],
     'fix': [
        "Replaced the aligned-allocation pattern with a dedicated allocator that avoids the fragmenting path, which stopped the steady growth under sustained load.",
        "Reproduced the behaviour inside the real runtime rather than a local environment, then reworked the allocation to avoid the large contiguous request.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "Nodes running {svc} restarted repeatedly on out-of-memory conditions, and cluster leadership moved between them.",
        "{svc} crashed every few hours in {region} under sustained load, masking the underlying growth.",
     ],
     'cause': [
        "A background agent on each node retried a failing call to {dep} in a loop, retaining the context of every attempt. Under sustained load the retained contexts exhausted available memory and the node was terminated.",
        "A buffer in {comp} was sized from an attacker-influenced header without an upper bound, so a small number of unusual requests allocated far more memory than the node had.",
     ],
     'fix': [
        "Bounded the retry loop and released the context between attempts, then added alerting specific to this agent's memory use since the node's normal dynamic usage had masked the growth.",
        "Clamped the buffer size to a maximum and rejected requests declaring a larger size, then added memory-growth alerting independent of crash events.",
     ]},
]

# ----------------------------------------------------------------------- other
P['other'] = [
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "{svc} was degraded for {dur} because of a fault at {dep} rather than in the organisation's own systems.",
        "{pct} of requests to {surface} failed while every internal component reported healthy.",
     ],
     'cause': [
        "{dep} experienced a regional fault. {svc} depends on it for a step it cannot complete locally, so the upstream problem surfaced directly to customers with no degraded mode available.",
        "{dep} began returning malformed responses rather than errors. {comp} had no validation on the response shape, so it propagated the bad data as a failure further downstream.",
     ],
     'fix': [
        "Served a reduced experience while {dep} recovered, then added a cached fallback and a status banner so an upstream fault degrades rather than removes the feature.",
        "Added response validation in {comp} so a malformed upstream reply is rejected at the boundary, and raised an explicit alert distinguishing an upstream fault from an internal one.",
     ]},
    {'sev': {'Critical': 1, 'High': 2, 'Medium': 4, 'Low': 3},
     'issue': [
        "{surface} displayed incorrect values to {pct} of users for {dur} while every service reported healthy.",
        "Reports generated by {svc} contained figures that did not reconcile with the underlying records.",
     ],
     'cause': [
        "A rounding change in {comp} was applied at an intermediate step rather than at presentation, so each subsequent calculation compounded the difference and totals drifted from the source records.",
        "A time-zone assumption in {svc} placed events in the wrong reporting period for users outside the primary region, so daily totals were attributed to the adjacent day.",
     ],
     'fix': [
        "Moved rounding to the presentation layer so intermediate calculations retain full precision, and recomputed the affected reports.",
        "Normalised event timestamps to a single zone before aggregation, regenerated the affected periods, and added a reconciliation check against source records.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "A scheduled job in {svc} did not run for {dur} and the omission was noticed only when downstream data went stale.",
        "{svc} silently skipped its periodic processing, leaving {tbl} without updates.",
     ],
     'cause': [
        "The scheduler entry for {svc} was removed as part of an unrelated cleanup. Nothing monitored for a job that fails to start, so the absence produced no signal at all.",
        "A clock change moved the job's window into a period when {store} was unavailable for maintenance, and the job treated the failure as a completed run rather than retrying.",
     ],
     'fix': [
        "Restored the scheduler entry, backfilled the missed processing, and added dead-man alerting that fires when an expected run does not occur.",
        "Moved the job outside the maintenance window and changed it to retry on failure rather than recording an unsuccessful attempt as complete.",
     ]},
    {'sev': {'Critical': 1, 'High': 3, 'Medium': 4, 'Low': 2},
     'issue': [
        "A maintenance window on {env} that was expected to be routine caused {dur} of unplanned downtime.",
        "A low-risk change to {env} resulted in a wider outage than its scope suggested.",
     ],
     'cause': [
        "The procedure assumed the network equipment serving {env} was configured to handle a traffic pattern it had never actually been verified against. The resulting flood affected the whole environment rather than the isolated segment that was intended.",
        "The change was tested against a single node but applied to the fleet simultaneously, so a defect that one node could absorb removed capacity everywhere at once.",
     ],
     'fix': [
        "Reconfigured the equipment to handle the traffic pattern correctly and added a pre-maintenance verification step covering it explicitly.",
        "Reverted the change and introduced staged application across the fleet with a health gate between stages.",
     ]},
]
