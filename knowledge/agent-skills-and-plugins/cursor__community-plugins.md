---
repo: cursor/community-plugins
deepwiki: https://deepwiki.com/cursor/community-plugins
github: https://github.com/cursor/community-plugins
harvested: 2026-07-13
cluster: agent-skills-and-plugins
---

> Distilled from the DeepWiki wiki for [`cursor/community-plugins`](https://deepwiki.com/cursor/community-plugins) on 2026-07-13. AI-generated secondary source — verify load-bearing facts against the repo.

# cursor/community-plugins — DeepWiki Knowledge

## What it is

`cursor/community-plugins` is the source code for **cursor.directory** — a community-run plugin
marketplace/directory web application for the Cursor code editor, not a plugin specification repo
itself. It is a Bun-managed monorepo containing a Next.js (App Router, Turbopack) frontend backed by
Supabase (PostgreSQL, using `pgmq` for job queuing), plus a companion CLI (`install-plugin`) that
downloads plugin components into a user's local `.cursor/` directory. Plugins here follow the "Open
Plugins" specification (open-plugins.com) and can bundle Cursor Rules (`.mdc`), MCP servers, Skills
(`SKILL.md`), Agents, Commands, Hooks, and LSP configs. The most distinctive and reusable content in
this wiki is the automated AI-driven security-scanning pipeline that vets every community submission
before it goes live — a working example of "review untrusted third-party agent-tooling submissions
with an agent" at production scale.

## Architecture

**Monorepo layout** (Bun workspaces): `apps/cursor` (the Next.js web app, `@directories/cursor`),
`packages/install-plugin` (the CLI, uses `@clack/prompts` for interactive UX), `supabase/migrations`
(versioned SQL schema). Root `package.json` pins dependency `overrides`/`resolutions` (e.g. forcing
Zod to `4.4.3` across all workspaces to avoid schema-validation version drift from third-party libs).

**Supply-chain security policy at the tooling level**: `bunfig.toml` sets `minimumReleaseAge: 604800`
(7 days) — Bun refuses to install any package version published less than a week ago, as a defense
against npm supply-chain attacks (the wiki names "Shai-Hulud worms" as the threat model). Core
high-velocity packages (`next`, `@types/bun`, `typescript`) are excluded from the delay so critical
updates aren't blocked. This is a concrete, working mitigation pattern independent of the plugin
system itself.

**Data model**: a `plugins` table (id, name, slug, `scan_status` enum [`pending`, `scanning`, `safe`,
`flagged`, `error`], `install_count`, `active` boolean) with a 1-to-many `plugin_components` table
(id, `plugin_id`, `type`, `content`, `metadata` JSONB). Three distinct Supabase client types are used
throughout: Server Client (standard authenticated requests), Admin Client (bypasses Row Level
Security for internal ops like the scan worker), Browser Client (client-side interactions).

**Plugin ingestion pipeline** — two entry paths converge on the same core logic:
1. *User submission*: `PluginForm` UI → `parseGitHubPluginAction` (Auto mode, parses a GitHub URL) or
   manual component entry → `createPluginAction` → `insertPlugin`.
2. *Bulk seeding*: `extract-from-github.ts` searches GitHub (`topic:cursor-plugin`, `topic:mcp`, code
   search for `.mcp.json` filenames), writes results to `plugins.jsonl` for manual inspection, then
   `insert-from-jsonl.ts` reads that file and calls `insertPlugin({skipScan: true})` for
   curated/trusted sources so they go live immediately as `active: true` without waiting on the AI
   scanner.

**GitHub component detection** (`parseGitHubPlugin` library) — the file/directory signals used to
auto-discover plugin components in a repo, directly useful as a checklist for what "counts" as a
Cursor-ecosystem plugin component:

| Component | Detection | Metadata extracted |
|---|---|---|
| Rules | `.cursor/rules/*.mdc` or `.cursorrules` | frontmatter: name, description, tags |
| MCP Servers | `.cursor/mcp.json` or `mcp.json` | server name, runtime config |
| Skills | `SKILL.md` | skill definition text |
| Agents | `.cursor/agents/*.md` | agent instructions |
| Commands | `.cursor/commands/*.json` | command triggers and scripts |
| Hooks | `.cursor/hooks/` directory | lifecycle hook scripts |
| LSP | `.lsp.json` | Language Server Protocol config |

Implementation notes: component-name slugs are capped at 80 characters to avoid `ENAMETOOLONG`
errors during Next.js static generation; a custom regex-based parser extracts YAML-like frontmatter
from `.mdc`/`.md` files; `fetchWithRateLimit` implements bounded retries (30s budget) and respects
GitHub's `retry-after` and `x-ratelimit-reset` headers.

**Security scanning pipeline** — the core novel subsystem. It's asynchronous/queue-based so a
1-3-minute agent task never blocks the submitting user's request:
1. `insertPlugin` calls `enqueuePluginScan(pluginId)` → `pgmq_public.send` RPC → message lands in the
   `plugin_scans` PGMQ queue.
2. `kickDrainAfterResponse()` uses Next.js `after()` to fire a non-blocking request to the drain
   route *immediately after* the HTTP response is sent to the user — reduces perceived latency
   without holding the request open.
3. `/api/queue/plugin-scans/drain` is the consumer: `maxDuration = 800` (seconds) to accommodate the
   long agent run; visibility timeout 900s (if the worker crashes mid-scan, the message reappears
   after 15 min); messages are "buried" (archived, flagged for admin) after `MAX_ATTEMPTS = 5` to stop
   poison-pill looping.
4. `runPluginScan(pluginId)`: loads the plugin + components, runs `findSimilarPlugins` (PostgreSQL
   trigram similarity RPC, `SIMILAR_THRESHOLD = 0.7`) to catch duplicate/"typo-clone" submissions,
   clones the GitHub repo to a temp dir, builds a prompt containing the repo file tree + component
   content + similar-plugin candidates, and runs a **Cursor SDK Agent (`composer-2`) in a sandboxed
   local mode** to produce a verdict.
5. `applyVerdict` parses the agent's JSON output against a `verdictSchema` and writes
   `plugins.scan_status` / `plugins.active`.
6. Error handling distinguishes: `FatalScanError` → archived, `scan_status = error`; a generic
   `Error` → left in queue to let the visibility timeout expire and get retried; `read_ct > 5` →
   archived and flagged for admin review (poison message).
7. A `recover-stuck-scans` cron job runs every 15 minutes, resets plugins stuck in `pending`/
   `scanning` for >15 min back to `pending`, and re-enqueues them.
8. DB permission hardening: a migration revokes `EXECUTE` on `pgmq_public` from `PUBLIC`, restricting
   queue access to the `service_role` only — prevents any authenticated user from manipulating the
   scan queue directly.

**Plugin state machine**: `Pending →(readNextPluginScan)→ Scanning →(runPluginScan success)→ Safe
→(auto-publish)→ Active`; `Scanning →(AI warning)→ Flagged →(approvePluginAction)→ Active` or
`→(declinePluginAction)→ [deleted]`; `Scanning →(FatalScanError)→ Error →(rescanPluginAction)→
Scanning`.

**Installation mechanisms** (two parallel paths depending on component type):
- **Deep links** (`cursor://` URI scheme) for one-click install directly into the editor:
  `rule?name=...&text=...` for Rules, `command?name=...&text=...` for Commands,
  `mcp/install?name=...&config=...` (config Base64-encoded) for MCP servers. Capped at
  `MAX_DEEPLINK_URL_LENGTH = 8000` chars — beyond that, OS protocol handlers or Cursor's internal
  parser may truncate/malform the URI, so the UI falls back to a "Copy to Clipboard" action.
- **CLI** (`npx @cursor/install-plugin <slug>` / `bunx install-plugin <slug>`) for complex components
  or when deep-linking isn't supported — hits `GET /api/plugins/[slug]`, which validates the plugin
  is `active`, transforms `plugin_components` rows into a clean `{type, name, content, metadata}`
  JSON payload, and returns it to the CLI.

## Key patterns & techniques

- **Non-blocking scan kickoff via `after()`**: rather than making the user wait on the agent scan
  synchronously, or relying purely on a cron poll, the app fires the queue-drain request
  fire-and-forget immediately after responding — a pattern worth reusing anywhere a web request needs
  to trigger a slow background agent job with minimal added latency.
- **Trigram-similarity duplicate detection before the LLM scan**: `findSimilarPlugins` runs a cheap
  PostgreSQL-native trigram similarity check (threshold 0.7) and feeds the candidates into the
  security agent's prompt, rather than relying on the LLM alone to notice near-duplicate/typo-clone
  submissions — combines deterministic pre-filtering with LLM judgment.
- **Poison-message handling for agent-backed queues**: capping `MAX_ATTEMPTS` and distinguishing fatal
  vs. retryable errors is a reusable pattern for any pipeline where a queue consumer invokes a
  non-deterministic AI agent that might fail unpredictably.
- **`install-plugin` CLI flags**: `--force` (overwrite without prompting), `--dry-run` (log intended
  changes only), `--all` (install every component), `--only <slugs>`, `--exclude <slugs>` — a
  reasonable flag surface for any "selective component installer" CLI. Interactive selection (when no
  flags given) uses `clack.multiselect` so users browse component descriptions and choose which to
  apply.
- **Per-component-type installers with different merge semantics**: `rule`/`agent`/`command` write a
  new file (`.cursor/rules/<slug>.mdc`, etc.); `mcp_server` and `hook` instead *merge* into a shared
  JSON file (`.cursor/mcp.json`'s `mcpServers` key, `.cursor/hooks/hooks.json`) via
  read-modify-write (`readJsonFile` → merge → `writeJsonFile`) — because multiple installed plugins
  need to coexist inside the same config file rather than overwriting each other.
- **Install-count rate limiting to prevent leaderboard gaming**: `install-global` (20 req/hour) and
  `install-per-plugin` (3 req/24h, keyed by `ip:pluginId`) rules gate the `increment_install_count`
  RPC — a concrete anti-abuse pattern for any public "trending/most-installed" ranking feature.

## Practical how-tos

- Local dev: `bun install` → `cp apps/cursor/.env.example apps/cursor/.env` (set
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`; optional
  `ADMIN_USER_IDS`, `CURSOR_API_KEY` for the scan worker) → apply SQL from `supabase/migrations/` →
  `bun dev` (runs `next dev --turbopack`, serves at `localhost:3000`).
  `bunfig.toml`'s 7-day `minimumReleaseAge` applies to all installs, so pinning a brand-new package
  version will fail until it ages out.
- Seed data locally: `bun run seed:extract` (crawls GitHub, writes `plugins.jsonl`) then
  `bun run seed:insert` (upserts into Supabase).
- CLI dev: in `packages/install-plugin`, `bun install` then `bun run dev` (TypeScript watch mode);
  the published binary entry point is `./dist/index.js`.
- Install a plugin from the directory into a project: `bunx install-plugin <slug>` (or
  `npx @cursor/install-plugin <slug>`), optionally with `--all`/`--only`/`--exclude`/`--force`/
  `--dry-run`.

## Gotchas & caveats

- This wiki documents a *marketplace web application*, not a plugin authoring spec — if the goal is
  "how do I write a Cursor plugin," the component-detection table above (which files/dirs get
  recognized) is the useful part; the rest is Next.js/Supabase implementation detail specific to this
  one directory site.
- Deep links silently degrade at 8000 characters — any automation generating install links for large
  MCP configs or long rule text needs to check length and fall back to the CLI/clipboard path.
- Bulk-seeded plugins (`insert-from-jsonl.ts`) explicitly skip the AI security scan
  (`skipScan: true`) and go `active` immediately — this is a trust boundary: curated/admin-sourced
  plugins bypass the same scrutiny applied to public user submissions.
- The security scan depends on a specific proprietary component (Cursor SDK Agent `composer-2`
  running in "sandboxed local mode") — the pipeline architecture (queue → agent → verdict schema →
  status update) is portable, but the scanning model itself is not open/documented further in this
  wiki.

## Wiki pages used

Overview; Getting Started & Local Development; Monorepo Structure; Plugin System; Plugin Submission &
GitHub Ingestion; Plugin Security Scanning Pipeline; Plugin Detail View & Installation; install-plugin
CLI. (structure.md also lists Database Schema & Migrations, Server-Side Data Queries, Supabase Client
Utilities, Server Actions, MCP Servers Directory, User Profiles/Social Features, Companies Directory,
Frontend Application Shell, and other Infrastructure pages — not read in full; those cover generic
Next.js/Supabase app plumbing with lower marginal value for agent-tooling knowledge.)
