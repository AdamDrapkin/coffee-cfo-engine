# The org chart: who works for the CFO

Rule of thumb: a program is faster, cheaper and more exact than an agent for anything mechanical. Agents are hired only for judgment, and each gets a small, separate job so one failure never blocks the rest. This follows the council pattern (strict orchestrator, isolated parallel workers, failed workers do not stop the run, a checklist before anything is written).

## Salaried staff (programs, free, always on, seconds)
| Role | Does | Where |
|---|---|---|
| Front desk | starts the session, waits for iCloud, counts files | `week` gate, `ready.py`, `health.py` |
| Screen readers (many at once) | read every screen with macOS Vision, 158 screens in about 15 s; the Mac worker pre-reads new screens so this is often 0 s | `native/ocr.swift`, `vision.py`, `watcher.py` |
| Bookkeepers (one per screen type) | turn text positions into fields: weekly results, newsletters, cost summary, exteriors, interiors, equipment, managers, marketing, menu items, blends, income statements, store performance, customer reviews | `screens.py` |
| Auditor | adds up cash flows and costs, revenue minus expenses, compares to what is already on file | parsers, `week.py` |
| Second reader | re-reads every number with a different recognizer and flags near-miss digits | `review.py cross_check` |
| Records clerk | removes duplicates, files new records as append-only notes, moves inbox files to raw | `week.py`, `absorb.py` |
| Inspector | lint, coverage gaps, corrections banners | `lint.py`, `coverage.py` |

## Hired agents (only when the packet asks)
| Role | How many | Trigger | Job | Output cap |
|---|---|---|---|---|
| CFO (you) | 1 | always | read the packet, decide, answer the CEO | about 10 lines |
| Screen reviewer | 1 per 6 unrecognized screens, all at once | NEEDS EYES | read the text dumps, open the image only if needed, return rows | 4k tokens each |
| Second-look auditor | 1 per 10 flagged numbers | CHECK THESE or READERS DISAGREE | compare the image to both readings, rule which is right | 2k tokens each |
| Parser engineer | 0 during a week; 1 between weeks | a layout appears twice in `parser-gaps.md` | write the parser and a test from the saved sample | offline |
| Deep analysts (optional, only for big money decisions) | 3, in parallel | CEO asks a stakes question | cash and risk, store operations, rules and truth; then the CFO merges | 1.5k each |

Headcount by workload (screens in the inbox): 1 to 60 screens and clean flags: CFO alone. 60 to 200: CFO plus reviewers only for unrecognized screens. Four months of backlog: run `week` in slices of the inbox (the engine handles any size), still CFO plus reviewers. More agents never help when the number of unrecognized screens is small; they only add startup cost and quota use.

## How to hire in Antigravity
Use `define_subagent` then `invoke_subagent` (or `manage_subagents`) for each reviewer in one step so they run together. Give each one only: its screen names, the path to the dumps, the review-desk instructions, and the row format. Do not give them the ledger. If subagents are unavailable, the CFO reviews the same items in one pass; it is slower but the result is identical.
