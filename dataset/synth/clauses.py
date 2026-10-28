"""Composable clauses that multiply the variety of generated entries.

A pattern in patterns.py anchors the *mechanism* (and therefore stays coherent
with its own fix). These pools supply the surrounding sentences, which are
phrased to be compatible with any mechanism in the same category:

    root_cause = <pattern cause>  + " " + <CONSEQ[category]>
    solution   = <pattern fix>    + " " + <PREVENT[category]>
    issue      = <pattern issue>  + optional " " + <SCOPE>

So each pattern's two cause templates become 2 x len(CONSEQ) distinct causes.
"""

# how the mechanism reached customers - generic within a category
CONSEQ = {
    'configuration_deployment': [
        "Because the change was applied fleet-wide rather than in stages, every instance was affected before anyone could intervene.",
        "The rollout had no health gate between stages, so the faulty state reached all instances at once.",
        "Nothing compared the applied state against the intended state, so the divergence persisted until customers reported it.",
        "The change passed review because its diff looked small, and its effect at runtime was not obvious from the text.",
        "The affected path is exercised only under production traffic, so pre-production checks had reported success.",
        "Impact was uniform across tenants, which initially pointed responders towards a dependency rather than a local change.",
        "Alerting fired on the symptom rather than the change, so the connection to the rollout was not made immediately.",
        "The previous configuration had been in place long enough that no one recalled why the superseded value mattered.",
    ],
    'database_issue': [
        "The additional load pushed the cluster past the point where it could serve its normal read volume, so unrelated queries also began failing.",
        "Connections accumulated faster than they were released, so callers queued behind a pool that never recovered on its own.",
        "Because the failure mode was a slowdown rather than an error, retries added further load to an already-saturated cluster.",
        "Replicas fell behind as the primary absorbed the extra work, which removed read capacity exactly when it was most needed.",
        "The query planner had no recent statistics for the affected relation, so it continued choosing a plan that no longer suited the data.",
        "Lock waits propagated to unrelated statements, so the impact spread well beyond the queries that caused it.",
        "Monitoring tracked availability rather than correctness, so the cluster continued to report healthy throughout.",
        "The backlog that built up during the incident took longer to drain than the original fault lasted.",
    ],
    'api_latency': [
        "As queues grew, client retries added load to the same saturated path and amplified the delay well beyond the original shortfall.",
        "Requests consumed worker capacity before timing out, so the service spent its budget on work that was discarded.",
        "Because each request was individually fast, backend dashboards stayed within normal bounds while callers saw seconds of delay.",
        "Upstream callers had no timeout of their own, so the slowdown propagated into services that were otherwise healthy.",
        "Autoscaling keyed on CPU rather than queue depth, so it did not add capacity while requests were waiting rather than computing.",
        "The affected path had no concurrency limit, so a single slow dependency was enough to occupy every available worker.",
        "Latency rose gradually rather than stepping, so threshold-based alerting did not fire until impact was already broad.",
        "Load shedding was not configured, so the service accepted more work than it could complete within its deadline.",
    ],
    'networking_dns': [
        "Negative results were cached downstream, so the failure persisted for some clients after the underlying record was corrected.",
        "Because service discovery itself was affected, healthy instances could not be found and traffic continued to reach replaced ones.",
        "The failure removed the paths engineers would normally use to diagnose it, which extended time to recovery considerably.",
        "Every service that resolved the affected name failed together, which made the blast radius far larger than the change implied.",
        "Retries did not help because the resolution step failed before any connection was attempted.",
        "Clients held the stale answer for the full lifetime of their cache, so recovery was staggered rather than immediate.",
        "Internal callers were affected while external monitoring continued to pass, so detection relied on customer reports.",
        "The change looked routine in review because its effect depended on which resolver path a caller happened to use.",
    ],
    'hardware_infra': [
        "Automated failover moved some load but could not compensate for the size of the capacity shortfall.",
        "Because the component reported itself healthy, the orchestrator kept scheduling work onto it that could not complete.",
        "Remaining capacity absorbed the redirected load until it too was saturated, which widened the impact.",
        "Recovery required physical intervention, so time to repair was governed by access rather than by diagnosis.",
        "The redundancy that was expected to cover this failure shared an upstream component with the path that failed.",
        "Higher-priority traffic was protected as designed, which meant sustained degradation for everything below it.",
        "Health checks tested process liveness rather than the ability to do useful work, so the fault stayed hidden.",
        "The fault was intermittent, so instances were repeatedly returned to service before being removed for good.",
    ],
    'authentication': [
        "Because the failure was in the credential path rather than the application, every feature behind sign-in became unreachable.",
        "Affected users retried repeatedly, which added load to the same component that was already failing.",
        "The error surfaced to users as an invalid credential, so support initially treated it as a user-side problem.",
        "Sessions established before the change continued to work, which made the impact look smaller than it was.",
        "Service-to-service calls used the same validation path, so internal workflows failed alongside end-user sign-in.",
        "Because tokens are cached by clients, the impact appeared gradually as existing tokens expired.",
        "Monitoring covered availability of the endpoint rather than successful authentication, so it stayed green.",
        "The change had been reviewed as a security improvement, so its blast radius was not examined closely.",
    ],
    'payment_processing': [
        "Because the money movement itself was unaffected, internal dashboards showed success while customers saw failure.",
        "Failed attempts were retried by customers, which produced further load on an already-constrained path.",
        "Reconciliation ran only daily, so the discrepancy was not surfaced until well after the window closed.",
        "The failure occurred after authorisation but before confirmation, which left records in an ambiguous state.",
        "Merchants had no way to distinguish a delayed payment from a failed one, which generated substantial support load.",
        "Because the path is only exercised at peak, load testing at normal volume had not surfaced the limit.",
        "Downstream ledger entries were written from the same flow, so the inconsistency propagated into reporting.",
        "Alerting was keyed on error rate rather than on completion rate, so a silent stall produced no signal.",
    ],
    'security_incident': [
        "Because the credential had broader permissions than it needed, the reachable surface was far larger than the initial entry point.",
        "Detection depended on a third party's report, so the window between access and discovery was measured in weeks.",
        "Audit logging covered the application but not the administrative path that was used, which complicated scoping.",
        "The affected system had been excluded from routine inventory, so nothing flagged it as unpatched.",
        "Because the access used valid credentials, it did not trigger any of the anomaly rules that were in place.",
        "The blast radius could not be bounded quickly, so every credential the system had held was rotated as a precaution.",
        "Existing mitigation rules were scoped to a different traffic profile, so they did not engage automatically.",
        "The change had been labelled low-risk, which meant it bypassed the review depth its scope warranted.",
    ],
    'concurrency_race_condition': [
        "Because the processes stalled rather than crashed, no error was logged and the instances continued to pass their health checks.",
        "The behaviour depended on timing, so it could not be reproduced reliably and took substantial effort to isolate.",
        "Lost updates were silent, so the inconsistency was discovered only when later logic encountered a state it treated as impossible.",
        "The defect had been present for some time and surfaced only once traffic shape changed enough to hit the interleaving.",
        "Affected workers held their connections while stalled, which exhausted the pool and spread impact to unrelated requests.",
        "Because each individual operation appeared to succeed, metrics showed normal throughput while work was being dropped.",
        "The window was narrow enough that it affected only a small fraction of requests, which delayed detection.",
        "Recovery required restarting the affected processes, since nothing detected a worker that had stopped making progress.",
    ],
    'memory_leak': [
        "Because the growth was gradual, it was mistaken for normal variation until instances began being terminated.",
        "The retained objects remained reachable, which is why conventional heap analysis did not identify a leak.",
        "Instances were restarted automatically on termination, which masked the underlying growth from everyone but the on-call engineer.",
        "Capacity was sufficient at normal load, so the ceiling was reached only during an extended period of sustained traffic.",
        "The process used memory dynamically in normal operation, so alerting could not distinguish growth from ordinary use.",
        "Each restart reset the measurement window, which hid the trend from dashboards that aggregated over short intervals.",
        "By the time impact was visible, the backlog of work that had accumulated took longer to clear than the fault itself.",
        "Because only one environment was affected, the problem was initially attributed to that environment rather than the code.",
    ],
    'other': [
        "Because every internal component reported healthy, responders spent much of the incident ruling out their own systems.",
        "The incorrect values were written downstream before the fault was found, so correcting it required a backfill.",
        "Nothing reconciled the output against its source, so the discrepancy persisted until a customer raised it.",
        "The absence of an expected event produced no signal, since alerting covered failures rather than omissions.",
        "Impact was limited to a subset of users, which delayed detection and complicated reproduction.",
        "The dependency had no degraded mode, so an upstream fault removed the feature rather than reducing it.",
        "Because the change was outside the normal release path, it did not appear in any deployment history.",
        "The affected process ran infrequently, so the next scheduled run was the earliest point recovery could be verified.",
    ],
}

# follow-up work - generic within a category
PREVENT = {
    'configuration_deployment': [
        "Staged rollouts with an automatic health gate were introduced so a bad configuration can no longer reach the whole fleet.",
        "A pre-apply diff review was added that reports the runtime effect of a change rather than only its text.",
        "Drift detection now alerts on any divergence between intended and applied state.",
        "The affected path was added to pre-production verification so the same defect would be caught before release.",
        "Alerting was changed to correlate symptom onset with recent changes so the trigger is surfaced automatically.",
        "A documented rollback procedure was added for this class of change and tested in a drill.",
    ],
    'database_issue': [
        "A saturation metric with alerting was added so the limit is visible before it is reached.",
        "Migrations touching a large relation now run against a single replica first, with a gate before fleet-wide application.",
        "Backup success is now monitored directly, and restore drills were scheduled to verify snapshots are usable.",
        "A review step was added that rejects a new query path without an index backing its filter columns.",
        "Replication lag is now an alerted metric rather than being inferred from replica availability.",
        "Destructive operations now require a second approval and an explicit target allow-list.",
    ],
    'api_latency': [
        "Load shedding was added so the service rejects work it cannot complete within its deadline.",
        "Retries now use exponential backoff with jitter, and a concurrency cap bounds in-flight calls to the dependency.",
        "Autoscaling was re-keyed on queue depth so capacity is added while requests are waiting rather than computing.",
        "Per-tenant concurrency limits were introduced so one caller cannot consume a shared pool.",
        "Client-side latency is now measured so user-visible slowness is visible even when backend timings look normal.",
        "A capacity model was built from measured dependency latency and is reviewed before each peak event.",
    ],
    'networking_dns': [
        "A management path independent of the production routing plane was provisioned so diagnosis no longer depends on the failing component.",
        "A validation step now blocks a change that would withdraw routes or empty a record set in use.",
        "Negative-response cache lifetimes were shortened so a corrected record propagates promptly.",
        "Routing configuration now scales with the fleet rather than being maintained as a fixed value.",
        "A rule was adopted that resolution-dependent tooling may not be used to repair a resolution outage.",
        "Certificate and record expiry are now alerted well before the deadline rather than reported silently.",
    ],
    'hardware_infra': [
        "Capacity headroom was increased so a single component failure cannot push the region below serviceable capacity.",
        "Health checks were extended to exercise a real operation so a component that cannot do useful work is removed automatically.",
        "Nominally redundant paths were audited for shared upstream components and separated where they were not independent.",
        "A circuit breaker and cached fallback were added so an upstream fault degrades rather than removes the feature.",
        "Maintenance and fleet upgrades may no longer overlap in the same region without an explicit capacity check.",
        "An out-of-band access path was established so recovery does not depend on the affected infrastructure.",
    ],
    'authentication': [
        "Key rotation now publishes the new key and accepts both for an overlap window before retiring the old one.",
        "A pre-apply check now lists every resource a policy change will affect before it is applied.",
        "Error responses now distinguish an infrastructure failure from an invalid credential so support can triage correctly.",
        "Successful authentication rate is now monitored rather than only endpoint availability.",
        "Validation changes are staged behind a per-tenant warning period before they are enforced.",
        "A dual-read path was added so a change to session or token format cannot invalidate everything at once.",
    ],
    'payment_processing': [
        "Idempotency keys are now required on every call to the processor so a retry cannot create a second payment.",
        "Completion rate is now alerted alongside error rate so a silent stall produces a signal.",
        "Load testing against peak forecasts was added ahead of promotional events.",
        "Reconciliation now runs continuously rather than daily, and resolves ambiguous records against the processor ledger.",
        "Active health checks were added on delivery workers rather than inferring health from an absence of errors.",
        "A deadline was introduced so a payment attempt fails fast instead of consuming capacity it cannot use.",
    ],
    'security_incident': [
        "Credentials were reissued with least-privilege scope and the remaining set was audited for excessive permissions.",
        "A decommissioning process was introduced that revokes credentials and network access as part of retirement.",
        "Administrative actions are now captured in the audit trail so scoping an incident does not depend on inference.",
        "Host inventory is now reconciled against issued credentials periodically so orphaned access is detected automatically.",
        "Risk-proportional review requirements were adopted so a change of that scope cannot be labelled routine.",
        "Mitigation rules were broadened to cover this traffic profile and their coverage is now tested regularly.",
    ],
    'concurrency_race_condition': [
        "A single global lock-ordering rule was adopted and a watchdog now restarts a worker that stops making progress.",
        "Lock acquisition now has a timeout so a stall surfaces as an error rather than silence.",
        "The invariant is now enforced by a database constraint rather than an application-level check.",
        "A race detector was added to the test pipeline so this class of defect fails the build.",
        "Fencing tokens were introduced so writes from a superseded leader are rejected.",
        "A stress test was added that runs the affected code under deliberately adverse timing.",
    ],
    'memory_leak': [
        "Memory growth is now alerted over a rolling window rather than only on process restarts.",
        "The cache was given a size limit and an eviction policy so it cannot grow with the number of distinct keys.",
        "Allocation behaviour is now verified inside the real runtime rather than a local environment.",
        "A bound was placed on the retained structure so its size no longer tracks process lifetime.",
        "Buffer sizes derived from request input are now clamped to a maximum.",
        "Restart events are now correlated with memory trend so an automatic restart cannot mask growth.",
    ],
    'other': [
        "A reconciliation check against source records was added so a discrepancy is surfaced automatically.",
        "Dead-man alerting was added so an expected run that does not occur produces a signal.",
        "Response validation was added at the boundary so a malformed upstream reply is rejected rather than propagated.",
        "A cached fallback and status indicator were added so an upstream fault degrades the feature rather than removing it.",
        "The change path was brought inside the normal release process so it appears in deployment history.",
        "The job now retries on failure rather than recording an unsuccessful attempt as complete.",
    ],
}

# extra scope sentences for the issue field
SCOPE = [
    "Impact was limited to {region}.",
    "Both {surface} and internal tooling were affected.",
    "Internal tooling was affected alongside customer-facing traffic.",
    "A subset of tenants saw no impact at all.",
    "The problem resolved and recurred twice before being fully mitigated.",
    "Severity varied by tenant depending on request mix.",
    "",
    "",
]

# Terse, status-page style titles. Gold's `issue` field is frequently just a
# short title like "Delays starting Gen 2 Docker Jobs.", which is what gives it
# a long low tail in length. Used in place of the full symptom sentence.
TERSE = {
    'configuration_deployment': [
        "Errors on {surface} following a recent change.",
        "{svc} degraded after a routine rollout.",
        "Unexpected behaviour in {svc} across {env}.",
        "Service disruption traced to a configuration change.",
        "{svc} unavailable following a planned change.",
        "Elevated error rates after a release to {env}.",
    ],
    'database_issue': [
        "Elevated query latency against {store}.",
        "Database errors affecting {svc}.",
        "{svc} degraded by a datastore problem.",
        "Data access failures in {env}.",
        "Read and write errors against {store}.",
        "{svc} unavailable due to a database fault.",
    ],
    'api_latency': [
        "Elevated response times on {surface}.",
        "{svc} timing out for a subset of callers.",
        "Degraded performance affecting {svc}.",
        "{surface} slow or unresponsive.",
        "Increased latency and timeouts in {region}.",
        "{svc} shedding requests under load.",
    ],
    'networking_dns': [
        "Connectivity failures affecting {svc}.",
        "Network errors between services in {env}.",
        "{surface} unreachable for a subset of clients.",
        "Traffic to {svc} failing to reach its destination.",
        "Intermittent connection failures in {region}.",
        "{svc} unable to reach its dependencies.",
    ],
    'hardware_infra': [
        "Capacity reduction affecting {svc} in {region}.",
        "Infrastructure fault degrading {svc}.",
        "{svc} degraded by a platform-level failure.",
        "Reduced availability in {region}.",
        "{svc} affected by an infrastructure event.",
    ],
    'authentication': [
        "Users unable to sign in to {surface}.",
        "Authentication failures affecting {svc}.",
        "Access to {surface} denied for a subset of users.",
        "Credential validation failures in {env}.",
        "Sign-in and authorisation errors on {surface}.",
    ],
    'payment_processing': [
        "Payment failures affecting {surface}.",
        "Transaction processing degraded in {svc}.",
        "Payment records inconsistent for a subset of customers.",
        "Delays in payment processing through {svc}.",
    ],
    'security_incident': [
        "Security incident affecting {svc}.",
        "Unauthorised activity detected in {env}.",
        "{surface} affected by a security event.",
        "Potential data exposure involving {svc}.",
    ],
    'concurrency_race_condition': [
        "{svc} stalled with no errors reported.",
        "Inconsistent state observed in {svc}.",
        "Intermittent failures in {svc} under load.",
        "{svc} processing work incorrectly under concurrency.",
    ],
    'memory_leak': [
        "Memory growth in {svc} leading to restarts.",
        "{svc} terminated repeatedly on memory exhaustion.",
        "Elevated memory use in {svc} in {region}.",
    ],
    'other': [
        "{svc} degraded for a subset of users.",
        "Incorrect behaviour observed on {surface}.",
        "Processing in {svc} did not complete as expected.",
        "Unplanned disruption affecting {svc}.",
    ],
}
