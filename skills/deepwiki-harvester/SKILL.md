---
name: deepwiki-harvester
description: Use when harvesting architecture knowledge from public repositories through DeepWiki or turning multiple repository wikis into grounded briefs.
---

# DeepWiki Harvester

Harvest repository knowledge without treating generated wiki text as primary evidence.

## Workflow

1. Define the repository list and the question each brief must answer.
2. Use the host's configured DeepWiki MCP tools to fetch the repository structure and full wiki contents.
3. Save one brief per repository under a domain directory.
4. Record repository, DeepWiki page, fetch date, and source links.
5. Separate mechanisms stated in the wiki from your synthesis.
6. Spot-check load-bearing claims against the actual repository or official documentation.
7. Add the brief to the knowledge index only after its source trail is complete.

## Brief contract

Each brief must contain:

- repository and upstream links;
- harvest date;
- architecture and component boundaries;
- concrete mechanisms worth reusing;
- operational or security constraints;
- explicit uncertainty where wiki text is incomplete;
- source attribution for distinctive claims.

Never imply that DeepWiki is a primary source. Never invent missing APIs, defaults, versions, benchmarks, or guarantees.

## Multi-repository synthesis

Cluster mechanisms by problem, not by repository popularity. Preserve provenance at the claim level and distinguish repeated patterns from one-off designs. A pattern is reusable only when its preconditions and failure modes are stated.

Use the existing corpus format in [the knowledge index](../../knowledge/INDEX.md).
