---
repo: donnemartin/system-design-primer
deepwiki: https://deepwiki.com/donnemartin/system-design-primer
github: https://github.com/donnemartin/system-design-primer
harvested: 2026-07-09
cluster: backend-and-deployment
---

> Distilled from the DeepWiki wiki for [`donnemartin/system-design-primer`](https://deepwiki.com/donnemartin/system-design-primer) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# donnemartin/system-design-primer — Distilled Knowledge

## What it is

An organized reference and study guide for system design interviews and large-scale distributed system architecture.

It combines:
1. A theoretical fundamentals section covering trade-offs, patterns, and core infrastructure components.
2. A set of fully worked system-design interview solutions (Twitter timeline/search, Pastebin/URL shortener, Mint.com, Web Crawler, social graph, sales ranking, query cache).
3. Object-oriented design solutions (LRU cache, deck of cards, call center, parking lot, chat app).
4. An interview methodology chapter.

It is a knowledge/reference repo rather than a runnable system — its value is the distilled architectural vocabulary and the concrete numeric/algorithmic worked examples.

## Architecture (how it's built, key components)

Not applicable in the software-architecture sense — this is a documentation repository. Its own "architecture" is a layered curriculum: fundamentals → methodology → worked solutions → OOD problems → translations. The content itself, though, systematically documents the architecture of *generic* large-scale web systems, which is summarized below.

## Key patterns & techniques (the transferable knowledge)

### The four-step interview/design methodology

1. **Requirements & constraints** — clarify users, scale (users, RPS), functionality (inputs/outputs), data volume, and read:write ratio before designing anything. Every worked solution in the repo starts here (e.g., Twitter: 100M users, 500M tweets/day, 200:1 read:write ratio; sub-second timeline generation requirement).
2. **High-level design** — sketch major components and their connections, justifying each choice, before drilling into any one component (e.g., Client → DNS → CDN, Client → Load Balancer → Web Servers → separate Write API / Read API).
3. **Core component design** — for each major component design the API (endpoints, request/response shape, auth), database schema, algorithms (hashing, ranking, search), and data structures (caches, queues, graphs) in detail.
4. **Scaling analysis** — identify concrete bottlenecks from step 1's numbers and apply load balancing, horizontal scaling, caching, sharding, and replication to address them specifically (not generically). Example: Twitter's identified bottleneck is the fanout service, addressed with async fanout plus *selective* fanout for celebrity accounts (skip fanning out to millions of followers on write; compute their timelines on read instead).

**Back-of-envelope estimation as a first-class design tool**:
- Every solution justifies its architecture with concrete arithmetic.
- Reference values: `2^10≈1KB, 2^20≈1MB, 2^30≈1GB, 2^40≈1TB`.
- Known latency numbers: memory ~250 microseconds, SSD ~1ms, disk ~20ms (disk is ~80x slower than memory, SSD ~4x slower).
- Derived throughput/storage figures — e.g., web crawler: 1B links × 4 weekly crawls/month = 4B links/month ÷ ~2.5M seconds/month = 1,600 writes/sec; 500KB average page × 4B links = 2PB/month storage.
- This turns "should we cache this" or "do we need sharding" from a vague intuition into an arithmetic answer.

### CAP theorem and consistency as an explicit trade-off, not an afterthought

- Since network partitions are unavoidable in any distributed system, every design necessarily picks CP (consistency + partition tolerance — wait for a definitive answer, risk timeouts; appropriate for financial/ACID systems) or AP (availability + partition tolerance — always answer, risk staleness; appropriate for social media, DNS).
- Three named consistency patterns sit on this spectrum:
  - **Weak** — VoIP/gaming — no read-after-write guarantee at all.
  - **Eventual** — DNS, email, social feeds — converges within milliseconds, chosen for availability.
  - **Strong** — RDBMS, financial systems — synchronous, chosen for correctness at a latency cost.

### Availability as multiplicative math, and fail-over topology as a design choice

- Series availability compounds *down*: `A_total = A(component1) × A(component2)` — chaining components each with 99.9% uptime multiplies the failure probability.
- Parallel/redundant availability compounds *up*: `A_total = 1 - (1-A1)(1-A2)` — redundant paths raise combined availability above any single path.
- This is the mathematical justification for redundancy at every tier rather than a single "reliable enough" component.
- Two named fail-over topologies:
  - **Active-passive** — standby takes over the active's IP on heartbeat loss; "hot" standby is fast, "cold" standby is slow because it needs full startup.
  - **Active-active** — both nodes serve traffic simultaneously, requiring DNS (public-facing) or application-logic/load-balancer routing (internal-facing) to know about both nodes.
- Fail-over is explicitly not free: named disadvantages are additional hardware cost (redundant servers sit idle or under-utilized most of the time), increased operational complexity (monitoring, failure-detection logic, the fail-over mechanism itself all need to be built and maintained), and potential data loss (the active system can fail before newly written data has replicated to the passive one) — fail-over buys availability at these three concrete costs, not for free.

### Layer 4 vs Layer 7 load balancing as a genuinely different mechanism, not just a config knob

- **Layer 4** (transport layer): inspects only IP/port and forwards packets via NAT without looking at payload — cheap, protocol-agnostic, but can't route by content.
- **Layer 7** (application layer): actually terminates the connection, reads the HTTP request (headers, cookies, body), and *then* opens a fresh connection to the chosen backend — enabling content-based routing (e.g., route video traffic to video-optimized servers, billing traffic to PCI-compliant servers) at the cost of an extra connection hop and more CPU per request.
- Routing algorithms available at either layer: random, least-loaded, round-robin/weighted round-robin, session/cookie-based (sticky sessions).

### Database scaling as a sequence of increasingly invasive techniques

Ordered roughly by increasing complexity/invasiveness:
1. **Master-slave replication** — writes to one master, reads fan out to N slaves — read scaling only.
2. **Master-master replication** — bidirectional sync, both nodes accept writes — write scaling, but conflict resolution complexity.
3. **Federation** — functional partitioning; split one monolithic DB into per-domain DBs like `forums_db`, `users_db`, `products_db`; reduces read/write traffic per DB and allows domain-specific schema tuning, but cross-domain joins now require application-level joins.
4. **Sharding** — horizontal partitioning; split *one logical table* across N physical shards by a key like last-name range or geography; the most invasive because it usually requires re-architecting the application's data-access layer, but is the only technique that scales writes for a single logical entity past what one machine can hold.

**Denormalization** (duplicate data across tables to avoid joins) is explicitly framed as a technique you reach for *after* federation/sharding already made joins impractically expensive across shards/DBs — not a starting point.

**NoSQL as BASE instead of ACID**: Basically Available, Soft State, Eventual Consistency — the deliberate inverse of RDBMS's ACID guarantees, traded for horizontal scalability. Four NoSQL shapes with distinct use cases:
- **Key-value** (Redis/DynamoDB) — O(1) hash-table semantics, cache/session storage.
- **Document** (MongoDB/CouchDB) — schema-flexible, queryable by document structure.
- **Wide-column** (Cassandra/HBase) — high write throughput, huge datasets.
- **Graph** (Neo4j/FlockDB) — relationship-heavy queries like social graphs.

### Caching: four update patterns, each with a different failure mode

- **Cache-aside (lazy loading)**: app checks cache, on miss reads DB and populates cache. Cache only holds what's actually been requested; a cold cache or one that was flushed causes a stampede of DB reads until it's repopulated.
- **Write-through**: every write goes to cache *and* DB synchronously — guarantees cache consistency but adds write latency.
- **Write-behind (write-back)**: write to cache, batch-flush to DB asynchronously later — much lower write latency, but risks data loss if the cache dies before flushing.
- **Refresh-ahead**: predictively refresh cache entries *before* they expire, based on observed access patterns — avoids the "cache just expired, now everyone pays a slow read" scenario cache-aside is prone to.

Cache placement is layered, not singular: client (browser/OS), CDN (geographic), web-server (Varnish/NGINX), application (Redis/Memcached), and database (built-in query cache) can all cache the same logical data at different points in the request path, each trading freshness for latency differently.

### CDN push vs pull as a traffic-volume decision

- **Push CDNs** (origin uploads content, TTL-based expiry) suit low-traffic sites with infrequent updates — you pay to push once, it's cheap because it happens rarely.
- **Pull CDNs** (edge fetches from origin on first request, then caches) suit high-traffic/dynamic-content sites — the first request per edge node is slow, but subsequent ones are fast, and you never push content nobody requests.

### Asynchronous processing and back-pressure as paired concerns

- Message queues (Redis, RabbitMQ, SQS — simple job dispatch) vs task queues (Celery — complex multi-step workflows with scheduling) decouple an expensive operation (image/video processing, email, batch analytics, periodic cleanup) from the request path, letting the app server return an immediate "job queued" response.
- But an unbounded queue that grows faster than workers can drain it eventually causes memory overflow / forced disk reads.
- The paired mitigation is explicit **back-pressure**: return HTTP 503 to callers once the queue passes a threshold, forcing them into exponential backoff rather than letting the queue grow unboundedly.

### RPC vs REST as behavior-focused vs resource-focused API design

- The same operations look structurally different depending on the paradigm: RPC signup is `POST /signup`, REST signup is `POST /persons`; RPC delete is `POST /resign {personid}`, REST delete is `DELETE /persons/1234`.
- RPC couples the client to specific server actions/verbs — tends toward better native performance, common for internal service-to-service calls.
- REST couples the client to resource state transitions via standard HTTP verbs — stateless, cacheable, favored for public APIs consumed by unknown/diverse clients.

### Web crawler design (worked solution) — priority-queue crawling with duplicate suppression at two levels

Target scale in the worked example: 1B links, weekly average re-crawl → 4B link-visits/month → 1,600 writes/sec; 100B searches/month → 40,000 search-QPS.

- **Crawl loop**: `extract_max_priority_page()` pops the highest-priority pending URL from a Redis sorted set (`links_to_crawl`); if its content signature matches something already in `crawled_links` (duplicate/cycle detected), call `reduce_priority_link_to_crawl()` instead of processing it — this both avoids infinite loops from graph cycles *and* naturally deprioritizes low-value duplicate content without needing a separate cycle-detection pass.
- **Two-level duplicate detection**:
  1. An offline MapReduce job on the *seed* URL list — map each URL to `(url, 1)`, reduce by summing and keeping only URLs whose sum equals 1 — cheaply removes duplicate seed URLs before crawling even starts.
  2. At crawl time, content-based duplicate detection via a page signature (hash of URL + contents), checked against `crawled_similar()`, using algorithms like Jaccard index (set-overlap) or cosine similarity (TF-IDF vector) to catch near-duplicate content across different URLs.
- **Freshness policy**: default weekly re-crawl, but adaptively more frequent for high-traffic/frequently-changing sites (mined from observed historical update frequency per site), while honoring robots.txt-specified crawl-rate limits.
- **Scaling additions once bottlenecks appear**:
  - Memory cache (Redis/Memcached) in front of the search-query path specifically because query popularity is highly uneven (some queries run once, others constantly) — cache-aside absorbs traffic spikes on hot queries.
  - Sharding + federation for both the Reverse Index Service and Document Service since neither fits on one machine at billions-of-documents scale.
  - Crawler-side DNS caching (local lookup table, periodically refreshed) and connection pooling to frequently-crawled domains, specifically to cut per-request latency overhead that dominates at 1,600 req/sec sustained.
- **Search query pipeline**: parse (strip markup, tokenize, fix typos, normalize case, convert to boolean ops) → cache check → on miss, Reverse Index Service finds+ranks candidate document IDs → Document Service fetches titles/snippets for the top results → assemble JSON response. This separation (index lookup vs metadata fetch as two distinct sharded services) means the two can scale independently based on their very different access patterns (index lookup is compute-heavy ranking, metadata fetch is simple key lookup).

### Named bottleneck-to-solution mappings across worked solutions

The repo's own cross-solution bottleneck table is a useful checklist of "what usually breaks first, and what fixes it":
- **Twitter** — fanout service is the bottleneck; fixed with async fanout plus selective fanout for celebrity accounts.
- **Twitter** — timeline reads are the bottleneck; fixed with a Redis cache sized for 40K reads/sec.
- **Pastebin** — paste reads are the bottleneck; fixed with CDN + Memcached to absorb 400M reads/month.
- **Pastebin** — storage is the bottleneck; fixed with an S3 object store plus sharded SQL for metadata only (not the paste content itself).
- **Mint.com** — transaction sync is the bottleneck; fixed with MapReduce batch processing rather than synchronous per-transaction work.
- **Web Crawler** — URL deduplication is the bottleneck; fixed with a Bloom filter plus a distributed hash table.
This table is itself an instance of the methodology's step 4 (scaling analysis) applied consistently: the fix in each row is specific to the *named* bottleneck, not a generic "add more servers" — reinforcing that scaling decisions should be traced back to a concrete numbered constraint from step 1, not applied reflexively.

## Practical how-tos

- **Structuring a system-design interview answer**: always start by asking clarifying questions (users, scale, functionality, data, read:write ratio) before drawing any boxes — jumping straight to architecture without establishing scale is the most commonly cited failure mode implicitly, since every worked solution front-loads this step.
- **Justifying a caching decision quantitatively**: cite the memory/SSD/disk latency ratio (250 microsec / 1ms / 20ms — roughly 4x and 80x) to make the case for a cache layer concrete rather than hand-wavy.
- **Choosing federation vs sharding**: reach for federation first (split by function/domain — cheaper to reason about, keeps schemas simple) and only shard a single logical table once federation alone can't handle the write volume on that specific entity.
- **Picking selective fanout for a "celebrity" write-heavy social feature**: don't materialize every follower's timeline synchronously on every write if follower counts are power-law distributed — compute high-follower-count accounts' appearances in *reader* timelines at read time instead of push-fanning-out on write.
- **Building a URL shortener hash**: MD5 hash of URL+timestamp, encode the first 43 bits in Base62 for a 7-character shortlink, check for collision against the SQL table, and append-and-rehash on collision.

## Gotchas & caveats

- The repo is explicitly a *reference for scale numbers and vocabulary*, not runnable production code — the "solutions" are pseudocode/README-level designs meant to demonstrate reasoning, not deployable systems.
- Every documented pattern trades something for something else; there is no pattern presented as universally correct (e.g., write-behind caching is explicitly flagged as risking data loss on cache failure before flush — it's not framed as strictly better than write-through, only faster).
- Selective/hybrid fanout (used for celebrity accounts in the Twitter solution) is a targeted fix for a specific power-law bottleneck, not a general substitute for fanout-on-write — applying it everywhere would lose the read-time performance benefit fanout-on-write is meant to provide for the common case.
- Layer 7 load balancing's content-inspection capability comes at a real architectural cost (an extra TCP handshake/connection to the backend, more CPU per request) — it isn't a strictly-better replacement for Layer 4, it's a different trade-off point.

## Wiki pages used

- System Design Fundamentals (overview/synthesis page)
- Interview Approach Methodology
- Availability Patterns (partial)
- Database Systems and Scaling
- Load Balancing and Reverse Proxies
- Web Crawler System (solution)
