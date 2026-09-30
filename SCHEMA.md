# Schema

## Identity
- Domain: Coffee Inc. 2+ (Apple Arcade), company Panda's Coffee
- Settings: Normal difficulty, 2 competitors, USD, $800,000 starting capital
- Source types: game screenshots, typed notes, sourced research

## Layers
- `raw/`: immutable inputs (master prompt, screenshots, research outputs)
- `wiki/`: LLM-maintained notes, written only by Python from validated output
- `core/`: modular Gemini context pack split from the master prompt
- `exports/`: generated from the wiki, never hand-edited

## Directory structure
```
inbox/          drop zone from the phone
raw/assets/     cfo-master-prompt.md
raw/screenshots/  {date}-wk{game_week}-{type}-{n}.png
raw/research/   sourced research outputs
core/           persona, intake, formats, router, playbooks, output contract
wiki/index.md   master index
wiki/log.md     append-only log
wiki/knowledge-base/  one note per game systems section
wiki/ledger/    weeks, stores, cities, competitors, decisions,
                capital-allocation, loans, investments, acquisitions
wiki/briefings/ every CFO briefing and weekly close, dated
wiki/tests/     in-game experiments and results
wiki/decisions/ process decisions for this toolchain
wiki/outputs/quota-log.md  every Gemini call
exports/        the two master-prompt Markdown files
scripts/        Python toolchain
tests/          pytest, fixtures marked SYNTHETIC
```

## Page frontmatter
```yaml
---
title: "Page Title"
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
summary: "One to two sentences"
tags: [tag]
type: knowledge | ledger | briefing | test | decision | index
status: draft | review | final
---
```

## Ledger rows
Every ledger note carries `source_screenshot`, `confidence` (High, Moderate, Low, Unknown) and `extracted_by`.
Structured numbers live in frontmatter (week, revenue, cogs, ending_cash, debt) so Dataview can render tables. Dataview is optional.

## Confidence labels
- High: clear screenshots, reliable research, sufficient data
- Moderate: partial data, important inputs missing
- Low: preliminary inference, no major irreversible decision on it
- Unknown: no adequate evidence

## Mechanic labels
Confirmed, Community, Inference, Unknown.

## Log entry format
`## [YYYY-MM-DD] <operation> | <title>`
Operations: init, ingest, query, close, research, absorb, export, lint, decision.

## Links and hubs
- Every page must be reachable from `wiki/hubs/map.md` by following links, and no page may be isolated. `coffee lint` fails otherwise.
- Hub pages under `wiki/hubs/` are generated after every filing (briefings, weeks, decisions, events, catalog, stores, cities, competitors, capital, knowledge, process, rules, archive). Each store also gets a generated dossier page. Never edit them by hand.
- Ledger notes are append-only, so old ones are linked FROM hubs and dossiers rather than edited. New ledger notes carry their own links: their hub, related stores and options, and what an amendment amends. Each briefing links the previous briefing.
- Related links come from exact name matching; a name shared by two catalog categories is never guessed.
