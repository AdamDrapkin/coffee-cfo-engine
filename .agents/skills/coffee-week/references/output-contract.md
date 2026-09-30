# Answer format in one page

Write the briefing (headings Recommendation, Confidence, Next Upload Request) then ONE fenced json block.

Fields: `intake`, `extraction`, `ledger_updates`, `next_upload_request`, `ceo_words` (the CEO's message exactly), `inbox_files_used`, `mobile_summary` (at most 12 lines), and `bundle` (the id from the packet) when you build on the engine's readings.

Ledger targets: week, store, city, competitor, decision, capital-allocation, loan, investment, acquisition, assumption, event, test, catalog, correction.

Rules the validator enforces: every number in ledger_updates appears in an extraction row, the CEO's words, the note, or the engine bundle; Confidence High needs real extraction rows; an amend needs a reason; a week is never overwritten; corrections need `claim` and `correction`. No emdashes. Never mention numbers from old Coffee Inc. 2 as confirmed for 2+.

Write the answer to `inbox/answer-paste.md` after the marker line, then `sh scripts/run.sh absorb --by antigravity`. Full contract: `core/output-contract.md`.
