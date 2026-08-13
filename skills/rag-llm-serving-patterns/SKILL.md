---
name: rag-llm-serving-patterns
description: Use when designing or tuning RAG pipelines, document ingestion, chunking, retrieval, reranking, LLM serving, batching, caching, or inference memory.
---

# RAG and LLM Serving Patterns

Separate retrieval quality, evidence integrity, and serving performance so each can be measured independently.

## RAG pipeline

1. Parse with format-aware boundaries and preserve source offsets.
2. Normalize metadata without discarding original text.
3. Chunk by document structure, then add parent/child or hierarchical summaries when needed.
4. Retrieve with explicit corpus and authorization filters.
5. Fuse candidate streams deterministically.
6. Rerank within a bounded candidate budget.
7. Generate only from retained evidence and return resolvable citations.
8. Evaluate retrieval, citation, answer, latency, and cost separately.

## Serving

Budget model weights, KV cache, activations, adapters, and runtime overhead per device. Use continuous batching for throughput, prefix caching for repeated context, and speculative decoding only when acceptance rate repays draft-model cost.

## Failure behavior

Expose empty retrieval, parser loss, stale index, reranker failure, truncation, and context overflow. Do not silently substitute model memory for missing evidence.

Source briefs: [RAG and LLM serving](../../knowledge/rag-and-llm-serving/).
