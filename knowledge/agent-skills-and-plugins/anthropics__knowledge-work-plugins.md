---
repo: anthropics/knowledge-work-plugins
deepwiki: https://deepwiki.com/anthropics/knowledge-work-plugins
github: https://github.com/anthropics/knowledge-work-plugins
harvested: 2026-07-13
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`anthropics/knowledge-work-plugins`](https://deepwiki.com/anthropics/knowledge-work-plugins) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# anthropics/knowledge-work-plugins — DeepWiki Knowledge

## What it is

`knowledge-work-plugins` is an Anthropic-owned, open-source Claude plugin marketplace containing
first-party and partner-built plugins that extend **Claude Cowork** and **Claude Code** for specific
job functions (sales, finance, legal, data, bio-research, engineering, HR, small-business, etc.).
Each plugin is a file-based bundle of Markdown + JSON — no code, no build step, no infrastructure —
that packages domain expertise (skills), explicit actions (commands), and external tool connections
(MCP servers). The repo is structured as a `.claude-plugin/marketplace.json` manifest owned by
`{name: 'Anthropic'}` listing ~20 plugin directories plus a `partner-built/` subtree (Slack, Apollo,
Common Room, Brand Voice/Tribe AI, Zoom).

Target users: end users in a role who want Claude to understand their domain; team admins who
customize plugins with company-specific terminology/tools; plugin developers who build new plugins,
often via the meta-plugin `cowork-plugin-management`.

## Architecture

Four core design principles run through the whole repo:

1. **File-based components** — all logic is Markdown/JSON, no compiled code.
2. **Tool abstraction** — skills reference `~~category` placeholders (e.g. `~~data warehouse`,
   `~~project tracker`) instead of hardcoding a vendor, so one plugin works with Snowflake or
   BigQuery, Jira or Linear, etc.
3. **Auto-activation** — skills fire automatically when the user's request matches trigger phrases in
   their description; commands require explicit `/plugin:action` invocation.
4. **MCP integration** — all external tool access goes through Model Context Protocol servers declared
   in `.mcp.json`.

Standard plugin directory layout:
```
plugin-name/
├── .claude-plugin/plugin.json   # Required manifest (name, version, description, author,
│                                #   optional path overrides: commands, agents, hooks, mcpServers)
├── skills/skill-name/
│   ├── SKILL.md                 # Core knowledge, YAML frontmatter (name, description)
│   ├── references/              # Progressive-disclosure docs, loaded on demand
│   ├── examples/
│   └── scripts/
├── commands/                    # Legacy explicit slash commands (single .md files)
├── agents/agent-name.md         # Subagent definitions, YAML frontmatter (model, color, tools)
├── hooks/hooks.json              # Event-driven logic (PreToolUse, PostToolUse, SessionStart, ...)
├── .mcp.json                     # MCP server definitions (mcpServers: { id: {type, url, oauth?} })
├── CONNECTORS.md                 # Documents ~~ placeholder categories (required if placeholders used)
└── README.md
```

`plugin.json` only strictly requires `name` (kebab-case). It can override auto-discovery paths for
`commands`, `agents`, `hooks`, `mcpServers`.

**Skills use three-tier progressive disclosure** to manage the context window:
1. Metadata (`name` + `description` from frontmatter) — always in context.
2. `SKILL.md` body — loaded only when the description's trigger phrases match the conversation.
   Keep it under ~2,000–3,000 words (sources disagree slightly, both cited).
3. Bundled resources (`references/`, `examples/`, `scripts/`) — loaded by Claude only when it
   explicitly needs deeper detail.

**Skills vs. Commands** (explicit distinction drawn by the wiki):

| Aspect | Skills | Commands (legacy) |
|---|---|---|
| Activation | Automatic (description match) | Explicit slash command |
| Location | `skills/name/SKILL.md` | `commands/name.md` |
| Visibility | Background/progressive disclosure | Slash-command menu |
| Control | Claude decides | User decides |

The Cowork UI presents both as one "Skills" concept but the wiki explicitly states new plugins should
be scaffolded with `skills/*/SKILL.md`, not legacy `commands/`, because only the skills format supports
progressive disclosure via `references/`.

**Connector/placeholder system**: skill text says things like "Create ticket in `~~project tracker`".
`CONNECTORS.md` documents the category; `.mcp.json` resolves it to a concrete MCP server id/URL at
runtime. Swapping vendors means editing `.mcp.json` only — skill logic never changes. Example
category→keyword mapping used by the discovery tool: `project-management` → `["asana","jira","linear",
"monday","tasks"]`; `crm` → `["salesforce","hubspot","crm"]`; `data-warehouse` → `["bigquery",
"snowflake","redshift"]`; `analytics-bi` → `["datadog","grafana","analytics"]`.

**Agents** (`agents/*.md`) are restricted-toolset sub-personas with YAML frontmatter specifying
`model` (inherit/sonnet/opus/haiku), `color` (UI: blue/cyan=analysis, magenta=creative, green=success,
yellow/red=validation/security), and a `tools` allowlist (e.g. `["Read","Grep","Glob"]`).

**Hooks** (`hooks/hooks.json`) intercept lifecycle events: `PreToolUse`, `PostToolUse`, `SessionStart`,
`UserPromptSubmit`, `Stop`, `SubagentStop`, `SessionEnd`, `PreCompact`, `Notification`. Two hook types:
`prompt` (Claude evaluates via natural language) and `command` (deterministic shell script that must
return JSON `{"decision": "approve"|"block"|"ask_user", "reason": "..."}`).

## Key patterns & techniques

- **`${CLAUDE_PLUGIN_ROOT}` variable**: all intra-plugin path references in `.mcp.json` and hooks must
  use this instead of absolute/hardcoded paths, for portability across install locations.
- **MCP config formats**: `.mcp.json` supports "wrapped" (`{"mcpServers": {...}}`) format; server types
  are `stdio` (local process, `command`+`args`), `http` (remote URL), and `sse`. Some servers include
  OAuth blocks (`{"oauth": {"clientId": "...", "callbackPort": 3118}}`) for user-specific auth (e.g.
  Slack). Some entries have empty URLs — these are placeholders for tools requiring separate user
  configuration (e.g. `benchling`, `google calendar`).
- **MCP config precedence**: (1) explicit path in `plugin.json`'s `mcpServers` field, (2) default
  `.mcp.json` at plugin root, (3) if the plugin only bundles `.mcpb` files, a new `.mcp.json` is
  created at root for custom connections.
- **`cowork-plugin-management` meta-plugin**: a plugin that builds/edits other plugins. Two skills:
  - `create-cowork-plugin` — five-phase guided workflow: Discovery → Planning (plugin.json) → Design
    (component-schemas.md) → Implementation (skills/, agents/, .mcp.json) → Review/packaging into a
    `.plugin` file delivered to `outputs/`.
  - `cowork-plugin-customizer` — resolves `~~` placeholders: greps for `~~` prefixes, calls
    `search_mcp_registry(keywords=[...])` to find candidate MCP servers, presents choice to user,
    calls `suggest_connectors()` to render "Connect" UI buttons, then updates `.mcp.json` with the
    resolved server URL. This is the concrete tool-call sequence used to turn a generic template
    plugin into a company-specific one.
- **Discovery tools exposed by cowork-plugin-management**: `search_mcp_registry` (returns name, url,
  tools, connected status from the global MCP directory) and `suggest_connectors` (triggers UI Connect
  buttons for the end user to authorize a new MCP server).
- **Bio-research plugin as a concrete large example**: 11 MCP integrations (PubMed/bioRxiv/Consensus
  for `~~literature`, Wiley for `~~journal access`, Sage Bionetworks/Synapse for `~~data repository`,
  ChEMBL for `~~chemical database`, OpenTargets for `~~drug targets`, clinical trials registry,
  BioRender for illustration, Owkin for AI research, Benchling placeholder for lab platform, plus two
  optional binary-only servers: 10X Genomics txg-mcp and Harvard MIMS ToolUniverse) combined with 6
  analysis skills (single-cell RNA QC via scverse, scvi-tools deep learning, Nextflow/nf-core
  pipelines, lab-instrument-to-Allotrope(ASM) format conversion, and a 9-skill "Scientific Problem
  Selection" framework based on Fischbach & Walsh). Installed via `/install anthropics/
  knowledge-work-plugins bio-research` then `/start` to initialize.

## Practical how-tos

- **Install a plugin**: `claude plugin marketplace add anthropics/knowledge-work-plugins` then
  `claude plugin install sales@knowledge-work-plugins`.
- **Author a `plugin.json`**:
  ```json
  {
    "name": "data-analyst",
    "version": "0.1.0",
    "description": "Expert SQL generation and visualization for Snowflake.",
    "author": { "name": "Engineering Team" },
    "mcpServers": "./.mcp.json",
    "hooks": "./hooks/hooks.json"
  }
  ```
- **Author a `SKILL.md`**: frontmatter description must be third-person and include quoted trigger
  phrases ("This skill should be used when the user asks to 'design an API'..."); body must be written
  in imperative/infinitive form ("Parse the file," not "You should parse").
- **Local MCP server entry** (stdio):
  ```json
  { "mcpServers": { "local-tool": { "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/server.js"] } } }
  ```
- **Customization workflow for admins**: (1) swap connectors by editing `.mcp.json` URLs, (2) add
  company terminology/org structure directly into skill files, (3) adjust workflow markdown to match
  internal process — all without touching any code.
- **Data plugin command surface** (concrete example of commands as user-facing entry points):
  `/analyze`, `/explore-data`, `/write-query`, `/create-viz`, `/build-dashboard`, each backed by a
  file in `commands/`.

## Gotchas & caveats

- Commands are explicitly called out as "legacy" — the wiki repeatedly states new plugins should
  default to `skills/*/SKILL.md` rather than `commands/*.md` unless a legacy single-file format is
  specifically required, because skills alone support progressive disclosure.
- The `~~` placeholder pattern should only be introduced "if the plugin is intended for external
  distribution" — for a single-org internal plugin it's unnecessary indirection.
- Governance: the repo runs an automated CI/CD pipeline distinguishing "vendored" (local) plugins from
  "external" plugins pinned to git SHAs. `bump-plugin-shas.yml` opens per-entry PRs to update pinned
  SHAs; `scan-plugins.yml` runs an LLM-based policy reviewer (checking hook registration scope,
  telemetry disclosure, deceptive descriptions) against `.github/policy/prompt.md` / `schema.json`,
  using Workload Identity Federation for keyless auth and caching (plugin, SHA) verdicts (invalidated
  when the policy prompt/schema changes); `check-mcp-urls.yml` probes MCP endpoints for liveness;
  `revert-failed-bumps.yml` rolls back SHA bumps that fail scanning. This is a real-world example of
  governing a marketplace of many independently-evolving, partially-external plugin definitions.
- SKILL.md word-limit guidance is inconsistent across pages of the same wiki (one page says "under
  2,000 words", another says "under 3,000 words") — treat as "keep it short, push detail to
  references/" rather than a hard number.

## Wiki pages used

Introduction; What are Knowledge Work Plugins?; Plugin System Architecture; Plugin Structure and
Components; Skills vs Commands; MCP Server Integration; Customizing Plugins; Bio-Research Overview and
Capabilities; Creating a New Plugin; Using cowork-plugin-management; CI/CD and Governance. (Structure.md
also lists Plugin Marketplace, Installation and Getting Started, Connector System and Tool Abstraction,
and per-business-function plugin pages, not read in full due to redundancy with pages above.)
