# Token budget and quota facts

## Verified
- Gemini's maximum output is 65,536 tokens per response, and thinking tokens count against that same ceiling (the cap is on thinking plus visible output combined). At High effort a single answer can burn most of it on thinking. Sources: Google AI developer forum thread "Gemini 3.8 Flash HIGH: does maxOutputTokens include thinking tokens?", GitHub googleapis/python-genai issue 2062.
- This vault's own measurement: the same analysis prompt took 5.9 s at low effort, 9.5 s at medium and 17.4 s at high; one high run took 62.9 s with 9.3k thinking tokens.
- Antigravity quota (Google AI Pro) is shared across the desktop app, CLI and SDK, and refreshes about every 5 hours.
- Four `agy -p` calls launched together finished in 14.4 s wall, so parallel calls truly overlap.

## Not documented (do not assume)
- Whether a subagent's tokens are billed on a separate meter from the main conversation. Google's forum posts say subagents burn quota "in parallel" and one goal can spawn 10 or more model calls, and nothing says they are counted separately. Treat every subagent as spending from the same quota, in addition to the main conversation. Each subagent also keeps its own context, so its 65,536 cap is its own, but the quota is shared.
- No usage meter exists inside the chat for the vault to read, so the vault tracks load with its own points (health.py).

## Rules that follow
1. Programs first: they cost zero tokens.
2. One conversation per week, because every message re-reads the whole history and images stay in it.
3. No image viewing unless the packet asks; each image in context slows every later step (the last run went from 5 s to 43 s per step).
4. Answers stay small: at most 40 ledger updates and 100 extraction rows in one JSON; the engine files big batches itself.
5. Reviewers return under 4k tokens each. Set Low or Medium effort for weekly runs.
6. Hire agents only when the packet's STAFFING line says so; every agent spends shared quota.
