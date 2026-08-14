---
name: scraping-mcp-automation-patterns
description: Use when building or reviewing scraping, browser automation, MCP servers or clients, workflow engines, API SDKs, or local document-processing automation.
---

# Scraping, MCP, and Automation Patterns

Prefer declared interfaces, resumable state, and observable failure over opaque automation.

## Acquisition

Use documented APIs first. For browser automation, use semantic locators, wait on observable conditions, preserve canonical URLs, respect access controls and rate limits, and classify failures before fallback. Never convert a denial into an evasion strategy.

## MCP

Keep tools small, typed, and transport-independent. Validate arguments, return structured errors, declare side effects, support cancellation, and make resumable operations expose stable continuation state. Keep authentication and authorization outside tool descriptions.

## Workflow engines

Represent executions as durable state transitions. Make nodes idempotent, persist before external effects, bound retries, separate retryable from terminal errors, and expose partial completion.

## Document processing

Detect format from content and metadata, preserve source offsets, isolate parsers, cap resource use, and retain hashes plus transformation receipts.

Source briefs: [tooling, MCP, and automation](../../knowledge/tooling-mcp-automation/).
