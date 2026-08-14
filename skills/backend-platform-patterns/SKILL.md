---
name: backend-platform-patterns
description: Use when designing or reviewing backend APIs, service platforms, identity, event streaming, caches, databases, deployment orchestration, or distributed-system boundaries.
---

# Backend Platform Patterns

Make contracts explicit at service boundaries and choose state models from failure requirements.

## Application boundary

Validate input into typed domain models, inject dependencies through visible constructors or providers, and serialize through response schemas that cannot expose undeclared fields. Keep authentication, authorization, and business rules distinct.

## State and messaging

- Use transactions for local invariants.
- Use durable events for cross-service propagation.
- Partition by a stable key and make consumers idempotent.
- Treat caches as derived state with explicit invalidation and staleness policy.
- Select relational, key-value, time-series, or log storage from query and consistency needs.

## Identity

Validate issuer, audience, expiry, signature, and proof-of-possession where applicable. Translate external identity into an internal principal once, then authorize every resource access against that principal.

## Operations

Provide health, readiness, migrations, rollback, bounded retries, structured logs, metrics, traces, and reproducible deployment configuration before scaling topology.

Source briefs: [backend and deployment](../../knowledge/backend-and-deployment/).
