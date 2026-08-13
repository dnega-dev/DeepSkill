---
name: agent-orchestration-patterns
description: Use when designing or reviewing multi-agent execution, task graphs, tool loops, delegation, checkpoints, resumability, or human approval boundaries.
---

# Agent Orchestration Patterns

Make coordination state explicit and keep policy outside probabilistic execution.

## Select an execution model

- Use a graph when tasks have dependencies, branches, retries, or resumable checkpoints.
- Use a supervisor loop when workers share a compact state and tasks emerge dynamically.
- Use parallel fan-out only for independent work with immutable inputs.
- Use a deterministic pipeline when the sequence is fixed.

## Required state

Track task identity, input provenance, status, attempts, produced artifacts, verification evidence, and the next permitted transition. Do not use chat history as the only state store.

## Safety and correctness

- Commit parallel writes at a synchronization boundary.
- Make reducers deterministic and associative where order may vary.
- Separate tool execution from tool selection.
- Persist checkpoints before irreversible or expensive actions.
- Require human approval at permission, financial, publication, and destructive boundaries.
- Treat worker completion as a claim until outputs are verified.

## Failure handling

Classify errors as retryable, terminal, policy-blocked, or incomplete. Bound retries, vary the attempted remedy, preserve the last useful artifact, and resume from a checkpoint instead of replaying successful work.

Source briefs: [agent orchestration and harnesses](../../knowledge/agent-orchestration/).
