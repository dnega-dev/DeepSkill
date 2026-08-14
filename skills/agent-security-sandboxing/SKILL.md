---
name: agent-security-sandboxing
description: Use when securing autonomous agents, sandboxes, tool permissions, policy engines, approval workflows, trust boundaries, or agent-generated policy changes.
---

# Agent Security and Sandboxing

Keep enforcement deterministic, least-privileged, and outside the model's reasoning loop.

## Architecture

- Run tools in isolated processes or containers with explicit filesystem, network, credential, and resource limits.
- Issue short-lived, task-scoped capabilities instead of ambient credentials.
- Separate policy proposal from policy enforcement.
- Log every permission decision and tool effect with tamper-evident provenance.
- Default unknown actions to denied or human review.

## Policy changes

Represent policy as structured data. Compare proposed policy with the current policy, identify newly granted capabilities, and verify invariants before activation. Agent-generated changes must never approve themselves.

## Trust model

Trust decays across time, delegation depth, and unverifiable transformations. Re-establish it through signed artifacts, deterministic validation, reproducible builds, and human approval at critical boundaries.

## Tests

Exercise path traversal, network egress, credential access, command injection, confused-deputy delegation, stale approvals, policy expansion, resource exhaustion, and audit-log gaps.

Source briefs: [agent security and governance](../../knowledge/agent-security-and-governance/).
