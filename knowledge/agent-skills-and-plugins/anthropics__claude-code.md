---
repo: anthropics/claude-code
deepwiki: https://deepwiki.com/anthropics/claude-code
github: https://github.com/anthropics/claude-code
harvested: 2026-07-09
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`anthropics/claude-code`](https://deepwiki.com/anthropics/claude-code) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# anthropics/claude-code — Distilled Knowledge

## What it is

Claude Code is Anthropic's agentic coding CLI: a terminal tool that combines LLM reasoning with
direct system access (a tool-based architecture) to read/write code, run shell commands, manage git
workflows, and orchestrate multi-agent work. It is proprietary software (Anthropic Commercial
Terms), current release series 2.1.x. It ships two primary surfaces: an interactive CLI/REPL for
local development, and GitHub Actions-based automation (issue triage, deduplication, `@claude`
mention handling). This repo's wiki is largely changelog-derived (most claims cite `CHANGELOG.md`),
so it documents recent/current behavior rather than a stable architectural spec — versions and exact
feature availability should be treated as a snapshot as of v2.1.197 (Claude Sonnet 5 became the
default model with a native 1M-token context window at that release).

Install: `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux) or `brew install --cask
claude-code`; `irm https://claude.ai/install.ps1 | iex` or `winget install Anthropic.ClaudeCode`
(Windows). npm install is deprecated in favor of these installers.

## Architecture (how it's built, key components)

**Layered request flow:** User input → InputParser → SessionContext (conversation history) →
AgentExecutor → tool decision (model selects a tool) → PermissionChecker → (ask: interactive prompt
/ deny: return / allow: proceed) → PreToolUse hook → tool execution (BashTool/FileReadTool/etc.) →
PostToolUse hook → ContextManager token check → (under limit: continue / over limit: trigger
compaction) → response to user.

**Core subsystems and their config surfaces:**
| System | Responsibility | Config |
|---|---|---|
| Agent System | Execute requests, spawn subagents, manage task lifecycle | `settings.json` `agent` field |
| Tool System | Bash, file ops, web, MCP capabilities | `settings.json` `disallowedTools` |
| Permission System | allow/ask/deny rules | `settings.json` permission rules |
| Context Manager | Token tracking, auto-compaction | context window limits |
| Hook System | Lifecycle event interception | `.claude/hooks/*.py`, plugin hooks |
| Plugin System | Discover/load extensions | `marketplace.json`, `plugin.json` |
| Skill System | Load SKILL.md guidance / custom commands | `.claude/skills/` |
| MCP Integration | External tool servers | `.mcp.json` |

**Agent hierarchy.** A main agent (managed by the session manager) holds the primary conversation.
It spawns **subagents** via the `Task` tool for parallel/delegated work; each subagent gets its own
independent context window (so one task's token usage doesn't consume the main thread's budget),
model configuration, and permission scope. Subagent nesting is capped at a 5-level depth limit.
Subagents report back via `TaskUpdate` (progress) and `TaskOutputTool` (final result), and can send
async messages that wake the main agent. Main-context auto-compaction triggers at 98% of the window.

Execution modes for subagents: default (shared working directory — simple parallel tasks),
`isolation: worktree` (temporary git worktree, for tasks needing file isolation or parallel branches
— triggers `WorktreeCreate`/`WorktreeRemove` hooks), and `background: true` (non-blocking, works
with either isolation mode; auto-backgrounds when a subagent doesn't need user input, or manually
via Ctrl+F). Background sessions persist across daemon restarts/updates (including Windows handoff
instead of kill) and are auto-resumed when the `claude agents` view is reopened; worktrees under
`.claude/worktrees/` are swept after 30 days. API requests from subagents carry
`x-claude-code-agent-id` / `x-claude-code-parent-agent-id` headers for tracing.

**Agent definition files** live at `.claude/agents/*.md` (project), `~/.claude/agents/` (user), or
are shipped via plugins. Frontmatter fields: `name`, `description`, `model`, `tools` (allowed
subset), `memory` (`user`/`project`/`local` scope), `isolation` (`worktree`), `background`, `effort`
(reasoning-effort level), `maxTurns`, `disallowedTools`, `mcpServers`. `Task` tool call parameters
at invocation time: `description`, `agent_type` (resolves case-insensitively, e.g. "Code Reviewer" →
`code-reviewer`), `model`, `allowed_tools`, `permission_mode`, `context` (e.g. `fork` to inherit the
parent's current context).

**Tool system.** Typed tool classes include BashTool, PowerShellTool (Windows, exit-code parity with
Bash for `git diff`/`grep`), FileReadTool/FileWriteTool/FileEditTool (path-safety + symlink checks),
WebFetchTool/WebSearchTool (commonly denied under strict configs), TaskTool, AskUserQuestion,
EnterWorktree. Every tool call passes through a `PermissionChecker` before execution.

**Permission system — hierarchy and enforcement.** Settings cascade: `managed-settings.json`
(enterprise, highest precedence) → `settings.json` (user) → `.claude/settings.json` (project) →
`settings.local.json` (local override, testing). File paths: enterprise at
`~/.config/claude/managed-settings.json` (`%APPDATA%\ClaudeCode\managed-settings.json` on Windows),
user at `~/.config/claude/settings.json`, project at `.claude/settings.json`, local at
`settings.local.json`. Enterprise-only lockdown flags: `allowManagedPermissionRulesOnly` (ignore all
non-managed allow/ask/deny rules), `allowManagedHooksOnly` (block user/project hooks),
`strictKnownMarketplaces` (restrict plugin installs to an approved marketplace URL list),
`disableBypassPermissionsMode: "disable"` (block `--dangerously-skip-permissions`). Three rule
types: `allow` (auto-execute), `ask` (interactive prompt with Allow-Once/Always-Allow/Deny), `deny`
(immediate reject). `--dangerously-skip-permissions` propagates its bypass to spawned subagents.
Auto-mode denials now log specific reasons to the transcript and `/permissions` recent-denials view.

**Sandbox** wraps only the `Bash` tool (does NOT apply to
Read/Write/WebSearch/WebFetch/MCP/hooks/slash-commands). Config knobs: `sandbox.enabled`,
`autoAllowBashIfSandboxed` (treat sandboxed bash as pre-approved even if globally `ask`),
`allowUnsandboxedCommands` (if false, block anything that can't be wrapped), `excludedCommands`
(blacklist specific binaries from sandbox wrapping), `network.allowedDomains` (egress allowlist —
all else blocked), `allowUnixSockets`/`allowLocalBinding`, `enableWeakerNestedSandbox`. Three
example configs ship in `examples/settings/`: `settings-strict.json` (deny all web tools, ask for
Bash, full lockdown of managed-only rules/hooks/marketplaces, no network in sandbox),
`settings-lax.json` (disable bypass flag + restrict marketplaces, otherwise permissive),
`settings-bash-sandbox.json` (sandbox-focused, managed-only permission rules).

**Hook system.** Lifecycle events: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`Stop`, `SubagentStop`, `PreCompact`, `SessionEnd`, `Notification`, `WorktreeCreate`,
`TeammateIdle`, `EnterWorktree`, `TaskCreated`, `TaskCompleted`. Two implementation styles:
**prompt-based** (LLM-driven, returns structured JSON like `{"hookSpecificOutput": {"hookEventName":
"SessionStart", "additionalContext": "..."}}` to inject instructions) and **command-based**
(external script via stdin/exit-code). Command hooks receive `{tool_name, tool_input}` as JSON on
stdin; exit 0 = allow/continue, exit 1 = error shown to user only (not to Claude), exit 2 = block —
for `PreToolUse` this cancels the tool call and feeds stderr back to Claude as the tool result. Hook
matchers support wildcards (`mcp__brave-search__.*`) but use **exact match** for hyphenated
identifiers (e.g. `code-reviewer`, `mcp__brave-search`) specifically to prevent accidental substring
collisions.

**MCP integration.** Three layers: MCP infrastructure (connection manager, transports:
stdio/SSE/HTTP/WebSocket), external MCP servers, and integration points (discovery/invocation).
Config locations: `~/.claude/mcp-servers.json` (user), `.claude/mcp-servers.json` (project), or
plugin-bundled (`.mcp.json` at plugin root, or inline `mcpServers` in `plugin.json`). Transport
parameter shapes: stdio (`command`+`args`+`env`, Claude Code spawns/owns the child process), SSE
(`type: sse`+`url`, OAuth handled automatically), HTTP (`type: http`+`url`+`headers`), WebSocket
(`type: ws`+`url`). All configs support `${CLAUDE_PLUGIN_ROOT}` and shell-variable substitution for
portability. Tool naming: `mcp__plugin_<plugin-name>_<server-name>__<tool-name>` — namespaced to
avoid collisions. Auth methods: OAuth (automatic browser prompt for SSE/HTTP), header-based tokens,
or `env` vars for stdio. `claude.ai` MCP connectors (remote servers configured in your claude.ai
account) are automatically disabled when a manual `ANTHROPIC_API_KEY` is set. `claude mcp
list`/`get` no longer auto-spawn `.mcp.json` servers in untrusted workspaces even if a committed
`.claude/settings.json` self-approved them — these show `⏸ Pending approval` instead.

**Plugin system.** Discovery scope precedence (highest→lowest): Managed
(`.claude-plugin/marketplace.json`, bundled) → Project (`.claude/plugins/`) → User
(`~/.claude/plugins/`) → Auto-load (`.claude/skills/`, no marketplace registration needed). Plugins
needing executable components/hooks require a **trust dialog** approval before loading;
project-settings-only-enabled external plugins require explicit install consent on every load path.
`plugin.json` required fields: `name` (kebab-case), `version` (semver), `description`, `author`. A
plugin directory can bundle: **commands** (slash commands as `.md` files), **agents** (specialized
subagent definitions), **hooks** (`hooks/hooks.json`), **MCP servers** (`.mcp.json`), **skills**
(`SKILL.md` files under `skills/<name>/`).

**Skill System (Claude Code's variant).** Same core mechanics as anthropics/skills: required
`SKILL.md` (YAML frontmatter `name`/`description`/optional `license`, plus Markdown body) with
optional `scripts/`, `references/`, `assets/`. Three-level progressive-disclosure loading: metadata
(always in system prompt), instructions (injected when description matches task), resources
(on-demand via tool calls like `ls`/`cat`/`grep`). **Skills vs. Plugins distinction stated
explicitly here**: a skill is the atomic unit of specialized knowledge ("onboarding guide" for a
domain); a plugin is the distribution/management vehicle that can bundle multiple skills plus
commands/agents/hooks. Skills transform Claude "from a general-purpose assistant into a specialized
agent equipped with domain-specific expertise... that no base model can fully possess."

## Key patterns & techniques (the transferable knowledge)

**Independent-context subagent delegation.** Spawning subagents with their own context window is the
core mechanism for avoiding token-budget exhaustion on complex multi-step work — the main thread's
context isn't consumed by exploratory/parallel sub-tasks. Combined with worktree isolation, this
also gives file-system-level isolation for parallel branches of work without cross-contamination.

**Defense-in-depth security layering.** Multiple independent security boundaries stack: (1)
application-level permission rules (allow/ask/deny), (2) sandbox process isolation for Bash
specifically, (3) network egress allowlisting via `iptables`/`ipset` in the reference DevContainer,
(4) enterprise policy locks (`managed-settings.json`) that user/project config cannot override. No
single layer is trusted alone.

**Settings cascade with lockable enterprise overrides.** The 4-tier settings hierarchy (managed →
user → project → local) is a reusable config pattern: give individual developers/projects
flexibility by default, but let a small set of named boolean flags at the top tier ("XOnly" flags)
hard-lock specific subsystems (permissions, hooks, marketplaces) so lower tiers literally cannot
override them regardless of what's written in project files.

**Exact-match hook matcher fix for hyphenated names.** A real bug class documented here: naive
substring/prefix matching on hook matchers caused `code-review` to accidentally match
`code-reviewer`, or `mcp__brave` to match `mcp__brave-search`. The fix — switching to exact-match
for hyphenated identifiers, wildcard-only for explicit glob patterns — is a general lesson for any
matcher/router built on string prefixes: hyphen-separated identifiers need exact-match semantics,
not prefix matching, unless a wildcard is explicit.

**Multi-agent team pattern (Feature Development plugin) as a concrete worked example.** A main
orchestrator spawns 2-3 parallel `code-explorer` agents (Phase 2: exploration, tools restricted to
Glob/Grep/LS/Read/NotebookRead/WebFetch/TodoWrite/WebSearch/KillShell/BashOutput), then 2-3 parallel
`code-architect` agents with different design philosophies (Phase 4, e.g. "Minimal" vs. "Clean"
blueprints), then 3 parallel `code-reviewer` agents with different review lenses (Phase 6, e.g.
"Simplicity" vs. "Bugs"). This "spawn N agents with the same tools but different
framing/instructions, then synthesize" pattern is a reusable way to get diverse takes on the same
artifact without manually running N sequential passes.

**Denial transparency as a debugging/trust feature.** When auto-mode or permission rules block an
action, the specific denial reason is now surfaced in the transcript, toast notifications, and the
`/permissions` view — rather than a silent failure. This is a broadly applicable pattern for any
policy-enforcement layer: always surface *why* something was blocked, not just *that* it was
blocked.

## Practical how-tos (concrete workflows)

**Restrict a project to a strict security posture:** ship a `.claude/settings.json` (or push via
`managed-settings.json` at the enterprise level) that denies `WebSearch`/`WebFetch`, sets `Bash` to
`ask`, sets `allowManagedPermissionRulesOnly: true` and `allowManagedHooksOnly: true`, sets
`strictKnownMarketplaces` to an explicit array, and configures `sandbox` with
`network.allowedDomains` restricted and `allowUnsandboxedCommands: false`.

**Write a PreToolUse validation hook:** a Python script reads `json.load(sys.stdin)`, checks
`tool_name == "Bash"`, regex-matches the command against a validation ruleset (e.g. flagging `grep`
in favor of `rg`), and calls `sys.exit(2)` with an explanatory stderr message to block — or
`sys.exit(0)` to allow. Register it in `hooks.json` or plugin manifest under `PreToolUse` with a
`matcher` (e.g. `"Bash"`) pointing at the command.

**Bundle MCP servers in a plugin:** prefer a dedicated `.mcp.json` at the plugin root for multiple
servers (clearer separation), or use the inline `mcpServers` field in `plugin.json` for a single
simple server. Use `${CLAUDE_PLUGIN_ROOT}` in paths for portability across install locations.

**Start an isolated worktree session:** `claude --worktree` or `-w` launches in an isolated git
worktree; `EnterWorktree`/`ExitWorktree` allow mid-session switching between Claude-managed
worktrees (ExitWorktree verifies worktree state before removal). The status line shows the active
worktree name/path.

**Monitor background subagents:** run `claude agents` to see a side panel of
running/blocked/completed sessions with status labels ("Done", "Needs your input", "Needs attention"
for stalled agents). Idle subagents auto-hide after 30s; the panel caps at 5 visible rows with
scroll hints.

## Gotchas & caveats

- This wiki's content is derived almost entirely from `CHANGELOG.md` entries rather than a stable
  architecture document — treat specifics (exact flag names, exact hook list) as a snapshot tied to
  release ~2.1.197, not a permanent spec. Verify against current docs before relying on precise
  behavior.
- `sandbox` settings apply ONLY to the `Bash` tool — Read, Write, WebSearch, WebFetch, MCP servers,
  hooks, and internal slash commands are unaffected by sandbox config.
- `--dangerously-skip-permissions` cascades its bypass mode to any subagents the session spawns — a
  bypass isn't scoped to just the top-level agent.
- MCP OAuth previously broke on enterprise IdPs (e.g. self-hosted GitLab) because the client requested
  the entire `scopes_supported` catalog instead of only the needed scope, causing `invalid_scope`
  errors — a general caution when implementing OAuth clients against arbitrary IdPs: request only
  what's needed, not the full advertised catalog.
- `claude.ai` MCP connectors silently stop working the moment a manual `ANTHROPIC_API_KEY` is set — an
  easy-to-miss interaction if debugging "why did my remote MCP server disappear."
- Subagent Task-tool nesting has a hard 5-level depth limit; deeply recursive delegation designs will
  hit this ceiling.
- Hook matcher exact-match-for-hyphens was a bug fix, meaning older/naive hook configs relying on
  substring matching against hyphenated tool/server names may behave differently after this change.
- Plugin trust dialogs and MCP untrusted-workspace gating exist specifically to prevent a committed
  `.claude/settings.json` in a shared repo from silently auto-approving execution for anyone who
  clones it — don't assume a repo's own settings file is sufficient authorization.

## Wiki pages used

Claude Code Overview, System Architecture, Feature Evolution & Release History, License & Security
Policy, Configuration Management, Core Systems, Agent System & Subagents, Tool System & Permissions,
Hook System, MCP Server Integration, Plugin System, Skill System, Sandbox Environment (partial). Not
read in depth: User Guide subpages (Installation & Setup, CLI Commands & Interaction Modes, Session
Management, Providing Feedback & Reporting Issues), Context Window & Compaction, UI/UX & Terminal
Integration, Official Plugins section (Plugin Marketplace & Discovery, Code Review Plugin, Feature
Development Plugin, Output Style Plugins, Ralph Wiggum Plugin, Frontend Design Plugin, Plugin
Development Kit, Other Marketplace Plugins — only referenced indirectly via Plugin System/Skill
System pages), GitHub Automation section (all 6 subpages), Development Environment section
(DevContainer, Network Security, Base Image, Container Orchestration, Enterprise MDM), Claude
Gateway section (GCP Deployment, Terraform), Glossary.
