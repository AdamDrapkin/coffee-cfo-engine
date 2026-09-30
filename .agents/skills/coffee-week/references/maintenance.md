# How this skill is maintained

## How the files are used
Only `SKILL.md` loads when the skill triggers. The chat opens a reference file only when SKILL.md tells it to, at the step that needs it. Scripts are run, not read.

## What updates itself (AUTO)
| File | Written by | When |
|---|---|---|
| `references/parser-gaps.md` | `review.record_gaps` inside `coffee week` | each time a screen layout is not recognized; a repeat layout raises its count |
| `references/company-state.md` | `state_page.write` after `coffee week` and `analysis-absorb` | the current setup, weekly history, decisions, unknowns and corrections |
| `references/run-log.md` | `review.log_run` inside `coffee week` | after every run: date, screens, recognized, needing eyes, flags, seconds |
| `.coffee-work/week/latest.md` and `review/*.txt` (in the work folder, not the skill) | `coffee week` | every run, overwritten |

## What is hand-written and stays until someone edits it
`SKILL.md`, `org-chart.md`, `pipeline.md`, `review-desk.md`, `self-healing.md`, `token-budget.md`, `output-contract.md`, `run-postmortem.md`. Their numbers (for example the time budget) are measurements from one date; check `run-log.md` for current ones and update the file when they drift.

## How the hand-written files get queued and redone
After every `coffee week` the engine runs `upkeep` and writes `references/upkeep-queue.md` (AUTO). An item is queued when:
1. a layout in parser-gaps.md has been seen 2 or more times (build the parser),
2. the last runs of 60 screens or fewer have a median over 45 s (speed regression),
3. 3 of the last 5 runs had screens needing eyes (recognition drift), or
4. the engine code changed since the docs were last reviewed (a hash of the engine files is compared with `.reviewed.json`).
The packet then ends with one UPKEEP DUE line. The weekly chat only tells the CEO; it must not do the work during a week, because it is not allowed to edit scripts or docs.
The work is done in a maintenance session (Claude Code, or a chat the CEO opens for it): read upkeep-queue.md, do each item, run tests and lint, then `sh scripts/run.sh upkeep --done "what changed"`. That records the new hash, appends to `upkeep-log.md` and clears the queue. `sh scripts/run.sh upkeep` shows the queue at any time.

## Updating after a new problem
1. If `parser-gaps.md` shows a layout twice, build the parser in `scripts/coffeekb/screens.py` with a synthetic test in `tests/test_screens.py`, then move that line from gaps to built in the file.
2. If a new failure appears, add a row to `self-healing.md` (symptom, cause, response, action).
3. If a run is unusually slow, add a dated postmortem next to the existing one; never rewrite the old one.
4. The parts of this skill that describe the engine must match `week.py`; the test suite fails if the engine changes behavior, which is the cue to revisit them.

## Maintenance sessions follow CONTRIBUTING-AI.md and ARCHITECTURE.md (vault root)
Pre-code ritual, scope discipline, failure audit and a change summary recorded with `upkeep --done`. Drift (files over 400 lines, import cycles, long functions, problems.log entries, slow filing, repo size) appears in the upkeep queue automatically.

## Database
The SQLite database (ARCHITECTURE.md, ADR-009) is rebuilt from the ledger after every filing and exported to text daily by the worker. The upkeep queue reports a stale database, a failed health check or an old export. After any engine change run `sh scripts/run.sh golden check`, `db compare` and `db verify`.
- Screenshots: originals in raw/screenshots are deleted after 3 days (scripts/coffeekb/retention.py, run daily by the worker). The full text of every screen stays in raw/ocr/screens/ and all values are in the ledger. `--reprocess` only works on screenshots still retained.
