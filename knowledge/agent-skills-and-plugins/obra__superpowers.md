---
repo: obra/superpowers
deepwiki: https://deepwiki.com/obra/superpowers
github: https://github.com/obra/superpowers
harvested: 2026-07-09
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`obra/superpowers`](https://deepwiki.com/obra/superpowers) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# obra/superpowers — Distilled Knowledge

## What it is

Superpowers is a multi-platform "complete software development methodology for coding agents,"
distributed as a plugin/skill library (current version `6.1.1`, maintained at
github.com/obra/superpowers). It supports Claude Code, Antigravity, Codex, OpenCode, Cursor, Kimi
Code, Pi, and GitHub Copilot CLI (Gemini CLI support was removed in v6.1.0 following its EOL). Its
core mechanism is a library of `SKILL.md` files plus a **mandatory instruction protocol** — the
`using-superpowers` meta-skill — that forces the agent to check for and invoke relevant skills
before taking any action, including before asking clarifying questions.

The system's stated goal: transform AI coding agents "from reactive code-writers into systematic
engineers" by forcing a step-back design phase before implementation, replacing ad hoc/intuitive
problem-solving with enforced multi-phase processes, and treating skill-writing itself as a TDD
discipline applied to documentation.

## Architecture (how it's built, key components)

**Single source of truth, multi-platform shims.** The `skills/` directory is the canonical content.
Each platform gets a thin integration layer that bootstraps the same `using-superpowers/SKILL.md`
content into session context and maps Claude-Code-native tool names to platform equivalents:

| Platform | Integration mechanism | Config/entry point |
|---|---|---|
| Claude Code | Native marketplace/hooks | `.claude-plugin/plugin.json`, `hooks/hooks.json` → `hooks/session-start` |
| Pi | Session-start extension | `.pi/extensions/superpowers.ts`, hooks `session_start`/`session_compact`/`context` |
| Codex | Native skill discovery (as of v6.1.0, no session-start hook needed) | `.agents/plugins/marketplace.json`; scans `~/.agents/skills/` |
| OpenCode | JS plugin / prompt transform | `.opencode/INSTALL.md`; injects `superpowersSkillsDir` into `config.skills.paths` via a `config` hook |
| Cursor | Marketplace/hooks | `/add-plugin superpowers` |
| Antigravity | Session-start hook | `agy plugin install`; bootstraps from the first message |

**Skill discovery mechanisms** fall into three categories: (1) **native discovery**
(Codex/OpenCode/Pi scan a skills directory for `SKILL.md` frontmatter), (2) **plugin-driven
injection** (Claude Code/Cursor), (3) **metadata loading** (Gemini CLI, now deprecated, via
`gemini-extension.json`). Regardless of mechanism, only skill `name`+`description` metadata is
pre-loaded into the system prompt at session start; the full `SKILL.md` body is pulled into context
only when the agent determines relevance.

**Three-tier skill priority / shadowing.** When a skill name exists in multiple locations,
resolution order is: (1, highest, outside the tier system) explicit user instructions in
`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/direct chat — always wins; (2) Project skills
(`.claude/skills/`, `.superpowers/skills/`); (3) Personal skills (`~/.config/superpowers/skills/`);
(4, lowest) the Superpowers standard library itself. To override a core skill, a developer creates a
same-named directory with a `SKILL.md` at a higher-priority tier (e.g. `mkdir -p
.superpowers/skills/brainstorming/` in a project) — the higher-tier file is loaded instead.

**Bootstrap injection (the `using-superpowers` meta-skill).** This is the first skill every session
encounters. Unlike other skills, it is not loaded on-demand — it's injected directly into session
context via platform hooks (e.g. Pi's `superpowers.ts` reads the file, strips YAML frontmatter, and
injects it as a `role: user` message wrapped in an `<EXTREMELY_IMPORTANT>` marker, re-injecting
after `session_compact` so it survives context compaction). It defines: the 1% invocation rule, the
instruction-priority hierarchy, a `SUBAGENT-STOP` escape gate, process-vs-implementation skill
ordering, and a Red Flags rationalization table.

**Platform tool-mapping layer.** Skills are authored using Claude-Code-native tool names (`Skill`,
`Task`, `TodoWrite`, `Read`/`Write`/`Edit`, `Bash`). Each platform gets a mapping table injected at
bootstrap or via a `references/<platform>-tools.md` file, e.g.: `Skill`→Pi's native `read`;
`TodoWrite`→`TODO.md`/plan files; `Task`→`subagent` (Pi) or `spawn_agent` (Codex) or `update_plan`
(Codex, for TodoWrite); Copilot CLI maps `TodoWrite`→a `sql` tool against a `todos` table.

## Key patterns & techniques (the transferable knowledge)

**The 1% Rule as an anti-rationalization enforcement mechanism.** The core invocation gate: "If you
think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST
invoke the skill... This is not negotiable. You cannot rationalize your way out of this." The
threshold is deliberately set low specifically because the system's designers assume agents under
pressure will otherwise find plausible-sounding reasons to skip inconvenient process. This is a
general pattern for any rule you want an LLM agent to actually follow under adversarial/pressured
conditions: state the threshold as absurdly permissive (1%, not "when clearly relevant") to close
the rationalization gap, and back it with explicit "you do not have a choice" language rather than
soft suggestion.

**Instruction priority hierarchy** (reusable conflict-resolution pattern for any agent with both
user config and injected process rules): (1) explicit user instructions always win — e.g. if
`CLAUDE.md` says "don't use TDD" while a skill mandates TDD, the user instruction wins; (2)
injected/library process skills override default model behavior; (3) the base system prompt is
lowest priority. Crucially, the rule includes a safety valve: agents must "only skip skill workflows
when the human partner has explicitly requested it" — preventing the agent from inferring permission
to skip from ambiguous signals.

**Process-before-implementation skill ordering.** When multiple skills could apply, Process skills
(`brainstorming`, `systematic-debugging` — these decide HOW to approach a task) must be resolved
before Implementation skills (`test-driven-development`, `writing-plans`, domain-specific skills —
these guide EXECUTION). E.g. "let's build X" triggers `brainstorming` before any implementation
skill fires; "fix this bug" triggers `systematic-debugging` before domain-specific skills. This is a
generalizable meta-pattern: separate "decide the strategy" skills from "execute the strategy" skills
and always sequence the former ahead of the latter.

**Red Flags / rationalization tables** — a concrete technique for hardening any "must-follow"
instruction. Pre-emptively enumerate the specific internal thoughts an agent will have when tempted
to skip a rule, and pair each with a one-line rebuttal, e.g.: "I need more context first" → "Skill
check comes BEFORE clarifying questions"; "This is just a simple question" → "Questions are tasks.
Check for skills"; "The skill is overkill" → "Simple things become complex. Use it"; "I know what
that means" → "Knowing the concept ≠ using the skill. Invoke it." This Excuse→Reality table format
recurs across skills (e.g. `systematic-debugging`, `test-driven-development`) as the standard
hardening mechanism.

**SUBAGENT-STOP gate** — an explicit circuit-breaker to prevent infinite/recursive protocol
re-invocation: "If you were dispatched as a subagent to execute a specific task, ignore this skill."
Subagents already have a narrowly-scoped task from their controller and shouldn't re-trigger the
full skill-discovery protocol. This is a reusable pattern for any recursive/hierarchical agent
system with a global "always check X" rule — the rule needs an explicit exemption for delegated
workers, or it will thrash.

**TDD applied to process documentation (the most novel transferable idea in this repo).** Skills are
authored via a RED-GREEN-REFACTOR cycle where the "test" is a subagent's behavior and the
"production code" is the `SKILL.md` file:
- **RED**: Design a "pressure scenario" combining 3+ stressors (time pressure, sunk cost, authority
  pressure, exhaustion, social pressure, economic pressure — e.g. "production is down, $10k/min lost,
  5 minutes to deploy window" combined with "your partner says just ship it"). Dispatch a subagent
  WITHOUT the skill and capture its rationalization verbatim (e.g. "I'm being pragmatic, not
  dogmatic") in a `baseline-results.md`.
- **GREEN**: Write the minimal `SKILL.md` content that addresses the observed failure, then re-run the
  same scenario WITH the skill present and verify compliance.
- **REFACTOR**: Run harder pressure variants to find new loopholes/rationalizations, then harden the
  skill with explicit negations ("Delete it. Start over. No exceptions: don't keep it as 'reference',
  don't 'adapt' it, delete means delete" — contrasted with the weaker original "Write code before
  test? Delete it") and add newly-discovered excuses to the Red Flags table.
- **Iron Law**: "NO SKILL WITHOUT A FAILING TEST FIRST" — applies to new skills, edits (need a new
  pressure scenario proving the addition is necessary), and refactors (must re-verify against existing
  pressure tests).

Pressure scenario design rules: combine 3+ pressures (a single pressure like just a deadline is too
easy for a modern LLM to resist); force concrete A/B/C choices rather than open-ended "what should
you do?"; use real constraints (specific times, dollar amounts, file paths) to ground the scenario
in "Code Entity Space" rather than abstraction; explicitly forbid "easy outs" like "I would ask the
user" or deferring the decision.

**Claude Search Optimization (CSO) — the description-field discipline.** The `description`
frontmatter field is the sole gatekeeper for whether a skill's full body ever gets read. Hard rules:
must start with "Use when..." to focus on triggering conditions; must be third-person (it's injected
into the system prompt, and first-person breaks POV consistency); must describe ONLY *when* to use
the skill, NEVER summarize *what* it does or *how* — because testing showed that a description like
"Use when executing plans — dispatches subagent per task with code review between tasks" causes the
agent to treat that one-sentence summary as a complete instruction set and skip reading the actual
multi-stage review logic in the body, silently performing only one review pass instead of the
documented two-stage (spec-compliance + code-quality) process. This is a strong, non-obvious lesson
for anyone writing retrieval-triggering metadata for LLM agents: a *helpful-sounding* summary in the
trigger field can be actively harmful because the LLM may substitute it for the real content.

**Concrete SKILL.md conventions:** name must be lowercase, letters/numbers/hyphens only (no
parentheses), recommended gerund form (`writing-skills`, `executing-plans`); total frontmatter ≤1024
characters, description recommended ≤500 characters; standard body sections in order: Overview (1-2
sentence core principle) → When to Use (symptoms/triggers + explicit "When NOT to use" list, with a
flowchart if the decision is non-obvious) → Core Pattern (before/after code, for Technique/Pattern
skills) → Implementation (inline if <50 lines, link to a separate reference file if 100+ lines) →
Quick Reference (table, for Reference-type skills) → Common Mistakes (failure modes + fixes) →
optional Real-World Impact. Heavy reference material and reusable scripts/tools go in separate files
alongside `SKILL.md`, not inlined — this keeps the always-injected metadata cheap and the on-demand
body focused.

**Skill type taxonomy:** Technique (concrete method with specific steps, e.g. `root-cause-tracing`),
Pattern (a way of thinking about problems/code organization, e.g. `test-invariants`), Reference
(static info — API docs, syntax). Explicitly NOT skills: narratives about one specific problem
solved once; project-specific conventions (those belong in `CLAUDE.md`); mechanical constraints that
automation could enforce instead.

**Degrees-of-freedom calibration.** Match specificity to task fragility: Low Freedom (exact
scripts/sequences) for fragile operations like database migrations where deviation breaks things;
Medium Freedom (preferred patterns, some variation acceptable); High Freedom (heuristics only) for
context-dependent tasks like code review where multiple valid approaches exist. Over-specifying a
high-freedom task wastes tokens and produces brittle, over-fit guidance; under-specifying a
low-freedom task risks catastrophic failure.

**Multi-stage subagent review with model-tier cost optimization (subagent-driven-development /
SDD).** The core formula: fresh subagent per task (no context pollution from prior tasks) +
task-scoped review (spec compliance + code quality merged into one reviewer pass) + a final broad
review across the whole branch = fast iteration without sacrificing quality. Model selection is
matched to task nature, not uniformly maxed out: mechanical tasks (isolated functions, clear specs,
1-2 files) get a fast/cheap model; integration tasks (multi-file coordination, debugging) get a
standard model; architecture/design/final-review get the most capable model available. Explicit
caveat embedded in the skill: "turn count beats token price" — cheap models often take 2-3x the
turns to reach a correct result, so a naive per-token cost calculation misses the true
wall-clock/total-cost picture; a mid-tier model is recommended as the floor for reviewers and
prose-heavy implementers.

**Implementer status protocol** — a small, reusable vocabulary for subagent-to-controller status
signaling: `DONE` (confident completion, proceed to review), `DONE_WITH_CONCERNS` (finished but
flagged doubts — controller must read and address before review), `NEEDS_CONTEXT` (missing info —
controller supplies and re-dispatches), `BLOCKED` (cannot complete — controller assesses whether to
add context, upgrade the model, or decompose the task further). This gives a controller agent a
small, unambiguous state machine instead of parsing free-text subagent reports.

**Diff-file handoff instead of inline paste.** SDD's task reviewer reads a diff via a temp file
(`git diff > /tmp/sdd-task.diff`) rather than having the diff pasted into its prompt — avoiding both
context bloat in the dispatch prompt and truncation risk for large diffs. The reviewer is also
explicitly instructed to be skeptical: "treat the implementer's report as unverified claims — verify
everything against the diff," and to stay scoped to the diff file rather than crawling the broader
codebase unless a concrete risk is named.

**The systematic-debugging Iron Law and 3-Fix escalation rule.** "NO FIXES WITHOUT ROOT CAUSE
INVESTIGATION FIRST" is a hard gate — Phase 1 (root cause investigation) must complete before any
fix is proposed, in any of four phases (Root Cause Investigation → Pattern Analysis → Hypothesis and
Testing → Implementation), each of which must fully complete before the next begins. A structural
escalation rule: if three or more fix attempts fail, the agent MUST stop applying more fixes and
question the underlying architecture instead of continuing to iterate — repeated failed fixes are
treated as a signal of a deeper design problem, not bad luck.

**Defense-in-depth as a debugging/design technique** (not just security): validate the same
invariant at every layer data passes through (entry-point validation, business-logic validation,
environment guards, debug instrumentation) so that a given bug class becomes structurally impossible
rather than caught by a single fragile check.

## Practical how-tos (concrete workflows)

**The end-to-end pipeline:** `brainstorming` (idea → approved design doc) → `using-git-worktrees`
(isolate the work) → `writing-plans` (design → 2-5-minute atomic tasks with exact file paths and
verification steps) → `subagent-driven-development` (or `executing-plans` for
single-session/no-subagent-support environments) → `test-driven-development` (RED-GREEN-REFACTOR per
task) → `finishing-a-development-branch` (completion/merge).

**Running `brainstorming`:** invoke via `Skill` tool with `superpowers:brainstorming` (Claude Code),
`@superpowers:brainstorming` mention (OpenCode), or `activate_skill` (Gemini CLI, deprecated). It
enforces a `<HARD-GATE>`: no implementation action of any kind — not even scaffolding — until a
design is presented and the user has explicitly approved it, and this applies even to projects the
agent perceives as trivial ("simple" projects are explicitly called out as where unexamined
assumptions cause the most wasted work). Sequential checklist, no step skippable: (1) explore
project context (files/docs/commits) before asking anything; (2) offer a visual companion tool if
the topic has visual questions; (3) ask one clarifying question per message; (4) propose 2-3
approaches with trade-offs and a stated recommendation; (5) present the design section-by-section
and get approval per section; (6) write the design doc to
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`; (7) self-review the spec for
placeholders/TBDs, internal consistency, scope creep, and unresolved ambiguity; (8) have the user
review the saved file; (9) transition — the ONLY permitted next step is invoking `writing-plans`.

**Choosing between SDD and executing-plans:** use `subagent-driven-development` when you have a
plan, tasks are mostly independent, and you're staying in the current session (fresh subagent per
task, task-scoped review, faster iteration, no human-in-the-loop between tasks). Use
`executing-plans` when tasks are tightly coupled or you need a separate/parallel session. Neither
substitutes for having a plan first — if there's no plan, go back to brainstorming/planning.

**Writing a skill (the actual authoring loop):** design a 3+-pressure scenario relevant to the rule
you want to enforce → dispatch a subagent without any skill guidance, capture its excuse verbatim →
write the minimal `SKILL.md` addressing that specific failure (Overview, When to Use, and enough
Implementation detail) → re-run the same subagent with the skill present and confirm compliance →
run a harder/adjacent pressure variant to hunt for new loopholes → add explicit negations and a
rationalization-table entry for any new excuse found → repeat until the skill survives your hardest
pressure tests → run the CSO checklist on the description field (starts with "Use when...", zero
information about internal steps, third person, gerund-form kebab-case name) before shipping.

**Overriding a core skill for a project:** `mkdir -p .superpowers/skills/<skill-name>/` and place a
`SKILL.md` there with the same name — it shadows the core library version for that project without
touching the upstream repo.

## Gotchas & caveats

- The wiki's own examples show real failure modes from insufficiently-strict descriptions: a workflow-
  summarizing description caused an agent to perform only one code review pass when the skill's actual
  flowchart specified two (spec-compliance then code-quality) — verify your own skill/tool
  descriptions don't accidentally become a substitute for the real instructions.
- The 1% rule is intentionally extreme and could be read as encouraging excessive skill-checking
  overhead; the system's designers accept this cost specifically to counter the LLM's tendency to
  rationalize skipping.
- SUBAGENT-STOP means dispatched subagents do NOT get the meta-skill's protections/checks — a
  controller must ensure subagent prompts are otherwise well-scoped, since the subagent won't
  independently re-verify skill applicability.
- Gemini CLI support was fully removed in v6.1.0 after upstream EOL — any documentation or workflow
  assuming Gemini CLI integration is stale.
- SDD's cost-optimization advice (pick cheap models for mechanical tasks) is explicitly caveated:
  cheap models can take 2-3x more turns, which may increase both wall-clock time and total token cost
  despite a lower per-token rate — don't optimize purely on model price.
- The 3-Fix escalation rule in `systematic-debugging` means repeated fix attempts on the same bug are
  treated as a red flag for the AGENT itself to stop and reconsider architecture, not just a
  suggestion for a human reviewer.
- As of v6.0.3, SDD scratch files moved from `.git/` to a self-ignoring `.superpowers/sdd/` directory
  specifically because some environments (Claude Code among them) protect `.git/` from direct writes —
  a reminder that git-internal directories are not a safe general-purpose scratch space for agent
  tooling.
- Contributor guidelines for this project explicitly reject "AI-generated slop": no third-party
  dependencies, no "compliance" rewrites, no domain-specific skills, and new-harness integrations
  require a session transcript proving the bootstrap actually auto-triggers `brainstorming` — i.e.,
  they demand behavioral proof, not just code review, before accepting a new platform integration.

## Wiki pages used

Overview, Core Concepts (What Are Skills, The Mandatory Skill Check Protocol, Finding and Invoking
Skills, Skill Priority and Overriding), Creating Skills (What is a Skill, TDD Methodology, Claude
Search Optimization, Testing Skills with Pressure Scenarios, SKILL.md Format and Structure, Skill
Creation Checklist — partial), Key Skills Reference (using-superpowers meta-skill, brainstorming,
subagent-driven-development, systematic-debugging — partial read of test-driven-development). Not
read in depth: Getting Started platform-installation pages (Claude Code/Cursor/OpenCode/Codex/Gemini
CLI), Architecture section (Dual Repository Design, Skills Repository Management, Multi-Platform
Integration, Session Lifecycle and Bootstrap, Skills Discovery and Resolution, Tool Mapping Layer —
covered indirectly via Core Concepts), Platform-Specific Features section, Development Workflows
section (Complete Workflow Pipeline, Visual Brainstorming Companion detail, Using Git Worktrees,
Writing Implementation Plans, Executing Plans in Batches, Code Review Process, Finishing Development
Branches), writing-plans/test-driven-development/using-git-worktrees/Other Essential Skills detail
pages, Contributing Skills, Testing Infrastructure section, Technical Reference section (Directory
Structure, Configuration Files, Hooks System, Deprecated Commands, Environment Variables, Release
History), Glossary.
