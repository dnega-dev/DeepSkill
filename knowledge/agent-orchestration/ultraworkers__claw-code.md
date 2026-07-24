---
repo: ultraworkers/claw-code
deepwiki: https://deepwiki.com/ultraworkers/claw-code
github: https://github.com/ultraworkers/claw-code
harvested: 2026-07-13
cluster: agent-orchestration
---

> Distilled from the DeepWiki wiki for [`ultraworkers/claw-code`](https://deepwiki.com/ultraworkers/claw-code) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# ultraworkers/claw-code — DeepWiki Knowledge

## What it is

`claw-code` is a local-first coding-agent harness, originally inspired by Claude Code's architectural
patterns but rebuilt independently, with a dual-track architecture:
1. A **production Rust implementation** (`rust/`) — a Cargo workspace producing the `claw` CLI binary,
   with `unsafe_code = "forbid"` enforced across all crates. Provides an interactive REPL, slash
   commands, a multi-provider API client (Anthropic + OpenAI-compatible endpoints, including local
   servers like Ollama/vLLM/llama.cpp), MCP integration, a plugin/hooks system, and — the most
   distinctive layer — a full "control plane" for **machine-orchestrated multi-agent worker
   lifecycles**: explicit worker boot state machines, lane events, a policy engine, a "green contract"
   for merge-readiness, approval tokens, task packets/registries, and automated recovery recipes.
2. A **Python porting workspace** (`src/`) used as a "clean-room" reference/verification layer to map
   the original TypeScript-like system's surface area before/alongside implementing it in Rust; it's
   also used for ongoing parity auditing (`PARITY.md`).

This is best understood as an attempt to build the infrastructure needed to run many autonomous
coding-agent instances ("workers") in parallel against a codebase with strong reliability guarantees
(no proceeding to work before the environment is verified ready, automatic detection/recovery from
common failure modes, machine-readable event streams for external orchestration, and policy-gated
merge/escalation decisions) rather than a single interactive assistant.

## Architecture

**Crate graph** (Rust workspace): `rusty-claude-cli` (binary `claw`, REPL + `prompt`/`init`
subcommands) depends on `runtime` (central engine: `TaskRegistry`, `PermissionEnforcer`,
`LspClient`), `api` (provider-agnostic client for Anthropic/OpenAI-compatible endpoints), `tools`
(bash, file ops, etc.; wires `TaskRegistry` into tool dispatch), `commands` (slash commands),
`plugins` (hooks/extensions), and `compat-harness`. A `mock-anthropic-service` crate implements a
deterministic subset of the Anthropic `/v1/messages` API for reproducible test harnesses.

**Workspace-aware configuration**: project memory files discovered in priority order `CLAUDE.md` →
`CLAW.md` → `AGENTS.md`; `.claw.json` (shared project settings, e.g. default permission mode like
`acceptEdits`); `.claw/settings.json` (project config) and `.claw/settings.local.json`
(machine-specific overrides, gitignored); `.claw/sessions/` (serialized conversation history, also
gitignored). `claw init` runs `initialize_repo`, which detects the stack (`RepoDetection`: languages,
frameworks, e.g. `package_json`, `rust_workspace`, `typescript` markers) and generates a tailored
`CLAUDE.md`, tracking each artifact's outcome via an `InitStatus` enum (`Created`, `Updated`,
`Partial`, `Deferred`, `Skipped`).

**Auth**: `ANTHROPIC_API_KEY` (for `sk-ant-*` keys → `x-api-key` header) and
`ANTHROPIC_AUTH_TOKEN` (for OAuth/proxy bearer tokens → `Authorization: Bearer` header) are
explicitly *not* interchangeable — using the wrong one sends the wrong header type. `/doctor` runs a
first-run diagnostic covering auth and environment.

**Worker Boot state machine** (`WorkerStatus`): `Spawning → TrustRequired |
ToolPermissionRequired → ReadyForPrompt → Running → Finished | Failed`. This exists specifically
so a machine orchestrator never delivers a prompt to a worker before its environment is verified
ready — `TrustRequired` fires on cues like "trust the files in this folder"; resolution modes are
`WorkerTrustResolution::AutoAllowlisted` or `ManualApproval`.

**Prompt-misdelivery detection**: a named failure mode where a task prompt lands in a raw bash shell
instead of the agent's actual input buffer. The system tracks `WorkerPromptTarget` (`Shell`,
`WrongTarget`, `WrongTask`) to detect this and has a dedicated `RedirectPromptToAgent` recovery step.
If boot fails without clear logs, a `StartupEvidenceBundle` is collected (`last_lifecycle_state`,
`pane_command`, `transport_healthy`, `mcp_healthy`), and a `StartupFailureClassification` categorizes
the root cause (e.g. `PromptAcceptanceTimeout`, `WorkerCrashed`).

**Lane events** (`LaneEventName`): machine-readable signals for external monitors —
`lane.started`, `lane.ready`, `lane.green`/`lane.red` (validation status), `lane.finished`/
`lane.failed`, `branch.stale_against_main`. Failures are classified via `LaneFailureClass`:
`PromptDelivery`, `TrustGate`, `BranchDivergence`, `McpHandshake`, `WorkspaceMismatch`.

**SessionStore workspace isolation**: sessions are namespaced by a fingerprint derived from the
canonical workspace root path, stored at `<data_dir>/sessions/<workspace_hash>/`, specifically to
prevent collisions between parallel worker instances operating on different checkouts of the same or
different repos.

**Recovery Recipes** — seven canonical `FailureScenario`s, each mapped to a `RecoveryRecipe` of
ordered `RecoveryStep`s, with a hard **"one automatic attempt before escalation"** policy tracked per
scenario via `RecoveryContext`:

| Scenario | Recovery step |
|---|---|
| `TrustPromptUnresolved` | `AcceptTrustPrompt` |
| `PromptMisdelivery` | `RedirectPromptToAgent` |
| `StaleBranch` | `RebaseBranch` |
| `CompileRedCrossCrate` | `CleanBuild` |
| `McpHandshakeFailure` | `RetryMcpHandshake` |
| `PartialPluginStartup` | `RestartPlugin` |
| `ProviderFailure` | (transport/provider layer errors) |

Exhausted automation → `EscalateToHuman`. All recovery steps that involve shell execution
(`CleanBuild`, `RebaseBranch`) go through the same bash-validation pipeline as normal tool calls.

**StaleBase divergence guard**: compares worktree `HEAD` against an expected base commit (from a
`--base-commit` flag or a `.claw-base` file) via `git rev-parse`; result is `BaseCommitState::
Matches | Diverged | NotAGitRepo`. Exists to stop an agent from silently operating against a codebase
version that has drifted from what the orchestrator believes it's working on.

**Bash command validation/permission gating**: commands are classified into `CommandIntent`
categories (`ReadOnly`, `Write`, `Destructive`, `Network`, `ProcessManagement`,
`PackageManagement`, `SystemAdmin`). In `PermissionMode::ReadOnly`, `WRITE_COMMANDS` (e.g. `rm`,
`cp`, `mv`) and `STATE_MODIFYING_COMMANDS` (e.g. `apt`, `cargo`, `docker`) are blocked outright.
Known-destructive patterns (`rm -rf /`, fork bombs) are flagged `Warn` or `Block`.

**Policy Engine, Green Contract, Approval Tokens** — a rules-based layer that decides whether a lane
can merge, needs recovery, or must escalate:
- `PolicyRule` = condition + action + priority. `PolicyCondition` variants include `GreenAt{level}`,
  `StaleBranch`, `ApprovalTokenPresent`, plus logical `And`/`Or` composition. `PolicyAction` variants
  include `MergeToDev`, `RecoverOnce`, `RequireApprovalToken`, `Escalate`. `PolicyEngine::evaluate`
  walks rules against a `LaneContext`, collecting matched actions (prioritized) plus an audit trail
  of `PolicyDecisionEvent`s.
- **Green Contract** defines a `GreenLevel` hierarchy a lane must satisfy to progress:
  `TargetedTests → Package → Workspace → MergeReady` (the last includes freshness + recovery-context
  requirements). Evidence is proven via `GreenEvidence`: `TestCommandProvenance` (exact command +
  exit code run), `KnownFlake` tracking (ignorable unless `block_known_flakes` is set),
  `base_branch_fresh` boolean. `GreenContract::evaluate_evidence` compares evidence to requirements
  and produces a `GreenEvidenceOutcome`.
- **Approval Tokens** are machine-readable, auditable exceptions to policy blocks (not freeform text
  approvals). Lifecycle: `Pending → Granted → Consumed | Expired | Revoked`. Scoped via
  `ApprovalScope` (limits validity to specific policies/actions/repos/branches). A **delegation
  chain** (`ApprovalDelegationHop`) records every actor/session that handled the token for full
  traceability from original approver to final executor. An `ApprovalTokenLedger` manages
  insert/verify/consume with replay and scope-violation prevention.
- **G004 conformance harness**: validates raw JSON event/report/approval-token bundles (source-agnostic
  — works on artifacts from Rust, Python, or golden fixtures) against a strict schema: lane-event
  sequence numbers must be strictly increasing, terminal events (`lane.finished`) must carry an
  `eventFingerprint`, reports must match `schemaVersion: "g004.report.v1"` and have valid `findings`
  (facts/hypotheses/negative evidence) and `fieldDeltas`, approval tokens must carry `oneTimeUse` and
  an intact `delegationChain`.

**Task Packet / Task Registry / Team+Cron** — the work-definition and tracking layer:
- `TaskPacket`: objective, `scope` (`Workspace`/`Module`/`SingleFile`/`Custom`),
  `acceptance_criteria`, `resources` (allowed files/dirs/services), `verification_plan`,
  `branch_policy`, optional `recovery_policy`. `validate_packet` enforces: `objective`/`repo`/
  `branch_policy`/`commit_policy` non-empty; `scope_path` mandatory for non-`Workspace` scopes;
  either `acceptance_tests` or `acceptance_criteria` required; either `reporting_contract` or
  `reporting_targets` required.
- `TaskRegistry` (`Arc<Mutex<RegistryInner>>` for concurrent access) tracks `TaskStatus`: `Created →
  Running → Blocked/Completed/Failed/Stopped`. Health is tracked via `LaneHeartbeat` (observed_at,
  transport_alive, status string) → `LaneFreshness` (`Healthy`/`Stalled` [no heartbeat within
  `stalled_after_secs`]/`TransportDead`). `LaneBoard` is a point-in-time snapshot of all tasks
  categorized as Active/Blocked/Finished.
- `detect_lane_completion` heuristic requires *all* of: status is "completed"/"finished"
  (case-insensitive), `output.error is None`, `output.current_blocker is None`, `test_green == true`,
  `has_pushed == true` (code actually landed in the remote). Only then does
  `evaluate_completed_lane` invoke the Policy Engine for `CloseoutLane`/`CleanupSession` actions —
  i.e. "the agent said it's done" is explicitly *not* sufficient; completion requires verified,
  pushed, green work.
- `TeamRegistry` groups agents working on shared objectives (tasks carry a `team_id`); `CronRegistry`
  handles scheduled task execution (`CronCreate`/`Delete`/`List`); `LaneBoardEntry` includes
  `team_id` for per-team dashboard filtering.

**MCP integration** — hardened lifecycle phases (`McpLifecyclePhase`): `ConfigLoad → SpawnConnect →
InitializeHandshake → ToolDiscovery → Ready`, so failures can be pinpointed to an exact phase.
Transports: Stdio (`McpStdioTransport`), SSE/HTTP/WebSocket (`McpRemoteTransport`), and a "Managed
Proxy" transport for gateway-mediated connections. Tool namespacing avoids collisions across servers:
every remote tool is prefixed `mcp__[server_name]__`, with names normalized to
alphanumeric/underscore/hyphen. Default tool-call timeout is 60s (`DEFAULT_MCP_TOOL_CALL_TIMEOUT_MS`);
stdio init timeout 10s; tool-listing timeout 30s. Server configs are uniquely identified by a
`scoped_mcp_config_hash` (command + args + env + `required` flag) and a human-readable
`mcp_server_signature` (e.g. `stdio:[uvx|mcp-server]`). A `required: true` flag on a server config
propagates its connection status through discovery reports (so orchestrators know if a mandatory tool
provider is down).

**Plugin system** — three `PluginKind`s: `Builtin` (compiled in), `Bundled` (shipped in
`bundled/`), `External` (user-installed, tracked in `installed.json`). Manifest at
`.claude-plugin/plugin.json` (same path convention as Claude Code plugins) defines metadata,
`PluginPermission` (`Read`/`Write`/`Execute`), hook registrations, lifecycle scripts (`Init`/
`Shutdown`), custom tools (`PluginToolManifest`: input_schema, command, required_permission), and
custom slash commands. `HookEvent`: `PreToolUse` (exit code `2` denies execution), `PostToolUse`,
`PostToolUseFailure`. Hook scripts receive context via env vars: `HOOK_EVENT`, `HOOK_TOOL_NAME`,
`HOOK_TOOL_INPUT` (raw JSON), `HOOK_TOOL_OUTPUT` (post-use only), `HOOK_TOOL_IS_ERROR`. A
`HookAbortSignal` (`AtomicBool`) lets the runtime forcibly cancel a long-running/unresponsive hook.
Test isolation (`EnvLock`) redirects `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME` to temp dirs during CI
so ambient plugin state can't leak into regression tests.

## Key patterns & techniques

- **Explicit state machines over implicit readiness assumptions**: rather than assuming a spawned
  worker/agent process is immediately ready, the whole boot pipeline is modeled as a state machine
  with named blocking states (`TrustRequired`, `ToolPermissionRequired`) so an orchestrator can poll
  or react to *why* a worker isn't accepting work yet, instead of guessing from raw output.
- **Prompt-misdelivery as a first-class failure mode**: explicitly naming and detecting "the prompt
  landed in the wrong place" (e.g. a raw shell instead of the agent) is a mature response to a
  failure mode that's easy to overlook when driving CLI agents via terminal automation/pane-scraping.
- **"One automatic recovery attempt before escalation"**: a deliberately conservative policy — avoids
  both infinite silent retry loops and over-eager human interruption for transient issues.
- **Deterministic completion gating**: requiring `test_green && has_pushed && !error && !blocker`
  before treating a lane as "done" — regardless of what the agent's own text output claims — is a
  reusable pattern for any system orchestrating autonomous coding agents where self-reported
  completion is unreliable.
- **Approval tokens as structured, auditable, one-time-use exceptions** (vs. ad hoc "yes go ahead" in
  chat) with a full delegation chain — a pattern worth reusing anywhere policy exceptions need to
  survive an audit.
- **Schema-agnostic conformance validation** (G004 harness operating on raw `serde_json::Value`
  rather than internal Rust types) so the same validator can check artifacts produced by different
  language implementations (Rust vs. Python) or golden fixtures — useful when running a
  polyglot/parity-tracked system.
- **Clean-room parity auditing**: maintaining a reference Python implementation specifically to
  verify a from-scratch Rust rewrite matches intended behavior, validated via a scripted
  `mock_parity_harness` (12 scenarios) against a deterministic `MockAnthropicService`, tracked across
  "9 lanes" (functional checkpoints) merged incrementally into `main`.

## Practical how-tos

- Build: `cd rust && cargo build --workspace` (debug) or `--release`; binary lands at
  `rust/target/debug/claw` (or `.exe` on Windows). Linux/macOS/WSL also has `./install.sh`.
- First run: `./target/debug/claw` then `/doctor` inside the REPL to check auth/env.
- One-shot prompt: `./target/debug/claw prompt "explain this codebase"`.
- Init a project: `claw init` — idempotent, writes `.claw/settings.json`, `.claw.json`, `CLAUDE.md`.
- Inspect worker state: `claw state` reads `.claw/worker-state.json` (active worker ID, session ref,
  current permission mode). `claw status` reports loaded memory files and hook validation results.
- Local OpenAI-compatible providers (Ollama/vLLM/llama.cpp): set `OPENAI_BASE_URL`.

## Gotchas & caveats

- `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are not interchangeable — they map to different HTTP
  headers (`x-api-key` vs `Authorization: Bearer`), so swapping them silently produces auth failures
  rather than an obvious config error.
- Much of this wiki describes an ambitious in-progress control plane (worker lanes, policy engine,
  approval tokens, task registry) built specifically for this project — these are not standardized
  protocols shared with other agent tooling; treat the concepts as design inspiration, not
  interoperable standards, when applying elsewhere.
- The completion-detection heuristic is strict by design (`test_green` AND `has_pushed` both
  required) — a lane that passes tests locally but hasn't pushed is deliberately *not* considered
  finished, which could surprise anyone expecting "tests pass" alone to signal done.
- The project explicitly maintains two parallel implementations (Rust production, Python reference)
  and a parity-audit process between them — anyone consuming only the Rust half should be aware the
  Python workspace exists as the design's source of truth for intended behavior, not as a secondary
  product.

## Wiki pages used

Overview; Getting Started; Repository Structure; MCP Integration; Plugin System; Worker Boot and Lane
System; Recovery Recipes and Branch Management; Policy Engine, Green Contract, and Approval Tokens;
Task Packet, Task Registry, and Team/Cron System. (structure.md also lists CLI/REPL, Runtime/
Conversation Engine, Session Management, System Prompt, API Client/Provider Routing, Tool Execution
Engine, LSP Integration, Compat Harness, Lane Events and Report Schema, claw-analog, claw-rag-service,
the full Python Porting Workspace section, Configuration/Permissions, and Testing/CI pages — not read
in full given time constraints; those largely mirror or extend patterns already captured above.)
