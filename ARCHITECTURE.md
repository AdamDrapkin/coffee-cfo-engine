# Architecture

## System overview
Coffee Inc. 2+ knowledge base. The CEO plays and uploads screenshots. A program reads and files every screen; an AI chat writes the analysis. Python owns every write; the AI never writes ledger files. History is append-only.

## Layers (dependencies point down only)
```
INTERFACE    scripts/coffee.py (commands), scripts/run.sh, the Mac worker (watcher.py)
SERVICE      week.py (orchestrates a week), absorb.py (files answers, analyses, reviewed rows), decisions.py, lookup.py, upkeep.py
DOMAIN       week_dedupe.py, week_store.py, analysis.py, briefing.py, packet.py, audit.py, review.py, facts.py, search.py, state_page.py, digest.py, hubs.py, corrections.py, coverage.py, health.py
PARSERS      screens.py (classify + dispatch), parsers_news / parsers_build / parsers_menu / parsers_store
DATA         ledger.py (append-only writer), validate.py, lint.py, render.py, index.py, db/ (SQLite: schema and migrations, load, queries, sync, export, totals)
INTEGRATION  vision.py + native/ocr.swift (macOS text reading), gemini_client.py (optional agy backend), sync.py (git), frames.py, inbox.py, ready.py
SHARED       screens_core.py (text boxes, money helpers), util.py (paths, frontmatter, locks, note_problem)
```
Rules: parsers know layouts and nothing about the ledger; the ledger writer knows nothing about screens; the packet and briefing only read. Nothing below SHARED imports upward.

## Data flow of a week
inbox (iCloud) -> ready gate -> vision (cached by the worker) -> screens.classify/parse -> week_store (store, review, menu-week updates) -> week_dedupe (drop what is on file, detect real changes) -> absorb.file_text (validate, write ledger notes, briefing, hubs) -> audit (read back and compare) -> packet -> chat -> analysis-absorb (analysis briefing, decision, unknowns, game facts) -> state_page.

## Where the truth lives
- Screens: iCloud only (`raw/screenshots/`, not in git). Their full text: `raw/ocr/screens/` (in git).
- Facts as records: `wiki/ledger/` (weeks, stores, menu-weeks, reviews, decisions, catalog, events, competitors, corrections).
- Judgment: `wiki/briefings/*-analysis.md`. Current situation: `.agents/skills/coffee-week/references/company-state.md` (generated).
- Answers to questions: `coffee facts <topic>` then `coffee find <words>`. Never a picture.

## Key design decisions (ADR)
- **ADR-001 Deterministic reading, AI judgment.** Reading screens is mechanical (macOS text recognition, parsers, cross-checks); the AI only analyzes. Consequence: a week runs in seconds and every number is traceable.
- **ADR-002 Append-only ledger, corrections as records.** Nothing is edited or deleted; a wrong fact gets a correction note and a banner. Consequence: full history, larger folders.
- **ADR-003 One weekly menu record per store.** Per-item sales, price, unit cost and margin live in `menu-weeks`; catalog amends only for real changes (price change, unit cost 5% or more, margin 3 points or more). Consequence: item questions never need images.
- **ADR-004 A comparison is only ever with the week before.** A missing week is reported as missing, never replaced by an older week. Consequence: no silent wrong deltas.
- **ADR-005 No silent failures.** Every broad `except` records the problem (`note_problem` -> `.coffee-work/problems.log`); every subprocess call has a timeout. Enforced by tests.
- **ADR-006 Screenshots stay in iCloud, not git.** The repo keeps text only. Consequence: the backup grows by a fraction of a megabyte per week.
- **ADR-007 Decisions and unknowns have explicit status.** `decide` and `resolve` close them with a reason. Consequence: nothing stays "pending" forever.
- **ADR-008 Key-based model access is not supported.** The AI Studio backend was removed.
- **ADR-009 SQLite for facts, markdown for judgment (built through Sprint 7; the cutover, Sprint 8, is decided later).** A SQLite file at `~/.coffee-inc-kb-work/coffee.db` (never in iCloud) will hold every number, date, status and list, keyed by store and week. Prose (analyses, playbooks, rules) stays as markdown; pages are generated from the database. Until the cutover the ledger notes stay as the fallback and a comparison command proves the two agree. Consequence: exact, fast, multi-store queries and no partial weeks (one transaction per week); cost: a migration, and one writer only. Acceptance tests: `sh scripts/run.sh golden check` (frozen answers), `db compare` (database vs ledger totals) and `db verify` (rebuild from the text export). Status today: the ledger stays the writer and the database is rebuilt from it in one transaction after every filing; readers use the database only while its ledger signature matches, and fall back to the ledger (with a note) otherwise. Text export goes to `wiki/db-export/` daily.

## Database
File: `~/.coffee-inc-kb-work/coffee.db` (outside iCloud; `dbhealth` refuses synced folders). Commands: `db init | status | refresh | compare | export | verify | check`. Tables are keyed by store and week (`store_week`, `menu_week`, `review`, `decision`, `unknown`, `lever`, ...); views `v_item_rank`, `v_vs_last_week`, `v_open_decisions`, `v_store_compare`; full-text search over reviews, screens and briefings. Migrations are numbered SQL files in `coffeekb/db/migrations/`.

## Environment
`COFFEE_VAULT` (vault path), `COFFEE_WORK` (scratch), `COFFEE_POLL`, `COFFEE_BACKEND` (optional agy). No secrets are stored; `sync.py` refuses to push anything that looks like a key.

## Known limits
Weekly figures are followed for the store with the most records; a second store works but its weekly history is read with `facts`. Files over 400 lines and functions over 80 lines are reported by upkeep as drift (`week.run`, `hubs.rebuild`, `briefing.build` are the current ones).
