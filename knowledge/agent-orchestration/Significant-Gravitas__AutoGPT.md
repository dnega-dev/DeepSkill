---
repo: Significant-Gravitas/AutoGPT
deepwiki: https://deepwiki.com/Significant-Gravitas/AutoGPT
github: https://github.com/Significant-Gravitas/AutoGPT
harvested: 2026-07-09
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`Significant-Gravitas/AutoGPT`](https://deepwiki.com/Significant-Gravitas/AutoGPT) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# Significant-Gravitas/AutoGPT — Distilled Knowledge

## What it is

The repository has evolved from a single standalone autonomous agent into a full-stack visual agent-building platform, and now contains **two separate, differently-licensed product lines that coexist in one repo**:

- **AutoGPT Platform** (`autogpt_platform/`, Polyform Shield License — restricts commercial competing-product use without a separate commercial license): a full-stack application where users build "agent graphs" visually by connecting reusable "blocks," backed by a FastAPI microservice backend and a Next.js frontend with a React Flow editor. This is the actively developed system.
- **Classic AutoGPT** (`classic/`, MIT License): the original standalone CLI agent, the **Forge** toolkit for building Agent-Protocol-compliant agents, and **agbenchmark** for standardized agent performance testing.
- **Shared infrastructure** (`autogpt_libs/`, MIT): auth (Supabase JWT), structured logging, feature flags (LaunchDarkly), Redis-backed distributed locking primitives.

The Platform also has a **Copilot system** — an AI-assisted chat interface for building/running agents via natural language, itself agentic (dual execution paths, detailed below).

External infra dependencies: Supabase (auth), PostgreSQL (via Prisma), Redis (distributed locking, 3-shard cluster, event bus), RabbitMQ (message broker for execution queues), FalkorDB (graph memory store), ClamAV (file upload virus scanning). LLM providers integrated: OpenAI, Anthropic, Groq, Ollama, OpenRouter, Llama API, AI/ML API, v0 (Vercel).

## Architecture (how it's built, key components)

### Core execution vocabulary
| Term | Code entity | Meaning |
|---|---|---|
| Graph | `AgentGraph` / `GraphModel` | A complete workflow definition: nodes + connections |
| Node | `AgentNode` / `NodeModel` | One execution unit — an instantiated Block plus its config |
| Link | `AgentNodeLink` | A directed data-flow connection between two nodes |
| Block | `Block` (`backend/blocks/_base.py`) | The reusable functional unit a node instantiates (LLM call, HTTP request, Discord post, etc.) |

Execution status enum (both graph- and node-level): `INCOMPLETE` (waiting for input) → `QUEUED` → `RUNNING` → `COMPLETED` | `FAILED` | `TERMINATED` | `REVIEW` (paused for human review, can resume to `QUEUED`/`RUNNING`/`TERMINATED`/`FAILED`).

### Block base class
Every block subclasses the abstract `Block` class: `id` (UUID), `name`, `description`, `categories: set[BlockCategory]`, `input_schema`/`output_schema` (Pydantic `BlockSchemaInput`/`BlockSchemaOutput`), `block_type: BlockType` (e.g. `WEBHOOK`, `AI`, `NOTE`), `execution_stats: NodeExecutionStats`, `static_output: bool`.

Execution is **generator-based**: the abstract `run()` method is an async generator that `yield`s `(output_name, output_data)` tuples — a block can emit multiple named outputs, and can even yield the same output multiple times (used for iteration blocks). The public `execute()` wrapper orchestrates the lifecycle: validate input against `input_schema` → call `run()` → validate each yielded output against `output_schema` → collect `execution_stats` → return.

`BlockSchemaInput`/`BlockSchemaOutput` (Pydantic models) expose `jsonschema()` (for the frontend), `validate_data()`, `get_required_fields()`, `get_missing_input()`, `get_missing_links()` (checks whether required inputs actually have upstream connections, not just default values). Fields use `SchemaField(description=, placeholder=, default=, advanced=, title=)` — `advanced=True` hides a field in the basic UI mode, which is a UX-level input-schema convention worth reusing in any low-code tool.

### Execution system (distributed, event-driven)
`ExecutionManager` is the central orchestrator, running as a multi-process system: a main manager (`ProcessPoolExecutor`) spawns Graph Workers, each of which runs its own asyncio event loops for node execution and node evaluation. Execution requests flow through RabbitMQ (`graph_execution_queue` carrying `GraphExecutionEntry`, plus a separate `graph_execution_cancel_queue`); node-level parallelism happens in-process via an in-memory node execution queue. Real-time status updates broadcast through a Redis event bus (`AsyncRedisExecutionEventBus`) to a WebSocket server, which pushes to the frontend.

Per-node execution flow: `validate_exec()` → prepare context (block instance, credentials, extra kwargs) → acquire a Redis-backed credentials lock (`creds_manager.acquire()`, preventing concurrent use of the same credential) → `Block.execute()` (async generator) → persist outputs to DB / enqueue downstream nodes → release credentials lock (always, via `finally`) → update execution stats (timing, token/cost).

**Dependency resolution for node inputs**: a node's inputs can come from static links (`is_static=true`), dynamic links, node default values (`input_default`), or explicit input-mask overrides (`nodes_input_masks`, used for graph presets/parameterization). `validate_exec()` checks whether all required inputs are actually satisfied; if not, the node sits in `INCOMPLETE` until upstream nodes produce the missing values, at which point it's `QUEUED`.

Cost/credit tracking is threaded through execution: `_charge_usage()` checks `get_credits()` before spending (raising `InsufficientBalanceError` on insufficient balance), then `spend_credits()` records a `UsageTransactionMetadata` (graph_exec_id, node_exec_id, block details) — costs are computed per `BlockCostType` (RUN / BYTE / SECOND), filtered by model and/or credential provider/type, from a large `MODEL_COST` mapping table (~70+ models) covering a low tier (1 credit — GPT-4o-mini, Claude Haiku, Groq) up to premium (14-21 credits — Claude 4 Opus tier).

### Tool-calling / agentic orchestration: the "SmartDecisionMaker" / OrchestratorBlock
This is the platform's core agentic primitive — a block that lets an LLM autonomously choose and invoke *other connected blocks as tools* within the visual graph, i.e. tool-calling is implemented as a graph-native concept rather than a separate agent abstraction. Renamed from `SmartDecisionMakerBlock` to `OrchestratorBlock` in a later version but same mechanism:

1. `_create_tool_node_signatures(node_id)` inspects the blocks connected downstream of the orchestrator node and converts each into an OpenAI-style function/tool signature.
2. `llm_call(..., tools=tool_functions, parallel_tool_calls=input_data.multiple_tool_calls)` sends the prompt with those tool definitions to the configured LLM provider.
3. Per-call stats (`prompt_tokens`, `completion_tokens`, `llm_call_count=1`) are merged into `NodeExecutionStats` after every call — this happens even mid-loop, so cost tracking stays accurate across a multi-turn tool-calling session.
4. Returned tool calls are executed against the actual connected blocks, and results are fed back into the LLM as the next turn — a classic ReAct-style loop, but implemented over the platform's own block/graph primitives rather than an external agent framework.

All LLM-powered blocks (`AITextGeneratorBlock`, `AIStructuredResponseGeneratorBlock`, `AITextSummarizerBlock`, `OrchestratorBlock`, etc.) extend `AIBlockBase(Block, ABC)`, which adds `self.prompt` (stores the last prompt sent) and `merge_llm_stats()` for aggregating stats when one block delegates to another (e.g. `AITextGeneratorBlock` internally delegates to `AIStructuredResponseGeneratorBlock` and merges its stats afterward — a clean "wrap a more general primitive and re-tag stats as your own" pattern).

### LLM provider abstraction layer
`llm_call()` is the unified entry point across OpenAI, Anthropic, Groq, Ollama, OpenRouter/Llama-API/v0 (OpenAI-compatible with custom base URLs). Provider-specific quirks handled explicitly:
- **OpenAI**: standard `tools` array request, `message.tool_calls` response, supports `response_format` JSON mode.
- **Anthropic**: system messages extracted separately from the messages array; consecutive same-role messages are combined (a real Anthropic API requirement); tools converted via `convert_openai_tool_fmt_to_anthropic()` (maps `parameters`→`input_schema`, hoists `function` fields to top level); tool calls arrive as `tool_use` blocks inside the `content` array rather than a dedicated `tool_calls` field.
- **Groq**: uses `AsyncGroq` but explicitly does **not support tools**.
- **Ollama**: uses `generate()` rather than the chat-completions shape.

This is a reusable reference implementation of "normalize N different LLM providers' tool-calling formats behind one interface" — the OpenAI↔Anthropic tool-schema conversion function in particular is a concrete, battle-tested mapping worth reusing.

### Prompt compression (context window management)
`compress_context()` is a 4-step, escalating strategy applied when `total_tokens + reserve > target`:
1. **Normalize**: convert non-string content to JSON strings, cap at 20,000 chars to avoid pathological blobs (skips first/last messages and tool messages).
2. **Token-aware truncation**: cap each message (except first/last) at `start_cap` tokens (default 8,192); if still over budget, repeatedly halve the cap down to a `floor_cap` (default 128). Tool messages only have their *result content* truncated via a dedicated helper, preserving the tool-call/response pairing structure.
3. **Middle-out deletion**: delete whole messages starting from the center of the conversation, working outward symmetrically — protects the first message, last message, any message containing tool calls/results, and anything tagged with a `MAIN_OBJECTIVE_PREFIX` marker (so the agent never forgets its top-level task).
4. **Last-chance trim**: if still over budget, truncate first and last message content to `floor_cap`, keeping both the beginning and end via `_truncate_middle_tokens()` (elide the middle of a single message rather than the start or end).
If even that fails and `lossy_ok` is false, raises `ValueError` rather than silently corrupting the conversation. Token counting uses `tiktoken`, with explicit handling for both OpenAI (`tool_calls`) and Anthropic (`tool_use`/`tool_result` content blocks) message shapes.

### Copilot: dual agentic execution paths
The Copilot chat assistant supports two parallel implementations of "agent that can call tools," selected per-request via `resolve_effective_mode()` → `resolve_use_sdk_for_mode()` (checks explicit user mode request → Claude Code subscription status → a LaunchDarkly feature flag, in that priority order):

- **SDK path (`stream_chat_completion_sdk`, "extended thinking")**: delegates the entire tool-calling loop to the **Claude Agent SDK** itself (Anthropic-only). Sets up a `ClaudeSDKClient`, builds system prompt + context (user context, "Graphiti" memory supplements, environment context), routes tool calls through an internal MCP server (`create_copilot_mcp_server`) that proxies to the platform's own backend tools, strips internal `<thinking>` blocks from the user-visible output (`ThinkingStripper`), and streams results via a `stream_registry` to the frontend over SSE. Has an explicit 3-attempt retry ladder for "prompt too long" errors: attempt 1 = original transcript, attempt 2 = compact the transcript (`compact_transcript`), attempt 3 = drop the transcript entirely and rebuild messages fresh from the database.
- **Baseline path (`stream_chat_completion_baseline`, "fast")**: a hand-rolled `tool_call_loop` against a generic OpenAI-compatible client (routed through OpenRouter for provider flexibility) — send messages → LLM responds with text or tool calls → `execute_tool()` on tool calls → feed results back → repeat. A `BaselineReasoningEmitter` streams intermediate reasoning steps to the frontend.

Both paths share: a `TranscriptBuilder` for conversation history, an `AsyncClusterLock` acquired for the session (prevents two processes from handling the same conversation concurrently — important in a horizontally-scaled deployment), and `persist_and_record_usage()` for token/cost tracking. This dual-path design — a heavyweight SDK-delegated agent loop for complex reasoning vs. a lightweight hand-rolled loop for speed — is a reusable pattern for systems that need both "maximum capability" and "fast/cheap" agent tiers.

### Visual control-flow blocks
The Platform expresses agent control flow (branching, iteration) as graph-native blocks rather than code:
- `StepThroughItemsBlock` (categories: both `DATA` and `LOGIC`) iterates a list or dict, yielding `(item, key_or_index)` pairs one at a time — this is literally how "for loops" are expressed in the visual graph (each yield triggers downstream nodes once per item). Hard safety limits: `MAX_ITEMS = 10_000`, `MAX_ITEM_SIZE = 1MB` on string inputs — validated before iteration begins to prevent memory exhaustion from malicious/malformed graphs.
- `ConditionBlock` / `IfInputMatchesBlock` express branching via comparison operators.
- `StoreValueBlock` provides a constant, reusable value; marked `static_output=True` so it can be consumed multiple times without re-executing — a caching/memoization convention for pure values in a dataflow graph.
- `AIConditionBlock` uses an LLM call with a tight `max_tokens=50` to evaluate a *natural-language* condition and parse a true/false result — letting branching logic be expressed in plain English rather than a formal comparison, at the cost of an LLM round-trip per branch decision.

## Key patterns & techniques (transferable)

1. **Tool-calling as a first-class graph primitive, not a bolt-on agent framework.** Rather than building a separate "agent" abstraction, the orchestrator block treats *any connected block* as an invocable tool by auto-generating its function signature from the block's own input schema. This means every existing integration/utility block in the system automatically becomes usable by an LLM agent with zero extra wiring — a powerful "everything is a tool" design if you already have a rich component library.
2. **Provider tool-schema normalization as one explicit conversion function.** `convert_openai_tool_fmt_to_anthropic()` is a small, testable, reusable unit — treating OpenAI's function-calling shape as the canonical internal format and writing thin converters to other providers' shapes (rather than parameterizing every call site per-provider) keeps the rest of the codebase provider-agnostic.
3. **Escalating, protected context compression.** The 4-step compress-context strategy (normalize → truncate → middle-out delete → last-chance trim) with an explicit "never touch these" protection list (first/last message, tool call/result pairs, main-objective marker) is a robust general pattern for keeping long agent conversations within a context window without breaking tool-call/response pairing or losing the original task framing.
4. **Dual-tier agent execution (SDK-delegated vs. hand-rolled loop) selected by policy.** Rather than picking one agent-loop implementation, offering both a "delegate to a more capable but heavier external agent SDK" path and a "fast, cheap, hand-rolled loop" path, gated by subscription/feature-flag/explicit-choice, is a practical way to serve both power users and cost-sensitive/latency-sensitive traffic from the same product surface.
5. **Credential acquisition as a lock, not just a lookup.** Wrapping credential usage in an actual Redis lock (`creds_manager.acquire()`/`release()` in a `finally` block) — not just fetching the secret — prevents race conditions when the same OAuth token or API key might be used by concurrent executions (e.g. rate-limited or single-session external APIs).
6. **Static-output marking for pure/constant values in a dataflow graph.** `StoreValueBlock`'s `static_output=True` is a small but useful convention: explicitly flagging which outputs never change per-execution lets a graph engine safely cache/reuse them instead of re-invoking the producing node.
7. **Visual iteration via generator yield, with hard resource caps baked into the primitive.** Expressing "for each item, trigger this subgraph" as a generator that yields once per item (rather than a special-cased "loop" construct in the execution engine) keeps the execution model uniform, but only works safely because the iteration block itself enforces `MAX_ITEMS`/`MAX_ITEM_SIZE` — a reminder that user-facing loop primitives need their own resource guards, not just the graph engine's.
8. **Natural-language conditionals as an explicit, separate block type from formal comparisons.** Keeping `AIConditionBlock` (LLM-evaluated NL condition) distinct from `ConditionBlock` (formal operator comparison) rather than merging them preserves predictability for the common case while still offering an escape hatch for fuzzy conditions — with an intentionally tight token budget (`max_tokens=50`) to keep the LLM call cheap and fast for what should be a simple boolean.

## Practical how-tos

- **Define a custom block**: subclass `Block`, define nested `Input(BlockSchemaInput)`/`Output(BlockSchemaOutput)` Pydantic classes using `SchemaField(...)`, implement `async def run(self, input_data: Input, **kwargs) -> BlockOutput` as an async generator that yields `(output_name, value)` tuples, and register `id`, `categories`, `input_schema`, `output_schema`, plus `test_input`/`test_output` for automated testing in `__init__`.
- **Give an LLM access to tool-calling over existing blocks**: connect blocks downstream of an `OrchestratorBlock`/`SmartDecisionMakerBlock` node — their input schemas are auto-converted into tool signatures the LLM can invoke.
- **Iterate over a list in a visual graph**: wire a `StepThroughItemsBlock` between the list source and the per-item processing subgraph; it yields once per item automatically.
- **Add resilience to a multi-step AI block**: follow the `AIStructuredResponseGeneratorBlock` retry pattern — loop up to `input_data.retry` attempts, track `llm_retry_count` in stats on every non-first attempt, re-raise only after the final attempt fails.
- **Keep a long agent conversation inside a context window**: call `compress_context()` with `target_tokens` set to roughly half your model's context window (per the `compress_prompt_to_fit=True` convention used by `llm_call`) before every completion request, rather than only reacting after a "context too long" error.

## Gotchas & caveats

- **Two different license regimes in one repo** — code under `autogpt_platform/` is Polyform Shield (commercial-competing-product restrictions) while everything else (`classic/`, `autogpt_libs/`) is MIT; contributions to the platform folder additionally require signing a CLA. Anyone forking or embedding code from this repo needs to check which subtree it came from before assuming MIT terms apply.
- **`PrintToConsoleBlock` (a debugging utility) is `disabled=True` by default** — a reasonable default for a production visual-agent platform, but means naive testing of "does this block even work" via that block will silently do nothing unless explicitly enabled.
- **Groq provider explicitly does not support tool calling** in the `llm_call()` abstraction — code that assumes uniform tool-calling across all configured providers will fail/silently degrade specifically on Groq.
- **`StepThroughItemsBlock` caps at 10,000 items and 1MB string input** — large-scale batch/iteration workflows built on this primitive will hit a hard wall well before typical "big data" scale; this is a deliberate DoS-prevention limit, not a performance tuning knob.
- **The 3-attempt SDK-path retry ladder for "prompt too long" progressively degrades context** (full transcript → compacted → dropped-and-rebuilt-from-DB) — by the third attempt, prior turn-level nuance may be lost even though the request succeeds; a caller inspecting only "did the request succeed" won't see that context quality degraded en route.
- **Credential locks are per-credential, not per-user or per-graph** — `creds_manager.acquire()` is scoped to prevent concurrent use of the *same* credential; two different graphs/executions using the *same* stored OAuth token will serialize against each other even if otherwise fully independent.
- **`OrchestratorBlock` was formerly named `SmartDecisionMakerBlock`** — wiki/docs/code may reference either name depending on version; treat them as the same mechanism when reading older material or block-cost config tables.

## Wiki pages used

- Overview
- Repository Structure
- Core Components
- Key Terminology
- Execution System
- Block System
- AI Blocks (partial — tool call format conversion, prompt compression, usage patterns)
- Data and Control Flow Blocks (partial — iteration/branching blocks)
- Copilot Architecture and Execution
