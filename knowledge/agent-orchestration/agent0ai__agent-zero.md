---
repo: agent0ai/agent-zero
deepwiki: https://deepwiki.com/agent0ai/agent-zero
github: https://github.com/agent0ai/agent-zero
harvested: 2026-07-09
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`agent0ai/agent-zero`](https://deepwiki.com/agent0ai/agent-zero) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# agent0ai/agent-zero — Distilled Knowledge

## What it is

Agent Zero is a "dynamic, organic agentic framework designed to grow and learn through usage," built on the philosophy of **"Computer as a Tool"**: rather than a fixed library of pre-programmed functions, the agent uses a real operating system, terminal, and web browser to accomplish tasks — its primary tool is `code_execution_tool`, which lets it write and run arbitrary Python/shell code to solve problems it wasn't explicitly given a function for.

Four architectural pillars stated in the docs:
1. **Computer as a Tool** — full Linux system with a desktop, not a curated tool library.
2. **Organic Growth** — the agent extends itself via Skills and Plugins, building tools as work demands them.
3. **Multi-Agent Cooperation** — a hierarchical Superior/Subordinate model where agents spawn subordinate agents for subtasks, keeping the primary context clean.
4. **Universal Canvas** — a shared visual interface (browser sessions, Markdown editing, LibreOffice cowork) where agents and humans work on the same surfaces.

Stack: Python backend + Alpine.js frontend, typically run in Docker for isolation. Uses LiteLLM for multi-provider LLM access, FAISS for vector memory, Flask/Socket.io for the web server and real-time streaming.

## Architecture (how it's built, key components)

### Runtime separation: Framework vs. Execution
A deliberate security/architecture split between two environments:
| | Framework Runtime | Execution Runtime |
|---|---|---|
| Entry point | `run_ui.py` | `_code_execution` plugin |
| Purpose | API, LLM orchestration, WebSocket handlers | Terminal, GUI apps, agent-generated code |
| Python env | `/opt/venv-a0` (Python 3.12) | `/opt/venv` (Python 3.13) |
| State | `AgentContext` | `/a0/usr/` persistent volume |

The framework never executes agent-written code directly in its own process — everything the agent produces (shell commands, scripts, `pip install`) runs in a separate sandboxed environment, so the agent modifying its own execution environment (e.g. installing a library) cannot break the framework serving it. The **A0 CLI Connector** can bridge this further, letting a Dockerized agent operate on host-machine files/shell/browser (via CDP) while the framework itself stays contained.

### AgentContext: the state container
`AgentContext` is the central state container for one conversation/session — owns the root `Agent` instance (`agent0`), a `Log` for UI sync, and a `DeferredTask` wrapping the background monologue execution. Contexts are tracked in a global `_contexts` dict guarded by a reentrant lock; each has an 8-character generated ID and a `type` (`USER`, `TASK`, `BACKGROUND`, or `SUBORDINATE` for spawned sub-agents). Running the agent's reasoning loop inside a `DeferredTask` (rather than blocking the request handler) is what lets the web server stay responsive to interventions and status polling while a long LLM/tool chain executes.

### Superior/Subordinate hierarchy
Every agent instance has exactly one Superior (who gives instructions — the human user for the root agent, or a parent `Agent` for a spawned one) and can create Subordinates via `subagents.py` to delegate subtasks. The stated benefit is **context isolation**: a subordinate handles a narrow subtask and reports back a result, so the main agent's history doesn't get cluttered with low-level execution detail from work it delegated. Agent profiles (see below) are commonly matched to subordinate roles — e.g. delegating to a `developer` or `researcher` profile subordinate for specialized work.

### The Monologue Loop
`Agent.monologue()` is the reasoning entry point, implementing an iterative Thought → Action → Observation cycle via `_process_chain`:
1. **Prompt assembly** — gather history + the (dynamically assembled, see below) system prompt.
2. **LLM request** — call the configured model through `models.py`.
3. **Reasoning/thinking parsing** — `ChatGenerationResult` separates native provider reasoning tokens (e.g. DeepSeek R1) or manually-tagged `<think>`/`<reasoning>` content from the final response text, handling partial tags mid-stream via `_is_partial_opening_tag`/`_is_partial_closing_tag` so streamed output doesn't leak half-formed tags.
4. **Tool extraction** — parse LLM output for JSON tool calls via `extract_tools.extract_json_root_string`; malformed JSON is run through `DirtyJson` for best-effort recovery before giving up.
5. **Tool execution** — dispatch to the matching `Tool` subclass. If the tool is "terminal" (e.g. `response`), the loop ends and control returns to the user.
6. **Error handling** — a `RepairableException` triggers asking the LLM to fix its own mistake rather than crashing the loop.

`LoopData` (a dataclass) tracks per-execution state: `iteration_count` (loop safety), `total_tokens`/`prompt_tokens`/`completion_tokens`, and an `intervention` string. **Interventions**: if the user sends a new message while the agent is mid-thought, an `InterventionException` is raised, the loop catches it, appends the message into `LoopData.intervention`, and restarts the current iteration incorporating the new input — a clean mechanism for mid-flight steering without killing and restarting the whole task.

### Prompt system: assembled, not monolithic
The system prompt is built at the start of every monologue loop by chaining a series of numerically-prioritized extension classes, each appending a block of text to a `system_prompt` list that's joined at the end. Priority order (lower runs first):
| Priority | Purpose |
|---|---|
| 09 | Tool-specific config (e.g. text editor line limits) |
| 10 | Core personality/behavioral rules (`agent.system.main.md`) |
| 11 | Discovers and formats all `agent.system.tool.*.md` tool definition fragments |
| 12 | MCP-server-provided tools |
| 13 | Secrets/env vars (masked) + available Skills list |
| 14 | Project-specific instructions/variables |
| 16 | Persistent user-defined prompt fragments |

Prompt fragments are Markdown files supporting `{{placeholder}}` substitution and recursive `{{ include "..." }}` inclusion. Notably, `agent.system.main.communication.md` **enforces JSON-only responses** — the agent must always respond with `{thoughts, headline, tool_name, tool_args}` and text outside that JSON structure is explicitly forbidden — a strict machine-parseable output contract rather than free-form text with embedded tool calls.

**Agent profiles** (`agent0`, `developer`, `researcher`, `hacker`, `tiny-local`, etc.) are directories that override specific prompt fragments to change identity/capability while inheriting the rest from `default/`. Resolution checks user-space (`/a0/usr/agents/<profile>/`) before built-in (`/a0/agents/<profile>/`). The `tiny-local` profile is a good example of profile-driven prompt engineering for constrained resources: it strips the `thoughts`/`headline` reasoning fields from the required JSON schema entirely to save tokens for small local models. There's an explicit token budget guardrail: the default `agent0` prompt is kept under 10,000 tokens (enforced by a test) to stay compatible with most modern LLMs while still including the full tool surface.

### Tool system
Every tool subclasses a `Tool` base class with three lifecycle hooks: `before_execution` (optional setup/logging), `execute` (the core logic — receives LLM-provided args, returns a `Response`), `after_execution` (optional cleanup/injection, e.g. `VisionLoad` appends image content + token estimates to history here). The `Response` object has `message` (text returned to the agent's context) and `break_loop: bool` — `True` stops the monologue and waits for user input (e.g. the `response` terminal tool), `False` continues the reasoning chain (e.g. after a search or a skill load).

Built-in tools: `vision_load` (image loading for visual reasoning), `skills_tool` (search/list/load `SKILL.md` capabilities), `parallel` (concurrent tool execution — see below), `text_editor` (canonical file read/write/patch), `call_subordinate` (delegate to a sub-agent by profile), `scheduler` (background/deferred task scheduling).

**Tool call normalization**: the framework is deliberately resilient to variations in how an LLM formats a tool call — it normalizes fields like `tool`→`tool_name` and extracts action names from method-call-shaped output before dispatch, rather than requiring the LLM to hit one exact schema every time. If a `tool_name` is genuinely unrecognized after normalization, an error is returned to the agent (not a crash), letting it self-correct on the next iteration.

**Parallel tool execution**: the `parallel` tool wraps independent tool calls into background jobs (`helpers/parallel_tools.py`), normalizing multiple possible JSON shapes into a standard `NormalizedToolCall`. High-resource tools (e.g. `document_query`) are explicitly excluded from parallel execution to prevent worker-pool exhaustion. Jobs support start/await-by-id/collect-if-finished/cancel semantics — a fairly complete async job-management API surface exposed as a single tool.

### Extension framework: non-invasive hooking
This is the core mechanism that makes "almost nothing is hard-coded" true. The `@extensible` decorator wraps an existing function and implicitly creates two extension points — `start` and `end` — named by convention as `_functions/<module_path>/<qualname>/start` and `/end`. Extensions are Python classes (subclassing `Extension`) discovered from `python/extensions/` (system) and `usr/extensions/` (user), organized into subdirectories per hook point, and executed **in numeric filename order** (`_10_*.py` before `_20_*.py`) within each point — this is the same priority-by-filename convention used for the system-prompt assembly extensions above, applied generically.

Data flow: calling an `@extensible` function builds a `data` dict with `args`, `kwargs`, `result` (a sentinel `_UNSET` until set), and `exception`. `start` extensions run first and can **mutate args/kwargs or short-circuit by setting `result`** (skipping the original function entirely if `result` becomes non-`_UNSET`); the original function then runs if not short-circuited; `end` extensions run last and can modify the result or suppress/replace an exception. This is a full aspect-oriented-programming-style hook system layered onto plain Python functions with zero changes to their bodies — arbitrary behavior (logging, caching, validation, monkey-patchable business logic) can be injected at any `@extensible` boundary without touching the original code.

The same pattern exists on the frontend: JS extensions hook `initFw_start`/`initFw_end` via `callJsExtensions`, and UI "surfaces" allow injecting HTML at defined points.

A watchdog monitors extension/plugin directories for file changes and triggers cache invalidation + namespace purging (`modules.purge_namespace`) + a frontend reload notification — giving hot-reload of extensions/plugins without a full process restart.

### Plugin system: bundling tools + API + UI + prompts
Plugins are self-contained directories with a `plugin.yaml` manifest (`name`, `title`, `description`, `version`, `settings_sections`, `per_project_config`, `per_agent_config`, `always_enabled`), discovered from `usr/plugins/` (user, higher priority on name collision) and `plugins/` (core, bundled). A plugin can simultaneously contribute: Python tools, Flask API routes (`api/` subdirectory, handlers subclass `ApiHandler`), frontend Alpine.js components, new LLM providers (merged into `model_providers.yaml` via `ProviderManager._load_providers`), and prompt fragments.

Activation is controlled by marker files: `.toggle-1` (explicit on) / `.toggle-0` (explicit off), defaulting to on if neither exists — resolved hierarchically (agent-profile scope > project scope > global scope). `hooks.py` runs in the framework environment for install/uninstall/pre-update lifecycle events; `execute.py` is for manually-triggered maintenance tasks run from the UI. Notable bundled plugins: `_memory` (FAISS vector storage), `_model_config` (provider/model resolution), `_plugin_validator`, `_infection_check` (security scanning of downloaded code).

### LLM abstraction and rate limiting
Agent Zero never calls provider APIs directly — it uses a `LiteLLMChatWrapper` (a LangChain-`SimpleChatModel`-compatible class wrapping LiteLLM), configured by a `ModelConfig` dataclass (provider, credentials, context length, rate limits), with supported providers enumerated in `conf/model_providers.yaml` (anthropic, openai, deepseek, google, ollama, venice, xai, etc.). A `_model_config` plugin resolves which `ModelConfig` to actually use based on global/project/agent-profile-specific settings — the same hierarchical override pattern seen in plugin toggling.

**Rate limiting**: `RateLimiter` tracks rolling-window usage against `limit_requests` (RPM), `limit_input`/`limit_output` (TPM), forcing `asyncio.sleep` when a provider's limits would otherwise be hit — proactive throttling rather than reactive 429-retry. **Token counting** uses a fast heuristic (`approximate_tokens`, roughly 4 chars/token for English) instead of calling a remote tokenizer, trading precision for speed since this check runs on every request.

### Memory system
Uses FAISS (via a `MyFaiss` class extending LangChain's FAISS wrapper) with three scoped areas (`Memory.Area` enum): **MAIN** (general long-term facts/experiences), **FRAGMENTS** (short snippets auto-extracted from conversation by a background extension), **SOLUTIONS** (verified step-by-step technical fixes). Embeddings are cached via `CacheBackedEmbeddings` backed by a `LocalFileStore` to avoid redundant embedding-model calls for repeated text.

**Intelligent consolidation** (`MemoryConsolidator`) runs when a new memory is saved: (1) vector-search for similar existing memories, (2) re-validate those candidates still exist in the docstore via `get_by_ids()` — explicitly guarding against race conditions from concurrent consolidation, (3) an LLM call classifies the relationship into one of `MERGE`, `REPLACE`, `UPDATE`, `KEEP_SEPARATE`, `SKIP`, (4) execute — remove redundant docs, insert the consolidated version. This is a genuinely non-trivial approach to long-term-memory hygiene: rather than blindly appending every fact, an LLM actively decides whether new information supersedes, merges with, or is redundant with what's already stored.

**Cascade deletion**: `memory_forget` (semantic-query-based) and `memory_delete` (by-ID) both clean up derived records that reference the deleted memory's ID in their own `consolidated_from`/`updated_from` metadata — so deleting a source memory doesn't leave orphaned fragments/solutions pointing at nothing.

**Automatic recall + filtering**: relevant memories are retrieved at the start of every monologue via similarity search, then passed through an LLM-based relevance filter (`memory.memories_filter.sys.md`) before injection into the prompt — explicitly instructed to exclude vague texts, common greetings, and older facts superseded by newer ones. This two-stage retrieve-then-filter pattern (vector search for recall, LLM for precision) avoids polluting the prompt with technically-similar-but-actually-irrelevant memories. Background memorization at the end of each loop caps conversation history scanned at 80,000 characters and runs a separate quality filter (`filter_auto_memory_fragments`) to drop transient/low-value content before it's even considered for storage.

Knowledge Base (pre-existing files in `knowledge/`) is distinct from Memory (learned during execution): static source files + a FAISS index, updated on startup or manual reload rather than continuously.

### Skills system (Anthropic SKILL.md standard)
Skills are directories with a mandatory `SKILL.md` (YAML frontmatter: name, version, description, author, tags, trigger patterns) plus optional `scripts/` and support files — explicitly built on the `agentskills.io`/Anthropic open standard. Discovered from four scopes with clear precedence: core (`/a0/skills/`), user-global (`/a0/usr/skills/`), project-specific (`.a0proj/skills/`), and plugin-bundled (`plugins/*/skills/`).

`SkillsTool` exposes `search` (match query against name/description/triggers), `list`, and `load` (verify existence, normalize the name, record it into the agent's loaded-skills ledger, and inject the full skill body into chat history as a tool result). A key gotcha this wiki calls out explicitly: **loaded skill bodies live in tool-result history**, and if history gets compacted/summarized, the full skill text can be lost — an `IncludeLoadedSkills` extension reattaches missing skill bodies (within a 12,000-token budget) after compaction, and summarization prompts are instructed to preserve *skill names* from metadata without copying full bodies. There's also a hard cap of `MAX_ACTIVE_SKILLS = 20` on how many skills can be simultaneously "pinned" active to prevent context-window exhaustion from an unbounded skill list.

### External connectivity: MCP server, A2A, REST
Agent Zero can act as an **MCP server** (exposing itself as tools to other MCP clients like Claude Desktop), a **FastA2A** node (agent-to-agent protocol), and a plain **REST API** provider — all sharing one token-based auth scheme (`mcp_server_token`, regenerated whenever credentials change, invalidating old connection URLs).

- MCP endpoints: `/mcp/t-{token}[/p-{project}]/sse` and `/http` — the optional `/p-{project}` segment scopes the session to a specific project workspace, so one Agent Zero deployment can serve multiple isolated project contexts through the same MCP interface.
- A2A endpoints: `/a2a/t-{token}[/p-{project}]`, supporting four different auth transport methods (token-in-URL, Bearer header, `X-API-KEY` header, or `?api_key=` query param) for the `.well-known/agent.json` agent card — each A2A task runs in a fresh `AgentContext` typed `BACKGROUND`.
- REST: `/api_message` (send, with `context_id`/`attachments`/`project_name`), `/api_log_get`, `/api_terminate_chat`, `/api_reset_chat` — designed to bypass the web UI's CSRF protections in favor of API-key auth for third-party integrations.

## Key patterns & techniques (transferable)

1. **Framework/Execution runtime separation as a security boundary.** Running agent-generated code in a completely separate process/venv/filesystem-scope from the orchestration logic (rather than `exec()`-ing it inline) means the agent breaking its own sandbox (bad pip install, corrupted venv) cannot take down the thing serving it. Any "agent that writes and runs its own code" system should consider this split as a baseline safety property, not an optimization.
2. **Priority-ordered, filename-numbered extension composition for building a system prompt.** Rather than one hardcoded prompt string, assembling it from a list of numerically-ordered contributor classes (`_09_`, `_10_`, `_11_`...) makes the prompt genuinely modular — plugins can insert their own prompt fragment at an arbitrary priority slot without touching a monolithic template, and the ordering is legible just from the filenames.
3. **Aspect-oriented `@extensible` decorator with start/end hooks and short-circuit-by-result-sentinel.** A generic, reusable mechanism (any function can become an extension point just by adding one decorator) beats hand-rolling a bespoke hook system per feature. The short-circuit convention (`result` starts as a sentinel; setting it in a `start` hook skips the wrapped function) is a clean way to let extensions fully replace behavior, not just observe it.
4. **Retrieve-then-filter for memory recall.** Doing vector similarity search first (recall) and then a second LLM pass to judge actual relevance (precision) before prompt injection is a reusable two-stage pattern for any RAG-like system where "semantically similar" and "actually useful right now" diverge (e.g. stale facts, generic greetings ranking high on embedding similarity but adding no value).
5. **LLM-mediated memory consolidation with an explicit action taxonomy (MERGE/REPLACE/UPDATE/KEEP_SEPARATE/SKIP).** Rather than naive append-only memory or brittle rule-based deduplication, having the LLM classify the relationship between a new fact and its nearest existing neighbors into a small fixed set of actions is a practical middle ground — structured enough to implement deterministically, flexible enough to handle real-world ambiguity.
6. **Tool-call format normalization as a resilience layer.** Explicitly tolerating multiple JSON shapes for the "same" tool call (field renames, alternate structures) rather than requiring one canonical format reduces brittleness against LLM output variance — worth doing in any system where a model's structured-output adherence isn't 100% guaranteed.
7. **Context-preserving skill reattachment after history compaction.** Recognizing that summarization/compaction can silently destroy previously-injected reference material (like a loaded skill's full body) and building an explicit "reattach if missing, within a token budget" mechanism is a pattern worth copying for any agent that injects large reference blobs into history and later compacts that history.
8. **Hierarchical config/toggle resolution (agent-profile > project > global).** The same three-level override pattern shows up for plugin toggles and model config resolution — a reusable convention for "let settings cascade from broad to specific, with the most specific always winning."
9. **Proactive rate limiting via rolling-window tracking, not reactive 429 handling.** Tracking request/token counts in a rolling window and sleeping *before* exceeding a provider's stated limit avoids wasted round-trips and failed calls compared to a retry-after-429 approach.

## Practical how-tos

- **Add a new tool**: subclass `Tool` in `tools/`, implement `execute(self, **kwargs) -> Response`, optionally override `before_execution`/`after_execution`; add a corresponding `agent.system.tool.<name>.md` prompt fragment so the LLM knows the tool exists and how to call it (tool prompts are auto-discovered via the `agent.system.tool.*.md` glob pattern).
- **Add a new plugin**: create a directory in `usr/plugins/<name>/` with a `plugin.yaml` manifest; add `tools/`, `api/` (subclassing `ApiHandler`), `extensions/python/<hook_point>/_NN_*.py`, and/or `webui/` frontend files as needed; toggle with `.toggle-1`/`.toggle-0`.
- **Hook into an existing framework function without modifying it**: find (or add) `@extensible` on the target function, then drop a new `Extension` subclass into `python/extensions/_functions/<module_path>/<qualname>/start/` or `/end/` — numbered filename controls execution order relative to other extensions at that point.
- **Create a reusable Skill**: write a `SKILL.md` with YAML frontmatter (name, description, trigger patterns) plus any supporting scripts, placed in `usr/skills/<skill-name>/`; the agent discovers it via `skills_tool:search`/`:list` and pulls it into context via `:load`.
- **Delegate a subtask to a specialized sub-agent**: call `call_subordinate` with an `agent_profile` (e.g. `developer`, `researcher`) and a `message` — the subordinate runs its own full monologue loop with a clean context and reports back.
- **Expose Agent Zero to another MCP client**: enable the MCP server setting, retrieve the `mcp_server_token` from settings, connect to `/mcp/t-{token}/sse` (or `/http`), optionally scoping to `/p-{project}` for a specific project workspace.

## Gotchas & caveats

- **Loaded skill bodies live in tool-result history and can be silently lost on compaction** — the `IncludeLoadedSkills` reattachment mechanism has a 12,000-token budget; a very large skill body, or many simultaneously-active skills, could still exceed that budget and not be fully reattached after summarization.
- **`MAX_ACTIVE_SKILLS = 20` is a hard cap** — pinning more skills than that will not all stay active simultaneously; design skill sets with this ceiling in mind.
- **Parallel tool execution explicitly excludes high-resource tools like `document_query`** — not everything can be parallelized through the `parallel` tool; check exclusion lists before assuming a given tool supports concurrent invocation.
- **The default agent0 system prompt is deliberately capped under 10,000 tokens** — heavily customizing prompt fragments (more profiles, more injected context) risks silently breaking compatibility with smaller-context models that this budget was designed to support.
- **Token counting uses a heuristic approximation (~4 chars/token), not an exact tokenizer** — rate-limiting and context-budget decisions based on `approximate_tokens` can be off from the model provider's actual token count, especially for non-English text or code-heavy content.
- **Memory consolidation re-validates candidates via `get_by_ids()` specifically to guard against races** — this implies consolidation is not naturally safe under high concurrency without that check; anyone extending the memory system needs to preserve or replicate that validation step.
- **The Execution Runtime uses a different Python version (3.13) than the Framework Runtime (3.12)** — code/dependencies written assuming framework-side Python behavior may not transfer directly to agent-executed scripts.
- **Tool-call format normalization has limits** — if a `tool_name` remains unrecognized even after normalization, the agent gets an error message (recoverable) rather than the framework guessing intent; badly malformed or truly novel tool-call shapes still fail gracefully rather than silently succeeding.

## Wiki pages used

- Agent Zero Overview
- Getting Started & Installation (partial)
- Core Concepts & Terminology
- Agent Lifecycle & Monologue Loop
- Prompt System & Agent Profiles
- Tool System
- LLM Model Abstraction & Rate Limiting
- Extension & Plugin System
- Extension Framework
- Plugin Architecture & Lifecycle
- Memory System & Vector Database
- Skills System
- External Connectivity: MCP, A2A & REST API (partial)
