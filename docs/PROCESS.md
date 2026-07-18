# How DeepSkill was built

DeepSkill is the output of a repeatable, parallel-agent harvest pipeline — captured as the [`deepwiki-harvester`](../skills/deepwiki-harvester/) skill so anyone can run it again. It ran in two waves.

## The route

DeepWiki (by Cognition/Devin) hosts AI-generated documentation wikis for tens of thousands of public GitHub repos and exposes a **free, no-auth MCP endpoint** at `https://mcp.deepwiki.com/mcp` (JSON-RPC over streamable HTTP/SSE). Three public tools: `read_wiki_structure`, `read_wiki_contents`, `ask_question`. This beats scraping the JS-rendered site — it returns clean markdown. A stdlib-only [`fetch_wiki.py`](../skills/deepwiki-harvester/scripts/fetch_wiki.py) handles the handshake and streams each repo's `structure.md` + `contents.md` to disk (0.1–2.2 MB per repo — never into an agent's context window).

## Wave 1 — 2026-07-09 · 36 repos → 7 skills

- **Targets:** DeepWiki's featured/trending set plus repos matching an active production stack (LangGraph, FastAPI, Pydantic, React/Vite, Express, Keycloak, Kafka, EMQX, TimescaleDB, Turborepo, React Native, and more).
- **Harvest:** 6 parallel subagents, ~6 repos each. 36/36 fetched, zero retries (~29 MB corpus).
- **Distill:** each repo → a grounded `KNOWLEDGE.md` (What it is / Architecture / Key patterns / How-tos / Gotchas / Pages used), claims only from fetched wiki text.
- **Verify:** the orchestrator grep-checked 5 distinctive claims against raw wiki text — 5/5 confirmed.
- **Synthesize:** 6 drafter subagents merged domain clusters into 7 cross-repo skills.

## Wave 2 — 2026-07-13 · 31 repos → 3 new + 5 extended skills

- **Targets:** every qualifying repo across three GitHub star lists — `collab` (empty), `helpful-ai-tools` (21), `my-stack` (25) — deduplicated to 32 unique public third-party repos. GitHub's `/stars/<user>/lists/<slug>` pages are login-walled to anonymous requests, so enumeration used a rendering fetcher plus the starred API for cross-check.
- **Harvest:** 6 parallel subagents. 31/32 succeeded. One repo — `Mfrostbutter/Infra-AI-IT-Team-Runbook` — was not indexed on DeepWiki at harvest time, so it was recorded and skipped, not fabricated.
- **Verify:** 6 more distinctive claims spot-checked against raw wiki text — 6/6 confirmed (mem0's `linked_memory_ids`, OpenShell's Z3 prover, unsloth's Triton patching, heretic's directional ablation, agent-governance's Ed25519 trust rings, agentmemory's Ebbinghaus decay).
- **Integrate:** 3 new skills (LLM fine-tuning, agent security/sandboxing, agent memory) + sourced sections appended to 5 existing skills. Three new domains emerged: Agent Memory, Agent Security & Governance, LLM Fine-tuning & Model Research.

## Totals

| | Wave 1 | Wave 2 | Total |
|---|---|---|---|
| Repos harvested | 36 | 31 | **67** |
| Spot-checks passed | 5/5 | 6/6 | **11/11** |
| Skills | 7 new | 3 new + 5 extended | **10** |

## The grounding invariant

Every distilled claim comes from fetched wiki text that was actually read — never from a model's training knowledge. Distinctive claims were spot-verified against raw `contents.md` by grep before integration. DeepWiki wikis are AI-generated documentation of a repo's code: a high-quality **secondary** source, not the code itself. For load-bearing facts (exact API signatures, version-specific behavior), verify against the actual repository. Two repos in the corpus (`galilai-group/stable-worldmodel`, `facebookresearch/esm`) are pure ML research and are included as knowledge briefs but were not forced into a skill, since no platform-engineering pattern transferred cleanly.
