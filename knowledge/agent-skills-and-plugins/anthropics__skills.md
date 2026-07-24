---
repo: anthropics/skills
deepwiki: https://deepwiki.com/anthropics/skills
github: https://github.com/anthropics/skills
harvested: 2026-07-09
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`anthropics/skills`](https://deepwiki.com/anthropics/skills) on 2026-07-09. AI-generated secondary source — verify load-bearing facts against the repo.

# anthropics/skills — Distilled Knowledge

## What it is

`anthropics/skills` is Anthropic's reference implementation of the **Agent Skills** standard, a
community specification (published at agentskills.io) for defining reusable AI capabilities.

A "skill" is a self-contained directory whose only mandatory file is `SKILL.md` — YAML frontmatter
plus Markdown instructions — that Claude loads dynamically at runtime when a user's request matches
the skill's `description`.

The repo has three roles:
1. **Production reference** — `document-skills` (docx, pdf, pptx, xlsx) power Claude's actual
   production document capabilities; licensed source-available, not open source.
2. **Educational examples** — `example-skills` (skill-creator, mcp-builder, algorithmic-art, canvas-
   design, brand-guidelines, doc-coauthoring, frontend-design, internal-comms, slack-gif-creator,
   theme-factory, web-artifacts-builder, webapp-testing, and others), licensed Apache 2.0.
3. **Template + spec** — a `template/SKILL.md` starter and `spec/agent-skills-spec.md` pointing to the
   external standard.

Skills deploy across three surfaces: Claude Code (via `/plugin marketplace add` + `/plugin
install`), Claude.ai (pre-integrated for paid plans, or custom upload), and the Claude API (`POST
/v1/skills`, attached to messages via `skills=[skill-id]`).

## Architecture (how it's built, key components)

**Repository layout:**
```
anthropics/skills/
├── skills/                    # flat directory, one subfolder per skill
│   ├── docx/, pdf/, pptx/, xlsx/      # document-skills plugin (source-available)
│   ├── skill-creator/, mcp-builder/, ...  # example-skills plugin (Apache 2.0)
│   └── claude-api/                   # claude-api plugin (Apache 2.0)
├── spec/agent-skills-spec.md  # pointer to external agentskills.io spec
├── template/SKILL.md          # starter template
└── .claude-plugin/marketplace.json  # plugin registry
```

**Marketplace/plugin system.** `.claude-plugin/marketplace.json` is the central registry. Top-level
fields: `name`, `owner` (name/email), `metadata` (description/version), `plugins` (array). Each
plugin entry has `name`, `description`, `source` (base path, always `"./"` in this repo), `strict`
(boolean), and `skills` (array of relative paths like `./skills/pdf`). All plugins currently set
`strict: false`, meaning a malformed/missing `SKILL.md` in one skill does not block the rest of the
plugin from loading (strict:true would fail the whole plugin on any single bad skill). Three plugins
exist: `document-skills` (4 skills), `example-skills` (12 skills), `claude-api` (1 skill).

**Discovery/activation pipeline:** parse marketplace.json → enumerate `plugins[].skills[]` paths →
match user intent against each skill's `name`/`description` frontmatter → resolve `source +
skill_path` → load `SKILL.md` → parse YAML frontmatter → parse Markdown body → activate skill
context for the conversation.

**Progressive Disclosure — the three-level loading model** (the single most important architectural
idea in this repo):

| Level | Component | Content | Context impact |
|---|---|---|---|
| 1 | Metadata | `name` + `description` from frontmatter | Always in context (~100 words) |
| 2 | Body | SKILL.md Markdown instructions | Loaded only when the skill triggers |
| 3 | Resources | `scripts/`, `references/`, `assets/` | Loaded/executed on demand |

This exists specifically to manage context-window budget: Claude never pre-loads full instructions
for skills it isn't using.

**skill-creator** is the most operationally complex skill in the repo — a meta-skill that builds and
iteratively improves other skills. It orchestrates a CI/CD-style pipeline: draft SKILL.md → spawn
parallel subagents (with-skill vs. baseline) → grade outputs against assertions → aggregate metrics
→ launch an HTML review viewer → iterate on feedback → optimize the triggering description via a
train/test-split loop → package as a `.skill` file. Internal layout: `agents/` (grader.md,
comparator.md, analyzer.md — subagent prompt files), `scripts/` (run_loop.py,
improve_description.py, run_eval.py, aggregate_benchmark.py, package_skill.py, quick_validate.py,
utils.py), `eval-viewer/` (generate_review.py, generate_report.py), `assets/eval_review.html`,
`references/schemas.md`, `evals/evals.json`.

## Key patterns & techniques (the transferable knowledge)

**SKILL.md format.** Required YAML frontmatter fields: `name` (kebab-case, `^[a-z0-9-]+$`, no
leading/trailing/double hyphens, max 64 chars) and `description` (plain text, no `<`/`>` characters,
max 1024 chars — angle brackets are banned because they collide with placeholder syntax like
`<skill-name>`). Optional fields: `license`, `allowed-tools`, `metadata`, `compatibility` (string,
max 500 chars). The full allowed-key set enforced by validation is `{name, description, license,
allowed-tools, metadata, compatibility}` — any other top-level key fails validation. Markdown body:
H1 title, instructions, `## Examples`, `## Guidelines`; aim to keep the body under 500 lines and
`references/` files under 300 lines (add a TOC if larger).

**Description-as-trigger pattern.** The `description` field is the *sole* triggering mechanism —
Claude decides whether to activate a skill purely by matching intent against this string. This makes
description quality a first-class engineering concern, not an afterthought. Writing guidance
distilled from the skill-creator's own instructions and its `improve_description.py`:
- Use imperative/pushy phrasing to combat *under*-triggering: not "How to build a simple dashboard"
  but "Make sure to use this skill whenever the user mentions dashboards... even if they don't
  explicitly ask for a 'dashboard.'"
- Describe both WHAT the skill does and WHEN to use it.
- Focus on user intent/goals, not implementation details, to avoid overfitting to exact phrasings.
- Hard cap: 1024 characters (soft target ~100-200 words).

**Automated description-optimization loop (transferable eval pattern).** `run_loop.py` treats "does
this skill trigger correctly" as a supervised learning problem to avoid overfitting the description
to memorized eval prompts:
1. Generate ~20 trigger queries (10 should-trigger, 10 should-not-trigger), stratified.
2. Split 60/40 into train/test sets via `split_eval_set()` (stratified by `should_trigger` to keep
   balance).
3. Evaluate the current description on train, running each query 3x for a reliable trigger-rate
   estimate (LLM triggering isn't deterministic).
4. Call Claude (via `claude -p` subprocess) with `improve_description.py`, feeding it the specific
   FAILED-TO-TRIGGER and FALSE-TRIGGER cases from history, to propose a rewritten description.
5. Re-evaluate on train+test; track history so the same failed rewrite isn't repeated.
6. Repeat until max iterations or no further improvement.
7. **Select the final description by test-set score, not train-set score** — this is the overfitting
   guard, directly borrowed from classic ML methodology and applied to prompt/description engineering.

Notable implementation detail: `improve_description.py` strips the `CLAUDECODE` env var before
shelling out to `claude -p`, specifically to allow nesting a `claude -p` call inside an
already-running Claude Code session (otherwise the CLI may refuse to nest).

**Parallel with-skill vs. baseline subagent testing.** For every eval case, skill-creator spawns two
subagents *in the same turn*: one with the skill loaded, one without (baseline) or with the previous
skill version (for regression testing when improving an existing skill). This produces paired
comparison data (grading.json + timing.json for each arm) rather than just testing "does it work,"
letting the pipeline quantify the skill's actual lift over no-skill/old-skill baselines (pass_rate
delta, token delta, time delta).

**Exact-field-name contracts between pipeline stages.** The docs explicitly flag that
`grading.json`'s expectations array must use the literal field names `text`, `passed`, `evidence` —
not synonyms like `name`/`met`/`details` — because the downstream HTML viewer depends on those exact
keys. This is a general lesson for any multi-stage JSON pipeline: document and enforce the schema
contract at each interchange point, since a silent field-rename anywhere in the chain breaks
consumers with no error.

**Layered validation before packaging.** `quick_validate.py` runs 10 sequential gates (file exists →
starts with `---` → frontmatter regex matches → YAML parses → is a dict → keys are in the allowed
set → `name` present → `description` present → name format valid → description format valid →
compatibility format valid if present), short-circuiting on first failure and printing exactly one
message. `package_skill.py` calls this validator before zipping a skill directory into a `.skill`
file, and excludes `__pycache__`, `node_modules`, `*.pyc`, `.DS_Store` globally plus a root-level
`evals/` directory (test fixtures shouldn't ship in the distributable).

## Practical how-tos (concrete workflows)

**Install and use a skill (Claude Code):**
```bash
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
# or: /plugin install example-skills@anthropic-agent-skills
```
Then invoke with plain natural language: "Use the PDF skill to extract the form fields from
path/to/file.pdf."

**Create a new skill manually:**
1. `mkdir skills/my-skill-name` (kebab-case).
2. Write `SKILL.md` with frontmatter `name`/`description` + Markdown body (title, instructions, `##
   Examples`, `## Guidelines`).
3. Add `scripts/` (deterministic code, executed not loaded into context), `references/` (on-demand
   docs, <300 lines each), `assets/` (templates/icons/fonts used in output) as needed.
4. Validate: `python quick_validate.py skills/my-skill-name` — exit 0 = valid, exit 1 = fails with a
   specific message.
5. Package: `python skills/skill-creator/scripts/package_skill.py <path/to/skill-folder> [output-dir]`
   → produces a `.skill` zip.
6. To join the marketplace: add the skill's relative path to the appropriate plugin's `skills` array in
   `.claude-plugin/marketplace.json`.

**Build/improve a skill with skill-creator (the automated loop):** capture intent (what should it do
/ when should it trigger / expected output format / worth writing evals?) → interview for edge cases
→ draft SKILL.md → write 2-3 realistic eval prompts to `evals/evals.json` (assertions left empty at
this stage) → spawn parallel with-skill/baseline subagents → draft assertions while runs are in
flight → capture `timing.json` on completion notifications → grade via `agents/grader.md` →
aggregate via `scripts/aggregate_benchmark.py` (→ `benchmark.json`/`benchmark.md`) → launch
`eval-viewer/generate_review.py` (HTTP server, or `--static <path>` for headless environments) →
read `feedback.json` → iterate into a new `iteration-N+1/` directory if unsatisfied → once
satisfied, run `scripts/run_loop.py --eval-set --skill-path --model --max-iterations 5 --verbose` to
optimize the description → `package_skill.py` to ship.

**Workspace layout skill-creator produces** (sibling directory to the skill, kept separate from
skill source):
```
<skill-name>-workspace/
├── skill-snapshot/           # old skill copy, for regression baselines
├── evals/evals.json
├── iteration-1/
│   ├── benchmark.json / benchmark.md
│   ├── eval-0-<name>/
│   │   ├── eval_metadata.json
│   │   ├── with_skill/{outputs/, grading.json, metrics.json, timing.json}
│   │   └── without_skill/{outputs/, grading.json, metrics.json, timing.json}
│   └── eval-1-<name>/...
└── iteration-2/...
```

## Gotchas & caveats

- Angle brackets (`<`, `>`) are hard-banned in `description` — validation fails immediately, not a
  style suggestion.
- `name` max 64 chars, `description` max 1024 chars, `compatibility` max 500 chars — these are
  enforced, not advisory.
- Frontmatter keys outside `{name, description, license, allowed-tools, metadata, compatibility}` fail
  validation; nested keys under `metadata` are NOT checked (only top-level keys are validated).
- skill-creator's full feature set (parallel subagents, browser viewer, quantitative benchmarking,
  description optimization via `run_loop.py`, blind comparison) is only fully available in Claude Code
  and "Cowork"; on Claude.ai it runs sequentially with no baseline arm, no browser viewer (inline in
  conversation instead), and no optimization loop. Only packaging works identically everywhere.
- The `run_loop.py` train/test split exists specifically because evaluating and selecting a
  description by the same data it was tuned on overfits; always report/select by test score.
- Because triggering is LLM-driven and non-deterministic, `run_eval.py` runs each query 3x to get a
  stable trigger-rate signal rather than trusting a single run.
- Document skills (docx/pdf/pptx/xlsx) are "source-available," explicitly NOT Apache-licensed like the
  example skills — do not assume uniform licensing across the repo.
- `strict: false` is used on every plugin in this repo; a plugin author flipping to `strict: true`
  would make one broken skill block the entire plugin from loading.

## Wiki pages used

Overview, Quick Start, Core Concepts, Skills System Architecture, SKILL.md Format Specification,
Marketplace and Plugin System, Skill Creator, Skill Creator Workflow, Developer Guide, Creating a
New Skill, Skill Validation, Skill Packaging and Distribution, Technical Reference, Agent Skills
Specification (partial). Not read in depth: Skills Catalog / Document Skills / individual
DOCX/PDF/PPTX/XLSX pages, Example Skills, Claude API Documentation Skill, Test Case Creation and
Evaluation, Review and Benchmarking, Description Optimization (child page — covered indirectly via
Skill Creator + Developer Guide), Managed Agents API Reference, Third-Party Dependencies, Repository
Structure, Glossary, Platform Integration (partial, via Marketplace page overlap).
