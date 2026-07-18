---
repo: anthropics/anthropic-sdk-python
deepwiki: https://deepwiki.com/anthropics/anthropic-sdk-python
github: https://github.com/anthropics/anthropic-sdk-python
harvested: 2026-07-09
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`anthropics/anthropic-sdk-python`](https://deepwiki.com/anthropics/anthropic-sdk-python) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# anthropics/anthropic-sdk-python — Distilled Knowledge

## What it is

The official Python client library for the Claude API. Provides type-safe synchronous (`Anthropic`)
and asynchronous (`AsyncAnthropic`) clients, SSE streaming, automatic retries, cloud-provider
integrations (Google Vertex AI, AWS Bedrock, Azure/Anthropic Foundry), and a growing beta surface
that includes Managed Agents, MCP integration, and an agent toolset
(bash/read/write/edit/glob/grep). Supports Python 3.9-3.14 and is compatible with both Pydantic v1
and v2. This is the lowest-level, most mechanical repo in the batch — it documents an HTTP client
library, not an agent framework — but its beta "Managed Agents" and "Tool Runners" subsystems are
directly relevant to the agent-skills ecosystem theme, since they represent Anthropic's own
SDK-level primitives for building persistent, tool-using agents.

## Architecture (how it's built, key components)

**Layered architecture**: Public API surface (`Anthropic`/`AsyncAnthropic` clients,
`messages`/`completions`/`models`/`beta` resources) → Core infrastructure (`BaseClient`,
`APIResponse`/`AsyncAPIResponse`, `BaseModel`, `_utils` type guards/transforms) → Streaming system
(`Stream`/`AsyncStream` at the raw SSE level, `MessageStream`/`BetaMessageStream` at the
parsed-event level) → Type definitions (`types` package for stable API, `types.beta` for
experimental).

**Client hierarchy**: `BaseClient[_HttpxClientT, _DefaultStreamT]` →
`SyncAPIClient`/`AsyncAPIClient` → `Anthropic`/`AsyncAnthropic` (primary), plus `AnthropicVertex`
(OAuth2 via `google-auth`), `AnthropicBedrock` (AWS SigV4 signing), `AnthropicFoundry` (bearer
token). All cloud-provider clients share the same `BaseClient` request/retry/response machinery —
only authentication and base URL resolution differ, which is why adding a new cloud backend to this
SDK is a relatively contained change (subclass + auth plumbing, not a parallel HTTP stack).

**Resource organization**: stable v1 API (`client.messages`, `client.completions` [deprecated],
`client.models`, `client.messages.batches`) alongside an entirely separate `client.beta` namespace
(`beta.messages`, `beta.agents`, `beta.sessions`, `beta.files`, `beta.deployments`, `beta.vaults`,
`beta.environments`). The beta namespace is a full parallel type/resource tree (e.g. `BetaToolParam`
vs `ToolParam`, `BetaMessageStream` vs `MessageStream`) rather than optional fields bolted onto the
stable types — this is a deliberate strategy for evolving experimental features without ever
breaking the stable API's type contracts.

**Dual input/output type system**: request parameters are `TypedDict` schemas (e.g.
`MessageCreateParams`), validated via `maybe_transform()` before the HTTP call; responses are parsed
into Pydantic `BaseModel` subclasses via two modes — `construct_type()` (lenient, for
development/forward-compatibility with fields the SDK doesn't yet know about) and `validate_type()`
(strict, for production, controlled by a `_strict_response_validation` flag). This TypedDict-in /
Pydantic-out split lets input validation stay cheap and flexible (dicts) while output gets full
runtime type safety (Pydantic).

**Retry logic**: `_should_retry()` checks an explicit `x-should-retry` response header first (server
can force retry/no-retry regardless of status code), then falls back to status-code rules: retry on
408 (timeout), 409 (conflict), 429 (rate limit), and any 5xx. Backoff formula: `nb_retries =
min(max_retries - remaining_retries, 1000)`; `base_delay = min(INITIAL_RETRY_DELAY * 2^nb_retries,
MAX_RETRY_DELAY)` with `INITIAL_RETRY_DELAY=0.5s`, `MAX_RETRY_DELAY=8s`, default `max_retries=2`;
final `timeout = base_delay * jitter` where `jitter = 1 - 0.25 * random()` (i.e. uniformly 0.75-1.0x
of the base delay) — standard exponential-backoff-with-jitter, but the server-override header is a
notable design choice: it lets the API itself dictate retry behavior on a per-response basis rather
than trusting the client's static rules alone.

**Timeout hierarchy**: request-level `FinalRequestOptions.timeout` overrides client-level
`client.timeout`, which overrides the SDK default of 600 seconds (10 minutes) — a three-tier
fallback (most specific wins, falls back to progressively broader defaults) that's a clean, reusable
pattern for any configurable-timeout system.

**Response processing pipeline**: check `status_code < 400` → if error, `_make_status_error()`
raises a typed `APIStatusError` subclass → if success, `_process_response_data()` runs either
`validate_type()` or `construct_type()` depending on the strictness flag, producing the final typed
object.

## Key patterns & techniques (the transferable knowledge)

**Managed Agents — a full persistent-agent orchestration primitive built into the SDK/API.** This is
the most novel subsystem for this batch's theme, currently behind the `managed-agents-2026-04-01`
beta header. Core entity model:
- **Agent** (`BetaManagedAgentsAgent`): the template/identity, versioned — updating an agent requires
  passing the current `version` integer, which the server uses as an optimistic-concurrency check to
  reject concurrent overwrites (a standard optimistic-locking pattern applied to agent config
  mutation).
- **Session**: an active execution instance that can contain multiple **threads**, with a `multiagent`
  configuration letting a primary thread orchestrate work by spawning sub-threads — i.e.
  hierarchical/multi-agent execution is a first-class session concept, not something the caller has to
  hand-roll on top of independent API calls.
- **Deployment**: schedules or event-triggers for an agent, including cron-expression + timezone
  scheduling — turning an agent from "something you call" into "something that runs on its own."
- **Environment** + **self-hosted worker pattern**: for cases needing local resource access or higher
  security than Anthropic's managed execution, a user-run `EnvironmentWorker` polls for
  `BetaSelfHostedWork` items, heartbeats the lease while executing a tool (keeping the work item alive
  across a long-running local action), executes the local action, and posts the `tool_result` back via
  `POST /v1/beta/sessions/{id}/threads/{id}/events`. This bridges Anthropic's managed orchestration
  plane with a user's own infrastructure without giving up the orchestration/scheduling/versioning
  benefits of the managed layer.
- **Vault**: secure storage for environment variables/credentials, scoped to agents — separating
  secret management from agent config so secrets aren't embedded in agent definitions or version
  history.
- **Event-driven communication via webhooks**: session events (`SessionCreated`, `SessionRunning`,
  `SessionRequiresAction`), agent events (`AgentCreated`, `AgentUpdated`), and vault events
  (`VaultCredentialCreated`, `VaultCredentialRefreshFailed`) are all independently subscribable — a
  reusable pattern for exposing a stateful async system's lifecycle to external consumers without
  polling.
- **Advisor tool** (`advisor_20260301`): lets a model call *other models* for advice mid-task, with
  its own caching and `max_tokens` budget controls — an explicit SDK-level primitive for model-calls-
  model delegation (distinct from tool-use, which is model-calls-function).

**Three-tier tool taxonomy**: Server Tools (executed by Anthropic's own infrastructure —
`bash_20250124`, `code_execution_*`, `web_search_*`, `web_fetch_*`, `text_editor_*`,
`memory_20250818`, `computer_use_*`), Client Tools (your application executes the logic; Claude only
supplies `tool_use` parameters — `BaseFunctionTool`/`@beta_tool`-decorated functions), MCP Tools
(delegated to an external Model Context Protocol server via the `mcp_servers` parameter). This
taxonomy — server-executed vs. client-executed vs. protocol-delegated — is a clean mental model for
classifying any tool in an agent framework by *where the execution actually happens*, independent of
how it's invoked.

**Date-versioned server tools as an API evolution strategy.** Every server tool is versioned by
release date (`web_search_20250305`, `web_search_20260209`, `web_search_20260318`;
`code_execution_20250522` through `20260521`; `computer_use_20241022` through `20251124`), each with
its own distinct `TypedDict` class. This lets Anthropic evolve a tool's capabilities and parameters
over time without breaking any existing integration pinned to an older version string — callers
explicitly opt into new tool versions rather than being silently migrated. Generalizable to any API
surface where behavior needs to evolve without a hard breaking-change cutover.

**`@beta_tool` decorator: docstring/type-hints → JSON schema, automatically.** `BaseFunctionTool`
inspects a plain Python function's signature, type hints, and docstring via Pydantic v2
introspection to generate the tool's `input_schema` without the developer hand-writing JSON Schema.
`ToolError` is a specialized exception a tool implementation can raise to return structured error
content (including images, not just text) back to the model *without crashing the runner loop* —
i.e. tool failure becomes a normal, typed conversational turn (`is_error: True` on the tool result)
rather than an unhandled exception that aborts the whole run.

**Tool runner as a self-driving conversation loop.** `BetaToolRunner`/`BetaStreamingToolRunner` (and
async variants) implement: call the API → if response contains `tool_use` blocks, look up each tool
by name in `self._tools_by_name`, execute via `run_runnable_tool`, wrap the result as a
`BetaToolResultBlockParam` → append both the assistant's tool-use message and the tool results to
conversation history → call the API again → repeat until Claude returns a message with no tool
calls, or `max_iterations` is hit. This is the canonical "agent loop" shape, provided as a reusable
SDK primitive rather than something every caller has to reimplement — a strong argument for any SDK
wrapping a tool-using LLM to ship this loop itself rather than leaving it as example code.

**Session-scoped tool runner as the Managed-Agents-specific variant of the same loop.**
`SessionToolRunner` attaches to a Managed Agents session's event stream (rather than driving direct
`messages.create` calls) and dispatches `agent.tool_use`/`agent.custom_tool_use` events to local
tool implementations, posting `user.tool_result` back to the session. `EnvironmentWorker` wraps this
runner specifically to add work-item heartbeating and forced-stop handling for the
self-hosted-worker case. The existence of two structurally parallel runners (message-loop-driven vs.
session-event-driven) for the same underlying "execute tools locally, report results" concept is
worth noting: when a system gains a second execution mode (synchronous request/response vs.
long-lived async session), the tool-execution abstraction often needs its own parallel
implementation rather than a single one serving both.

**Built-in agent toolset as a scoped, sandboxed file/shell surface.** `beta_agent_toolset_20260401`
bundles `bash` (persistent `/bin/bash` subprocess), `read` (with `view_range` and size limits),
`write` (scoped to a `workdir`), `edit` (`old_string`→`new_string` exact replacement, echoing the
same exact-match editing pattern seen across the batch's other repos), `glob`, `grep`. Path safety
is centralized in `AgentToolContext`/`resolve_path`: it follows symlinks and verifies the
*canonical* resolved path stays within the `workdir` boundary unless an explicit
`unrestricted_paths` policy opts out — i.e. symlink-based directory-traversal escapes are checked
against the fully resolved path, not the literal string path, which is the correct way to implement
a workdir jail (a literal-string check alone is trivially bypassed by a symlink pointing outside the
sandbox).

**Standardized memory-tool command set for cross-session persistence.** `BetaAbstractMemoryTool`
exposes a fixed command vocabulary (`view`, `create`, `str_replace`, `insert`, `delete`, `rename`)
dispatched through a single `execute()` entry point, with `BetaLocalFilesystemMemoryTool` as a
concrete filesystem-backed implementation. Standardizing on a small, fixed command set (rather than
a bespoke API per memory backend) means alternate backends (e.g. a database-backed memory tool) can
be swapped in behind the same interface.

**Dual-path streaming architecture — mutable snapshot + immutable event stream, simultaneously.**
Every SSE event is processed through two parallel pipelines from the same source: the **accumulator
path** (`accumulate_event()`) mutates a single growing `ParsedMessage` snapshot object in place
(handles `message_start` initialization, `content_block_start` appends, per-block deltas for
text/tool-inputs/citations, and `message_delta` for `stop_reason`/`usage` updates), while the
**builder path** (`build_events()`) emits immutable typed events (`TextEvent`, `InputJsonEvent`,
`ThinkingEvent`, `CitationEvent`, terminal `ParsedMessageStopEvent`) for the application to iterate
over. This gives callers both a "current full state" view (`stream.current_message_snapshot`) and an
"each delta as it arrives" view (iterating `stream`) without forcing a choice between the two access
patterns — a reusable design for any streaming API needing both incremental and cumulative views of
the same growing object.

**Partial-JSON tool-input streaming via a hidden accumulation buffer.** Tool inputs arrive as
fragments of a JSON string across multiple deltas; the SDK maintains a hidden `__json_buf` per
tool-use block and re-parses it on every delta using the `jiter` library's partial-parsing mode,
exposing a progressively more-complete Python dict via `InputJsonEvent.snapshot` even before the
JSON is fully valid. A beta mode (`fine-grained-tool-streaming-2025-05-14`, `trailing-strings`)
further allows incomplete/truncated string fields to appear in the snapshot rather than waiting for
a field to fully close. This lets a UI render a tool call's arguments incrementally (e.g. showing a
search query as it's typed out) rather than only after the entire JSON object is complete.

**Stable-vs-beta as a systematically duplicated type/class tree, not a feature-flag branch.** Every
layer that beta needs to extend gets its own parallel class:
`ParsedMessageStreamEvent`→`ParsedBetaMessageStreamEvent`, `MessageStream`→`BetaMessageStream`,
`ToolUseBlock`→`BetaToolUseBlock`/`BetaMCPToolUseBlock`, `ToolParam`→`BetaToolParam`. Beta-only
events (`compaction`, `signature`) simply don't exist on the stable event union at all. This is a
deliberate cost/benefit trade (more duplicated code, but zero risk of a beta-only field silently
becoming load-bearing in the stable type contract) worth considering whenever a library needs to
ship experimental extensions to a widely-depended-on type hierarchy.

## Practical how-tos (concrete workflows)

**Basic sync streaming:**
```python
with client.messages.stream(
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
    model="claude-3-5-sonnet-latest",
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```
The context manager defers the actual API request until `__enter__`, guaranteeing the underlying
connection is closed even on error or partial consumption.

**Consuming partial tool-call JSON during streaming:**
```python
with client.messages.stream(...) as stream:
    for event in stream:
        if event.type == "input_json":
            print(event.snapshot)  # partially parsed dict, updates each delta
```

**Authentication resolution order** (for the primary `Anthropic`/`AsyncAnthropic` clients): API key
(`ANTHROPIC_API_KEY`) → auth token (`ANTHROPIC_AUTH_TOKEN`) → profile (`ANTHROPIC_PROFILE`) →
workload identity federation env vars. Config defaults: `timeout=600s`, `max_retries=2`, `base_url`
overridable for proxying or local testing against a mock server.

**Writing a client-side tool with automatic schema generation:**
```python
from anthropic.lib.tools import beta_tool

@beta_tool
def sum(left: int, right: int) -> str:
    """Add two numbers together."""
    return str(left + right)
```
Pass `tools=[sum]` to a `BetaToolRunner`; the runner drives the full call/execute/respond loop
automatically until Claude stops requesting tool calls.

**Bridging an MCP server's tools into a local tool runner:** use `mcp_tool`/`async_mcp_tool` from
`anthropic.lib.tools.mcp` to convert an MCP SDK tool object into a `BetaFunctionTool`, and
`mcp_message`/`mcp_resource_to_content` to convert MCP-native prompt messages and resources into the
SDK's `BetaMessageParam`/content-block shapes.

**Setting up a self-hosted Managed Agents worker:** poll for `BetaSelfHostedWork` items via `ant
worker poll`, set `ANTHROPIC_WORK_ID`/`ANTHROPIC_SESSION_ID` env vars for the dispatched work item,
heartbeat periodically while a local tool executes, POST the `tool_result` to the session/thread
events endpoint, and mark the work item "stopped" on completion.

## Gotchas & caveats

- The `Completions` API is explicitly deprecated in this SDK version — new integrations should use
  `Messages`.
- Managed Agents, the agent toolset, and MCP-related types are all under beta headers (e.g. `managed-
  agents-2026-04-01`) and subject to change; treat exact field/endpoint names here as a snapshot, not
  a stable contract.
- The stable-vs-beta type duplication means code written against `ToolParam`/`MessageStream` will NOT
  automatically pick up beta-only capabilities (`compaction`, `signature` events,
  `BetaMCPToolUseBlock`) — you must explicitly switch to the `beta.*` namespace and its parallel types
  to access them.
- The `x-should-retry` response header takes precedence over the client's own status-code-based retry
  heuristic — if you're mocking or testing against a fake server, forgetting to either omit or
  correctly set this header can produce retry behavior that doesn't match the documented status-code
  table.
- Workdir sandboxing in the agent toolset depends on canonical-path resolution catching symlink
  escapes; any custom tool implementation that reimplements path safety without following symlinks to
  their real target reintroduces the exact vulnerability this design avoids.
- `construct_type()` (lenient) vs `validate_type()` (strict) response parsing is controlled by a
  `_strict_response_validation` flag — code that assumes strict validation is always on (e.g. relying
  on validation errors for malformed responses) may behave differently if strictness is toggled off,
  since `construct_type()` will not raise on unexpected/malformed fields.
- Tool `ToolError` swallows exceptions into structured `is_error: True` content specifically so the
  model can react to a failure conversationally — but this means a bug inside a tool implementation
  that isn't intentionally raising `ToolError` (e.g. an unhandled `KeyError`) will still propagate as
  a real Python exception and abort the runner loop, rather than being gracefully reported to the
  model. Tools intended to fail gracefully must explicitly raise `ToolError`, not just let arbitrary
  exceptions bubble up.

## Wiki pages used

Overview, Client Architecture (Base Client and HTTP Layer, Synchronous and Asynchronous Clients —
retry logic, timeout hierarchy, response processing sections), API Resources (Managed Agents — read
in full), Streaming (main architecture page, read in full), Tool System (main page, Tool Definitions
and Parameters, Tool Runners and MCP Integration — read in full). Not read in depth: Installation
and Setup, Quick Start, Cloud Provider Integrations detail, Authentication and Configuration detail,
Request Lifecycle and Error Handling detail, Messages API / Beta Messages API / Completions API
(Deprecated) / Models API / Message Batches / Beta Features and Capabilities detail pages, Stream
Managers and Event Processing / Structured Output Parsing in Streams / Tool Input Streaming and
Partial JSON detail pages, Data Models and Type System section (BaseModel and Type Construction,
Type Validation and Serialization, Pydantic V1/V2 Compatibility, Request and Response Types),
Utilities and Helper Functions section, Response Processing section (Response Classes and Parsing,
Exception Types and Error Handling, Stream and SSE Decoding, Pagination and Response Wrappers),
Usage Patterns and Examples, Development and Contributing section, Glossary.
