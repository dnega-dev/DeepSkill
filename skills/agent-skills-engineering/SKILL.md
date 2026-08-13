---
name: agent-skills-engineering
description: Use when creating, reviewing, packaging, testing, or improving portable agent skills, plugins, triggers, hooks, or instruction bundles.
---

# Agent Skills Engineering

Build small instruction packages that trigger reliably and remain testable.

## Design rules

- Put only `name` and a trigger-focused `description` in frontmatter.
- Start descriptions with “Use when” and describe conditions, not the workflow.
- Keep the main file concise; move large references and deterministic tools into dedicated folders.
- Prefer one clear responsibility per skill.
- State tool and host assumptions explicitly.
- Make destructive or external actions require explicit authority.

## Workflow

1. Write representative prompts that should and should not trigger the skill.
2. Run them without the skill and record the failure.
3. Write the minimum instructions that correct that failure.
4. Re-run the prompts and inspect behavior, not merely prose validity.
5. Add regression prompts for discovered rationalizations and edge cases.
6. Validate frontmatter, paths, cross-references, scripts, and line count.

## Boundaries

Skills encode reusable judgment and procedure. Use hooks for unconditional enforcement, scripts for deterministic operations, and ordinary project documentation for human-only explanation.

Source briefs: [agent skills and plugin ecosystems](../../knowledge/agent-skills-and-plugins/).
