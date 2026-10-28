"""Slot vocabularies and fictional organisation names for synthetic RCA data.

Nothing here names a real company. Organisation names are built from invented
morphemes so a synthetic entry can never be mistaken for a record about a real
business.
"""

# ---------------------------------------------------------------- organisations
_PRE = ['Vel', 'Nor', 'Quan', 'Lum', 'Ather', 'Cask', 'Driff', 'Ember', 'Fen',
        'Glim', 'Harro', 'Ildra', 'Jarn', 'Kesto', 'Lyr', 'Mird', 'Noct',
        'Orbis', 'Pell', 'Quill', 'Rhen', 'Sable', 'Thal', 'Umbra', 'Verd',
        'Wyn', 'Xan', 'Yarr', 'Zeph', 'Brack', 'Calder', 'Dunmar', 'Esker',
        'Fallow', 'Girth', 'Holt', 'Inver', 'Kelp', 'Larch', 'Marl']
_SUF = ['ora', 'ix', 'yn', 'ara', 'os', 'eon', 'ith', 'une', 'ary', 'elle',
        'ode', 'ant', 'ess', 'ium', 'ula', 'erra', 'ano', 'ique', 'oss', 'ade']
_KIND = ['Systems', 'Labs', 'Cloud', 'Networks', 'Data', 'Technologies',
         'Platform', 'Digital', 'Works', 'Compute', 'Analytics', 'Software',
         'Interactive', 'Logistics', 'Financial', 'Health', 'Commerce',
         'Media', 'Robotics', 'Security', 'Payments', 'Telecom', 'Studios',
         'Infrastructure', 'Group', 'Holdings', 'Industries', 'Partners']


def org_pool(rng, n=260):
    """A stable pool of invented organisation names."""
    out, seen = [], set()
    while len(out) < n:
        name = rng.choice(_PRE) + rng.choice(_SUF)
        name = name.capitalize()
        if rng.random() < 0.72:
            name = f'{name} {rng.choice(_KIND)}'
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


# ------------------------------------------------------------------ slot values
SLOTS = {
    'svc': ['the checkout service', 'the search API', 'the notification service',
            'the billing service', 'the media transcoder', 'the identity service',
            'the document indexer', 'the webhook dispatcher', 'the pricing engine',
            'the recommendation service', 'the reporting API', 'the ingest gateway',
            'the asset pipeline', 'the sync service', 'the catalogue API',
            'the messaging bridge', 'the scheduling service', 'the audit log writer',
            'the entitlement service', 'the export worker', 'the chat backend',
            'the inventory service', 'the geocoding service', 'the feed builder'],
    'comp': ['the request router', 'the connection pool', 'the cache layer',
             'the job scheduler', 'the serialisation layer', 'the retry handler',
             'the admission controller', 'the config loader', 'the metrics agent',
             'the session store', 'the rate limiter', 'the batch consumer',
             'the health checker', 'the leader elector', 'the shard mapper',
             'the token validator', 'the queue consumer', 'the sidecar proxy'],
    'store': ['the primary Postgres cluster', 'the MySQL replica set',
              'the Redis cache tier', 'the Cassandra ring', 'the MongoDB shard',
              'the object store bucket', 'the Elasticsearch index',
              'the ClickHouse cluster', 'the Kafka topic', 'the DynamoDB table',
              'the SQLite metadata store', 'the time-series store'],
    'tbl': ['the accounts table', 'the sessions table', 'the orders table',
            'the events table', 'the subscriptions table', 'the entitlements table',
            'the documents table', 'the audit table', 'the ledger table',
            'the webhooks table', 'the invoices table', 'the devices table'],
    'region': ['us-east', 'us-west', 'eu-central', 'eu-west', 'ap-southeast',
               'ap-northeast', 'sa-east', 'ca-central', 'the primary region',
               'two of three availability zones', 'the Frankfurt region',
               'the Sydney region'],
    'env': ['production', 'the production fleet', 'the primary cluster',
            'the shared staging-to-production path', 'all regions',
            'a single production cell'],
    'surface': ['the web dashboard', 'the public API', 'the mobile apps',
                'the admin console', 'the partner API', 'the CLI',
                'the embedded widget', 'the reporting UI', 'the SDK',
                'the webhooks endpoint'],
    'actor': ['an engineer', 'an on-call engineer', 'a platform engineer',
              'an automated remediation job', 'a scheduled maintenance task',
              'a release pipeline', 'a infrastructure-as-code apply',
              'a routine capacity change'],
    # used as "{pct} of <things>", so values must NOT carry a trailing "of"
    'pct': ['3%', '7%', '11%', '18%', '24%', '31%', '42%', '55%', '63%', '78%',
            '85%', '94%', 'roughly a third', 'just under half',
            'a small subset', 'the majority', 'a handful'],
    # numeric-only, for "fell by {pctn}" / "{pctn} higher"
    'pctn': ['3%', '7%', '11%', '18%', '24%', '31%', '42%', '55%', '63%', '78%'],
    'dur': ['14 minutes', '23 minutes', '38 minutes', '51 minutes',
            '1 hour 12 minutes', '1 hour 47 minutes', '2 hours 5 minutes',
            '3 hours 20 minutes', '4 hours 36 minutes', '6 hours 10 minutes',
            '9 hours', 'most of the working day'],
    'num': ['two', 'three', 'four', 'six', 'eight', 'a dozen', 'dozens of',
            'several hundred', 'a handful of'],
    'limit': ['the connection limit', 'the file-descriptor limit',
              'the configured memory ceiling', 'the request timeout',
              'the queue depth limit', 'the per-tenant quota',
              'the maximum payload size', 'the thread-pool bound'],
    'dep': ['an upstream payment processor', 'a third-party email provider',
            'the managed DNS provider', 'a downstream KYC vendor',
            'the upstream CDN', 'a partner inventory feed',
            'the cloud provider block-storage service',
            'a third-party SMS gateway', 'the managed Kubernetes control plane',
            'an external geolocation API'],
    'metric': ['p99 latency', 'error rate', 'queue depth', 'replication lag',
               'request throughput', 'cache hit rate', 'connection count',
               'garbage-collection pause time'],
}
