# Working on this codebase (for AI maintenance sessions)

From the Vibe Persona rules. Follow them in every maintenance session, not during a weekly run.

## Before any change (pre-code ritual)
State: the file and layer you will touch (see ARCHITECTURE.md); what it depends on and what depends on it; the existing pattern you will follow; your assumptions, each with what breaks if it is wrong; the plan in order. If a request conflicts with ARCHITECTURE.md, say so and stop before writing code.

## While changing
- Touch only what the task needs. Note other problems, do not fix them in passing ("drift noted, out of scope").
- Prefer the boring solution. Extend an existing file before creating one; keep files under 400 lines and functions short.
- No silent failures: a broad `except` must call `note_problem` or re-raise. Every `subprocess` call has a `timeout`. `tests/test_screens.py::test_code_health_hard_rules` enforces both.
- Every fix gets a regression test that fails without it. Parsers get edge-case tests: empty, missing label, OCR typo, two stores, no screens.
- Never edit or delete ledger records; add a correction or an amend with a reason.
- One push-back per topic: if the request is wrong, say why with the concrete failure, then do what the CEO decides.

## Before you finish (failure audit)
Rate each assumption 1 to 10. Anything under 7 gets a verification step. Run the full test suite, `sh scripts/run.sh lint` and `sh scripts/run.sh upkeep`. Replay the last weeks on a copy of the vault when the engine changed.

## After every change (summary)
CHANGES MADE (file: what and why). THINGS I DIDN'T TOUCH (and why). POTENTIAL CONCERNS. TECHNICAL DEBT LOGGED. TESTS ADDED. Record it with `sh scripts/run.sh upkeep --done "<summary>"`.
