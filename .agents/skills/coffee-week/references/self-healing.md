# Self-healing catalog

Everything below has happened. Each row: how to spot it, what the system does, what you do.

| Symptom | Cause | System response | Your action |
|---|---|---|---|
| Cash flows do not add up | one number misread | CHECK THESE flag names the screen | review desk step 1 to 2 |
| READERS DISAGREE | one digit differs between readers | flag | review desk step 2 |
| NEEDS EYES screen | new or scrolled layout | text dump, gap register entry | review desk step 1 |
| Filing rejected: number not seen | you typed a number nobody read | validator refuses | remove it or get it from a dump; never guess |
| Duplicate warning | same record already on file | engine skips it | none |
| Weekly figure differs from the record | screen shows a different value than the ledger | engine keeps the old value, flags | review, then amend with a reason |
| A fact filed earlier is false | wrong reading or new evidence | none automatically | file a `correction` (claim, correction, applies_to, reason) and an amend on the right record |
| SESSION HEALTH NOTICE or NEW | conversation grew heavy | health line | tell the CEO to open a new conversation |
| Inbox shows `.icloud` placeholders | sync unfinished | gate waits up to 45 s | run `week` again; after 15 tries report the missing files |
| `week` prints WAITING | files still arriving | none | run it again |
| A command fails | environment problem | error text | report one line, stop; do not debug scripts |
| Chat stalls on "working" | huge single answer or huge conversation | health, batch limits | smaller answers, new conversation |
| Week has numbers but no analysis briefing | the chat answered in the chat only | `analysis-absorb` files the chat's analysis; the engine also writes a detailed data briefing itself | file the analysis with `analysis-absorb` before replying |
| Analysis rejected as thin | under 250 words or a section missing | filer names what is missing | add the sections and run `analysis-absorb` again |
| Menu costs or margins changed | unit costs move (for example a supplies setting) and the old ledger still shows old values | engine files an amend per changed item and lists MENU CHANGES in the packet | analyze the change; ask for the supplies screen if the cause is unknown |
| A cost or price moved and the analysis blamed the market | the CEO had changed something (blend, wage, cups) that the chat did not know | the engine reads the blend and wage from the store screens each week and prints CHANGES SINCE LAST WEEK; a decision the CEO carried out is recorded | read CHANGES and DECISIONS before explaining any move; file "What you changed" |
| Analysis calls a supplier blend the default blend | blend name was not read | the filer warns when the analysis says default blend but another blend is in use | use the blend name from the packet |
| A question about an item, group or metric | the answer is in structured records | `facts <topic>` returns it in one call | never open an image; if `facts` and `find` return nothing, say the vault has no record |
| Analysis names the wrong top seller | the ranking was not checked | the filer warns from the weekly menu record | use MENU SALES RANKING or `facts` |
| Handled problem in problems.log | a step failed and was survived | upkeep queues it | read the log, fix the cause in a maintenance session |
| "[db] the database was behind the ledger" note | a filing changed the ledger and the refresh failed | readers fall back to the ledger, so answers are still right | run `sh scripts/run.sh db refresh`; if it fails, read .coffee-work/problems.log |
| DB DISAGREES in the packet | database totals differ from the ledger | listed under CHECK THESE | run `db refresh` then `db compare`; report anything still different |
| Screen mislabeled by name | file name says balance sheet, image is a newsletter | classifier goes by the text on the screen | trust the classification in the packet |
| Packet says campaigns are unknown | No marketing screen was uploaded this week | engine says campaign changes are unknown instead of "removed" | say the comparison is unavailable; ask for the marketing screens only if a change matters |
| Same screen layout in NEEDS EYES two weeks running | The engine has no rule for it yet | none automatically | teach it with `learn-layout` (`references/self-repair.md`) |
| Screenshots missing for `--reprocess` | Originals are deleted after 3 days; their text stays in raw/ocr/screens/ | clear message | use `find` on the text; nothing to reprocess |
| Filing seems slow (25 to 30 s) | The gate waited for iCloud uploads to settle; the log now excludes that wait | none | none |

## Verifying a fix
After any fix, run `sh scripts/run.sh week` once more and `sh scripts/run.sh coverage`. Success means: no CHECK THESE, no NEEDS EYES, no COVERAGE GAP, and the week figures unchanged except for the fixed field.

## Manual reading versus AI reading
Program readings (Vision) are exact copies of the pixels' text with positions, so they win over an AI's eyes on digits. AI reading (you or a reviewer viewing an image) wins only on things text cannot carry: icons, colors, star fills on screens the engine does not count, charts. When they disagree on a digit, open the image once, and the image decides.
