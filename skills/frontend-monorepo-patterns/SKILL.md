---
name: frontend-monorepo-patterns
description: Use when building or reviewing frontend runtimes, React applications, monorepos, build graphs, hot reload, React Native, or desktop application architecture.
---

# Frontend, Monorepo, and Desktop Patterns

Keep rendering, platform integration, build orchestration, and application state behind distinct contracts.

## Frontend runtime

Model UI as state transitions, preserve stable identity across renders, and move side effects to explicit lifecycle boundaries. Measure hydration, interaction latency, bundle cost, and accessibility instead of optimizing component count.

## Build graph

Declare package inputs, outputs, environment dependencies, and task edges. Cache only deterministic tasks, include lockfiles and relevant configuration in cache keys, and keep local/CI execution equivalent.

## Platform seams

Use adapter or host-config boundaries for browser, native, and desktop capabilities. Keep permission, filesystem, window, media, and GPU operations outside presentation components.

## Delivery

Test unit behavior, component interaction, end-to-end critical paths, mobile/native integration, and packaged desktop artifacts. Validate upgrade and rollback paths for auto-update systems.

Source briefs: [frontend and desktop](../../knowledge/frontend-and-desktop/).
