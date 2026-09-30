# Pipeline, phases and time budget

| Phase | Owner | Budget | Gate to pass |
|---|---|---|---|
| 0 Session start | front desk | 0.1 s | marker written |
| 1 Sync check | front desk | 3 s (settle time) | all files complete, sizes stable, expected count |
| 2 Read | screen readers | 0 to 15 s | every image has a reading (cached or fresh) |
| 3 Parse | bookkeepers | under 0.1 s | each screen classified; unknown ones listed |
| 4 Cross-check | auditor and second reader | 2 to 6 s | sums add up; no near-miss digits |
| 5 Dedupe and file | records clerk | 1 to 6 s | validator accepts; nothing filed twice |
| 6 Packet | engine | under 0.1 s | latest.md written |
| 7 Review desk | reviewers | 10 to 20 s, parallel, only if needed | flags and NEEDS EYES empty |
| 7b Data briefing | engine | 0.1 s | rich briefing (all numbers, comparisons, menu, ratings, newspaper, checks) filed with the records |
| 8 Analysis | CFO | 15 to 25 s at Low or Medium effort | a full analysis of 300 to 500 words |

Measured on the real archive (158 screens, worst case, fresh vault): sync 3.1 s, read 15 s, parse 0.02 s, file 3 to 6 s, total about 21 to 25 s. A normal week is 30 to 60 screens: about 8 s of engine time. Add reviewers only if flagged.

Order matters: nothing is filed before it is parsed and cross-checked; nothing is analyzed before it is filed; the answer is written last.

Every week ends with two briefings in the vault: the data briefing (written by the engine, no judgment) and the CFO analysis (written by the chat, filed with `analysis-absorb`, refused if thin). An answer given only in the chat is never saved.
