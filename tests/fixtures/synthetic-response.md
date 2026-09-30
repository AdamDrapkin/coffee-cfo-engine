<!-- SYNTHETIC fixture. Numbers are made up for tests only. -->
# Panda's Coffee CFO Briefing

## Executive Decision
**Recommendation:** Wait

**Confidence:** Moderate

**One-sentence reason:** SYNTHETIC test answer.

## Next Upload Request
Upload:
1. Store list

```json
{
  "intake": [
    {"file": "shot-1.png", "type": "company dashboard", "confidence": "High", "game_week": "7"},
    {"file": "note-1.md", "type": "other", "confidence": "High", "game_week": "not_shown"}
  ],
  "extraction": [
    {"file": "shot-1.png", "field": "week", "value": "7", "unit": "", "confidence": "High", "unreadable": false},
    {"file": "shot-1.png", "field": "cash", "value": "$123,456", "unit": "USD", "confidence": "High", "unreadable": false},
    {"file": "shot-1.png", "field": "revenue", "value": "$48,210", "unit": "USD", "confidence": "High", "unreadable": false},
    {"file": "shot-1.png", "field": "debt", "value": "$0", "unit": "USD", "confidence": "High", "unreadable": false}
  ],
  "ledger_updates": [
    {"target": "week", "op": "append",
     "fields": {"week": "7", "revenue": "$48,210", "ending_cash": "$123,456", "debt": "$0"},
     "evidence": ["shot-1.png"], "confidence": "High"}
  ],
  "next_upload_request": ["store list"],
  "mobile_summary": {"decision": "Wait one week", "confidence": "Moderate",
    "do_now": ["Keep cash", "Send store list"], "do_not": ["Open a store yet"], "next_upload": ["Store list"]}
}
```
