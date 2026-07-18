---
repo: affaan-m/everything-claude-code
deepwiki: https://deepwiki.com/affaan-m/everything-claude-code
github: https://github.com/affaan-m/everything-claude-code
harvested: 2026-07-09
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`affaan-m/everything-claude-code`](https://deepwiki.com/affaan-m/everything-claude-code) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# affaan-m/everything-claude-code — Distilled Knowledge

## What it is

Everything Claude Code (ECC) is a large, production-hardened "performance optimization system" for
Claude Code and compatible AI agent harnesses (Cursor, OpenCode, Codex, Gemini, Antigravity). It
originated as an Anthropic hackathon-winning entry and has been battle-tested over 10+ months of
daily use building real products. As of v2.0.0-rc.1 it ships roughly 48 specialized agents, 182
skills, and 68 legacy slash-command shims, plus a hooks system, a hierarchical rules system for 12+
language ecosystems, MCP server configs, and a distinctive autonomous "Continuous Learning" pipeline
that mines session activity for reusable patterns. It's best understood as a comprehensive reference
implementation of "everything you'd configure by hand around Claude Code if you had a year to
iterate on it."

## Architecture (how it's built, key components)

**Seven component types**, each with a distinct role and invocation method:

| Component | Location | Purpose | Invocation |
|---|---|---|---|
| Agents | `agents/*.md` | Specialized subagents with restricted tool permissions | Delegated via Task tool or direct invocation |
| Skills | `skills/*/SKILL.md` | Reusable workflow/domain knowledge | Auto-loaded by context match |
| Commands | `commands/*.md` | Slash commands for quick execution | User types `/command-name` |
| Rules | `rules/` | Always-follow guidelines (common + language-specific) | Auto-loaded every session |
| Hooks | `hooks/hooks.json` + `scripts/hooks/*.js` | Event-driven deterministic scripts | Automatic on lifecycle events |
| MCPs | `mcp-configs/`, `.mcp.json` | External service integrations | Tool calls from the LLM |
| Instincts | `instincts/`, `~/.claude/homunculus/projects/<id>/instincts/` | Project-scoped patterns learned from observed sessions | Auto-loaded for project context |

**Four-layer architecture**, from interface to evolution: (1) User-Facing Layer — Commands + Rules;
(2) Intelligence Layer — Agents + Skills; (3) Automation Layer — Hooks + Scripts; (4) Learning Layer
— Observation System + Instinct Generation, which promotes learned instincts back up into Skills.
This creates a closed loop: Commands delegate to Agents → Agents reference Skills and are
constrained by Rules → Hooks monitor tool use for quality/safety and feed the Observation system →
Observations distill into Instincts → Instincts get promoted/evolved into new Skills.

**Plugin manifest strategy — explicit convention-over-configuration to dodge validator bugs.**
`.claude-plugin/plugin.json` deliberately avoids declaring `agents` or `hooks` fields, because
Claude Code v2.1+ auto-discovers `agents/*.md` and `hooks/hooks.json` by directory convention, and
explicitly listing them caused validation errors/duplicate loading in earlier plugin schema
versions. The manifest also ships an explicit empty `mcpServers: {}` object specifically to prevent
an "overlong tool name" error that occurs when Claude auto-discovers a root `.mcp.json` during
plugin installation. `commands` and `skills` fields must be arrays per the enforced schema. Separate
manifests exist for Codex (`.codex-plugin/plugin.json`) and OpenCode (`.opencode/`) to satisfy each
harness's native format.

**Agent file structure.** Frontmatter fields: `name` (kebab-case, required), `description`
(single-line summary, required), `tools` (array of allowed tool names — creates a security boundary,
e.g. a reviewer agent gets `Read/Grep/Glob/Bash` but not `Edit`, preventing accidental code
modification during review), `model` (optional — haiku/sonnet/opus). Model routing by task type:
Haiku for fast exploration/simple updates/pattern detection (`doc-updater`, the continuous-learning
`observer`); Sonnet for standard coding/multi-file review/database work (`database-reviewer`,
`e2e-runner`, `tdd-guide`); Opus for high-sensitivity architecture decisions (`architect`) and
complex remediation. The global `agent.yaml` prefers `claude-opus-4-6` with `claude-sonnet-4-6`
fallback.

**Hooks — deterministic vs. probabilistic contrast.** The wiki is explicit that hooks differ
fundamentally from Skills (invoked probabilistically by the agent's judgment) and Rules
(natural-language constraints the agent can still misapply): hooks run deterministically, triggered
100% of the time by the underlying engine, regardless of what the LLM "decides." I/O contract: hooks
receive a JSON payload on stdin (`tool_name`, `tool_input`, `transcript_path`, etc.), must echo the
original JSON back to stdout to keep the tool chain intact, may emit warnings to the user/agent via
stderr, and control flow via exit code — exit 0 continues, exit 2 blocks (PreToolUse only). Six
lifecycle phases: SessionStart (bootstrap context, load previous summaries), PreToolUse
(validate/block before execution), PostToolUse (auditing, formatting, background observation), Stop
(extract session summaries from `transcript.jsonl`), PreCompact (suggest checkpoints before context
summarization), SessionEnd. `hooks/hooks.json` uses a `plugin-hook-bootstrap.js` pattern to resolve
`CLAUDE_PLUGIN_ROOT` so hook scripts find their dependencies regardless of install path.

**Continuous Learning v2 — the most distinctive subsystem.** A five-phase pipeline that converts raw
session activity into reusable knowledge, entirely via deterministic hooks plus a background daemon
(not by asking the LLM to self-report at session end, which the docs note was the unreliable v1
approach):
1. **Observation** (`observe.sh`, registered on both PreToolUse and PostToolUse): captures every tool
   call to `observations.jsonl`. Includes a 5-layer guard system to avoid observing automated subagent
   sessions (detected via `agent_id`) or the observer's own analysis loop (avoiding infinite self-
   observation). Project-scopes observations by hashing `git remote get-url origin` (or local path)
   into a 12-character SHA256 `_CLV2_PROJECT_ID`, storing under `~/.claude/homunculus/projects/<id>/`.
   Signaling to the background daemon is throttled (`kill -USR1` sent only every
   `ECC_OBSERVER_SIGNAL_EVERY_N`, default 20 observations) to avoid signaling storms.
2. **Analysis** (`observer-loop.sh`, a background daemon invoking Claude Haiku periodically): reads
   `observations.jsonl` via `tail -n 500` (configurable via `MAX_ANALYSIS_LINES`) rather than the full
   file, to bound token cost. Guarded by a re-entrancy flag (`ANALYZING`) and a cooldown throttle
   (`ANALYSIS_COOLDOWN`, default 60s) to prevent overlapping/runaway Claude analysis processes. A
   `session-guardian.sh` further gates analysis cycles based on active hours and idle detection.
3. **Codification**: detected patterns become "instincts" — YAML-frontmatter markdown files with fields
   `id` (kebab-case), `trigger` (natural-language activation condition), `confidence` (0.3-0.85,
   weighted by observed frequency: 3-5 occurrences→0.5, 6-10→0.7, 11+→0.85), `domain` (code-
   style/testing/git/debugging/workflow/file-patterns), `scope` (project default, or global).
4. **Evolution**: `/evolve` clusters related instincts by domain/similarity into full `SKILL.md` files,
   commands, or agents, stored under the project's `evolved/` directory. `/promote` moves a project-
   scoped instinct to global scope once verified as universal (not project-specific).
5. **Usage**: when an ECC agent starts, relevant instincts for the current project ID are injected into
   its prompt; a registry at `~/.claude/homunculus/projects.json` maps hashed IDs back to human-
   readable project names.

Related commands: `/instinct-status` (view learned instincts), `/instinct-export` (portable export),
`/evolve`, `/promote`, `/projects`.

**Skill Health Monitoring.** `skill-runs.jsonl` logs skill execution; a `skills-health` CLI reads
this log to produce a health dashboard — treating skills as monitored artifacts with usage/success
telemetry rather than static files.

## Key patterns & techniques (the transferable knowledge)

**Deterministic-hooks-vs-probabilistic-skills as a design taxonomy.** This repo draws a sharp,
explicit line: use a hook (deterministic script, guaranteed to run, hard block via exit code) for
anything that MUST happen every time (formatting, type-checking, secret-scanning, blocking a
specific dangerous bash pattern); use a skill (loaded probabilistically based on the agent's
judgment of relevance) for domain knowledge and workflow guidance the agent should reference but
doesn't need enforced with 100% reliability; use a rule (natural-language, always-loaded but still
agent-interpreted) for softer style/process constraints. This three-way taxonomy is a reusable
mental model for deciding which enforcement mechanism fits a given requirement's actual reliability
need.

**Fact-forcing PreToolUse gates.** `gateguard-fact-force.js` forces the agent to investigate before
editing — e.g., list importers of a module or check API schemas — by blocking the edit tool call
until an investigation step has been recorded, maintaining per-session state in `~/.gateguard` of
which files have already passed this "investigation gate." This is a generalizable pattern for
forcing an agent to gather context before acting, implemented at the tool-call layer rather than
relying on prompt instructions the agent might skip.

**Reliability-first observation architecture (v1→v2 lesson).** The explicit design rationale for
Continuous Learning v2 is that *asking the LLM to self-summarize at session end* (the presumed v1
approach) is unreliable — the model may forget, compress inaccurately, or simply not do it. v2's
fix: capture 100% of tool usage deterministically via hooks (not LLM self-report), and defer the
*interpretation* of that raw log to a separate, asynchronous, cheap-model (Haiku) analysis pass.
This separation — deterministic capture now, probabilistic interpretation later, out of the critical
path — is a broadly reusable pattern for building any "learn from what the agent did" system: don't
trust the agent to accurately narrate its own actions in real time; log mechanically, analyze later.

**Cost/resource guardrails around background LLM analysis.** Multiple independent throttles stack to
keep an always-on background analyzer cheap and non-disruptive: signal-count throttling (only wake
the analyzer every N observations, not on every single one), a hard cooldown between analysis runs,
tail-based sampling (analyze only the most recent N lines, not the whole growing log), a re-entrancy
guard (never run two analysis passes concurrently), and active-hours/idle gating via a "session
guardian." Any system that wants a cheap background model doing continuous pattern-mining on live
data should consider this same stack of independent throttles rather than relying on just one.

**Confidence scoring by observed frequency.** Instincts aren't binary learned/not-learned — they
carry a confidence score that increases stepwise with corroborating observation count (0.3 → 0.5 at
3-5 occurrences → 0.7 at 6-10 → 0.85 at 11+). This gives downstream consumers (the agent
prompt-injection step, the `/evolve` clustering command) a graded signal rather than treating every
detected pattern as equally trustworthy — a single anomalous observation shouldn't carry the same
weight as a pattern seen a dozen times.

**Project identity via content hashing, not path.** Project scoping is keyed off a SHA256 hash of
`git remote get-url origin` (falling back to the local repo root path), not the working directory
string. This makes instincts/observations portable across clones of the same repo on different
machines or in different local paths — a technique worth reusing anywhere you need a stable project
identity that survives relocation.

**Security-by-tool-restriction for review agents.** Rather than trusting a "reviewer" agent's
instructions alone to keep it read-only, its `tools` frontmatter literally omits `Edit`/`Write` —
the security boundary is enforced at the tool-permission layer, not just the prompt layer. This is
the same idea as least-privilege service accounts applied to LLM agents: don't rely on the model
choosing not to misuse a capability it technically has.

**Explicit parallel-over-sequential delegation for independent review passes.** The docs call out
sequential agent chaining (security scan → perf review → type check, one after another) as an
anti-pattern when the checks are independent, and recommend spawning them concurrently instead. This
mirrors the same "spawn N parallel subagents for independent facets of the same artifact" pattern
seen elsewhere in this batch (e.g. Claude Code's Feature Development plugin), reinforcing it as a
general orchestration heuristic rather than a one-off.

**Context-window budget discipline as an explicit agent instruction.** Agents are told to avoid
operating in the last 20% of the context window for large refactors — an explicit, numeric budget
rule rather than a vague "watch your context" reminder, making it something an agent (or a wrapping
harness) can actually check against.

## Practical how-tos (concrete workflows)

**Install:** via marketplace (`/plugin marketplace add affaan-m/everything-claude-code` → `/plugin
install everything-claude-code@everything-claude-code` → `/configure-ecc` wizard) or via the
manifest-driven Selective Install system (`./install.sh --profile core|developer|full`, or
`--dry-run` to preview, or `--target cursor typescript` for platform+language-scoped installs).
Note: language-specific `rules/` files must be installed via a **separate manual step** (`git clone`
+ `install.sh`/`install.ps1`) because Claude Code plugins cannot automatically distribute files into
`~/.claude/rules/` — a platform limitation, not an ECC design choice.

**Verify installation:** `/plugin list` shows the plugin enabled; typing `/everything-claude-code:`
should autocomplete to available commands; `/everything-claude-code:plan "test"` should produce a
response that identifies itself as the `planner` agent; `/setup-pm` shows the detected package
manager; `ls ~/.claude/rules` should show `common/` plus installed language folders.

**Standard feature-development pipeline:** Phase 0 (Research & Reuse — GitHub code search,
package-registry search, MCP/skills search; adopt/extend an existing solution if found, otherwise
proceed) → Phase 1 (`planner` agent generates PRD/architecture/task-list) → Phase 2 (`tdd-guide`
agent: RED write-failing-tests → GREEN implement-to-pass → REFACTOR/IMPROVE) → Phase 3
(`code-reviewer` then `security-reviewer`, address CRITICAL issues) → Phase 4 (`/verify`: build →
typecheck → lint → test) → Phase 5 (conventional commit → push). The system mandates
research-and-reuse before any new implementation and requires 80%+ test coverage for new work.

**Package-manager detection cascade** (used consistently across the tool): environment variable
`CLAUDE_PACKAGE_MANAGER` → project `.claude/package-manager.json` → `package.json` `packageManager`
field → lockfile detection (`yarn.lock`, `pnpm-lock.yaml`, etc.) → global
`~/.claude/package-manager.json`. This priority order is a reusable pattern for any tool needing to
infer project tooling preferences without forcing explicit configuration everywhere.

**Hook runtime tuning via env vars:** `ECC_HOOK_PROFILE=minimal|standard|strict` adjusts overall
hook aggressiveness; `ECC_DISABLED_HOOKS` is a comma-separated list of hook IDs to skip entirely —
useful for debugging a specific hook without disabling the whole system.

**Writing a SKILL.md in this system:** frontmatter `name`, `description` (for auto-activation),
`origin: ECC`, `version`; body sections `## When to Activate` (critical for auto-activation —
describe concrete trigger scenarios), `## Core Concepts`, `## Code Examples` (copy-pasteable,
well-commented), `## Anti-Patterns` (concrete "don't do this"), `## Best Practices`.

## Gotchas & caveats

- Version/count figures (48 agents, 182 skills, 68 commands vs. an alternate page's "47 agents, 181
  skills, 79 commands") are inconsistent across wiki pages — the underlying repo evolves quickly and
  different pages were generated at slightly different snapshots; treat exact counts as approximate,
  not load-bearing.
- The empty `mcpServers: {}` in `plugin.json` is a workaround for a specific Claude Code auto-
  discovery bug (overlong tool name error from root `.mcp.json` auto-discovery during plugin install)
  — this is fragile coupling to current platform behavior and could need revisiting if the platform's
  discovery logic changes.
- Rules cannot be distributed automatically via the plugin mechanism — this is a hard platform
  limitation (not a bug ECC can fix), so any fork/adaptation of this pattern needs its own manual-
  install step for anything targeting `~/.claude/rules/`.
- The Continuous Learning pipeline is stateful and disk-persistent (`~/.claude/homunculus/projects/`)
  outside the git repo — cloning the ECC repo alone does not carry over any learned instincts; they're
  keyed to the local machine's observation history.
- Multi-layer self-observation guards (Layers 1-5 in `observe.sh`) exist specifically because a naive
  observation hook would otherwise observe its own background analysis subagent's tool calls,
  corrupting the training signal with meta-observations of the observer itself — a subtle failure mode
  worth watching for in any self-monitoring agent system.
- Aggressive model-cost routing (Haiku for "simple" tasks) assumes task classification is accurate;
  misclassifying a task as mechanical when it actually needs deeper reasoning would silently degrade
  output quality rather than fail loudly.
- The "Agent-First" proactive delegation principle (orchestrator delegates without waiting for
  explicit user request) trades user control for automation — teams adopting this pattern should be
  aware it changes agent behavior from reactive to proactive by design, which may surprise users
  expecting to explicitly invoke each step.

## Wiki pages used

Overview, Getting Started, Core Concepts (Plugin Architecture, Agents, Skills — partial read through
Commands), Hooks, Continuous Learning System, Continuous Learning v2 Architecture, Observation
System (partial), Development Workflows (Complete Feature Development, workflow categories/selection
guide — partial). Not read in depth: Rules, MCPs (Model Context Protocol), Installation & Setup
subpages, Component Reference section, Hooks System detail subpages (PreToolUse/PostToolUse/Session
& Context/Testing/Creating Custom Hooks), Session Management System section, Observer Agent &
Pattern Detection / Instinct Structure & Management / Evolution Pipeline / Project-Scoped Learning /
Skill Creator Integration / Evaluation System / Skill Evolution & Health Tracking detail pages,
Configuration Guide section, remaining Development Workflows subpages (Search-First, TDD Workflow,
Code Review & Security, Checkpoint & Verification, Eval-Driven Development, Autonomous Loop
Patterns), Advanced Topics section (Agent Delegation & Orchestration, Token Optimization, Memory &
Context Preservation, Utility Library, Package Manager System, Project Detection, Testing
Infrastructure, Plankton Code Quality, Tmux Worktree Orchestration, Python LLM Abstraction Layer),
Cross-Platform Support section, Platform-Specific Skills, ECC2 Rust TUI section, Contributing
section, Troubleshooting section, Examples & Templates, Glossary.
