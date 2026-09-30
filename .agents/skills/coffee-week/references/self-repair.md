# Self-repair: how the chat teaches the engine

The CEO does not want to come back to a coding assistant every week. The chat (you) is part of the machine: when the engine meets something new, you record it AND teach the engine so the same thing is handled automatically next week. You never edit code. You teach through data files that the engine checks before it accepts them.

## Step 1: notice what is out of the norm
Check the packet every week for these. Each one has a fixed response.

| You see | It means | You do |
|---|---|---|
| NEEDS EYES lists a screen | A layout the engine has no rule for | Steps 2 and 3 below |
| CHECK THESE / READERS DISAGREE | A number may be misread | Look at the text dump only; fix with `review-file`, never guess |
| Screen count outside 25 to 28 | Missing or extra screens | Ask the CEO before analyzing |
| NOT COMPARED for a value | Last week had no record of it | Say the comparison is unavailable |
| MENU CHANGES absent but the CEO said he changed prices | The change did not reach the screens | Say so; do not credit any price effect |
| A figure moved more than 25% with no CHANGES line | Unexplained jump | Name it in "What I could not verify"; do not invent a cause |
| DB REFRESH FAILED or DB DISAGREES | Database behind the ledger | Run `sh scripts/run.sh db refresh`; if still wrong, report one line |
| The same screen was in NEEDS EYES last week | The engine has not learned it yet | Teach it (step 3) |

## Step 2: record what the unrecognized screen shows
Read the text dump named under NEEDS EYES (not the image). Write one line per value in `inbox/review-paste.md` as `FILE | field | value | unit`, then run `sh scripts/run.sh review-file`. Field names are short lowercase words with underscores.

## Step 3: teach the engine the layout (only for recurring settings-style screens)
If the screen is something the CEO will upload again (a settings board, a status panel), write a rule in `inbox/layout-paste.md` and run `sh scripts/run.sh learn-layout`. Format, one line each:

```
LAYOUT | campaign settings
MATCH | MARKETING CAMPAIGNS
MATCH | Free WIFI
SAMPLE | IMG_8817.PNG
FIELD | free_wifi_price | Free WIFI | below | money | USD per week | $300
FIELD | power_strip_state | Desk Power Strip | below | onoff | | On
```

- MATCH: text that must appear on the screen (every MATCH line must be present). Choose words unique to this layout.
- SAMPLE: the screen file name; its saved text is read from `raw/ocr/`.
- FIELD: `field name | anchor text on the screen | right, below or above | money, number, percent, onoff or text | unit | the value you read by eye`. The engine reads the nearest value of that type in that direction from the anchor.

The engine accepts the rule only if it reproduces every value you read and the MATCH lines do not fit any screen an existing parser already reads. If it rejects the rule it says why; fix the anchor, direction, type or MATCH and run again. A saved rule is stored in `core/learned-layouts.json` and is used from the next `week` on. Rules are only appended; to change one, add a new one with a different name.

## Step 4: say it in one line
End the chat answer with one line: "Learned a new layout: <name>" or "Recorded by hand, too irregular to learn: <why>". That is how the CEO sees the system improving.

## What you must not do
- Do not edit or create scripts, tests or any file other than the five paste files in `inbox/`.
- Do not learn a rule from a screen you are unsure about; record it with `review-file` and stop.
- Do not teach a rule for something that belongs in the ledger as a decision (what the CEO decided); use the decision recipes in `filing-cookbook.md`.
- A problem that needs real code (a wrong calculation, a crash, a new kind of report) is not yours to fix. Say it in one line at the end: "Engine issue: <what happened>". The maintainer handles it in a maintenance session.
