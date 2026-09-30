# Filing cookbook: exact recipes, copy and adapt

Use these instead of exploring. Every recipe was tested.

## A. Values from screens the engine did not recognize (the usual case)
`inbox/review-paste.md`:
```
IMG_8764.PNG | menu_item | Muffin
IMG_8764.PNG | price | $2.25 | USD
IMG_8764.PNG | unit_cost | $0.68 | USD
IMG_8764.PNG | margin | 70% | percent
IMG_8768.PNG | sales | $12,268 | USD
```
Then `sh scripts/run.sh review-file`. One line per value; use the exact file names from the packet. Write `unreadable` as the value if you cannot read something.

## B. Your analysis
`inbox/analysis-paste.md` in the SKILL.md step 5 format, then `sh scripts/run.sh analysis-absorb`. It creates the analysis briefing, one decision record, one assumption row per item under "What I could not read or verify", and one decision per bullet under "What you changed".

## C. Something filed earlier is wrong
Use `inbox/answer-paste.md` (plain briefing with the headings Recommendation, Confidence, Next Upload Request, then ONE json block) with a correction:
```json
{"intake": [], "extraction": [{"file": "IMG_1.PNG", "field": "x", "value": "1", "unit": "", "confidence": "High", "unreadable": false}],
 "ledger_updates": [{"target": "correction", "op": "append", "confidence": "High", "evidence": ["IMG_1.PNG"], "reason": "why",
   "fields": {"claim": "the exact wrong wording", "correction": "what is true", "applies_to": []}}],
 "next_upload_request": ["Nothing further"], "ceo_words": "", "inbox_files_used": [],
 "mobile_summary": {"decision": "Correction filed", "confidence": "High", "do_now": ["Nothing"], "do_not": ["Nothing"], "next_upload": ["Nothing"]}}
```
Then `sh scripts/run.sh absorb --by antigravity`. Every number in `ledger_updates` must also appear in `extraction`.

## D. What the CEO changed (blend, cups, wages, marketing)
Put it in the analysis under the heading "What you changed", one bullet each, in the CEO's words. Do not write JSON for it.

## D2. Close a decision or an open unknown
- `sh scripts/run.sh decide "<words from the decision>" done "what happened"` (status: open, done, not-possible, superseded, unknown).
- `sh scripts/run.sh resolve "<words from the unknown>" "how it was settled"`.
Use these when the CEO tells you what they did or answers a question; never leave a decision "pending" once you know.

## D3. Menu and history questions
`sh scripts/run.sh facts iced coffee` (one item, week by week with units sold and rank), `facts cold drinks` (ranking of a group), `facts cups` or `facts ratings` (a metric by week), `facts training` (decisions on a topic).

## E. Never
- Never hand-edit files under `wiki/`, `raw/`, `core/` or `scripts/`.
- Never run `python -m core.absorb`, read `scripts/`, or search for how absorb works. The commands are: `week`, `review-file`, `analysis-absorb`, `absorb`, `coverage`, `lint`, `session-health`.
