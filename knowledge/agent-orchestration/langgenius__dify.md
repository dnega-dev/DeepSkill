---
repo: langgenius/dify
deepwiki: https://deepwiki.com/langgenius/dify
github: https://github.com/langgenius/dify
harvested: 2026-07-09
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`langgenius/dify`](https://deepwiki.com/langgenius/dify) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# langgenius/dify — Distilled Knowledge

## What it is

Dify is an open-source platform for developing LLM applications, combining agentic workflows, RAG pipelines, agent capabilities, model management, and observability into one environment, accessible via both a visual builder and programmatic APIs. It's multi-tenant (workspace isolation + RBAC), model-agnostic (100+ models across dozens of providers via a unified interface), and extensible via a plugin system.

Editions: Dify Cloud (hosted SaaS), Self-Hosted Community (open-source, Docker Compose/K8s), Enterprise (SSO, custom branding).

Service topology (Docker Compose): `api` (Flask, main REST server), `worker` (Celery, async tasks — dataset indexing, document processing, workflow execution), `worker-beat` (Celery scheduler), `web` (Next.js frontend), `plugin_daemon` (plugin execution, separate Go/Python service communicating with `api` via internal Docker networking + `PLUGIN_DIFY_INNER_API_KEY`), `sandbox` (Go-based, executes untrusted Python/Node code from workflows, network-restricted via `ssrf_proxy`). Notably, **`api`, `worker`, and `worker-beat` all use the same Docker image** (`langgenius/dify-api`), differentiated only by a `MODE` environment variable — one build artifact, multiple runtime roles.

Data layer: PostgreSQL 15 (primary, MySQL 8.0 as an alternative), Redis 6 (Celery broker + cache), a `VectorFactory` abstraction supporting 23+ vector DB backends (default Weaviate; also Milvus, Qdrant, PGVector, Chroma, Elasticsearch, etc.), and Apache OpenDAL (or native cloud SDKs) for file storage (default local filesystem, options for S3/Azure/Aliyun OSS/GCS).

There is also a **separate, newer Agent Runtime**: a standalone FastAPI service built on a framework called "Agenton," decoupled from the main Flask API so it can scale independently for long-running agentic reasoning loops (see below).

## Architecture (how it's built, key components)

### Application modes (AppMode enum)
Every Dify app has a `mode` that determines its execution path:
| Mode | Generator class | Category |
|---|---|---|
| `completion` | `MessageBasedAppGenerator` | Easy UI (prompt-based, single-turn) |
| `chat` | `MessageBasedAppGenerator` | Easy UI (multi-turn) |
| `agent-chat` | `MessageBasedAppGenerator` | Easy UI (multi-turn + autonomous tool-calling via `AgentModeConfig`) |
| `workflow` | `WorkflowAppGenerator` | Workflow-based (stateless visual graph) |
| `advanced-chat` | `WorkflowAppGenerator` | Workflow-based (visual graph + conversation memory) |
| `rag-pipeline` | `PipelineRunner` | Pipeline-based (indexing/retrieval) |
| `agent` | (Agent Runtime, see below) | New Agent V2 path |

"Easy UI" apps (completion/chat/agent-chat) are simpler — System Prompt + LLM settings via `AppModelConfig`, no visual graph. Workflow-based apps execute a full `GraphEngine`-driven node graph, distinguished at the `Workflow` model level by a `type` field (`workflow` vs `chat` vs `rag-pipeline`) — same underlying execution machinery, different persistence/memory semantics layered on top.

Execution is unified through a `BasedGenerateTaskPipeline` class hierarchy (`EasyUIBasedGenerateTaskPipeline`, `WorkflowAppGenerateTaskPipeline`, `AdvancedChatAppGenerateTaskPipeline`), all consuming events from an `AppQueueManager` and converting them into either streaming or blocking HTTP responses — the pipeline abstraction is what lets very different execution models (simple prompt call vs. full graph run) present a consistent streaming/blocking API surface to clients.

### Workflow engine: static definition vs. runtime execution
Deliberate separation of concerns across four layers:
1. **Static definition**: the `Workflow` SQLAlchemy model stores the graph "blueprint" — `graph` (LongText, nodes/edges JSON), `_features` (JSON: opening statements etc.), `_environment_variables` (encrypted), `version` (`draft` for the working copy, or a published version/timestamp), `type` (`workflow`/`chat`/`rag-pipeline`), `kind` (`standard`/`snippet` — snippets are presumably reusable sub-graphs). No execution state lives here.
2. **Execution engine**: `GraphEngine` (provided by an internal `graphon` package) traverses the graph, manages node transitions, and supports parallel execution. It's initialized by `WorkflowEntry` with a `Graph` object, a `GraphRuntimeState`, and a `CommandChannel` (default `InMemoryChannel`).
3. **Runtime state management**: `VariablePool` is the central data repository during a run — nodes read inputs and write outputs into it via selectors like `['node_id', 'output_key']`. Initialized via `VariablePool.from_bootstrap()` with system variables, user inputs, and environment variables. For persistence, a `VariableTruncator` enforces size limits and offloads oversized variable data to external storage rather than blowing up database row size limits.
4. **Execution recording**: `WorkflowRun` (per-execution record: status `running`/`succeeded`/`failed`/`stopped`, `total_tokens`, `total_steps`, `elapsed_time`) and `WorkflowNodeExecutionModel` (per-node record: inputs/outputs, offloaded to `WorkflowNodeExecutionOffload` + `FileService` if oversized) persist granular execution history and metrics separately from the blueprint.

**Node factory / dependency injection**: `DifyNodeFactory` bridges the generic graph engine to Dify-specific node implementations — `register_nodes()` dynamically imports node modules to register with the base `Node` class, `resolve_workflow_node_class` finds the right class for a `NodeType` + version (defaulting to `latest` if a pinned version isn't found — a versioned-node-type system that lets node implementations evolve without breaking already-published workflows pinned to an older version), and the factory injects Dify-specific runtime objects (e.g. `DifyPreparedLLM` for LLM nodes, `DifyToolFileManager` for tool nodes) into node instances at construction time.

**Layered execution ("Agenton" layer system)**: the `GraphEngine`/Agenton compositor supports composable "layers" wrapped around core execution — `LLMQuotaLayer` (rate/quota limiting) and `ObservabilityLayer` (tracing) are named examples. This is effectively middleware for the graph engine, conceptually similar to LangChain's agent middleware or LangGraph's wrap hooks, but implemented as graph-engine-level layers rather than per-node hooks.

### Agent Node in workflows (the tool-calling primitive inside a visual graph)
`AgentNode` is a specialized workflow node that delegates execution to a pluggable "agent strategy" rather than performing a fixed task — the bridge between the deterministic graph engine and iterative agentic reasoning. Execution flow inside `_run`:
1. Validate the `DifyRunContext`.
2. **Strategy resolution**: `AgentStrategyResolver.resolve()` looks up the concrete strategy implementation by `agent_strategy_provider_name` + `agent_strategy_name` (could be a plugin-provided strategy or a built-in one).
3. **Parameter building**: `AgentRuntimeSupport` resolves workflow `VariablePool` values into concrete parameters the strategy expects, plus prepares credentials.
4. **Invocation**: calls `strategy.invoke()`.
5. **Stream transformation**: `AgentMessageTransformer` converts the agent's raw message stream into `NodeEventBase` objects the graph engine understands — this is how an agent's internal "thought → tool call → observation" loop gets surfaced as ordinary node-execution events to the rest of the workflow and to the client's SSE stream.

Output variables exposed by an Agent Node: `text` (primary response), `usage` (tokens), `files`, `json` (structured data), plus dynamic outputs defined by the specific strategy's own output schema — so different agent strategies can expose different structured outputs beyond the fixed base set.

### Agent V2: Roster + Composer + "Soul" configuration
A newer layer on top of Agent Nodes. Two binding modes for how a workflow's Agent Node gets its agent definition (`WorkflowAgentNodeBinding`):
- `ROSTER_AGENT`: binds to a **shared** agent definition in a tenant-wide roster (reusable across multiple workflows).
- `INLINE_AGENT`: an agent defined specifically for just this one node (not shared).

`AgentComposerService` manages these bindings during design/editing; on publish, `WorkflowAgentPublishService` **freezes the binding and projects it into the node's static data** — meaning a published workflow's agent config is a point-in-time snapshot, decoupled from subsequent edits to the underlying roster agent, unless it's explicitly republished. Publishing validates the Agent Node graph via `ComposerConfigValidator` (checks the "Agent Soul" config and "Node Job" config are valid) and validates slash-mention syntax in prompts (references to humans/tools) via `composer_validator`.

An "Agent Soul Configuration" (`AgentSoulConfig`) is the actual identity definition — model, prompts, tools, knowledge base — for an Agent V2 agent, distinct from the workflow-node-level wiring.

### Dify Agent Runtime (standalone FastAPI service, "Agenton" framework)
A separate service (not the main Flask `api`) purpose-built for high-performance agentic execution, decoupled so it can scale independently and use async Python patterns for long-running reasoning loops. Built on Pydantic AI for structured/type-safe tool calling.

Request flow: Dify Console/App → POST `/run` (payload = `AgentSoulConfig` + input) → FastAPI entrypoint → Agenton compositor creates a session snapshot → **reasoning loop**: request completion with tools → LLM responds with tool call or final thought → if tool call, execute (via sandbox for code, or the Dify tool engine for other tools) → repeat → final response streamed back as SSE or returned blocking. Response mode note: **Agent applications are currently SSE-only (streaming)** — blocking mode for agent apps isn't yet supported the way it is for simpler completion/workflow apps, reflecting that agent reasoning loops are inherently more naturally expressed as a stream of intermediate events than a single blocking return.

The `LayerNode`/`LayerProvider` abstraction (Agenton's core composability primitive) is the same layering concept used by the main `GraphEngine` — `AgentNode` (workflow-embedded) is described as one concrete example of a `LayerNode`. This suggests Agenton is (or is becoming) the shared execution substrate underneath both the classic workflow graph engine and the new standalone Agent Runtime, rather than two entirely separate systems.

### Human Input Node and pause/resume (workflow-level HITL)
A dedicated mechanism for pausing a workflow mid-execution to wait on a human-submitted form, architecturally analogous to LangGraph's `interrupt()` but built around explicit event types and a dedicated persistence layer rather than a re-execution-from-top model:

1. `HumanInputNode._run()` yields a `GraphRunPausedEvent` containing one or more `HumanInputRequired` pause reasons (`form_id`, `node_id`, `node_title`, `inputs`, `actions`).
2. `GraphEngine` catches the pause event; `PauseStatePersistenceLayer` serializes the entire `GraphRuntimeState` (via its own `dumps()` method) into a `WorkflowResumptionContext`, including the full `VariablePool` and system variables like `workflow_run_id`.
3. `WorkflowExecutionStatus` flips to `PAUSED`; the `WorkflowRun` record is updated.
4. On resume, the app runner fetches the stored `WorkflowResumptionContext` from the repository and re-invokes the engine with the `serialized_graph_runtime_state` — the engine picks back up **from the paused node** rather than replaying the whole graph from the start (a meaningful architectural difference from LangGraph's "re-execute the node function from the top" interrupt semantics).
5. Timeout handling is first-class: `HumanInputForm` tracks an `expiration_time`; if unmet, a `QueueHumanInputFormTimeoutEvent` fires, which the `WorkflowResponseConverter` turns into a `HumanInputFormTimeoutResponse` sent to the client — form-based HITL has an explicit "nobody answered in time" failure mode built in, not just a success path.

`HumanInputFormRecipient` supports multiple delivery/response surfaces (`CONSOLE`, `STANDALONE_WEB_APP`), meaning the same paused-workflow-waiting-on-a-form can be answered from different UI contexts depending on who's expected to respond.

### Tool provider architecture
`ToolProviderType` enum: `BUILT_IN` (hardcoded, filesystem-discovered), `API` (user-defined OpenAPI/Swagger schema, tenant-scoped), `WORKFLOW` (a published workflow exposed as a reusable tool — meaning workflows can call other workflows-as-tools), `PLUGIN` (marketplace-distributed, managed by the plugin daemon), `MCP` (Model Context Protocol server-provided tools), `DATASET_RETRIEVAL` (specialized knowledge-base-query tools with no credential/schema concept of their own — they're generated from dataset metadata). A singleton `ToolManager` dispatches `get_tool_runtime()` calls by provider type to the matching controller (`ApiToolProviderController`, `WorkflowToolProviderController`, etc.), with hardcoded built-in providers cached behind a lock for lazy, thread-safe initialization.

This is notable as a genuinely broad "everything can be a tool" surface: not just external API/plugin tools, but **published workflows themselves are first-class tools** — meaning composition of agentic workflows can be recursive (a workflow with an Agent Node whose strategy calls another published workflow as a tool).

## Key patterns & techniques (transferable)

1. **One Docker image, multiple roles via a `MODE` env var.** Rather than building/maintaining separate images for API server, Celery worker, and Celery beat scheduler, using the same image with a mode flag reduces build/deploy surface area and guarantees version parity across roles that must agree on task schemas.
2. **Strict separation of blueprint (static graph definition) from runtime state (VariablePool/GraphRuntimeState) from execution history (WorkflowRun/NodeExecution records).** Three distinct data models for three distinct concerns — editing a workflow blueprint never touches historical execution records; a running execution's live state is independent of both. This is a robust general pattern for any system that needs versioned definitions, replayable/inspectable state, and durable audit history simultaneously.
3. **Versioned node-type resolution with a `latest` fallback.** Letting node implementations evolve (new `NodeType` versions) while already-published workflows keep resolving to the version they were built against (unless they explicitly want `latest`) is a clean backward-compatibility mechanism for a visual builder where users' saved graphs must keep working across platform upgrades.
4. **Freeze-on-publish for agent bindings.** Snapshotting a shared ("roster") agent's config into the workflow's own node data at publish time — rather than always resolving live — trades flexibility (edits to the roster agent don't retroactively change already-published workflows) for stability and predictability of production behavior, an important distinction for anyone building a "shared component library referenced by many consumers" system.
5. **Explicit timeout-as-a-first-class-event for human-in-the-loop.** Modeling "the human never responded" as its own event type (`QueueHumanInputFormTimeoutEvent`) with its own response type (`HumanInputFormTimeoutResponse`), rather than leaving HITL flows to hang indefinitely or fail ambiguously, is a pattern worth copying in any agent system with a human-approval step.
6. **Resume-from-paused-node rather than replay-from-top.** Persisting the *entire* `GraphRuntimeState` (not just a resume value) means resumption doesn't need to re-execute any node logic that already ran — a different (arguably more expensive-to-implement, but more predictable) tradeoff than LangGraph's cheaper "re-run the function, short-circuit at the interrupt call" approach. Worth knowing both exist as alternative implementations of the same HITL-pause concept.
7. **"Workflows as tools" for recursive composition.** Exposing a published workflow itself as a tool provider type (alongside API/plugin/MCP tools) means agent systems can compose arbitrarily — an agent's tool can itself be a full multi-step workflow, which can itself contain an agent node. This is a powerful, simple composability primitive worth considering for any tool-provider abstraction.
8. **Data offloading for oversized execution artifacts.** Both `VariablePool` persistence and `WorkflowNodeExecutionModel` use a size-threshold-triggered offload to external file storage (rather than failing or truncating silently) — a reusable pattern for any system persisting execution traces where individual values might occasionally be very large (e.g. large LLM outputs, file contents passed between nodes).
9. **Layered/middleware composition at the graph-engine level, not just per-node.** `LLMQuotaLayer`/`ObservabilityLayer` wrap the entire graph engine's execution rather than being bolted onto individual nodes — useful when a cross-cutting concern (rate limiting, tracing) needs visibility across the whole run, not just one node's lifecycle.

## Practical how-tos

- **Choose an app mode**: use Easy UI modes (`chat`/`completion`/`agent-chat`) for simple prompt-driven apps; use `workflow`/`advanced-chat` when you need a visual multi-step graph; use `rag-pipeline` specifically for custom document indexing/retrieval pipelines; use the new `agent` mode (Agent Runtime) for agent-first applications built around a "Soul" configuration.
- **Add a tool-calling agent inside a visual workflow**: drop an Agent Node into the graph, select an agent strategy (built-in or plugin-provided), and either bind it to a shared roster agent or configure it inline for that node only.
- **Add a pause-for-human-approval step in a workflow**: use a Human Input Node with a `FormDefinition`; configure delivery recipients (Console vs. standalone web app) and an expiration time so unanswered forms don't hang the workflow indefinitely.
- **Expose a published workflow as a callable tool for other agents/workflows**: publish it, then reference it via the `WORKFLOW` tool provider type — no separate API wrapper needed.
- **Add a custom tool via OpenAPI spec**: register it as an `API`-type tool provider; Dify derives the tool's schema from the OpenAPI/Swagger document rather than requiring hand-written Python.
- **Debug a workflow run**: inspect `WorkflowRun` for the aggregate status/metrics and `WorkflowNodeExecutionModel` per-node for granular input/output tracing; large payloads will be referenced via `WorkflowNodeExecutionOffload` rather than stored inline.

## Gotchas & caveats

- **Agent applications are currently SSE-streaming-only** — blocking-mode responses aren't fully supported for the agent execution path the way they are for completion/workflow apps; integrations expecting a simple blocking JSON response from an agent app need to handle SSE instead.
- **Published Agent V2 bindings are frozen snapshots** — updating a shared roster agent's definition does not retroactively change workflows that already published against it; a republish is required to pick up the change. This can surprise anyone assuming "shared" means "always in sync."
- **Human Input Node resumption relies on the full `GraphRuntimeState` being persisted and later deserialized correctly** — this is a heavier persistence mechanism than a lightweight resume-value approach; large `VariablePool` contents at pause time all get serialized (subject to the same offload/truncation mechanism used elsewhere).
- **Node type resolution silently falls back to `latest` if a specific pinned version isn't found** — this could mean an older workflow picks up newer (potentially behaviorally different) node logic if the exact version it was built against is no longer registered, rather than failing loudly.
- **The `sandbox` service for code execution is network-restricted via an `ssrf_proxy`** — code-execution nodes in workflows do not have unrestricted network access by default; this is a deliberate security boundary, not a bug, but could surprise someone expecting arbitrary outbound requests from a code node.
- **Vector database is pluggable across 23+ backends but defaults to Weaviate** — deployments relying on the default configuration are implicitly coupled to Weaviate's specific behavior/limits unless explicitly reconfigured.
- **`DATASET_RETRIEVAL` tool provider type has no credential storage of its own** (per the provider comparison table) — it's generated purely from dataset metadata, so its "tool-ness" is more constrained than the other five provider types which all support genuine multi-tenant credentials.

## Wiki pages used

- Introduction to Dify
- System Architecture Overview (partial, via Introduction)
- Application Types and Execution Modes
- Workflow Definition and Execution Model
- Agent Node in Workflows
- Human Input Node and Pause-Resume Mechanism
- Tool Provider Types and Architecture (partial)
- Dify Agent Runtime
- Agenton Framework and Layer Architecture
- Dify Agent Server and Runtime API
