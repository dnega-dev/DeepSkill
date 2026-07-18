---
repo: langchain-ai/langgraph
deepwiki: https://deepwiki.com/langchain-ai/langgraph
github: https://github.com/langchain-ai/langgraph
harvested: 2026-07-09
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`langchain-ai/langgraph`](https://deepwiki.com/langchain-ai/langgraph) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# langchain-ai/langgraph — Distilled Knowledge

## What it is

LangGraph is a low-level orchestration framework for building stateful, multi-actor applications with LLMs. Unlike high-level abstractions, it provides infrastructure without abstracting prompts or architecture, giving developers full control over application logic. It's designed specifically for the unique challenges of long-running agentic workflows: persistence, cycle management, and human intervention.

Three core capabilities, each with a specific implementation:
- **Durable execution**: agents persist through failures and resume from exact state — `BaseCheckpointSaver` persists `Checkpoint` objects (channel values + versions) after each step.
- **Human-in-the-loop**: inspect/modify agent state at any point — an interrupt system that allows state modification via `update_state()` and resumption.
- **Comprehensive memory**: short-term working memory (channel system, step-level) plus long-term persistent storage (`BaseStore`, cross-thread).

The execution model is a **Bulk Synchronous Parallel (BSP)** engine inspired by Google's Pregel paper. Distributed as a monorepo: `langgraph` (core, depends on `langgraph-checkpoint` + `langchain-core`), `langgraph-checkpoint` (base checkpoint interfaces + `JsonPlusSerializer`), `langgraph-prebuilt` (ReAct agent, `ToolNode`), `langgraph-sdk` (Python client for LangGraph API servers), `langgraph-cli` (`dev`/`build`/`up` commands), plus separate `langgraph-checkpoint-postgres`/`-sqlite` packages. Requires Python `>=3.10`; core deps include `langchain-core>=1.4.7,<2`, `langgraph-checkpoint>=4.1.0,<5.0.0`, `pydantic>=2.7.4`.

## Architecture (how it's built, key components)

### Graph definition: StateGraph
`StateGraph(state_schema, context_schema=None, *, input_schema=None, output_schema=None)` is a builder that holds internal registries (`nodes`, `edges`, `branches`, `channels`, `managed`, `waiting_edges`) before compilation. Lifecycle: define → `add_node()` → `add_edge()`/`add_conditional_edges()` → `compile(checkpointer=, store=, interrupt_before=, interrupt_after=)` → get a `CompiledStateGraph` (which **is-a** `Pregel` instance) → `invoke()`/`stream()`/`astream()`.

Node input schema inference: if `add_node` isn't given an explicit `input_schema`, LangGraph inspects the node function's type hints on its first parameter; falls back to the graph's full `state_schema` if no hints exist.

Compilation validates: all edge-referenced nodes exist, reducer signatures are valid, and managed channels aren't exposed through I/O schemas — raises `ValueError` on failure.

### Functional API: @task / @entrypoint
An alternative to the declarative builder — write native Python control flow (loops, conditionals) while still getting Pregel's persistence/parallelization. Both decorators compile down to the *same* `Pregel` engine underneath.
- `@task`: wraps a function into a `_TaskFunction`; calling it schedules concurrent execution within the current Pregel superstep and immediately returns a `SyncAsyncFuture[T]` — call `.result()` to block. Parameters: `name`, `retry_policy`, `cache_policy`, `timeout`. Tasks can only be called from inside an `@entrypoint` or a `StateGraph` node.
- `@entrypoint`: transforms a function into a `Pregel` instance directly (no explicit `.compile()`). Parameters: `checkpointer`, `store`, `context_schema`. Special injectable parameters by name: `config` (RunnableConfig), `previous` (the return value from the prior invocation — requires a checkpointer), `runtime` (bundles `context`, `store`, `stream_writer`).
- `entrypoint.final(value=..., save=...)` decouples what's *returned* to the caller (`value`) from what's *persisted* for the next invocation as `previous` (`save`) — useful when you want to expose a different shape than you checkpoint.
- Channel layout under the hood: Input is an `EphemeralValue`, `PREVIOUS` is a `LastValue` (persists across threads), Output is a `LastValue`.
- `RunControl.request_drain()` inside an entrypoint requests a graceful stop that still lets already-scheduled tasks finish before exiting.

### Pregel execution engine (BSP model)
Every step (superstep) has three phases:
1. **Plan** — `prepare_next_tasks()` examines which channels were updated in the previous step and, via a `trigger_to_nodes` map, determines which nodes are triggered; builds `PregelExecutableTask` objects (`id`, `name`, `input`, `proc`, `writes: deque`).
2. **Execute** — `PregelRunner.tick()` (sync) / `.atick()` (async) runs all selected tasks concurrently. Tasks **cannot see each other's writes until the next step** — this is the core BSP isolation guarantee.
3. **Update** — `apply_writes()` commits all task writes to channels atomically once the whole batch completes; channel versions are bumped via `get_next_version()` only when `BaseChannel.update()` returns `True`.

`SyncPregelLoop`/`AsyncPregelLoop` (subclasses of `PregelLoop`) drive the state machine: track `step`, `channels`, `tasks`, and the current `checkpoint`. Checkpoint durability modes: `sync` (block until checkpoint saved) vs `async` (continue execution while it saves in background).

`Runtime`/`ExecutionInfo` give nodes access to run-scoped metadata (`store`, `checkpoint_id`, `task_id`) — accessed by adding a `runtime: Runtime` parameter to a node function.

### State and channels
Every key in the state schema maps to a `BaseChannel` instance. `BaseChannel` interface: `update(values)` (apply a batch of updates, returns whether version should bump), `get()`, `checkpoint()` (serializable snapshot), `from_checkpoint(checkpoint)` (restore).

| Schema annotation | Channel type | Behavior |
|---|---|---|
| plain type, no annotation | `LastValue` | Replaces value; **raises `InvalidUpdateError` if multiple nodes write to it in the same superstep** |
| `Annotated[T, reducer_fn]` | `BinaryOperatorAggregate` | Applies the reducer (e.g. `operator.add`) to merge concurrent updates |
| `Annotated[list, add_messages]` | `DeltaChannel` (Beta) | Specialized for message history; stores a sentinel + replays ancestor writes through the reducer instead of snapshotting full state every checkpoint (writes periodic `_DeltaSnapshot` blobs per `snapshot_frequency`) |
| n/a — declared separately | `Topic` | Multi-writer pub/sub; accumulates into a list; `accumulate=False` (default) empties after each step, `accumulate=True` persists |
| n/a | `EphemeralValue` | Cleared after consumption/superstep end; optional `guard` blocks multiple updates in one step |
| n/a | `UntrackedValue` | Returns `MISSING` on `checkpoint()` — value lives at runtime but is never persisted |

The `Overwrite(value=...)` primitive lets a node bypass a `BinaryOperatorAggregate`'s reducer entirely and force-replace the channel value. Only one `Overwrite` value is allowed per superstep. Recognized in three forms: the dataclass, `{"__overwrite__": value}`, or the JSON-serialized `{"type": "__overwrite__", "value": ...}`.

### Control flow primitives
- `START`/`END` are interned sentinel strings (`"__start__"`/`"__end__"`), never executed as real nodes.
- `add_edge(src, dst)`: static/unconditional. Multiple static edges from the same source run their targets in the **same superstep** (parallel) — if they write the same unreducered key, that's an `InvalidUpdateError`.
- `add_conditional_edges(source, path_fn, path_map=None)`: `path_fn(state)` can return a node-name string, a list of strings (fan-out), a `Send`, a list of `Send`, or a mix. `path_map` remaps symbolic return values to real node names (also produces labeled edges in visualizations).
- `Send(node, arg)`: schedules a node with **custom per-invocation state** different from the graph's ambient state — the mechanism for the map step of map-reduce fan-out. Multiple `Send`s from one edge function run concurrently next superstep.
- `Command(goto=, update=, resume=, graph=)`: lets a node simultaneously decide routing (`goto`) and apply a state update (`update`), replacing the need for a separate conditional edge when the node itself knows where to go next. `resume` supplies a value for a pending `interrupt()` when `Command` is passed as graph *input*. `graph=Command.PARENT` lets a subgraph node route/update the **parent** graph — internally raises a `ParentCommand` exception the parent's loop catches.

### Nested graphs / subgraphs
A `CompiledStateGraph` can be passed directly as a node in another `StateGraph.add_node()` — the parent treats it as an opaque node and calls its `invoke`/`ainvoke`, and the child runs its own full Pregel loop.

- **State projection, not full passthrough**: parent → child passes only the state keys that exist in the child's `input_schema`; child → parent writes the child's `output_schema` keys back **using the parent's own reducers** — meaning a parent and child can legitimately use different reducer semantics for a same-named key.
- **Checkpoint namespacing**: each subgraph invocation gets its own `checkpoint_ns`, formatted `{node_name}:{task_id}`, and nested subgraphs chain with `|` (`NS_SEP`): `{parent_node}:{parent_task_id}|{child_node}:{child_task_id}`. All levels share the same `thread_id`.
- Subgraph `checkpointer=` param on compile: `None` (default) inherits the parent's saver, distinguished only by namespace — this is what lets a "stateless" subgraph still support `interrupt()`/resume via the parent's thread; `True` = independent persistent checkpointing; `False` = disable even if parent has one; or pass an explicit `BaseCheckpointSaver`.
- Interrupts inside a subgraph **bubble up to the parent** transparently — the parent doesn't need special-case logic; it just sees the interrupt in its own `StateSnapshot.interrupts`.
- `get_graph(xray=True)` recursively expands nested Pregel instances into a unified visualization.

### Human-in-the-loop / interrupts
Two mechanisms, both requiring a checkpointer:

| Type | Config | Trigger | Resume |
|---|---|---|---|
| Static | `interrupt_before=[...]` / `interrupt_after=[...]` on `compile()` (or `"*"` for all nodes) | Before/after a named node executes | `invoke(None, config)` |
| Dynamic | `interrupt(value)` call inside a node's own code | Anywhere in node logic | `Command(resume=value)` |

Dynamic `interrupt()` mechanics: first call inside a task raises `GraphInterrupt` (with a deterministic `id` hashed from checkpoint namespace + a counter — stable across retries) and the interrupt is stored under a special reserved `INTERRUPT` write-index/channel in the checkpoint's pending writes. **On resume, the node re-executes from the beginning of its function body**; the `interrupt()` call now finds the matching resume value already staged in a config-scratchpad and returns it instead of raising. This means any code before the `interrupt()` call in a node re-runs on every resume — it should be idempotent or cheap.

`StateSnapshot` fields exposed via `get_state()`: `values`, `next` (tuple of pending nodes), `tasks`, `interrupts` (tuple of active dynamic interrupts — empty for static interrupts, since those pause at a graph boundary rather than raising an object).

### Persistence: checkpointing
`Checkpoint` TypedDict: `v` (format version), `id` (UUID v6, monotonically increasing), `ts` (ISO8601), `channel_values`, `channel_versions`, `versions_seen` (node → channel-versions map), `updated_channels`. `CheckpointTuple` wraps a checkpoint with its `config`, `metadata`, `parent_config`, and `pending_writes`. `CheckpointMetadata.source` is one of `"input" | "loop" | "update" | "fork"` — `"fork"` is what time-travel/state-forking produces.

`BaseCheckpointSaver` interface: `get_tuple`/`list` (reads), `put`/`put_writes` (writes), plus `get_delta_channel_history` for `DeltaChannel` reconstruction (walks the ancestor checkpoint chain). Implementations: `InMemorySaver` (dev/test only, `defaultdict`-backed), `SqliteSaver`/`AsyncSqliteSaver` (local dev, thread/asyncio `Lock`-serialized writes), `PostgresSaver`/`AsyncPostgresSaver` (production; supports connection pooling and psycopg Pipeline batching; 4-table schema: `checkpoints`, `checkpoint_blobs` for binary channel data, `checkpoint_writes` for intermediate writes, `checkpoint_migrations`). `ShallowPostgresSaver` (only latest checkpoint, no time-travel history) is **deprecated as of 2.0.20** in favor of `PostgresSaver` + `durability='exit'`.

Special write-index markers used in `put_writes`: `ERROR=-1`, `SCHEDULED=-2`, `INTERRUPT=-3`, `RESUME=-4`.

### Persistence: long-term memory (Store)
`BaseStore` is a separate abstraction from checkpointing — cross-thread, cross-conversation persistent key-value memory with hierarchical namespaces (tuples of strings, cannot be empty, and individual segments can't contain `.` in Postgres/SQLite backends). Core ops: `get`/`put`/`delete`/`search`/`list_namespaces`, all with sync+async+batch variants. `Item` = `{namespace, key, value, created_at, updated_at}`; `SearchItem` adds a `score`.

Supports **vector search** (via `IndexConfig`: `dims`, `embed`, `fields` — JSON paths to embed; Postgres backend uses `pgvector` with HNSW/IVFFlat indices, SQLite uses `sqlite-vec` with cosine-only) and **TTL** (`default_ttl`, `refresh_on_read`, `sweep_interval_minutes` for a background deletion sweeper). `AsyncBatchedBaseStore` batches concurrent store calls through an internal `asyncio.Queue` + background task for efficiency, exposing sync compatibility via `asyncio.run_coroutine_threadsafe`.

### Error handling and retries
`RetryPolicy` (attachable per-node via `add_node(..., retry_policy=)` or per-task via `@task(retry_policy=)`): `initial_interval=0.5s`, `backoff_factor=2.0`, `max_interval=128.0s`, `max_attempts=3`, `jitter=True`, `retry_on` (exception filter). Delay formula: `min(max_interval, initial_interval * backoff_factor**(attempts-1))` plus optional `random.uniform(0,1)` jitter. Multiple policies can be supplied as a sequence — the **first one whose `retry_on` matches** is used.

Default retry behavior: retries transient errors (`ConnectionError`, 5xx from httpx/requests); explicitly does NOT retry programming errors (`ValueError`, `TypeError`, `SyntaxError`). Control-flow signals (`GraphBubbleUp`, `GraphInterrupt`, `ParentCommand`) are **never** retried regardless of policy — critical, since retrying an interrupt would break HITL semantics.

Before each retry, `task.writes.clear()` is called — partial writes from a failed attempt never leak into the retried attempt's state. `runtime.execution_info.node_attempt` exposes the 1-indexed attempt number to node code. On final failure (all retries exhausted), the error is written to a reserved `ERROR` channel and stored in `pending_writes` if a checkpointer exists — **the checkpoint version is not advanced**, so state stays exactly where the failed superstep began. A node can be designated as another node's `error_handler` via `add_node(..., error_handler="handler_node_name")`, receiving error context through a parameter typed `NodeError`.

### Prebuilt: ReAct agent (`create_react_agent`)
Lives in `langgraph-prebuilt`, built on `StateGraph`. Signature includes `model`, `tools`, `prompt`, `response_format`, `pre_model_hook`, `post_model_hook`, `state_schema`, `context_schema`, `checkpointer`, `store`, `interrupt_before/after`, `version: "v1"|"v2"`.

Default `AgentState`: `messages: Annotated[Sequence[BaseMessage], add_messages]` + `remaining_steps: NotRequired[RemainingSteps]` (a managed channel tracking loop budget to prevent infinite loops — checked via `_are_more_steps_needed`, which returns "need more steps" once remaining steps drop below the threshold needed to safely call another tool or return-direct tool).

Graph shape: `START → [pre_model_hook?] → agent → [post_model_hook?] → should_continue (routes on tool_calls) → tools (ToolNode) → agent (loop)` or `→ [generate_structured_response?] → END`.

Model can be static (`ChatOpenAI(...)` instance or `"openai:gpt-4"` string via `init_chat_model`) or **dynamic** — a callable `(state, runtime) -> BaseChatModel` resolved per-turn, letting you switch models based on runtime context (e.g. escalate to a stronger model under certain conditions). Tools are auto-bound via `.bind_tools()` unless already bound.

`prompt` parameter accepts `None` (raw messages), `str`/`SystemMessage` (prepended), or a `Callable`/`Runnable` that receives state (and optionally `config`/`store` by parameter-name injection) and returns the full model input — this is how you inject store-backed user memory into the system prompt per-turn.

`_validate_chat_history` enforces that every `AIMessage.tool_calls` entry has a matching `ToolMessage` before calling the model again — protects against malformed state causing provider API errors.

### Prebuilt: ToolNode
`ToolNode(tools, name="tools", handle_tool_errors=..., messages_key="messages", wrap_tool_call=, awrap_tool_call=)` extends `RunnableCallable`. Handles parallel tool execution (via `ThreadPoolExecutor` or `asyncio.gather`), dependency injection, and configurable error handling.

Accepts three input shapes and detects which one it got: full graph-state dict, a bare message list, or a raw list of `ToolCall` dicts — output is reformatted to match whichever shape came in.

**Dependency injection** into tool parameters via annotations, resolved once at `ToolNode.__init__` time (cached per tool in `_injected_args`) and applied per-call:
- `InjectedState` — inject the whole graph state or one field, e.g. `state: Annotated[dict, InjectedState]`.
- `InjectedStore` — inject the `BaseStore`.
- `ToolRuntime` (dataclass bundling `state`, `tool_call_id`, `config`, `context`, `store`, `stream_writer`) — inject everything at once.

`NotRequired` state fields missing from a `TypedDict` state are injected as `None` rather than raising `KeyError`.

Tool execution error handling: exceptions raised inside a tool are caught; `GraphBubbleUp`-family exceptions (interrupts, parent commands) are re-raised untouched, everything else goes through `_handle_tool_error` per the `handle_tool_errors` config and becomes a `ToolMessage(status="error")`. Tools may also return a `Command` object directly — these bypass the normal `ToolMessage` wrapping and are passed straight through, letting a tool control graph routing/state the same way a node's `Command` return does.

`tools_condition` is the standard router: `"tools"` if the last message has tool_calls, else `END`.

## Key patterns & techniques (transferable)

1. **BSP execution as the concurrency safety model.** Isolating writes so tasks in the same superstep can't see each other's results until the next step is what makes parallel node execution deterministic and debuggable — no race conditions from partial reads. If you're building a parallel task orchestrator, "commit-then-reveal" per round is a robust pattern.
2. **Reducers as the answer to "what happens when N writers hit the same key."** Rather than forcing every state field to be single-writer, LangGraph lets you attach a merge function (`operator.add`, `add_messages`, or custom) per field via type annotation. This is a clean, declarative way to handle concurrent contributions to shared state without ad hoc locking.
3. **`Overwrite` as an escape hatch from a reducer.** Sometimes you need "replace, not merge" even on a field that normally accumulates — having an explicit typed sentinel for that (rather than a magic value or a separate un-reduced field) keeps the API surface small.
4. **`Command` unifying "what changed" and "where next."** Instead of separating state mutation (return value) from routing (conditional edge function), letting a node return both together (when it's the node itself that knows the answer) removes an entire class of split logic and keeps decision-making colocated with the code that has the context.
5. **Checkpoint namespacing by path, not by flat ID.** The `parent:task_id|child:task_id` namespace scheme means subgraph state history composes naturally under a single `thread_id" — you get free hierarchical debugging/inspection without inventing a new ID scheme per nesting level.
6. **Interrupt-as-exception + re-execution-on-resume.** Rather than a complex continuation/coroutine-suspend mechanism, LangGraph re-runs the node function from the top on resume and short-circuits the specific `interrupt()` call site via a scratchpad lookup keyed by a deterministic ID. Simple to implement, but has a real gotcha (see below) — anyone copying this pattern needs to warn users about side effects before the interrupt point.
7. **Retry policy chains matched by predicate, not by priority number.** Supplying a sequence of `RetryPolicy` and picking the first whose `retry_on` matches the actual exception is a clean way to have different backoff behavior for different failure classes on the same node, without a giant if/elif in application code.
8. **Injected arguments resolved once, applied many times.** `ToolNode` analyzes each tool's signature for injection annotations exactly once at construction and caches the result — avoids re-doing reflection/schema-walking on every single tool call, which matters when an agent calls the same tool hundreds of times in a session.
9. **Dynamic model selection as a first-class pattern.** Accepting a callable `(state, runtime) -> model` instead of only a static model instance lets you build cost/quality-tiered agents (escalate to a bigger model conditionally) without forking the whole graph.
10. **Separate short-term (channels/checkpoint) vs long-term (Store) memory as distinct systems.** Conflating "state for this run" with "durable cross-session memory" is a common design mistake; LangGraph's explicit split (checkpointer = this thread's execution history, store = arbitrary cross-thread key-value with optional vector search) is a reusable memory architecture for any agent system.

## Practical how-tos

- **Basic graph**:
```python
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

class State(TypedDict):
    text: str

def node_a(state: State) -> dict:
    return {"text": state["text"] + "a"}

graph = StateGraph(State)
graph.add_node("node_a", node_a)
graph.add_edge(START, "node_a")
compiled = graph.compile(checkpointer=my_saver)
```
- **Fan-out / map-reduce**: return a list of `Send(node_name, custom_state)` from a conditional-edge function; each becomes an independent parallel task feeding into a common downstream reduce node.
- **Node controls its own routing + state update**: `return Command(goto="b", update={"foo": "bar"})` from inside a node instead of wiring a separate conditional edge.
- **Pause for human approval**: call `interrupt("Please approve X")` inside a node; resume later with `graph.invoke(Command(resume="approved"), config)`. Requires a checkpointer.
- **Embed a subgraph**: compile a child `StateGraph`, then `parent_graph.add_node("subgraph_node", compiled_child)` — treat it exactly like any other node.
- **Cross-graph command from inside a subgraph**: `return Command(graph=Command.PARENT, update={"parent_key": "v"}, goto="some_parent_node")`.
- **Persistent cross-session memory injected into the system prompt**:
```python
def prompt_with_store(state, config, *, store):
    user_id = config["configurable"]["user_id"]
    user_data = store.get(("memories", user_id), "user_name")
    return [SystemMessage(user_data.value["data"])] + state["messages"]

agent = create_react_agent(model, tools, prompt=prompt_with_store, store=InMemoryStore())
```
- **Give a tool access to graph state/store without exposing it to the LLM's schema**:
```python
from langgraph.prebuilt import InjectedState, InjectedStore
from typing import Annotated

def my_tool(query: str, state: Annotated[dict, InjectedState], store: Annotated[BaseStore, InjectedStore()]):
    ...
```
- **Attach differentiated retry behavior**: `add_node("call_api", fn, retry_policy=[RetryPolicy(retry_on=RateLimitError, max_attempts=5), RetryPolicy(retry_on=ConnectionError, max_attempts=3)])`.
- **Choose production checkpointer**: `PostgresSaver` for production (with connection pooling), `SqliteSaver` for local dev, `InMemorySaver` only for tests.

## Gotchas & caveats

- **Two nodes writing to the same `LastValue` channel in one superstep raises `InvalidUpdateError`.** If you expect concurrent writers to a field, you must annotate it with a reducer (`BinaryOperatorAggregate`) or use a `Topic` channel — plain fields are implicitly single-writer-per-step.
- **Code before an `interrupt()` call re-runs on every resume.** Since the node function re-executes from the top when resumed, any side effects (API calls, appends to external systems) placed before the `interrupt()` call will fire again on each resume unless you make them idempotent or move them after the interrupt point.
- **`GraphBubbleUp`/`GraphInterrupt`/`ParentCommand` are never retried, by design** — don't rely on `RetryPolicy` to somehow "retry through" an interrupt; that's not what it's for, and it would break HITL semantics if it did.
- **Static interrupts produce an empty `interrupts` tuple in `StateSnapshot`** (unlike dynamic `interrupt()` calls) — code that inspects `snapshot.interrupts` to detect "is this graph paused" will miss static interrupts; check `snapshot.next` instead for those.
- **Subgraph checkpointer defaulting to `None` inherits the parent's saver** — if you actually want subgraph state isolated/independent, you must explicitly pass `checkpointer=True` or a specific saver at subgraph compile time.
- **`DeltaChannel` is explicitly Beta** — it optimizes message-history storage by replaying writes instead of snapshotting, which is efficient but is a newer, less-battle-tested code path than `LastValue`/`BinaryOperatorAggregate`.
- **`ShallowPostgresSaver` is deprecated (as of 2.0.20, removal in 3.0.0)** — new code should use `PostgresSaver` with `durability='exit'` instead of the shallow-history variant.
- **Namespace components can't contain `.` in Postgres/SQLite store backends** — a seemingly cosmetic restriction that will surface as a runtime error if you build namespaces from arbitrary user strings (e.g. email addresses) without sanitizing.
- **Multiple static edges from one source run in the same superstep, not sequentially** — a common naming-based assumption ("edges run in order") is wrong; if you need sequencing, chain the edges explicitly rather than fanning out from one node and expecting order.
- **`remaining_steps` prevents infinite ReAct loops but silently truncates** — when the budget runs out mid-tool-calling, the agent returns a canned "need more steps" message rather than an exception; don't mistake this for a genuine successful completion when auditing agent runs.

## Wiki pages used

- Overview
- StateGraph API
- Functional API (@task and @entrypoint)
- Pregel Execution Engine
- State Management and Channels
- Control Flow Primitives
- Graph Composition and Nested Graphs
- Human-in-the-Loop and Interrupts
- Error Handling and Retry Policies (partial)
- Checkpointing Architecture
- Checkpoint Implementations
- Store System
- ReAct Agent (create_react_agent)
- ToolNode and Tool Execution
