<div align="center">

# 🧠 DeepSkill

### Portable agent skills, distilled from how the best open-source software is actually built.

[![Skills](https://img.shields.io/badge/skills-10-8b5cf6)](./skills)
[![Repos harvested](https://img.shields.io/badge/repos%20harvested-67-e8b054)](./docs/SOURCES.md)
[![Knowledge briefs](https://img.shields.io/badge/knowledge%20briefs-67-2ea043)](./knowledge/INDEX.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](./CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/dnega-dev/DeepSkill?style=social)](https://github.com/dnega-dev/DeepSkill/stargazers)

**67 production codebases, read wholesale. Distilled into 10 drop-in skills your coding agent can actually use.**

[Browse the skills →](./skills) · [Browse the knowledge base →](./knowledge/INDEX.md) · [How it was built →](./docs/PROCESS.md)

</div>

---

## What is this?

Most "awesome" lists are link dumps. **DeepSkill is the opposite: the knowledge, extracted and pre-digested.**

Every one of these 67 repositories — LangGraph, FastAPI, React, Kafka, Keycloak, unsloth, mem0, Playwright, and 59 more — has an AI-generated wiki on [DeepWiki](https://deepwiki.com). We pulled all of them through DeepWiki's free MCP endpoint, distilled each into a grounded architecture brief, then **synthesized the cross-cutting patterns into 10 portable [Agent Skills](https://www.anthropic.com/news/skills)** — `SKILL.md` files you can drop straight into Claude Code, Cursor, or any agent that reads the format.

The result is two things in one repo:

1. **[10 skills](./skills)** — dense, cross-repo pattern syntheses (agent orchestration, RAG serving, backend platforms, LLM fine-tuning, agent security, and more). Each merges patterns from 2–13 real systems and attributes every mechanism to its source.
2. **[67 knowledge briefs](./knowledge/INDEX.md)** — one grounded architecture extraction per repo. The raw material the skills are built from, browsable on its own.

**Grounding rule:** every claim traces to fetched wiki text that was actually read. DeepWiki wikis are AI-generated *secondary* sources — treat them as a strong starting point, and verify load-bearing facts (exact APIs, version behavior) against the real repo. Nothing here is invented.

---

## The 10 skills

| Skill | What it distills | Sources |
|---|---|---|
| [**deepwiki-harvester**](./skills/deepwiki-harvester/) | The engine behind this repo — harvest any public repo's wiki via DeepWiki's free MCP endpoint, then run parallel multi-repo campaigns. Ships the [`fetch_wiki.py`](./skills/deepwiki-harvester/scripts/fetch_wiki.py) script. | the method itself |
| [**agent-skills-engineering**](./skills/agent-skills-engineering/) | Authoring, triggering, validating & improving skills — progressive disclosure, CSO trigger discipline, TDD-for-docs, hooks vs skills vs rules, anti-rationalization, plugin/marketplace ecosystems. | anthropics/skills, superpowers, claude-code, everything-claude-code, claude-plugins-official, knowledge-work-plugins, cursor/community-plugins, ECC |
| [**agent-orchestration-patterns**](./skills/agent-orchestration-patterns/) | How agent frameworks execute & coordinate — BSP graph execution, reducers, pause/resume HITL models, tool-calling loops, memory taxonomies, 13-tool prompt conventions, real coding-agent harnesses. | LangChain, LangGraph, AutoGPT, Agent Zero, Dify, Langflow, OpenHands, opencode, openclaw, open-agents, Fabric, deepclaude, +2 |
| [**agent-memory-systems**](./skills/agent-memory-systems/) | Durable cross-session memory — additive extraction with supersession-by-linkage, hybrid RRF vs adaptive-divisor fusion, weighted-Dijkstra graph traversal, Ebbinghaus retention. | mem0, agentmemory |
| [**agent-security-sandboxing**](./skills/agent-security-sandboxing/) | Sandboxing & governing autonomous agents — static vs dynamic policy, deterministic policy outside the LLM loop, decaying cryptographic trust, Z3 verification, type-enforced privacy planes. | OpenShell, agent-governance-toolkit, RuView, claw-code |
| [**llm-finetuning-patterns**](./skills/llm-finetuning-patterns/) | Fine-tuning, quantization & weight editing — runtime library patching, fused Triton LoRA+quant kernels, SFT/GRPO/QAT, training-free directional ablation with Optuna search. | unsloth, unsloth-zoo, notebooks, heretic |
| [**rag-llm-serving-patterns**](./skills/rag-llm-serving-patterns/) | RAG & serving — format-aware chunking, RAPTOR/GraphRAG tiers, two-tier reranking, deterministic token triage, Text2SQL, per-layer memory accounting, speculative decoding, continuous batching. | RAGFlow, DB-GPT, Open WebUI, Ollama, Transformers, Prompt Optimizer |
| [**backend-platform-patterns**](./skills/backend-platform-patterns/) | Backend architecture — DI trees, response-model cloning as security, SPI/DPoP identity, event-sourced sharded coordinators, columnar time-series compression, deployment orchestration. | FastAPI, Pydantic, Express, Keycloak, Kafka, EMQX, Redis, TimescaleDB, system-design-primer, Coolify, Kubean, Dograh |
| [**frontend-monorepo-patterns**](./skills/frontend-monorepo-patterns/) | Frontend runtimes, monorepo builds & desktop apps — Fiber double-buffering, host-config seams, Vite HMR, Turborepo caching, RN New Architecture, Tauri/wgpu desktop runtimes. | React, Vite, Turborepo, React Native, Cap, presenton, voicebox, open-pencil |
| [**scraping-mcp-automation-patterns**](./skills/scraping-mcp-automation-patterns/) | Scraping, browser automation, MCP & workflow engines — scored engine waterfalls, lazy locators, transport-agnostic MCP with resumability, V8-isolate sandboxing, local document parsing. | Firecrawl, Playwright, MCP Python SDK, n8n, openai-python, skybridge, liteparse |

---

## A taste — patterns worth stealing

- **The 1% Rule** *(superpowers)* — "if there's even a 1% chance a skill applies, you MUST invoke it." The threshold is deliberately absurd because "when clearly relevant" leaves rationalization room.
- **Commit-then-reveal concurrency** *(LangGraph)* — tasks in a BSP superstep can't see each other's writes until batch commit: race-free parallelism without locks.
- **Done means pushed** *(claw-code)* — a completion check requires `test_green && has_pushed` plus verifiable command provenance. "The agent said it's done" is explicitly rejected.
- **Supersede, don't overwrite** *(mem0)* — chain a new memory to the old via `linked_memory_ids` instead of mutating: audit history preserved, whole lineages deletable atomically.
- **Prove the policy, don't trust it** *(OpenShell)* — a Z3 SMT solver gates auto-approval of policy changes, auto-reloading only on "no new risk found."
- **Illegal states won't compile** *(Cap)* — a type-state builder makes "video config on an audio-only pipeline" a compile error, not a runtime one.

Sixty more like these live in the [knowledge base](./knowledge/INDEX.md).

---

## Use it

**With a skills-aware agent (Claude Code, etc.):** copy any skill folder into your skills directory —

```bash
git clone https://github.com/dnega-dev/DeepSkill.git
cp -r DeepSkill/skills/agent-orchestration-patterns ~/.claude/skills/
```

Each [`SKILL.md`](./skills) is self-contained with YAML frontmatter (`name`, `description`) and a dense body. The agent loads the `description` to decide when to fire, and the body when triggered.

**As a reference:** just read. Start at the [knowledge index](./knowledge/INDEX.md) and jump to any repo's brief, or read a skill top-to-bottom for the synthesized cross-repo view.

**Harvest your own:** the [`deepwiki-harvester`](./skills/deepwiki-harvester/) skill + [`fetch_wiki.py`](./skills/deepwiki-harvester/scripts/fetch_wiki.py) let you point the same pipeline at any public repos you care about. No API key, no auth.

```bash
python3 skills/deepwiki-harvester/scripts/fetch_wiki.py langchain-ai/langgraph
# → deepwiki_corpus/langchain-ai__langgraph/{structure.md, contents.md}
```

---

## How it was built

A two-wave, parallel-agent sweep. Wave 1 harvested featured + stack-aligned repos; Wave 2 harvested every qualifying repo across three GitHub star lists. One orchestrator dispatched 25 subagents across the two waves; each fetched a repo's full wiki, distilled it under a strict grounding rule, and the orchestrator spot-verified distinctive claims against raw wiki text (11/11 checks passed) before synthesis.

Full write-up: [**docs/PROCESS.md**](./docs/PROCESS.md) · every source: [**docs/SOURCES.md**](./docs/SOURCES.md)

---

## Repository layout

```
DeepSkill/
├── skills/            10 portable SKILL.md skills (+ the harvester script)
├── knowledge/         67 grounded architecture briefs, grouped by domain
│   └── INDEX.md       start here to browse the knowledge base
├── docs/
│   ├── PROCESS.md     how the harvest ran, end to end
│   └── SOURCES.md     all 67 repos + DeepWiki/GitHub links + harvest dates
├── CONTRIBUTING.md
└── LICENSE            MIT
```

---

## Contributing

New repos to harvest, sharper distillations, corrections, new skill clusters — all welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md). The one hard rule: **every claim must trace to fetched source text, never to a model's guess.**

## License & attribution

The DeepSkill compilation — the skills, briefs, and tooling here — is [MIT](./LICENSE) licensed. The *knowledge* is distilled from 67 independent open-source projects (each under its own license) via their DeepWiki wikis; every brief links back to its source. DeepWiki is a product of Cognition. This repo is an independent compilation and is not affiliated with or endorsed by DeepWiki, Cognition, or the harvested projects.

<div align="center">
<sub>Built with the <a href="./skills/deepwiki-harvester/">deepwiki-harvester</a> skill. If this saved you time, a ⭐ helps others find it.</sub>
</div>
