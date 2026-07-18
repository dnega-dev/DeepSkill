---
repo: langchain-ai/langchain
deepwiki: https://deepwiki.com/langchain-ai/langchain
github: https://github.com/langchain-ai/langchain
harvested: 2026-07-09
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`langchain-ai/langchain`](https://deepwiki.com/langchain-ai/langchain) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# langchain-ai/langchain — Distilled Knowledge

## What it is

LangChain is a modular framework for building agents and LLM-powered applications through composability. It implements a foundational abstraction layer (the `Runnable` interface) so developers can chain LLMs, tools, retrievers, and prompts together while keeping model interoperability and rapid prototyping. As of the wiki snapshot, the repo is organized as a monorepo:

- `langchain-core` (v1.4.8) — base abstractions: `Runnable`, `BaseMessage`, `BaseTool`. Depends on `pydantic>=2.7.4`, `langsmith>=0.3.45`, `tenacity>=8.1.0`.
- `langchain` (v1.3.11) — the modern "agent engineering platform" package; integrates with `langgraph` for orchestration.
- `langchain-classic` (v1.0.8) — legacy chains/SQLAlchemy support for backward compatibility.
- `langchain-text-splitters` (v1.1.2) — document chunking utilities.
- Partner packages (`langchain-openai`, `langchain-anthropic`, `langchain-ollama`, etc.) implement the core base classes (`BaseChatModel`, `Embeddings`, `BaseLLM`) per-provider.

`langchain` depends directly on `langgraph>=1.2.5` for agent orchestration and on `langsmith` for tracing/observability. A separate higher-level package, "Deep Agents," is built on top of LangChain for planning and subagent capability (mentioned but not detailed in this wiki snapshot).

## Architecture (how it's built, key components)

### The Runnable interface / LCEL
Every composable component (chat models, tools, prompts, retrievers, output parsers) subclasses `Runnable(ABC, Generic[Input, Output])` (`libs/core/langchain_core/runnables/base.py`). The **only abstract method is `invoke`**; every other method (`ainvoke`, `batch`, `abatch`, `stream`, `astream`, `astream_log`, `astream_events`, `batch_as_completed`) has a default implementation that delegates to `invoke` (e.g. `ainvoke` defaults to running `invoke` in a thread-pool executor; `batch` defaults to a thread pool with `max_concurrency` respected via `RunnableConfig`).

Most concrete classes subclass `RunnableSerializable` (adds JSON dump/load) rather than `Runnable` directly. Every runnable exposes Pydantic-derived `input_schema`/`output_schema`, config-aware variants (`get_input_schema(config)`), and `get_graph(config)` for visualization.

LCEL (LangChain Expression Language) is the pipe-operator (`|`) composition syntax:
- `chain = prompt | model | parser` calls `__or__`, producing a `RunnableSequence` (stores `first`, `middle: list`, `last` separately; streaming flows step-to-step via `transform`/`atransform`).
- `coerce_to_runnable()` auto-wraps plain callables into `RunnableLambda` and plain dicts into `RunnableParallel`.
- `RunnableParallel` (aka `RunnableMap`) fans one input to multiple runnables concurrently, collecting a dict of results. A bare dict literal in a `|` chain is auto-coerced to this.
- `RunnableBranch` implements if/elif/else routing: a list of `(predicate, runnable)` pairs plus a mandatory trailing default runnable (no predicate).
- `RunnableLambda` wraps any Python callable; when the function has no type annotations, LangChain inspects the function's AST to infer an input schema from dict-key accesses.
- `RunnablePassthrough` returns input unchanged; `.assign(**kwargs)` merges newly computed keys into a dict input while preserving existing keys — the standard way to build up a working dict of intermediate values through a chain (e.g. attaching retrieved `context` alongside the original `question`).
- `RunnableWithFallbacks` (`.with_fallbacks(fallbacks, exceptions_to_handle=..., exception_key=...)`) tries fallback runnables in order on exception.
- `RunnableWithMessageHistory` wraps an inner runnable with automatic `BaseChatMessageHistory` load/insert/exit-listener logic — internal pipeline is `load_history → insert_history (assign) → check_sync_or_async → inner runnable (with on_end listener that persists history)`.

`RunnableConfig` (TypedDict) is the config object threaded through every call: `tags`, `metadata`, `callbacks`, `run_name`, `max_concurrency`, `recursion_limit` (default 25), `configurable` (dict for runtime field overrides), `run_id`. `ensure_config()` normalizes partial configs by merging with a context-propagated `ContextVar` (`var_child_runnable_config`) so nested runnable calls inherit tags/metadata/callbacks/configurable without explicit passing. `merge_configs()` concatenates+dedupes tags, shallow-merges metadata/configurable (later wins), and takes the last non-default `recursion_limit`.

Two streaming/event APIs sit on top of the base interface: `astream_log` yields `RunLogPatch` JSON-patch objects that reconstruct a `RunLog`; `astream_events` yields typed `StreamEvent` dicts with component-specific event names (`on_chain_start/stream/end`, `on_chat_model_start/stream/end`, `on_tool_start/end`).

### Tools
`BaseTool` extends `RunnableSerializable`, so every tool gets `invoke`/`ainvoke`/`batch`/`stream` for free. Two concrete subclasses: `Tool` (single string-arg callables) and `StructuredTool` (multi-arg, full schema inference via `StructuredTool.from_function(func, args_schema=..., infer_schema=True, parse_docstring=True)`).

Key `BaseTool` fields: `name`, `description` (both required — this is literally what the model sees to decide when/why to call the tool), `args_schema`, `return_direct` (if `True`, the agent loop stops immediately after this tool runs instead of looping back to the model), `handle_tool_error`, `handle_validation_error`, `response_format` (`"content"` vs `"content_and_artifact"` — lets a tool return a rich object alongside the string shown to the model).

The `@tool` decorator (`langchain_core.tools.convert.tool`) converts a plain function (or Runnable) into a `BaseTool`. Schema inference pipeline: function → `create_schema_from_function()` (uses Pydantic's `validate_arguments`) → `_create_subset_model()` filters out internal args (`run_manager`, `callbacks`) and injected args → clean `args_schema`.

**Injected arguments** are populated by the framework at runtime and hidden from the LLM's tool schema: `Annotated[str, InjectedToolCallId()]` auto-populates the tool_call's own ID (useful for tools that need to emit a `Command` or correlate side effects back to the specific call). `InjectedToolArg` more generally marks any parameter as hidden from the schema (e.g. injecting `RunnableConfig`).

Error handling: raise `ToolException` inside `_run` for a "recoverable" error; `handle_tool_error` (bool/str/callable) controls whether it propagates, returns a fixed string, or is transformed by a callback. Same pattern exists for `handle_validation_error` on Pydantic `ValidationError`.

`convert_to_openai_function` / `convert_to_openai_tool` in `utils/function_calling.py` normalize Pydantic models, callables, TypedDicts, and `BaseTool` instances into provider function-calling schemas, stripping `title` fields to save tokens.

### Agent system (`create_agent` + middleware)
`create_agent()` (`libs/langchain_v1/langchain/agents/factory.py`) builds agents as a LangGraph `CompiledStateGraph`. This is the central integration point between LangChain and LangGraph in the modern (v1) package.

**Agent execution loop** (as a state machine):
```
START → before_agent hooks (sequential) → before_model hooks (sequential)
  → wrap_model_call handlers (nested, inner-first) → model invocation
  → after_model hooks (reverse sequential) → [has tool_calls?]
      yes → wrap_tool_call handlers (per call, nested) → tool execution → back to before_model
      no  → after_agent hooks (reverse sequential) → END
```

`AgentState` (TypedDict) carries: `messages: Annotated[list[AnyMessage], add_messages]` (the reducer that appends rather than replaces), `jump_to: JumpTo | None` (internal control-flow override — `"tools"`, `"model"`, `"end"`), `structured_response: ResponseT`.

**Middleware hook taxonomy** (`AgentMiddleware` base class):
| Hook | Order | Can jump_to | Use case |
|---|---|---|---|
| `before_agent` | sequential, first→last | yes | state init |
| `before_model` | sequential | yes | input transform, limits |
| `wrap_model_call` | nested composition (like middleware in a web framework — call chain then call next) | no | retry, fallback, caching |
| `after_model` | reverse sequential, last→first | yes | output processing, HITL |
| `wrap_tool_call` | nested, per-call | no | tool retry/validation |
| `after_agent` | reverse sequential | yes | finalization |

Routing after model/tools checks `jump_to` first (highest priority), then falls back to default logic (tool_calls present → "tools" node; `return_direct=True` on the executed tool → END).

Built-in middleware (each wraps one hook):
- `SummarizationMiddleware` (`before_model`): summarizes older history once a token/message/fraction trigger fires; uses `trim_messages` + `RemoveMessage` to prune, keeps a configurable `keep` amount.
- `HumanInTheLoopMiddleware` (`after_model`): calls `interrupt()` from `langgraph.types` to pause and wait for a human decision — `approve`, `edit` (change tool name/args), `reject` (with feedback), or `respond` (answer on the tool's behalf, skipping execution).
- `ModelFallbackMiddleware` / `ModelRetryMiddleware` (`wrap_model_call`): sequential alternate-model retry / exponential-backoff retry.
- `ToolRetryMiddleware` (`wrap_tool_call`): per-tool retry with `max_retries` (default 2), `backoff_factor` (default 2.0), `initial_delay` (default 1.0).
- `LLMToolSelectorMiddleware` (`wrap_model_call`): filters the tool list via an LLM call before the main model call — an efficiency pattern for agents with many tools.
- `ContextEditingMiddleware` (`wrap_model_call`): `ClearToolUsesEdit` strategy prunes old tool results to manage context window; supports `exclude_tools` so structured-output tool calls aren't pruned.
- `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware`: track counts at thread level (persisted) and run level (`UntrackedValue`, reset each run); configurable `exit_behavior` of `'continue'` (block with error message), `'error'` (raise), or `'end'` (inject a closing `ToolMessage`+`AIMessage` and stop).
- `PIIMiddleware` (`before_model`+`after_model`): regex/Luhn-based detectors (`detect_email`, `detect_credit_card`, `detect_ip`, `detect_mac_address`, `detect_url`) redact matches in streaming content via a `_PIIStreamTransformer` with a 128-char sliding buffer to catch patterns straddling delta chunk boundaries.
- `TodoListMiddleware`: injects a `write_todos` tool plus planning instructions into the system prompt for multi-step task tracking.
- `ShellToolMiddleware`: persistent shell session tool backed by `subprocess.Popen`, using a UUID `_DONE_MARKER_PREFIX` to detect command completion in the persistent stream, with pluggable `HostExecutionPolicy`/`DockerExecutionPolicy`/`CodexSandboxExecutionPolicy`.
- `FilesystemFileSearchMiddleware`: `glob_search` + `grep_search` (ripgrep with Python fallback) tools, enforcing path containment (`_is_within_root`) against directory traversal.
- `LLMToolEmulator`: replaces real tool execution with an LLM-generated plausible response — for testing agent flows without live side effects.

Middleware composes via nested wrapping: multiple `wrap_model_call` handlers form a call chain (`M1 → M2 → M3 → base_handler → M3 → M2 → M1`), analogous to onion-style middleware in web frameworks. `wrap_tool_call` composes the same way but independently per tool call.

`ModelRequest`/`ModelResponse` dataclasses carry model invocation parameters through middleware; `ModelRequest.override()` gives an immutable-update pattern — middleware should not mutate requests in place.

### Structured output
Three strategies selectable via `response_format=`:
- `AutoStrategy` (default): checks model-profile metadata for native structured-output support; if known-supported (e.g. GPT-4o, Claude 3.5 Sonnet) uses `ProviderStrategy`, else falls back to `ToolStrategy`. A hardcoded `FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT` list covers cases where profile data is missing.
- `ToolStrategy`: wraps the schema as a forced-choice artificial tool (`tool_choice` set to that tool's name); captures the resulting tool call, parses args, and injects a synthetic `ToolMessage` to keep the conversation history consistent.
- `ProviderStrategy`: delegates to the model's native `with_structured_output(method="json_schema")`; supports a `strict` flag for OpenAI's strict schema enforcement.

Error hierarchy: `StructuredOutputError` (base) → `MultipleStructuredOutputsError` (model returned >1 tool call when one structured response was expected) and `StructuredOutputValidationError` (schema validation failure) — the latter can be fed back to the model as a retry prompt via `STRUCTURED_OUTPUT_ERROR_TEMPLATE`.

## Key patterns & techniques (transferable)

1. **Single-abstract-method interface for composability.** Making `invoke` the only required method (everything else has a default built on it) is what lets *any* component — model, tool, prompt, retriever — be treated uniformly and piped together. If you're designing a plugin/component system, minimize the required surface area and give free default implementations for async/batch/stream on top of the one sync primitive.
2. **Context-propagating config via ContextVar.** `RunnableConfig` propagation through `var_child_runnable_config` means nested calls automatically inherit tags/metadata/callbacks without every layer of your code threading a config object explicitly. Useful pattern for cross-cutting concerns (tracing, tenant IDs, feature flags) in deeply nested execution.
3. **Middleware as onion/nested composition vs. sequential hooks — pick per use case.** LangChain deliberately uses two different composition models: sequential hooks (`before_model`, `after_model`) for hooks that need to see/modify state in order, and nested "wrap" hooks (`wrap_model_call`, `wrap_tool_call`) for hooks that need to intercept a single call transactionally (retry, fallback, caching) — the wrap pattern lets a middleware retry the *entire* inner chain, not just its own step.
4. **`jump_to` as an escape-hatch control-flow field, checked with strict priority.** Rather than only exposing normal edge routing, the agent state includes a `jump_to` field any hook can set, and the router checks it *before* default logic. This is a clean way to let arbitrary middleware short-circuit a graph without every middleware needing to know about every other middleware's routing needs.
5. **Injected arguments hide plumbing from the LLM's tool schema.** `InjectedToolArg`/`InjectedToolCallId`/`RunnableConfig`-by-param-name-matching let you give a tool function access to runtime context (call IDs, configs, callbacks) without polluting the JSON schema the model sees — keeps tool descriptions minimal and prevents the model from hallucinating values for fields it shouldn't set.
6. **`RunnablePassthrough.assign` for building up a working dict through a pipeline.** Rather than threading a growing struct manually, `.assign(key=lambda x: ...)` merges computed values into the existing dict input — a clean way to accumulate context (e.g., retrieved docs, summaries) alongside the original input through a multi-step chain.
7. **AutoStrategy pattern for provider-capability detection.** Rather than forcing callers to know which models support native structured output vs. tool-forcing, detect capability from a model-profile registry with a hardcoded fallback list — graceful degradation without caller-side branching.
8. **Sliding-buffer streaming transforms for pattern detection across chunks.** `PIIMiddleware`'s `_PIIStreamTransformer` keeps a 128-char buffer specifically to catch regex matches (like emails) that straddle two separate streamed content deltas — a general technique for any streaming-content processor that needs cross-chunk pattern matching.

## Practical how-tos

- **Build a chain**: `chain = prompt | model | parser` (or `.pipe(model, parser)`, or explicit `RunnableSequence(prompt, model, parser)`). A dict literal inside a chain auto-becomes `RunnableParallel`.
- **Fan out to N sub-chains and combine**: `RunnableParallel(summary=summarize_chain, keywords=keyword_chain)`, invoke once, get `{"summary": ..., "keywords": ...}`.
- **Conditional routing in a chain**: `RunnableBranch((predicate1, chain1), (predicate2, chain2), default_chain)` — default must be last and unconditioned.
- **Define a tool**: decorate a function with `@tool` (bare) or `@tool(response_format="content_and_artifact")` if you need to return both a string for the model and a richer object for your own app logic.
- **Create an agent**:
```python
from langchain.agents import create_agent
from langchain_core.tools import tool

@tool
def get_weather(location: str) -> str:
    """Get the weather for a location."""
    return f"Sunny in {location}"

agent = create_agent(model="openai:gpt-4o", tools=[get_weather], system_prompt="You are a helpful assistant.")
```
- **Get typed output from an agent**: pass `response_format=MyPydanticModel` to `create_agent` (defaults to `AutoStrategy`), or force a strategy: `response_format=ProviderStrategy(MyModel, strict=True)`.
- **Add retry/fallback to a model call**: `model.with_fallbacks([backup_model], exceptions_to_handle=(RateLimitError,))`, or attach `ModelRetryMiddleware`/`ModelFallbackMiddleware` at the agent level for the whole loop.
- **Cap runaway agent loops**: attach `ModelCallLimitMiddleware`/`ToolCallLimitMiddleware` with `exit_behavior="end"` or `"error"`.
- **Human approval before a sensitive tool runs**: attach `HumanInTheLoopMiddleware`; it calls `interrupt()` and needs a LangGraph checkpointer configured to actually pause/resume across a real interruption boundary.

## Gotchas & caveats

- `ainvoke`'s default implementation just runs sync `invoke` in a thread pool — a custom `Runnable` that overrides only `invoke` does not get "real" async concurrency; override `ainvoke` explicitly for true async I/O.
- `wrap_model_call`/`wrap_tool_call` middleware **cannot** set `jump_to` — only the sequential hooks (`before_agent`, `before_model`, `after_model`, `after_agent`) can redirect control flow. Don't try to short-circuit the graph from inside a wrap handler.
- `ContextEditingMiddleware`'s tool-result pruning can break structured output if it also clears the tool call that produced the structured response — must explicitly `exclude_tools` for the structured-output tool.
- Tool `args` schema strips injected parameters (`RunnableConfig`, `InjectedToolArg`) automatically — don't expect the model to ever populate those; they're framework-provided at call time.
- `ToolStrategy` for structured output only works reliably on models that support tool/function calling in the first place; it is the fallback specifically for models without native structured-output APIs.
- `AutoStrategy`'s capability detection depends on model-profile metadata; for unlisted/newer models it falls back to a static list (`FALLBACK_MODELS_WITH_STRUCTURED_OUTPUT`) that can lag behind actual provider capabilities.
- The monorepo has three overlapping "langchain" packages (`langchain`, `langchain-classic`, `langchain_v1`) — the wiki explicitly separates `langchain` (v1.3.11, modern agent platform) from `langchain-classic` (v1.0.8, legacy chains/SQLAlchemy) — mixing patterns from tutorials targeting different versions will not compose cleanly.

## Wiki pages used

- LangChain Overview
- Package Ecosystem
- Core Architecture
- Runnable Interface and LCEL
- Tools and Function Calling
- Agent System
- Agent Creation and Middleware Architecture
- Middleware Implementations
- Structured Output and Response Formats
- Configuration and Runtime Control (partial)
