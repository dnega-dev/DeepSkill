---
repo: mem0ai/mem0
deepwiki: https://deepwiki.com/mem0ai/mem0
github: https://github.com/mem0ai/mem0
harvested: 2026-07-13
cluster: agent-memory
---

> Distilled from the DeepWiki wiki for [`mem0ai/mem0`](https://deepwiki.com/mem0ai/mem0) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# mem0ai/mem0 — Distilled Knowledge

## What it is

Mem0 ("mem-zero") is a universal, self-improving memory layer for AI applications that stores and retrieves conversational history, user preferences, and domain knowledge across sessions [README.md:71-73]. It is a polyglot monorepo (Python + TypeScript SDKs, CLIs, server) offering two deployment modes with a consistent API: a hosted **Platform** (`MemoryClient`/`AsyncMemoryClient`) and a self-hosted **OSS** SDK (`Memory`/`AsyncMemory`). In April 2026 the project shipped a new **V3 memory algorithm** — a single-pass "additive extraction" pipeline replacing the older two-LLM-call ADD/UPDATE/DELETE/NONE decision process — reported to score 91.6 on the LoCoMo benchmark [README.md:45-62]. Core capabilities: multi-level memory scoping (User/Agent/Session), hybrid retrieval (vector + BM25 keyword + entity/graph signals fused in parallel), temporal reasoning, and built-in graph memory for entity-relationship recall.

## Architecture

**Three-tier design**: Client Layer (Python/TS SDKs, REST API, CLI, framework integrations) → Core Memory System (orchestration + factories) → Storage Layer (vector stores, graph databases, history/audit DB).

**Core orchestrator**: The `Memory` class (`mem0/memory/main.py:214`) is instantiated from a Pydantic `MemoryConfig` (`mem0/configs/base.py:15`) and wires up six components via factories in `mem0/utils/factory.py`:
| Component | Attribute | Factory |
|---|---|---|
| Vector store | `self.vector_store` | `VectorStoreFactory.create()` |
| Graph store (optional) | `self.graph` | `GraphStoreFactory.create()` — only if `graph_store` config present, sets `self.enable_graph=True` |
| History DB | `self.db` | `SQLiteManager()` directly |
| LLM | `self.llm` | `LlmFactory.create()` |
| Embedder | `self.embedding_model` | `EmbedderFactory.create()` |
| Reranker (optional) | `self.reranker` | `RerankerFactory.create()` |

The factory pattern abstracts over 60 providers: 3+ LLM providers (OpenAI, Anthropic, Groq, Ollama, AWS Bedrock, etc.), vector stores split into Cloud/Managed (Pinecone, Upstash, MongoDB, Azure AI Search, Databricks, Vertex AI Vector Search, Turbopuffer), Open Source (Qdrant, Chroma, Milvus, PGVector, Redis, Valkey, Elasticsearch, OpenSearch, Weaviate), and Local/Embedded (FAISS, S3 Vectors); and graph stores (Neo4j, Memgraph, AWS Neptune Analytics, Kuzu).

**Add operation lifecycle** (V3 additive pipeline, `Memory.add()` → `_add_to_vector_store()` in `main.py:382-536`):
1. Context Retrieval — pull a rolling window of the last 10 messages from `SQLiteManager` for temporal context.
2. Single-Pass Extraction — one LLM call using `ADDITIVE_EXTRACTION_PROMPT`, which does in-context deduplication itself (no separate ADD/UPDATE/DELETE decision call anymore).
3. Entity Linking — `extract_entities()` links facts into a `{collection}_entities` graph.
4. Persistence — `Memory._create_memory()` writes to the vector store and chains new memories to prior ones via `linked_memory_ids` rather than mutating in place.
5. Vector and graph writes execute concurrently via `ThreadPoolExecutor` (`main.py:411-419`); a `SQLiteManager.add_history()` audit record is written for every change.

**Search operation lifecycle** (`Memory.search()`, `main.py:800-899`): embed the query → concurrently query vector store and graph store → fuse scores with `score_and_rank()` (`mem0/utils/scoring.py:60`) → optional reranker pass if `rerank=True` and a reranker is configured.

**History/audit**: `SQLiteManager` (`mem0/memory/storage.py:11`) maintains a `history` table (columns: id, memory_id, old_memory, new_memory, event [ADD/UPDATE/DELETE], actor_id, role) and a `messages` table for session context — every add/update/delete calls `self.db.add_history()`.

## Key patterns & techniques

**Session scoping / multi-tenant isolation**: every operation must supply at least one of `user_id`, `agent_id`, or `run_id`; `app_id` is also available. `_validate_and_trim_entity_id()` (`main.py:114-142`) rejects empty/whitespace-only/internally-spaced IDs. `_build_filters_and_metadata()` (`main.py:129-207`) produces both a `base_metadata_template` (attached to new memories) and `effective_query_filters` (applied on search) from the same session IDs — this is the mechanism that prevents cross-user/cross-agent leakage. Vector stores build dedicated payload indexes for these fields (Qdrant creates keyword indexes on `user_id`/`agent_id`/`run_id`/`actor_id` at collection init for O(1) filtered lookups).

**Advanced filter operators** (Platform v2 filters): `eq` (default), `ne`, `in`, `gt`/`lt`/`gte`, `contains`, `icontains` (case-insensitive substring), `AND`/`OR` logical combination, and `*` as a wildcard for "any non-null value." Example: `{"OR": [{"user_id": "u1"}, {"run_id": "r1"}]}`.

**Graph memory**: entities (proper nouns/names/key phrases) become graph nodes; memories mentioning the same entity get linked through it, enabling multi-hop questions like "what do we know about Alice?" across unrelated conversations. On the hosted Platform, graph memory is *native and built-in* — no external graph DB or `enable_graph=True` config needed; entity matches simply boost a memory's combined relevance `score`. In OSS, you must configure an external `graph_store` provider. Entity deduplication uses cosine similarity against a configurable `threshold` (default **0.7**) so that e.g. "john_smith" and "john_s" merge into one node instead of creating duplicates; `0.9-1.0` = strict, `0.7-0.8` = balanced (default), `0.5-0.6` = lenient/aggressive, `<0.5` not recommended (high false-merge risk). During `search()`, BM25 reranking (via `rank_bm25`) is applied to graph-retrieved relationships before they're passed as context.

**Hybrid retrieval scoring** (`mem0/utils/scoring.py`): `score_and_rank()` combines up to three signals — semantic (vector) similarity, BM25 keyword score, and an entity/graph boost — via an *adaptive divisor* so the combined score always normalizes to [0,1]: divisor is 1.0 with semantic only, 2.0 with semantic+BM25, 2.5 with all three (entity boost weight = 0.5). Raw BM25 scores are unbounded, so they're squashed through a logistic sigmoid (`normalize_bm25`) whose midpoint/steepness parameters scale with query length (e.g. ≤3 terms: midpoint 5.0/steepness 0.7; >15 terms: midpoint 12.0/steepness 0.5) — short queries get a stricter curve than long ones.

**Custom prompts**: `MemoryConfig` exposes `custom_fact_extraction_prompt`, `custom_update_memory_prompt`, and `custom_instructions`. A one-off `prompt=` argument to `add()` overrides config-level settings for that single call. Requirements if you override: fact-extraction prompts must return `{"facts": [...]}"`; update prompts must return `{"memory": [{"id", "text", "event", "old_memory"?}]}`.

**Reranking as an optional second stage**: triggered by passing `rerank=True` to `search()`. Five providers via `RerankerFactory`: `cohere` (hosted, medium latency), `sentence_transformer` (local HF cross-encoders, low latency), `zero_entropy` (hosted neural), `llm_reranker` (any configured LLM scores 0.0-1.0 per document, high latency), `huggingface` (local `AutoModelForSequenceClassification` cross-encoders, sigmoid-normalized logits). `LLMReranker` sends the query and each candidate document as *separate messages* specifically to reduce prompt-injection risk from stored memory content, truncates input to 4000 chars (`_MAX_INPUT_LEN`), and extracts the score via regex clamped to [0,1]. All rerankers degrade gracefully on failure: log a warning (not an exception) and fall back to original vector-search order with a neutral 0.0 score, while still respecting the requested `top_k`.

**LLM proxy / drop-in memory augmentation**: `mem0.proxy.main.Mem0` wraps `litellm.completion()` behind an OpenAI-Chat-Completions-shaped interface (`Mem0(...).chat.completions.create(...)`). On each call it: (1) fires off `_async_add_to_memory()` on a daemon thread (non-blocking write), (2) builds a search query from the last 6 messages and calls `_fetch_relevant_memories()`, (3) prepends the retrieved facts (and entities/relations for OSS) to the final user message via `_format_query_with_memories()`, then (4) forwards to `litellm.completion()`. This is the "auto-inject memory into every chat call" pattern — supports 100+ providers through LiteLLM and validates function-calling support before proceeding.

## Practical how-tos

**Raw storage without LLM overhead**: pass `infer=False` to `add()` to skip fact extraction/conflict resolution entirely and store each message verbatim as its own vector entry — useful for pure conversation logging or minimizing latency.

**Multi-agent partitioning**: combine `user_id` + `agent_id` (+ optionally `run_id`) on both write and read to prevent one agent's context leaking into another's (e.g., a travel-planner agent's memories bleeding into a chef-recommender agent):
```python
client.add(messages, user_id="traveler_cam", agent_id="travel_planner", run_id="tokyo-2025-weekend")
filters = {"AND": [{"user_id": "traveler_cam"}, {"agent_id": "travel_planner"}, {"run_id": "tokyo-2025-weekend"}]}
results = client.search("dietary restrictions", filters=filters)
```

**Deleting superseded chains**: `delete(memory_id, delete_linked=True)` transitively removes an entire chain of memories connected via `linked_memory_ids` (the V3 superseding mechanism), not just the single node.

**Backdating memories**: pass a `timestamp` parameter to `add()` to insert historically-dated facts without disturbing current chronological ordering.

**Custom LLM for graph extraction only**: `config["graph_store"]["llm"]` lets you use a stronger/more expensive model (e.g. GPT-4, Claude 3.7 Sonnet) just for entity/relationship extraction while the rest of the pipeline uses a cheaper global `config["llm"]`.

**Installing graph extras**: graph dependencies are optional — `pip install "mem0ai[graph]"`, or `pip install "mem0ai[graph,extras]"` for AWS Neptune/Bedrock support.

## Gotchas & caveats

- **V3 dropped explicit UPDATE/DELETE decisions.** The old two-call pipeline asked the LLM to classify each fact as ADD/UPDATE/DELETE/NONE against existing memories; V3's single-pass model is effectively ADD-only, relying on the LLM's in-context understanding to skip already-known facts, plus a `linked_memory_ids` chain for logical supersession. If you built logic around explicit UPDATE/DELETE event handling from responses, verify it against the actual version you're running.
- **Reasoning-model output must be scrubbed.** `remove_code_blocks()` strips markdown fences *and* `<think>`/`<reasoning>` tags (e.g. from DeepSeek-R1) before JSON parsing; the TypeScript SDK additionally strips ChatML/OpenRouter noise tokens (`<|end_of_text|>`, `<|eot_id|>`, `<|im_end|>`). If you swap in a new reasoning model, confirm this cleanup path covers its tag format or JSON parsing will break.
- **`ensure_json_instruction` auto-injects a JSON directive** if neither your custom prompt nor the default mentions "json" — a safety net, but it means a custom prompt claiming JSON output implicitly relies on this string check ("json" must appear somewhere, case-insensitive).
- **Graph Memory ≠ Entity ID.** Don't confuse graph nodes (e.g. a node representing "Alice") with the `user_id`/`agent_id`/`app_id`/`run_id` scoping identifiers — memories stay isolated by entity ID even when they share a graph node.
- **Telemetry is opt-out by default**, sending anonymized events (OS, Python version, method names) to PostHog (hardcoded project key/host in source). 10% sampling on hot-path events by default (`MEM0_TELEMETRY_SAMPLE_RATE`), but lifecycle events (`mem0.init`, `mem0.reset`, `_create_procedural_memory`, `$identify`) always fire at 100%. Disable via `MEM0_TELEMETRY=False`.
- **Vector store score semantics differ per backend** — e.g. ChromaDB returns distances and converts via `score = 1.0 / (1.0 + raw_distance)`, while Qdrant returns native similarity; if you're comparing raw scores across backends or hand-rolling threshold logic, check the specific provider's `_parse_output`.
- **Session IDs are strictly validated**: empty, whitespace-only, or internally-whitespaced `user_id`/`agent_id`/`run_id` values raise `ValueError` rather than being silently accepted.

## Wiki pages used

Overview, System Architecture, Core Architecture (skim), Memory System, Memory Class (Open Source) (skim), Intelligent Memory Processing, Graph Memory Overview, Graph Store Providers, Similarity Thresholds, Session Scoping and Filters, Proxy Integration, Custom Prompts, Telemetry and Analytics. Total wiki: 17 top-level sections / ~50 sub-pages per structure.md; only the highest-value architecture/memory-mechanics pages were read in full — API reference, per-provider config pages (Vector Store Providers detail, LLM Providers detail, Embeddings), SDK client pages, and framework-integration pages were skipped as lower-value/repetitive for this distillation.
