---
repo: anomalyco/opencode
deepwiki: https://deepwiki.com/anomalyco/opencode
github: https://github.com/anomalyco/opencode
harvested: 2026-07-13
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`anomalyco/opencode`](https://deepwiki.com/anomalyco/opencode) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# anomalyco/opencode — DeepWiki Knowledge

## What it is

OpenCode is an open-source, provider-agnostic AI coding agent positioned as an alternative to
proprietary assistants like Claude Code and GitHub Copilot. It integrates 20+ LLM providers (OpenAI,
Anthropic, Google Gemini/Vertex, Amazon Bedrock/Azure, Groq, Together AI, Cerebras, Deepinfra,
Mistral, Perplexity, xAI, plus local models via OpenAI-compatible endpoints such as Ollama/llama.cpp),
and ships as a monorepo (Bun-managed) with a shared core server, multiple UI clients (Terminal UI,
Electron/Tauri desktop, VS Code and Zed extensions, Slack bot, web docs), a TypeScript SDK, and a
managed SaaS "Console" platform. The codebase is heavily built on the **Effect** TypeScript runtime
(services, generators, structured error types) and treats client-server separation, ACP (Agent
Client Protocol) editor integration, and a granular tool/permission system as first-class concerns.

## Architecture

**Monorepo package layout** (selected): `packages/opencode` (main CLI/HTTP server/session manager/
providers/tools), `packages/sdk/js` (`@opencode-ai/sdk`, TS client), `packages/plugin`
(`@opencode-ai/plugin`, plugin API), `packages/llm` (core LLM client library), `packages/core`
(domain schemas/typed errors/v2 services), `packages/schema` (canonical types), `packages/protocol`
(Effect HttpApi contract), `packages/client` (generated Promise/Effect clients), `packages/app`
(SolidJS shared UI logic), `packages/ui` (component library), `packages/desktop`, `packages/web`
(Astro docs site), `packages/slack`, `packages/tui` (OpenTUI-based terminal UI), `packages/cli`
(standalone CLI), `packages/codemode` (sandboxed code-execution runtime), plus a `packages/console/*`
family (SaaS backend/frontend/mail on Drizzle ORM + Cloudflare Workers + Stripe).

**Client-server split**: CLI/TUI, desktop apps, VS Code extension, and Slack bot all talk to the
core server via `@opencode-ai/sdk`; the Zed editor integration instead talks via the **Agent Client
Protocol (ACP)**, JSON-RPC over stdio. The server itself is a Hono HTTP server exposing session
management, provider proxying, and tool registry.

**Session & message model**: a Session has a descending-ULID `id` (so reverse-chronological sort is
free), plus `slug`, `projectID`, optional `workspaceID`/`parentID` (forked sessions), `directory`,
`agent`, `model`, `cost`, `tokens` (input/output/reasoning/cache breakdown), `revert`
(snapshot+diff info), per-session `permission` overrides, and `time` (created/updated/compacting/
archived). Messages are composed of typed **parts** rather than one text blob: `text`, `reasoning`
(model's visible chain-of-thought when supported), `tool` (call + state + output), `file`, `agent`
(subagent invocation reference), `compaction` (marks a summarization point), `snapshot` (worktree
state capture), `subtask` (recursive task delegation). This part-based model is what lets tool
results, snapshots, and reasoning coexist structurally in a single assistant turn instead of being
squashed into markdown.

**Agent system**: an Agent (`Agent.Info`) has a `mode` (`primary` or `subagent`), a permission
ruleset, and optional prompt/model overrides. Built-in agents: **Build** (default primary, permissive
but requires ask/confirm for sensitive ops), **Plan** (architectural planning; denies all edits except
to files under `.opencode/plans/*.md`), **General** (complex multitasking), **Explore** (permissive
read/search tools like `grep`/`glob`, restricted elsewhere). Permission rulesets merge three layers —
global defaults, agent-specific overrides, user config in `opencode.json` — with the most specific
matching rule winning; unmatched actions default to `ask`. Sensitive files like `.env` default to
`ask` even under the permissive Build agent.

**Agent loop**: `SessionPrompt.loop` → `SessionProcessor` streams the LLM response token-by-token,
emitting text/tool-call parts; intermediate assistant messages are persisted as they stream; each
tool call is dispatched to `ToolRegistry`; results update the corresponding tool part's state; the
loop returns `"continue"`, `"stop"`, or `"compact"`.

**Context compaction**: overflow is detected by comparing current token usage to the model's context
limit; messages are grouped into user-assistant "turns," and recent turns are kept within a token
budget; excessive tool outputs are truncated to a default max of 2,000 characters; a summary is
injected into prompt parts to preserve high-level state while freeing budget. Retry policy for LLM
calls uses exponential backoff and explicitly honors provider `retry-after` headers.

**Tool system**: every tool is defined via `Tool.define(id, initEffect)`, which wraps execution with
JSON-Schema parameter validation (returns a `Tool.InvalidArgumentsError` back to the LLM with
specifics on how to fix the call, rather than a bare failure), automatic output truncation, and
`Effect.withSpan` tracing. `Tool.Context` passed to every execution carries `sessionID`, `messageID`,
`agent`, an `abort` signal, a `metadata()` callback for UI updates, and `ask()` — the hook into the
permission system. Built-in tools: `read`, `edit`, `grep` (ripgrep-backed), `bash`, `glob`, `task`
(delegates to a subagent, optionally backgrounded), `skill`, `write`, `apply_patch` (unified diff),
`question` (ask the user and block for a reply), `webfetch`, `lsp`.

**Permission evaluation flow**: tool calls `ctx.ask(permission, pattern, ...rulesets)` →
`Permission.Service.evaluate` finds the last matching rule → `allow` proceeds, `deny` throws
`PermissionV1.DeniedError`, `ask` publishes an `Event.Asked`, creates a `Deferred`, and blocks the
tool call until the user replies `allow`/`once`/`always`/`reject`/`correct` — `"always"` replies get
folded into the session's `approved` rule set so the same ask isn't repeated. A dedicated
`assertExternalDirectoryEffect` check gates any filesystem tool (`read`/`edit`/`write`/`apply_patch`)
touching a path outside the project worktree, forcing an explicit `external_directory` permission
prompt.

**File-operation integrity mechanisms**: `EditTool` uses a per-path `Semaphore` to serialize
concurrent edits to the same file; line-ending style (`\n` vs `\r\n`) is auto-detected and preserved;
Byte Order Marks are detected and preserved across edit/patch; after any modification the LSP service
is notified (`lsp.touchFile()`) to re-index; `ReadTool` sniffs a file's leading bytes to detect binary
content and refuses to return it as text if so. An `Instruction.Service` surfaces project convention
files (`CLAUDE.md`, `AGENTS.md`) to tools like read/edit so agents stay aware of local norms.

**Background subagents** (`TaskTool` + `BackgroundJob.Service`): subagents can run detached for
long, independent work; they get a distinct permission derivation (`subagent-permissions.ts`) and are
explicitly denied some tools (e.g. `todowrite`) to avoid polluting the parent session's todo state
with subagent noise.

**CodeMode**: a confined execution environment (`packages/codemode`) used by a `CodeModeTool` to run
generated/untrusted code safely, exposing only a restricted subset of tools to the executing code and
verifying code signatures before execution.

**Plugin system**: plugins are JS/TS modules exporting a function matching the `Plugin` type; each
receives a `PluginInput` (SDK client, project metadata, a shell reference `$`, workspace registration)
and returns a `Hooks` object. Three load sources: internal (statically imported, hardcoded list —
e.g. `CodexAuthPlugin`, `CopilotAuthPlugin`, `AzureAuthPlugin`), npm (declared in `opencode.json`'s
`plugin` array, installed via Bun), local (`.opencode/plugins/` or global config dir, scanned from
disk). Core hooks: `chat.params` (mutate temperature/topP/maxTokens before request), `chat.headers`
(inject custom HTTP headers), `tool.execute.before`/`after` (mutate args, block by throwing, or
post-process output), `auth` (custom OAuth/API-key provider login flows), `provider` (dynamically
list models — e.g. Copilot's plugin fetches its model list live from GitHub's API), `event` (global
listener on the internal event `Bus`), `permission.ask` (override permission logic), `shell.env`
(inject env vars into all shell executions). `Plugin.trigger` iterates registered hooks for a given
name and executes them sequentially, letting each mutate a shared `output` object in place. Runtime
flags: `OPENCODE_PURE` (disables external plugins), `OPENCODE_DISABLE_DEFAULT_PLUGINS`.

**MCP integration**: `MCP.Service` connects to multiple servers at startup (local subprocess via
`StdioClientTransport`, or remote via HTTP/SSE), tracking each server's connection state as a
discriminated union: `connected`, `disabled`, `failed`, `needs_auth`, `needs_client_registration`.
Local servers are configured with a `command` array + optional `cwd`/`env`; remote servers with a
`url` + optional `oauth` config + custom `headers`. `McpCatalog.convertTool` turns MCP tool schemas
into executable agent tools; MCP *prompts* are surfaced as slash commands; MCP *resources* are
exposed via a `Resource` schema for direct reference. OAuth flow: `UnauthorizedError` during connect
→ `needs_auth` state → `McpOAuthProvider` handles metadata/dynamic client registration/token
exchange → a local callback HTTP server (default port `19876`, path `/mcp/oauth/callback`) receives
the redirect → tokens persist to `mcp-auth.json` → `McpBrowser` opens the auth URL in the user's
default browser automatically. CLI: `opencode mcp list|auth [name]|logout [name]|add`.

**Skills & Commands**: Commands are prompt templates with variable substitution (`$1`, `$ARGUMENTS`)
sourced from built-ins (`init`, `review`), `opencode.json`'s `command` object, MCP server prompts, or
one command auto-registered per discovered skill. Skills are `SKILL.md` files with YAML frontmatter,
discovered in precedence order: global (`~/.config/opencode/skills/`) → project (`.opencode/skills/`,
searched upward from cwd) → external-compat directories (`.claude/skills`, `.agents/skills` — direct
interop with Claude-Code-style skill layouts). A built-in `customize-opencode` skill hands the LLM the
actual `opencode.json`/agent-config schemas so self-configuration doesn't hallucinate fields. Runtime
flags: `OPENCODE_DISABLE_EXTERNAL_SKILLS`, `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` (specifically turns
off the Claude-Code-skill-compat loader), `OPENCODE_CONFIG_DIR`.

**ACP (Agent Client Protocol)**: OpenCode is a reference ACP implementation, used for deep Zed/
JetBrains/Neovim integration. Layers: `ACP.Agent` (implements the `ACPAgent` SDK interface;
dispatches `initialize`/`prompt`/`newSession`), `ACPService.Interface` (Effect-based business logic:
session lifecycle, auth, capability negotiation), `ACPSession.Service` (maps ACP session IDs to
internal OpenCode sessions, tracking selected model/working directory/message-part metadata). Tool
events are bridged to ACP `sessionUpdate` notifications via a `Subscription` class listening on the
internal event bus (`handlePartUpdated` for finalized parts, `handlePartDelta` for streaming text/
reasoning chunks → `agent_message_chunk`/`agent_thought_chunk`). Internal tool IDs map to ACP
`ToolKind` categories for IDE UI hints (e.g. `bash` → `execute`, `read` → `read`). Permission asks are
forwarded to the IDE via a `requestPermission` call that suspends execution pending the user's
response in the editor UI, rather than in a terminal prompt.

## Key patterns & techniques

- **Part-typed messages instead of flat text**: modeling reasoning, tool calls, file attachments,
  compaction markers, and subtask delegation as distinct discriminated part types (not just markdown
  formatting inside a text blob) makes rich UI rendering and structural analysis of a conversation
  possible without text parsing.
- **`ctx.ask()` as the single choke point for permission-gated actions**: every tool routes sensitive
  operations through one function that can synchronously return allow/deny or suspend on a `Deferred`
  awaiting human input — a clean separation between "tool logic" and "is this allowed right now."
- **External-directory boundary as an explicit, separately-named permission** (`external_directory`)
  rather than folding it into generic `write`/`edit` — makes "the agent tried to touch something
  outside the project" a distinctly auditable/askable event.
- **Turn-based compaction with explicit character-truncation defaults**: rather than a vague "shrink
  the context," the compaction system operates on well-defined turn boundaries and known truncation
  limits (2,000 chars per tool output) — easy to reason about and tune.
- **Manifest-free but hook-typed plugin API**: instead of a JSON manifest declaring capabilities up
  front (contrast with OpenClaw/knowledge-work-plugins), OpenCode plugins are plain functions that
  return a `Hooks` object at load time — simpler to author, at the cost of not being able to reason
  about a plugin's capabilities without executing it.
- **Skill-loader compatibility mode** for Claude-Code-style `.claude/skills`/`.agents/skills`
  directories — a concrete, working example of one agent tool intentionally interoperating with
  another's skill file format rather than requiring a rewrite.
- **CodeMode sandboxed execution with a restricted exposed tool surface and signature verification**
  as the mechanism for letting an LLM write and run code without giving it the full host tool
  capability set.

## Practical how-tos

- Custom plugin tool definition:
  ```ts
  import { tool } from "@opencode-ai/plugin"
  export const MyToolPlugin = async () => ({
    tool: {
      "my_custom_tool": tool({
        description: "Does something cool",
        args: { input: tool.schema.string() },
        async execute({ input }) { return `Processed: ${input}` },
      })
    }
  })
  ```
- MCP server config in `opencode.json` — local: `{"command": ["npx", "-y",
  "@modelcontextprotocol/server-everything"]}`; remote: `{"url": "...", "oauth": {...},
  "headers": {...}}`.
- Manage MCP connections: `opencode mcp list`, `opencode mcp auth <name>`,
  `opencode mcp logout <name>`, `opencode mcp add`.
- Start the ACP server (for editor integration): `opencode acp` — bootstraps an in-process server and
  wires stdio for JSON-RPC.
- Common TUI slash commands: `/compact` (context compaction, default keybind `<leader>c`), `/undo`
  (revert last message + file changes, `<leader>u`), `/init` (bootstrap `AGENTS.md`).

## Gotchas & caveats

- Plugins run with full trust — there's no manifest-based capability declaration the Gateway/host can
  inspect before executing plugin code (unlike OpenClaw's `openclaw.plugin.json` or the Anthropic
  plugin marketplaces' `plugin.json`); a malicious npm/local plugin can register arbitrary hooks.
- Background subagents deliberately lose access to some tools (e.g. `todowrite`) to avoid session
  noise — don't assume a subagent has parity with the primary agent's toolset.
- The `plan` agent's edit restriction is scoped specifically to `.opencode/plans/*.md` — attempting
  to have a "plan mode" agent edit anything else will correctly be denied by design, not a bug.
- Compaction's default tool-output truncation (2,000 chars) is a real information-loss point;
  anything that depends on full historical tool output surviving compaction needs to be surfaced
  through the injected summary instead.
- The current ACP implementation is explicitly described as a stepping-stone toward a fully
  Effect-based "acp-next" — treat some ACP internals as subject to near-term rework.

## Wiki pages used

Overview; Session & Agent System; Tool System & Permissions; Plugin System; MCP Integration; Skills &
Command System; ACP (Agent Client Protocol). (structure.md also lists Repository Structure &
Packages, Architecture Overview, CLI Entrypoint & Commands, Configuration System, AI Provider & Model
Management, HTTP Server & REST API, Event Bus & Real-time Updates, LSP & Code Formatting, LLM Core
Library, Core V2 Library, Schema/Protocol/Client packages, all User Interface pages, UI Component
Library, SDK & API, IDE Extensions & Integrations, Console Management System, Build & Release, and
Reference pages — not read in full given time constraints; the pages above were selected as the
highest-density source of reusable agent-tooling architecture for this harvesting pass.)
