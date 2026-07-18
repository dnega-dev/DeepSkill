---
repo: openclaw/openclaw
deepwiki: https://deepwiki.com/openclaw/openclaw
github: https://github.com/openclaw/openclaw
harvested: 2026-07-13
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`openclaw/openclaw`](https://deepwiki.com/openclaw/openclaw) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# openclaw/openclaw — DeepWiki Knowledge

## What it is

OpenClaw is a self-hosted, multi-platform "AI gateway" and personal-assistant system: a Node.js/
TypeScript control plane (the **Gateway**) that connects messaging platforms (WhatsApp, Telegram,
Slack, Discord, iMessage, Feishu, LINE, MS Teams, etc.) to AI agents, and orchestrates multi-agent
workflows, tool use, skills, and native mobile/desktop clients on top. It's powered by an embedded
"Pi Agent Core" runtime plus a "Codex" app-server harness for coding/tool-heavy workloads, and it
explicitly supports CLI-backend agents (Claude Code, Codex, Gemini CLI, Cursor) via the **Agent
Control Protocol (ACP)**. The system is built around a **Personal Assistant Trust Model**: single
trusted operator per Gateway instance, not a multi-tenant adversarial-isolation system. This is the
richest of the six repos in this batch for genuinely novel, reusable agent-infrastructure patterns —
multi-agent routing/isolation, a full ACP sub-agent orchestration layer, a manifest-driven plugin SDK,
and an explicit trust-boundary security model.

## Architecture

**Core primitives**: Gateway (always-on control plane; WebSocket/RPC server; manages config,
sessions, plugins, hooks) → Agents (isolated execution contexts with their own model/workspace
config) → Sessions (conversation state boundary; JSONL transcripts + metadata store) → Channels
(transport adapters: Telegram, WhatsApp, Discord, etc.) → Tools (shell, browser automation, MCP,
media) → Skills (`SKILL.md`-based modular capability definitions).

**Multi-agent isolation model** — a single Gateway process can host multiple fully isolated named
agents, each with:
- Workspace: `~/.openclaw/workspace-<agentId>` (filesystem root for tools/local skills)
- Agent dir: `~/.openclaw/agents/<agentId>/` (own `auth-profiles.json`, `models.json`)
- Session store: `~/.openclaw/agents/<agentId>/sessions/store.json` + per-session
  `<uuid>.jsonl` transcripts.

Routing is encoded directly in session-key strings, resolved via `resolveAgentIdFromSessionKey`
(case-insensitively normalized): `agent:work:main` → agent `work`; bare `main` → default agent;
`agent:main:subagent:xyz` → recursive sub-agent session under `main`; `*` → unscoped/global sentinel.
Because auth profiles are per-agent, two agents can use the same model provider (e.g. both OpenAI)
with different API keys without collision.

**Session scoping modes**: `main` (primary agent session), `subagent` (spawned via ACP/
`sessions_spawn` for task delegation), `cron` (scheduler-triggered). `SessionAccessor` is a
storage-neutral boundary coordinating transcripts (JSONL), metadata (a central store, e.g.
`sessions.json` or SQLite), and compaction checkpoints (context-window management).

**ACP & Sub-Agents (the standout subsystem)**: a parent agent can delegate discrete tasks to child
agents that run in fully isolated sessions and report back asynchronously.
- `AcpSessionManager` coordinates ACP session metadata, cached runtime handles (evicted on idle TTL,
  default `mcp.sessionIdleTtlMs = 600000`), per-session queues, and turn execution
  (`initializeSession` → `runTurn`); on Gateway restart it reconciles pending session identifiers for
  continuity.
- `subagent-registry.ts` tracks `{runId, childSessionKey, requesterSessionKey}` triples; queries
  include `countActiveRunsForSessionFromRuns` (enforces per-session concurrency limits) and
  `listRunsForRequesterFromRuns`. State is persisted to disk and rehydrated on Gateway startup
  (`persistSubagentRunsToDisk` / `restoreSubagentRunsFromDisk`), with orphan-run reconciliation for
  runs interrupted by a crash/restart.
- Termination reasons: `SUBAGENT_ENDED_REASON_COMPLETE` / `_ERROR` / `_KILLED`; on completion the
  system also triggers `cleanupBrowserSessionsForLifecycleEnd` to kill any browser-automation
  instances the sub-agent spun up.
- **Streaming relay to the parent**: `startAcpSpawnParentStreamRelay` forwards the child's live
  assistant text/status updates back into the parent's channel in real time, emitting "start" /
  "progress" / "done" system events; it also monitors for silence and emits a "still working" notice
  if the child produces no output for a configurable duration (default 60s) — a concrete pattern for
  keeping a human informed during a long-running delegated sub-task without flooding them.
- **Delivery on completion**: `deliverSubagentAnnouncement` decides how to route the final result back
  (direct message, embedded run queue, or gateway call) based on the requester's current session
  activity and configured "thread bindings" (a mechanism letting a sub-agent/ACP session "own" a
  specific messaging conversation thread, so replies land in the right place even for background
  tasks like media generation that "wake" the requester session on completion).
- Governing config: `acp.enabled` (default true), `agents.defaults.subagents.maxSpawnDepth` (default
  2 — caps how deeply sub-agents can spawn further sub-agents), `archiveAfterMinutes`,
  `announceTimeoutMs` (default 120000).

**Plugin architecture** — manifest-driven, capability-registration SDK:
- Discovery order (highest→lowest precedence): explicit config-declared plugin paths → workspace
  `extensions/*` → global user extensions dir → bundled plugins (via
  `OPENCLAW_BUNDLED_PLUGINS_DIR`).
- Each plugin ships an `openclaw.plugin.json` manifest (id, `activation` triggers —
  `onStartup`/`onProviders`/`onChannels` — declared `capabilities`, a Zod/JSON `configSchema`, and
  `slots` for exclusive-capability declarations like `memory` to prevent two plugins both claiming
  the same slot).
- On load, a plugin's entry module is dynamically imported (via `jiti`, with SDK-subpath alias
  resolution) and its `register(api)` function is called with an `OpenClawPluginApi`, through which
  it calls `registerProvider()`, `registerChannel()`, `registerTool()`, `registerHook()`, or
  `registerMemoryRuntime()`.
- SDK is exposed only via narrow, cataloged public subpaths under `openclaw/plugin-sdk/*` (e.g.
  `plugin-sdk/plugin-entry`, `plugin-sdk/core`, `plugin-sdk/provider-entry`, `plugin-sdk/health`,
  `plugin-sdk/memory-host-core`, `plugin-sdk/ssrf-runtime`) — private/internal/test subpaths are
  explicitly excluded from the public package surface, and a `plugin-sdk-surface-report.mjs` script
  audits and budgets the exported surface to prevent silent growth. Hardlinked plugin files can be
  rejected outright to prevent filesystem-escape tricks.
- Security note: plugins run **inside the Gateway process with full operator privileges** — they are
  explicitly categorized as "Trusted Code," not sandboxed from the rest of the system.

**Skills system** — implements the **AgentSkills.io** specification. A skill is a directory with a
`SKILL.md` (YAML frontmatter + Markdown body). Frontmatter fields include `name`,
`description` (workshop-limited to 160 bytes for discovery display), and
`metadata.openclaw.requires` (gating: `bins` — PATH binary check, `env` — required env vars, `config`
— required `openclaw.json` paths) plus `metadata.openclaw.install` (install specs: `kind` = brew/
node/go/uv/download, `url`, OS restrictions). Eligibility evaluation marks a skill `active` or
`missing-deps` based on OS match, binary presence on PATH, and config-path checks — skills with
missing deps stay visible in the UI but are excluded from the model's active toolset.

Skill source precedence (highest to lowest): workspace `<workspace>/skills` → project
`<workspace>/.agents/skills` → personal `~/.agents/skills` → managed `~/.openclaw/skills`
(installed via **ClawHub**, a skill registry/CLI) → bundled (shipped `./skills`) → extra configured
dirs + plugin-provided skills.

**Skill Workshop** — a proposal-based lifecycle for creating/editing skills safely: drafts are
staged as `SkillProposalRecord`s under `<stateDir>/skill-workshop/proposals/<id>/` (support files
capped at 64 files / 2MB total), pass through `scanSkillContent`/`scanSource` security scanning
(specifically important for ClawHub-installed skills sourced externally), and only on `applySkillProposal`
get written into the workspace via `writeWorkspaceSkill` — which also writes a `rollback.json` so the
change can be reverted. This propose→scan→apply→rollback pipeline is a reusable pattern for any system
that lets an agent (or an external registry) modify its own instruction/capability files.

**Security model & trust boundaries** — explicitly documented, not implicit:

| Boundary | Trust level |
|---|---|
| Gateway config/state (`openclaw.json`) | Trusted — whoever can write it controls everything |
| Gateway-authenticated callers | Trusted (operator-level; no per-user isolation within one Gateway) |
| Session keys | Routing context only — do not themselves confer authorization |
| Channel messages (inbound) | **Untrusted** — may carry injection/social-engineering payloads |
| Plugins/extensions | Trusted code (run in-process, full privileges) |
| Model providers | Trusted external services, but outbound calls still go through SSRF guards |

Explicitly out of scope: hallucinated model text is not itself a security failure "unless it triggers
a tool that bypasses the sandbox or SSRF guards"; operator-level host compromise voids all
guarantees; API-key security depends on the operator's own environment.

Defense-in-depth mechanisms named: `fetchWithSsrFGuard` for outbound network calls,
`sanitizeTransportPayloadText` for inbound channel content, CodeQL "critical quality" gates sharded
by trust-boundary domain (`core-auth-secrets`, `channel-runtime-boundary`, `network-ssrf-boundary`,
`process-exec-boundary`, `agent-runtime-boundary`, `config-boundary`, `plugin-boundary`), custom
OpenGrep rulepacks for tool-execution/credential code paths, and `pnpm-audit-prod.mjs` for
production-dependency advisory auditing (with explicit override handling for overbroad advisories,
e.g. a named "Mistral malware alert" false-positive). "Mantis" is a visual/E2E proofing layer that
runs real-messaging-platform (Telegram) regression checks with per-run credential isolation
(`OPENCLAW_QA_CREDENTIAL_OWNER_ID`) and automatic release of leaked test-account leases if an agent
run is interrupted mid-test.

## Key patterns & techniques

- **Session-key-encoded routing**: rather than a separate routing table, the agent/sub-agent/session
  identity is serialized directly into the session key string itself
  (`agent:<id>:subagent:<childId>`), making routing decisions a pure string-parsing operation and
  trivially recursive for nested sub-agents.
- **"Still working" liveness notices during long delegated tasks**: the ACP stream relay's silence
  timer (60s default) is a simple, generalizable UX pattern for any async-delegation system —
  proactively tell the human "still going" rather than leaving them wondering if the task died.
- **Thread bindings** for background-task wake-up: letting a sub-agent/ACP session "own" a specific
  conversation thread so a completion notification (e.g. "your video is ready") lands in the
  originating chat even though the triggering request happened turns earlier.
- **Propose → scan → apply → rollback** for self-modifying agent capabilities (skills): staging area
  isolates untrusted/AI-authored content from the live workspace until it passes a security scan and
  is explicitly applied, with a built-in undo path.
- **Manifest-first plugin discovery**: the Gateway can reason about a plugin's declared capabilities
  and activation triggers from `openclaw.plugin.json` alone, without executing any of the plugin's
  code — useful for building safe plugin catalogs/marketplaces without running arbitrary code just to
  list what a plugin does.
- **Public SDK surface budgeting**: an automated script (`plugin-sdk-surface-report.mjs`) tracks and
  enforces a budget on the number of public SDK exports, catching accidental surface-area growth in
  CI rather than relying on manual review discipline.
- **Explicit trust-boundary table as living documentation**: naming exactly which actors/data are
  Trusted vs. Untrusted vs. "routing context only" (session keys) is a clear, reusable template for
  documenting the security model of any agent-orchestration platform.

## Practical how-tos

- Install: `curl -fsSL https://openclaw.ai/install.sh | bash` (macOS/Linux) or
  `powershell -c "irm https://openclaw.ai/install.ps1 | iex"` (Windows). Requires Node.js 24
  (recommended) or 22.19+.
- First-time setup: `openclaw onboard` — interactive wizard for model-provider API keys, messaging
  channel account linking, and workspace init; populates `openclaw.json`.
- Update: `openclaw update --channel beta|stable|dev` — runs `runGatewayUpdate` (pulls source/package,
  syncs plugins for the channel, runs `doctorCommand` to repair config drift, then hands off to a
  restart script running the updated binary). Config snapshots are taken before mutating changes.
- Check version / update status: `openclaw --version`.

## Gotchas & caveats

- This is **not** a multi-tenant isolation system — anyone with Gateway-level auth or config-write
  access has full operator control over every agent the Gateway runs; don't assume per-user
  sandboxing exists unless you build it yourself on top.
- Plugins run in-process with full operator privileges; the plugin SDK boundary/surface auditing
  protects against *accidental* API misuse and supply-chain drift, not against a plugin author who
  deliberately writes malicious code.
- Sub-agent spawn depth is capped by default (`maxSpawnDepth = 2`) — deep recursive delegation chains
  need an explicit config change.
- Skills sourced externally (ClawHub-installed "Managed Skills") go through security scanning before
  being applied, but workspace-authored skills are lower-friction to write directly — the trust
  differential between these tiers is deliberate and worth preserving in any similar design.
- The wiki explicitly states hallucinated agent output is not itself treated as a security incident —
  only *becomes* one if it triggers a tool call that escapes the sandbox/SSRF guard, which is a
  meaningful design stance worth being aware of when reasoning about what "safe" means in this system.

## Wiki pages used

Overview; Getting Started; Core Concepts; Multi-Agent Routing; ACP & Sub-Agents; Plugin Architecture;
Skills System; Security Model & Trust Boundaries. (structure.md also lists Platform Architecture,
full Gateway subsystem pages [WebSocket Protocol/RPC, Auth, Configuration, Session & State Management,
Service Lifecycle, Control UI, HTTP APIs, Client SDK, TUI], Agent Runtime subsystem pages [Execution
Pipeline, System Prompt, Model Providers, Tools System detail pages, Commands, Context Compaction,
Automation & Cron, Codex & CLI Backends], Messaging Channels detail pages, Native Clients & Nodes
[Device Node Protocol, iOS/macOS, Android], Security Audit System/Sandboxing/Secret Management, and
Build & Release/Development pages — not read in full given the wiki's size; the pages above were
selected as the highest-density source of novel, reusable agent-tooling architecture.)
