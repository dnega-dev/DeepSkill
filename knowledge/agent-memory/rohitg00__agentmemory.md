---
repo: rohitg00/agentmemory
deepwiki: https://deepwiki.com/rohitg00/agentmemory
github: https://github.com/rohitg00/agentmemory
harvested: 2026-07-13
cluster: agent-memory
---

> Distilled from the DeepWiki wiki for [`rohitg00/agentmemory`](https://deepwiki.com/rohitg00/agentmemory) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# rohitg00/agentmemory — Distilled Knowledge

## What it is

`agentmemory` is a persistent, searchable, versioned memory database purpose-built for AI *coding* agents, solving the "amnesia" problem where an agent loses context between sessions and forces the user to re-explain architecture, coding standards, and past bug fixes [README.md:10-11]. It provides a single shared memory layer across different coding tools — Claude Code, Cursor, Windsurf, Cline, GitHub Copilot CLI — via native lifecycle hooks, an MCP server (53+ tools), and a REST API. It is a TypeScript system built on the **iii-engine** ("Intelligence Interface Infrastructure"), a small worker-process framework providing three primitives: HTTP Triggers, KV State, and Streams [package.json:4-5]. Installed via `npm install -g @agentmemory/agentmemory`; runs a local server (default port 3111 REST, 3112 WebSocket streams, 3113 dashboard viewer) rooted at `~/.agentmemory/`.

## Architecture

**iii-engine foundation**: `agentmemory` is a worker process connected to an `iii-engine` instance via `iii-sdk`, pinned to engine version `0.11.2` for compatibility [src/cli.ts:72-83]. Three primitives map to concrete implementations:
| Primitive | Implementation | Role |
|---|---|---|
| HTTP Triggers | `registerApiTriggers` (`src/triggers/api.ts:138-144`) | REST API + internal function endpoints |
| KV State | `StateKV` (`src/state/kv.ts:29`) | Namespaced persistence — 33 distinct KV scopes (sessions, observations, memories, graphNodes, etc.) |
| Streams | `STREAM` (`src/state/schema.ts:135-141`) | Real-time broadcast of observations to the dashboard |

**Worker startup sequence** (`src/index.ts`): load config → initialize LLM/embedding providers → connect to iii-engine via `registerWorker` → register all `mem::*` and `api::*` functions → `rebuildIndex` (loads existing data into BM25 + vector indices) → start health monitor → write `worker.pid` to `~/.agentmemory/`.

**Core Memory Pipeline — four stages**: `mem::observe` (capture) → `mem::compress` (LLM distillation) → `mem::remember` (tiered persistence) → `mem::smart-search` (hybrid retrieval).
1. **Observe**: ingests a `HookPayload` (raw JSON with `hookType`, `sessionId`, `project`, `data`) from an agent lifecycle event (e.g. `post_tool_use`, `prompt_submit`, `subagent_start`). Deduplicates via SHA-256 hashing of tool inputs (`DedupMap`), scrubs secrets/API keys (`stripPrivateData` using `SECRET_PATTERN_SOURCES`), detects and extracts multimodal image data, and writes under a per-session keyed lock (`withKeyedLock`) for atomicity.
2. **Compress**: LLM distills a `RawObservation` into a `CompressedObservation` (`facts`, `narrative`, `concepts`, `importance` 1-10) via XML-based output parsing (`parseCompressionXml`), validated against `CompressOutputSchema` with retry-based self-correction (`compressWithRetry`). If `AGENTMEMORY_AUTO_COMPRESS` is disabled, a zero-LLM heuristic fallback (`buildSyntheticCompression`) is used instead. Immediately indexes the result into both BM25 (`SearchIndex`) and vector (`VectorIndex`).
3. **Remember**: promotes compressed observations to long-term `Memory` objects. Detects near-duplicates via Jaccard similarity, supports versioning/superseding (old memory marked non-latest, new memory references it), and re-indexes into both search structures via `vectorIndexAddGuarded`. Memories are stamped with an `agentId` for multi-agent isolation.
4. **Consolidate/forget**: see below.

## Key patterns & techniques

**Reciprocal Rank Fusion (RRF) hybrid search**: `HybridSearch.tripleStreamSearch()` runs three retrieval paths in parallel — BM25 lexical (`SearchIndex`), vector/cosine semantic (`VectorIndex`), and graph/relational (`GraphRetrieval.searchByEntities`, seeded partly by entities extracted from the top-5 vector hits via `expandFromChunks`). Scores are fused with RRF: `Score(d) = Σ_s w_s · 1/(k + rank_s(d))` where `k` (`RRF_K`) = 60, and per-stream weights default to `bm25Weight=0.4`, `vectorWeight=0.6`, `graphWeight=0.3` (normalized to sum to 1.0 at execution time). After fusion, `diversifyBySession` caps how many results one high-activity session can dominate, and an optional local cross-encoder reranker (`Xenova/ms-marco-MiniLM-L-6-v2`, gated by `RERANK_ENABLED`) rescoring the top 20 via `[SEP]`-joined query-document pairs.

**Query expansion**: `mem::expand-query` uses an LLM to produce `reformulations`, `temporalConcretizations` (resolving relative time like "last week" into concrete dates), and `entityExtractions` before dispatching the actual search — a technique for improving recall on vague or temporally-relative queries.

**Progressive disclosure retrieval**: `mem::smart-search` returns a compact result list first (`CompactSearchResult`: id, title, type, score, timestamp only) so the calling agent doesn't burn its context budget on full content; the agent then requests full detail for specific IDs via `expandIds`, which triggers a second call that fetches full `CompressedObservation` bodies only for those items. This two-phase (list-then-expand) pattern directly manages the token budget of the *calling* agent, not just the memory system's own retrieval cost.

**Knowledge graph with weighted Dijkstra traversal**: nodes (`GraphNode`: file/function/concept/error/decision/pattern/library/person/project/preference/location/organization/event) and directed weighted edges (`GraphEdge`: uses/imports/modifies/causes/fixes/depends_on/related_to/works_at/prefers/blocked_by/caused_by/optimizes_for/rejected/avoids/located_in/succeeded_by, weight 0.0-1.0) are extracted from compressed observations via an LLM producing XML (`GRAPH_EXTRACTION_SYSTEM` prompt, parsed by a regex-based `parseGraphXml` tolerant of self-closing tags and reordered attributes). Retrieval uses `dijkstraTraversal` (replacing an earlier simpler BFS) with edge cost `1/weight` so *strong* relationship chains are preferred over merely *short* ones; default max depth 2. Path relevance score = `avgWeight * (1/pathLength)` — shorter, stronger paths score higher. Deduplication on save merges nodes matching on (name, type) and appends new `sourceObservationIds` rather than creating duplicates.

**Bi-temporal graph modeling**: edges carry `tcommit` (when recorded in the DB), `tvalid`/`tvalidEnd` (the real-world period during which the fact was true), and an `isLatest` flag. `temporalQuery(asOf)` reconstructs the graph exactly as it existed at any past timestamp by filtering on these three fields — a point-in-time recovery mechanism distinct from ordinary versioning.

**Retention scoring — Ebbinghaus forgetting curve**: `mem::retention-score` computes a 0-1 score per memory from three factors: (1) salience — a base value by memory type (`architecture`=0.9, `fact`=0.5, etc.), (2) temporal decay `e^(-λΔT)` with default decay constant λ=0.01, (3) a reinforcement boost from recent accesses in `KV.accessLog`, modeling the psychological "testing effect" (recall strengthens retention).

**4-tier consolidation pipeline** (`mem::consolidate` / `mem::consolidate-pipeline`): (1) group/filter observations with `title` set and `importance ≥ 5`, cluster by `concepts` tags; (2) keep clusters with ≥3 observations, cap at top-8 most-important per concept for LLM efficiency; (3) LLM synthesis with tier-specific prompts — Semantic tier merges `SessionSummary` → `SemanticMemory` facts, Reflect tier synthesizes higher-order `Insight` objects from `GraphNode` clusters, Procedural tier extracts step-by-step `ProceduralMemory` workflows from repeated patterns; (4) versioning — a new memory sharing a title with an existing one marks the old one `isLatest: false`, increments `version`, and records lineage in a `supersedes` array.

**Circuit breaker + fallback chain for LLM providers**: every provider is wrapped in a `ResilientProvider` managing a `CircuitBreaker` state machine (CLOSED → OPEN after 3 consecutive failures within a 60s window → HALF-OPEN after a 30s recovery timeout → back to CLOSED on success or OPEN on failure). A `FallbackChainProvider` tries a prioritized list of providers (e.g. Anthropic → OpenRouter) in sequence per call, propagating the last error only if the whole chain fails. Provider abstraction (`MemoryProvider` interface: `compress()`, `summarize()`) supports Anthropic, OpenAI (also used for DeepSeek/SiliconFlow/Azure), MiniMax (raw fetch to avoid SDK header rejection on its Anthropic-compatible API), OpenRouter, an Agent-SDK-spawning provider, and a `NoopProvider` safe default.

## Practical how-tos

**Onboarding flow**: `agentmemory --reset` or first run triggers interactive CLI onboarding — pick which agents to integrate (native plugin vs. MCP-only), pick an LLM provider for compression/consolidation, and it seeds `~/.agentmemory/.env` from `.env.example`.

**Environment/config knobs worth knowing**: `TOKEN_BUDGET` (default 2000, caps tokens per context injection), `MAX_OBS_PER_SESSION` (default 500), `EMBEDDING_PROVIDER` (defaults to `local` — a Xenova all-MiniLM-L6-v2 model — with cloud options gemini/openai/voyage/cohere/openrouter), `AGENTMEMORY_AUTO_COMPRESS` (toggles LLM compression vs. synthetic heuristic fallback), `RERANK_ENABLED` (toggles the cross-encoder rerank pass).

**Multi-agent task orchestration** (a separate subsystem beyond memory retrieval): `Action` objects (state machine: pending → blocked → active → done/cancelled) form a dependency graph via `ActionEdge` types (`requires`, `unlocks`, `gated_by` a Checkpoint/Sentinel, `conflicts_with` preventing two actions being active simultaneously). The `Frontier` priority queue scores runnable actions: base `priority*10` (clamped 1-10) + age bonus (+0.5/hr capped at 20) + unlock bonus (+5 per downstream action unlocked) + active-status bonus (+15, to encourage finishing started work over starting new work). Agents acquire a 10-minute TTL `Lease` on an action (`mem::lease-acquire`), must renew before expiry for long tasks, and release on completion; expired leases auto-revert the action to `pending` via periodic cleanup — this is the concurrency-safety mechanism preventing two agents from claiming the same task.

**Distillation chain for completed work**: `mem::crystallize` summarizes a chain of `done` actions into a narrative + lessons via a dedicated prompt, then triggers `mem::lesson-save` per extracted lesson (stored with confidence scores). `mem::auto-crystallize` batches this automatically for actions older than 7 days, grouped by parent/project.

## Gotchas & caveats

- **Agent-SDK provider recursion risk**: using `AgentSDKProvider` (which spawns `@anthropic-ai/claude-agent-sdk` child sessions) from within a plugin-hooked agent like Claude Code can cause infinite recursion — a child session inherits the same hooks, so a `Stop`-hook-triggered `mem::summarize` call could spawn a child that fires its own `Stop` hook. Mitigated by an environment marker (`AGENTMEMORY_SDK_CHILD=1`) set before spawning and checked on entry to short-circuit with an empty response — but this is a real footgun if you build custom providers that spawn sub-agents.
- **No LLM key = degraded mode, not failure**: if no LLM provider keys are found, the system silently defaults to a `NoopProvider` (unless `AGENTMEMORY_ALLOW_AGENT_SDK` is set) — memory capture/storage continues but compression/summarization becomes a no-op, which could be surprising if you expect fact extraction without confirming an API key is configured.
- **Circuit breaker failures are strict**: only 3 consecutive failures within 60 seconds trips the breaker to OPEN, after which calls fail immediately with `circuit_breaker_open` for 30 seconds before a single HALF-OPEN probe — a burst of transient errors during a provider outage will fully block memory compression for that window even if the underlying issue resolves faster.
- **Consolidation has a minimum cluster size**: clusters with fewer than 3 related observations are never consolidated regardless of importance — isolated high-value facts that don't cluster with anything else won't get synthesized into higher-level memory unless the pipeline design accounts for this.
- **Auto-forget uses a 0.9 Jaccard threshold for contradiction detection** — two memories need to be quite textually similar (not just semantically related) to be flagged as a superseding pair; conceptually-similar-but-differently-worded memories may accumulate as separate entries rather than being merged.
- **Eviction has hard age/importance cutoffs that run independently of retention scoring**: stale sessions >30 days with no summary, observations >90 days with importance <3 are deleted outright by `mem::evict`, and separately, low-value observations >180 days with importance ≤2 are pruned by `auto-forget` — these are blunt TTL-style rules distinct from the smoother Ebbinghaus decay score, so a memory can be scored as moderately "retained" yet still hit a hard eviction cutoff.
- **Graph staleness on cascade update**: when a memory is superseded, `mem::cascade-update` marks graph nodes/edges derived from the old memory's observations as `stale` (excluded from retrieval) rather than deleting them — stale data persists in storage and could resurface if a consumer bypasses the stale filter.

## Wiki pages used

Overview, Getting Started, Architecture Overview, Core Memory Pipeline, Consolidation & Forgetting, Hybrid Search & RRF Fusion, Knowledge Graph, LLM Providers & Circuit Breaker, Actions Leases & Frontier. Not read in depth: REST API Reference, MCP Server, Claude Plugin & Lifecycle Hooks, Third-Party Agent Integrations, Signals/Checkpoints/Team Collaboration, Mesh Networking, Embedding Providers detail, Telemetry/Health, Web Viewer, Type System/KV Schema, Concurrency, Test Suite, Benchmarks, Security, Governance, Deployment (lower-value/reference-style pages for this distillation). Total wiki: 12 top-level sections per structure.md.
