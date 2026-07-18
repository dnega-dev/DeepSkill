---
repo: anthropics/claude-plugins-official
deepwiki: https://deepwiki.com/anthropics/claude-plugins-official
github: https://github.com/anthropics/claude-plugins-official
harvested: 2026-07-13
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`anthropics/claude-plugins-official`](https://deepwiki.com/anthropics/claude-plugins-official) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# anthropics/claude-plugins-official — DeepWiki Knowledge

## What it is

`claude-plugins-official` is Anthropic's official Claude Code plugin marketplace and development
system. It catalogs 55+ plugins in a single registry (`.claude-plugin/marketplace.json`, owned by
`{name: "Anthropic"}`) and splits them across `plugins/` (Anthropic-maintained, internal) and
`external_plugins/` (partner/community-maintained, e.g. Asana, Vercel, Atlassian, Telegram, Discord).
Beyond distribution, the repo bundles a `plugin-dev` development toolkit for scaffolding new plugin
components, automated CI/CD validation of the marketplace registry, and several reference
implementations of non-trivial automation patterns (iterative dev loops, codebase-aware automation
recommendation, messaging-channel bridges).

This wiki is the deepest of the two Anthropic plugin-marketplace wikis for *general-purpose* Claude
Code extensibility mechanics (hooks, MCP transports/auth, skill triggering internals) — where
`knowledge-work-plugins` focuses on business-function plugin content, this one focuses on the
plugin *system* itself.

## Architecture

**Marketplace registry** (`.claude-plugin/marketplace.json`): root object has `$schema`, `name`
(`"claude-plugins-official"`), `description`, `owner: {name, email}`, and a `plugins` array. Each
plugin entry requires `name` (kebab-case, must be unique), `description`, `source`; optional fields:
`category` (`development`, `productivity`, `security`, `location`, etc.), `author`, `homepage`, `tags`
(e.g. `["community-managed"]`). `source` supports three shapes:
- Relative path, internal: `"./plugins/agent-sdk-dev"`
- Relative path, external: `"./external_plugins/asana"`
- Git object: `{"source": "url", "url": "https://github.com/..."}` or
  `{"source": "git-subdir", "url": "owner/repo", "path": "plugins/x", "ref": "main", "sha": "<pinned-commit>"}`

CI enforces this via `.github/scripts/validate-marketplace.ts` (JSON validity, required fields,
duplicate-name check) and `.github/scripts/check-marketplace-sorted.ts` (alphabetical order by name,
with a `--fix` flag), both run in `.github/workflows/validate-marketplace.yml` on every PR touching
the registry.

**Plugin component types** (same core five as the sister repo, but documented in more depth here):
manifest (`.claude-plugin/plugin.json`), commands (`commands/*.md`, legacy/explicit), agents
(`agents/*.md`, restricted-toolset sub-personas), skills (`skills/*/SKILL.md`, modern
context-triggered format), hooks (`hooks/hooks.json`), MCP config (`.mcp.json` or inline in
`plugin.json`).

**Skills system** — same progressive-disclosure model as the sister repo but with additional
frontmatter fields documented:
- `name` (required) — becomes the slash command for user-invocable skills.
- `description` (required, most critical field) — third-person, with quoted trigger phrases; this is
  literally what Claude matches against user intent to decide whether to load the skill.
- `user-invocable` (optional, default `true`) — set `false` to make a skill background-only
  (Claude-invoked, not user-callable).
- `disable-model-invocation` (optional, default `false`) — set `true` to make a skill user-only (only
  reachable via `/skill-name`), used for skills with side effects (e.g. deployment) that Claude
  shouldn't auto-trigger.
- `allowed-tools` (optional) — restricts/pre-approves tool access for the skill.

Bundled resource dirs: `references/` (docs loaded into context only on demand), `scripts/`
(Python/Bash executed via the Bash tool *without* their source entering context — the key mechanism
for keeping deterministic logic out of the token budget), `assets/` (output templates/logos, never
loaded into context, only used as output artifacts).

**Hooks system** — two implementation patterns:
- *Prompt-based* (recommended for complex/contextual judgment): `{"type": "prompt", "prompt":
  "Evaluate if this tool use is appropriate: $TOOL_INPUT", "timeout": 30}`. Supported events: `Stop`,
  `SubagentStop`, `UserPromptSubmit`, `PreToolUse`.
- *Command-based* (deterministic, fast): `{"type": "command", "command": "bash
  ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh", "timeout": 60}`.

Hook events and their properties: `PreToolUse` (before execution, can block), `PostToolUse` (after,
cannot block — used for auto-format/tests/type-check), `UserPromptSubmit` (on user message, can block/
inject context), `Stop` (on agent exit attempt, can block — used by `ralph-loop`), `SessionStart`
(session begin, cannot block — used to load context / set output style).

Hook config wrapper format:
```json
{ "hooks": { "PreToolUse": [ { "matcher": "Write|Edit",
    "hooks": [ { "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/validate.sh" } ] } ] } }
```

Hook stdout JSON shapes: standard `{"continue": true, "suppressOutput": false, "systemMessage": "..."}`;
blocking a tool call: `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
"permissionDecision": "deny"}, "systemMessage": "..."}`; blocking Stop: `{"decision": "block",
"reason": "...", "systemMessage": "..."}`.

**Critical hook rule ("Exit 0 Rule")**: hooks must always exit status 0, even on internal error —
wrap logic in try/except — because a non-zero exit code causes unexpected/undefined Claude Code
behavior, distinct from the JSON `decision` field which is the actual signaling channel.

**MCP server integration** — documented with real transport/auth/tool-design depth:
- Transports: `stdio` (local process, stdin/stdout), `SSE` (hosted + OAuth), `HTTP` (JSON-RPC,
  stateless), `WebSocket` (full duplex/real-time).
- Config locations, in resolution scope order conceptually: project `.mcp.json`, global
  `~/.claude.json`, plugin-bundled (`.mcp.json` at plugin root, recommended, or inline in
  `plugin.json` for simple cases).
- Env var expansion: `${CLAUDE_PLUGIN_ROOT}` → plugin's absolute path; `${USER_VAR}` → user's shell
  env (for API keys).
- "Remote Streamable-HTTP" is called out as the **default recommendation** for wrapping cloud APIs
  (zero-install, proper OAuth), commonly deployed via Cloudflare Workers using an `McpAgent` wrapper.
  "MCPB" (bundled local server with its own runtime) is for local file/OS access use cases.
- Auth tiers: Tier 1 static API key via env var; Tier 2 (preferred) OAuth 2.0 via **CIMD** (Client ID
  Metadata Document — host publishes metadata at an HTTPS URL, server fetches it, no pre-registration
  needed); Tier 3 fallback **DCR** (Dynamic Client Registration) for hosts lacking CIMD support.
- Interactive "MCP Apps": UI widgets rendered in an iframe inside chat, built with
  `registerAppTool` (declares tool + UI resource URI) and `registerAppResource` (serves widget
  HTML/JS). Widget-side SDK: `app.sendMessage()` injects a message into the conversation,
  `app.ontoolresult` fires when server tool results arrive, `app.callServerTool()` lets the widget
  call other server tools directly, bypassing Claude's reasoning loop.
- Tool design patterns: **Pattern A "One Tool Per Action"** for small surfaces (<15 operations, each
  with a precise schema); **Pattern B "Search + Execute"** for large surfaces (dozens/hundreds of
  endpoints) — `search_actions` (natural-language intent → matching actions) +
  `execute_action(id, params)` — explicitly framed as the way to keep context lean when wrapping a
  big API.

## Key patterns & techniques

- **`ralph-loop` plugin — "Ralph Wiggum technique" for iterative development.** This is the most
  distinctive pattern in the wiki: a `Stop` hook implements a self-referential feedback loop that
  intercepts every session-exit attempt and re-feeds the same prompt until either a completion signal
  or an iteration cap is hit.
  - State file `.claude/ralph-loop.local.md`: YAML frontmatter (`active`, `iteration`, `session_id`,
    `max_iterations` [0 = unlimited], `completion_promise`, `started_at`) + markdown body containing
    the literal prompt text to re-inject each loop.
  - `/ralph-loop "<prompt>" --max-iterations 10 --completion-promise 'DONE'` runs
    `setup-ralph-loop.sh`, which writes the state file.
  - On every Stop-hook trigger, `stop-hook.sh`: (1) exits cleanly if no state file exists; (2)
    validates iteration/max_iterations are numeric; (3) stops+deletes state if iteration limit hit;
    (4) parses the session transcript JSONL to grab the last assistant text block; (5) uses Perl
    (`perl -0777 -pe 's/.*?<promise>(.*?)<\/promise>.*/$1/s'`) to extract text inside `<promise>...
    </promise>` tags and compares it exactly to `completion_promise`; (6) if no stop condition,
    atomically increments `iteration` (write to `${FILE}.tmp.$$` then `mv`) and returns a `block`
    decision that feeds the original prompt back to the session.
  - **Session isolation**: because the state file is project-scoped but the Stop hook fires for every
    session in that project, the hook checks `session_id` against `CLAUDE_CODE_SESSION_ID` and allows
    exit without blocking if they don't match — prevents one project's ralph-loop from hijacking an
    unrelated concurrent session.
  - Claude is explicitly instructed (via system message/command description) that it may only emit
    the `<promise>` tag when the condition is genuinely true — an anti-cheating instruction baked
    into the prompt, not enforced mechanically.
  - Known Windows gotcha: the bash Stop hook needs Git for Windows; `bash` can misresolve to a broken
    WSL install, requiring a manual absolute-path fix in the cached `hooks/hooks.json`
    (`"C:/Program Files/Git/bin/bash.exe"`).
- **`claude-automation-recommender` skill** — a read-only static-analysis skill that inspects a
  codebase (via `Read`/`Glob`/`Grep`/`Bash`: `ls package.json pyproject.toml Cargo.toml go.mod`,
  grep for `react`/`supabase`/`stripe`/`aws-sdk`, check `.claude/`/`CLAUDE.md`, inspect
  `src/`/`tests/`/`components/`/`api/`) and maps detected signals to concrete automation
  recommendations across four categories, capped at "top 1-2 per type" with install commands
  included: MCP servers (react/next/express → context7 docs MCP; tests present → Playwright MCP;
  `@supabase/supabase-js` → Supabase MCP; GitHub remote → GitHub MCP; Sentry SDK → Sentry MCP), hooks
  (`.prettierrc`/`ruff.toml` → PostToolUse formatter; `.env`/`package-lock.json` → PreToolUse block
  hook; multitasking → Notification hooks matching `permission_prompt`/`idle_prompt`), subagents
  (>500 files → `code-reviewer`; `auth/`/stripe/PII detected → `security-reviewer`; raw SQL/complex
  ORM → `performance-analyzer`), and custom skills (`api-doc`, `create-migration` with a bundled
  `validate-migration.sh`, `new-component` scaffolding from `.template` files).
- **`hookify` plugin** — a declarative rule engine that turns YAML rules in
  `.claude/hookify.*.local.md` files into hook behavior without writing hook code: matches
  `tool_matcher` (e.g. `"Bash"`, `"Edit|Write"`, `"*"`) against `tool_name`, evaluates conditions
  (`regex_match`, `contains`, `equals`, `starts_with`, `ends_with`) against extracted fields (e.g.
  `command` for Bash, `new_text` for Edit, `reason` for Stop), and if any matched rule has
  `action: "block"` it returns a blocking response, otherwise combines matched warning rules into one
  `systemMessage`. Uses `@lru_cache` on regex compilation since `PreToolUse`/`PostToolUse` fire
  frequently and re-compiling patterns every call would be wasteful.
- **Messaging channel plugins (Telegram, Discord, iMessage)** — a shared architecture for bridging
  Claude Code to chat platforms: an MCP server process polls/webhooks the platform, validates the
  sender against `access.json` (`dmPolicy`: `pairing`/`allowlist`/`disabled`; `allowFrom`: approved
  IDs; `groups`: per-group policy e.g. `requireMention`; `pending`: in-flight pairing codes), saves
  attachments to a local `inbox/`, then sends an MCP notification `claude/channel` (payload:
  `chat_id`, `message_id`, `sender_id`, `text`) to wake up the CLI session, which is launched with
  `claude --channels plugin:<name>@claude-plugins-official`. Standard exposed tools: `reply` (with
  chunking for platform length limits), `react` (emoji reactions, Telegram/Discord), `chat_messages`
  (history fetch). **Pairing flow**: unknown sender → server generates a 5-6 char code → stored in
  `access.json.pending` with expiry → operator approves via e.g. `/telegram:access` → sender promoted
  to `allowFrom`. An `approved/` directory inside `~/.claude/channels/<plugin>/` acts as a
  filesystem-level signal for authorized sessions. `<PLUGIN>_ACCESS_MODE=static` env var disables
  runtime pairing, treating the current allowlist as read-only.

## Practical how-tos

- Install: `/plugin install {plugin-name}@claude-plugins-official`; browse via `/plugin install`
  discovery UI or `/plugin list` for installed plugins.
- Minimal internal `plugin.json` example structure includes `name`, `version`, `description`,
  `author`, optional path overrides.
- Minimal `SKILL.md`:
  ```markdown
  ---
  name: skill-name
  description: This skill should be used when the user asks to "phrase 1", "phrase 2", or needs guidance on [key concepts].
  version: 1.0.0
  ---
  # Skill Title
  ## Core Instructions
  ...
  ```
- Skill directory layout: `SKILL.md` (required) + optional `references/`, `scripts/`, `assets/`.
- MCP server bundled in `.mcp.json`:
  ```json
  { "mcpServers": { "my-service": { "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/dist/index.js"],
      "env": { "API_KEY": "${MY_SERVICE_API_KEY}" } } } }
  ```
- Skill creation process recommended by `plugin-dev`: (1) gather concrete usage examples first, (2)
  decide what's a deterministic script vs. a context reference vs. a boilerplate asset, (3) build the
  directory + write high-quality frontmatter metadata, (4) validate via the `skill-reviewer` agent or
  `plugin-dev` toolkit before shipping.
- To enable a messaging channel: `claude --channels plugin:imessage@claude-plugins-official`; place
  bot tokens (e.g. `TELEGRAM_BOT_TOKEN`) in a `.env` in the channel's state directory.

## Gotchas & caveats

- Same "commands are legacy, prefer skills" guidance as the sister repo, reinforced here: skills
  support progressive disclosure via `references/`; commands don't.
- Hooks that exit non-zero can cause "unexpected behavior" — always wrap hook script logic so it
  exits 0 regardless of internal errors, and communicate failure via the JSON `decision`/
  `systemMessage` fields instead.
- The ralph-loop pattern is powerful but self-admittedly relies on an honesty instruction ("do not lie
  to escape the loop") rather than a hard mechanical check — the only real safety net is
  `max_iterations`.
- Windows + bash-based Stop hooks (ralph-loop) can silently misbehave if the system's `bash` resolves
  to a broken WSL install rather than Git Bash; fix requires manually editing the cached
  `hooks/hooks.json` with an absolute path to `bash.exe`.
- Marketplace registry PRs are rejected by CI if plugin names collide, required fields are missing,
  or the array isn't kept in strict alphabetical order — contributors must consciously re-sort using
  the provided `--fix` flag.

## Wiki pages used

Overview; Getting Started; Plugin Marketplace; Plugin Architecture (partial); Skills System; Hooks
System; MCP Server Integration; Automation Recommender; ralph-loop (Iterative Development); Channel
Architecture and Access Control. (structure.md also lists Plugin Structure and Manifest, Commands,
Agents and Subagents, Plugin Settings and Configuration, LSP pages, per-plugin deep-dives under
Internal/External Plugins, Developer Guide, and Repository Management CI/CD pages — not read in full
due to overlap/lower marginal value vs. pages above.)
