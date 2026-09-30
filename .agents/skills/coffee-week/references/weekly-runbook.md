# Weekly runbook: exactly what to do, in order

You have done this before. A normal week is 25 to 28 screens and takes under a minute of machine time. Everything below is already decided, so follow it without exploring the vault or the scripts.

## 0. Before you run anything (10 seconds)
1. Read `references/company-state.md`. It is the current situation: setup, weekly history, decisions, unknowns, corrections. It replaces reading old briefings, the ledger and the digest.
2. Do not open `scripts/`, `core/`, old briefings or ledger files to "learn how it works". If this file does not answer a question, ask the CEO or run the command below and read its output.

## 1. Run the engine (one command)
`sh scripts/run.sh week`
Add `--expect N` only if the CEO gave a number. It waits for the files, reads all screens (the Mac worker reads them; you cannot), files what it recognizes, checks the numbers, and prints the packet. If it prints WAITING, run it again (up to 15 times).

## 2. Read the packet top to bottom, once
| Packet section | What it means | What you do |
|---|---|---|
| SCREEN COUNT | how many screens arrived. 25 to 28 is normal | below 25: ask the CEO if the upload finished; do not assume what is missing |
| STAFFING | who to hire | usually nobody |
| Filed / skipped | what went into the ledger | nothing |
| AUDIT | values read back from the ledger and compared with the screens | all match: fine. AUDIT FAIL: fix it (see self-healing) |
| CHECK THESE | flags | settle each with the review desk |
| NEEDS EYES | screens no parser knows | see step 3 |
| WEEK N FIGURES | ledger numbers with last week's | use them |
| CHANGES SINCE LAST WEEK | blend, wage, campaigns that changed | explain moved numbers with these first |
| DECISIONS AND COMMITMENTS | what was recommended and what the CEO did | connect this week's results to them |
| MENU SALES RANKING | units sold per item, by group | name top sellers only from this list |
| NOT COMPARED | metric missing in the week before | say the comparison is unavailable |
| WHAT COULD BE WRONG THIS WEEK | weak points of this batch | state those limits in the analysis |
| MENU CHANGES | unit costs and margins that moved | say what moved margins and why |
| ANALYSIS INPUTS | all numbers computed | use them; label computed and estimated figures |
| REVIEWS ON RECORD | theme counts by week and where reviews live | open wiki/hubs/hub-reviews.md, search by keyword |
| UPKEEP DUE | maintenance items | mention in one line at the end; do not do them |

## 3. Only if NEEDS EYES lists screens
1. Read each screen's text file (path in the packet). Most are a known layout scrolled differently.
2. Open the image only if the text is empty or unclear. One batch, all files together.
3. Write one line per value to `inbox/review-paste.md`:
   `IMG_8764.PNG | menu_item | Muffin` then `IMG_8764.PNG | price | $2.25 | USD` and so on.
4. Run `sh scripts/run.sh review-file`. It files the values and clears the screens from the inbox. Do not build JSON by hand for this.
5. If a new value should update the store or week records, say so in the analysis and mention it to the CEO; formal record changes are made by the maintenance session, not now.

## 4. Write the analysis (this is the main product)
Follow SKILL.md step 5 exactly: headings, 300 to 600 words, plain language. Write it once to `inbox/analysis-paste.md`, then run `sh scripts/run.sh analysis-absorb`. If it refuses, add what it names and run it again. Then give the CEO the same text.

## 5. Finish
End with the SESSION HEALTH sentence from the packet, word for word. Mention UPKEEP DUE in one line if the packet has it.

## Numbers come from the database
`facts`, the packet comparisons and the company state page read the SQLite database while it is fresh, and the ledger otherwise. The packet flags DB DISAGREES or DB REFRESH FAILED if that ever breaks; you do not need to act unless it does (then `sh scripts/run.sh db refresh`).

## Things that are always true
- Every action you recommend must exist in `references/game-levers.md`. Do not recommend staff training or anything else the game does not offer.
- Never open archived screenshots. Use `sh scripts/run.sh find <keywords>`; every screen's text is saved.
- The CEO plays; you analyze. Do not ask them to do technical steps.
- Plain words, no jargon, no tables in the chat.
- Never invent a number. Label estimates.
- The CEO changes things between weeks (blend, cups, wages, marketing). Assume something changed until CHANGES SINCE LAST WEEK says otherwise, and ask about anything the screens cannot show, once, at the end.
- One conversation per week.
