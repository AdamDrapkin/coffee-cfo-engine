# The review desk

Reviewers are the human eyes the engine asks for. They work from the packet, in this order, and stop at the first step that settles the question.

## 1. Read the text dump
`.coffee-work/week/review/<screen>.txt` lists every text box on the screen: y, x, height, confidence, text. Headings are uppercase lines around y 700 to 1800. Values sit to the right of their labels on the same y. Most unrecognized screens are a known layout scrolled to a different position; the dump settles them without opening the picture.

## 2. Compare the two readers (for READERS DISAGREE)
The accurate pass and the fast pass disagreed on one digit. Open only that image region, decide which digit is right, and file an amend with the reason "second reader disagreed; image checked".

## 3. Open the image (last resort)
Only for a screen whose dump is empty or cut off, or a flag the dump cannot settle. One image at a time is slow, so hire one reviewer per 6 screens and let them run together.

## 4. Return rows, not prose
Each reviewer returns rows: `file`, `field`, `value`, `unit`, `confidence`, and a line saying what went wrong and how it was fixed. Values must appear in the dump or the image. Anything unreadable is marked "unreadable", never guessed.

## 5. The CFO files the result
Write one small answer (about 40 records or fewer) with the rows in `extraction` and the records in `ledger_updates`, list the reviewed files in `inbox_files_used`, and run `sh scripts/run.sh absorb --by antigravity`. Then run `sh scripts/run.sh week` again: it must come back with no flags.

## What a reviewer reports back (root cause, in three short lines)
- What went wrong (for example: layout scrolled, so the header moved)
- How it was found (which flag or which dump line)
- How it was fixed, and whether a parser should be built (the engine has already added the layout to `parser-gaps.md`)
