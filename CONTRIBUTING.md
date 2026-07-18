# Contributing to DeepSkill

Thanks for helping grow the knowledge base. DeepSkill is a compilation of *grounded* knowledge — the bar for contributions is the same bar every existing brief was held to.

## The one hard rule

**Every claim must trace to fetched source text that was actually read — never to a model's guess or general knowledge.** DeepWiki wikis are AI-generated secondary sources; we treat them as a strong starting point, and load-bearing facts (exact APIs, version behavior, penalty figures, config values) should be verified against the real repository. A brief that reads plausibly but wasn't checked is worse than no brief.

## Ways to contribute

### 1. Harvest a new repo
1. Run the harvester: `python3 skills/deepwiki-harvester/scripts/fetch_wiki.py <owner>/<repo>`.
2. Distill `contents.md` into a brief following the standard sections: **What it is / Architecture / Key patterns & techniques / Practical how-tos / Gotchas & caveats / Wiki pages used**. Read the source — don't summarize the summary.
3. Add YAML frontmatter (`repo`, `deepwiki`, `github`, `harvested`, `cluster`) and the "distilled from…" disclaimer line, matching existing files under `knowledge/`.
4. Place it in the right `knowledge/<cluster>/` folder as `<owner>__<repo>.md`, add it to `knowledge/INDEX.md` and `docs/SOURCES.md`.

### 2. Sharpen a distillation
Tighten wording, add a missed mechanism, or fix an inaccuracy. Cite the wiki page you drew from in the PR description. Corrections that flag a previously-unverified claim are especially valued.

### 3. Extend or add a skill
Skills are cross-repo *syntheses*, not single-repo notes. If you add sources to a cluster, extend the matching `skills/<name>/SKILL.md` with an attributed section (name the source repo inline for each mechanism). A genuinely new domain (≥2–3 coherent sources) can become a new skill folder.

## Style

- Plain, factual register. No marketing language, no hype.
- Attribute distinctive mechanisms to their source repo inline (e.g. "LangGraph's Pregel engine…").
- Keep skill bodies dense but skimmable — headed sections, short paragraphs.
- `SKILL.md` frontmatter needs `name` (kebab-case) and `description` (a "when to use / what it covers" line).

## PRs

Open a PR against `main` with a short description of what you harvested or changed and which source pages you read. Small, focused PRs merge fastest.
