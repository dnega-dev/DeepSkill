---
name: agent-memory-systems
description: Use when designing, implementing, or evaluating durable agent memory, retrieval, supersession, scope isolation, retention, deletion, or memory ranking.
---

# Agent Memory Systems

Treat memory as versioned evidence with scope, provenance, lifecycle, and deletion semantics.

## Data model

Each memory should carry stable identity, content, source, scope, created time, validity interval, status, and links to prior or conflicting memories. Never overwrite a correction silently; append and link it as a superseding record.

## Retrieval

1. Enforce scope before ranking.
2. Retrieve lexical, vector, and graph candidates independently.
3. Normalize or rank-fuse streams deterministically.
4. Apply reranking only after authorization filtering.
5. Return provenance and lifecycle status with results.
6. Degrade explicitly when a retrieval stream fails.

## Lifecycle

Define idempotent writes, correction, soft deletion, hard deletion, retention class, expiry, and lineage deletion. Credentials and credential-shaped content require recursive scrubbing before persistence.

## Evaluation

Test cross-scope isolation, repeated-fact deduplication, linked corrections, conflicting facts, historical reads, stream failure, reranker failure, deletion replay, and audit completeness.

Source briefs: [agent memory](../../knowledge/agent-memory/).
