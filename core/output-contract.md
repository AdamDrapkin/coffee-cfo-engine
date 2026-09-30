# Output contract

Every answer has exactly two parts, in this order.

1. A human-readable briefing in the standard CFO format from 02-response-formats.md. It must contain the headings Executive Decision (with Recommendation and Confidence), and Next Upload Request.
2. ONE fenced JSON block (```json ... ```) with exactly this shape and nothing after it:

```json
{
  "intake": [{"file": "", "type": "", "confidence": "", "game_week": ""}],
  "extraction": [{"file": "", "field": "", "value": "", "unit": "", "confidence": "", "unreadable": false}],
  "ledger_updates": [{"target": "", "op": "append|amend", "fields": {}, "evidence": [], "confidence": "", "reason": ""}],
  "next_upload_request": [],
  "ceo_words": "",
  "inbox_files_used": [],
  "mobile_summary": {"decision": "", "confidence": "", "do_now": [], "do_not": [], "next_upload": []}
}
```

## Field rules
- file: the exact file name given to you. For typed notes use the note's file name.
- type: one of the Step A upload types, lowercase.
- confidence: exactly one of High, Moderate, Low, Unknown.
- game_week: the week number if visible, else "not_shown".
- ceo_words: the CEO's message copied exactly (empty if there was none). Numbers or facts the CEO typed go in extraction with file "ceo-message". Every value in such a row must appear in ceo_words.
- inbox_files_used: the exact file name of EVERY file in inbox/ that you reviewed for this answer (images, videos, notes). The toolchain files them away so the inbox stays empty. List a file only after you actually reviewed it.
- extraction: one row per visible number or fact. value is the text as shown. If you cannot read it, set value to "unreadable" and unreadable to true. If the screen does not show it, set value to "not_shown".
- ledger_updates.target: one of week, store, city, competitor, decision, capital-allocation, loan, investment, acquisition, assumption, event, test, catalog, correction.
- ledger_updates.fields: only values that appear in extraction or in the CEO's typed note. Never invent a number. Never round it into a different number.
- ledger_updates.op: append for new records. amend only to correct an earlier record, and amend requires a non-empty reason.
- evidence: the file names (and extraction fields) that support the update.
- Use these exact field names in ledger_updates.fields (lowercase, underscores). Include only fields you can see.
  - week: week, revenue, cogs, gross_profit, gross_margin, payroll, rent_occupancy, marketing, other_operating_expense, operating_profit, interest, taxes, net_income, cash_flow, operating_cash_flow, investing_cash_flow, financing_cash_flow, ending_cash, debt, equity_valuation
  - store: name, city, manager, open_date, foot_traffic, rent, deposit, investment_cost, sales, cogs, payroll, marketing, other_costs, operating_profit, net_profit, status
  - city: city, panda_stores, competitor_stores, total_revenue, total_profit, recommended_action
  - competitor: name, city, known_stores, threat_level, recent_moves
  - decision: decision, options, recommendation, ceo_decision
  - capital-allocation: opportunity, type, required_cash, recommendation, ceo_decision
  - loan: lender, original_amount, interest_rate, payment, balance
  - investment: asset, type, cost_basis, current_value, recommendation
  - acquisition: target, purchase_price, stores, recommendation, status
  - event: event, category, severity, required_response, completed
  - correction: claim (the exact wrong wording), correction (what is true now), applies_to (names of the notes or briefings that say it, if known), reason
  - catalog: category (exterior, interior, equipment, menu, staff, marketing, other), name, cost, plus any stat shown (quality, productivity, capacity, speed, upkeep) and notes
  - assumption: item, assumption, how_to_verify
- Before filing a decision, store, city or competitor record, run `ls` on its ledger folder. If the same thing is already recorded, do not append a second copy: use op amend with a reason, or skip it.
- Confidence is High only when the numbers you rely on are read directly and the recommendation follows from them. If it depends on a Community heuristic, an estimate or an Unknown mechanic (staffing levels, wages, marketing return), the confidence is Moderate or Low, and you say which unknown it depends on.
- Things change and mistakes happen. If the CEO says something already filed is wrong or out of date, or new evidence contradicts it, file ONE `correction` update (never edit or delete old records) AND an amend on the record that holds the right fact (for example the store's manager). The toolchain then puts a warning banner on the affected briefings and flags the old records.
- catalog: when the CEO shows choices (exterior and interior styles, machines, menu items, hires), file ONE catalog update per option so the options are recorded permanently, even if there are 30 or more. Include every stat shown for that option. This is how the game's real prices and stats are learned.
- mobile_summary: at most 12 short lines in total across all its lists. Short plain lines, no tables.
- You do not write files. Python does. Return text and this JSON only.

## Absolute rules
- Never invent a number. If a value is not visible or supplied, it does not go in ledger_updates.
- Unreadable or missing values are "unreadable" or "not_shown", never guessed.
- If evidence is insufficient, say: "Insufficient evidence for a high-confidence recommendation." and set Confidence to Low or Unknown.
