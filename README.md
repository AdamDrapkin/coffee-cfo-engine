# Coffee CFO Engine: a chat-driven knowledge base for Coffee Inc. 2+

You play Coffee Inc. 2+ (Apple Arcade). You paste a screenshot into a chat and say what you are trying to decide, in normal words. A Gemini-powered CFO answers in plain language, and in the background every number it read, every decision, and every lesson is filed into a wiki that grows as your company grows. Next week, next month, in a brand-new conversation, it still knows your company.

> Unofficial fan project. Not affiliated with Side Labs, Apple, Google, or Obsidian. Coffee Inc., Apple Arcade, Gemini, Antigravity and Obsidian are trademarks of their owners.

## Project status: closed (2026-09-30)

This project ran for 14 in-game weeks and was closed by choice after two days of building, because maintaining the machine had become more work than playing the game. It is left in a working, tested state: 129 automated tests pass, lint is clean, and the last commit matches the last week filed. Nothing here is abandoned half-way except the items listed under "Known limits" below.

## What this kit is, and is not
Everything in this kit is built on a business simulator (Coffee Inc. 2+). It is a complete working system and a learning tool. It is not a ready-made tool for a real business. With a Commercial License you may use it as a framework: give it to your own team and your own AI and adapt it to your business. Nothing in it is specific to any real industry.

## In depth: what this became

The short description above is the original idea. What was actually built is a small data system that splits a business-analysis job into three parts, each done by whatever does it best.

| Part | Does | Never does |
|---|---|---|
| **Programs (Python, macOS Vision OCR, SQLite)** | Read every screenshot, parse it, cross-check digits, do all arithmetic, compare weeks, file records, rebuild the database | Judge, recommend, or guess a missing value |
| **The chat (Gemini in Google's Antigravity)** | Reads the packet a program prepared, forms a judgment, answers in a fixed format, answers questions | Write anywhere except four paste files, edit code, or write SQL |
| **The CEO (you)** | Plays the game, uploads screenshots, decides | |

### Why this split
The first version was chat only: paste screenshots, ask, and have the model file what it read. One early week took 27.7 minutes because the chat opened 28 images one at a time, wandered through the source code and wrote its own script. It also forgot everything the next day. Every mechanical job (reading pixels, adding, comparing, remembering) moved into programs. A typical week now takes 3 to 10 seconds of engine time once the files have arrived (about 30 seconds when it waits for iCloud uploads to settle).

### The week engine (`coffee week`)
1. **Gate:** waits until iCloud has finished delivering the uploads (no placeholders, no file still growing, all expected files present).
2. **Read:** a compiled Swift helper runs macOS Vision OCR on every screenshot in parallel. A background worker pre-reads new screens the moment they land, and serves the chat, which cannot run the reader in its sandbox.
3. **Parse:** each screen is classified from its own text and handed to a deterministic parser for that layout (weekly results, income statement, reviews, menu items, blends, campaigns, agency contracts, company comparison board and more). Unrecognized screens are listed as NEEDS EYES with their full text, never guessed.
4. **Check:** a second, faster reader cross-checks digits; cash-flow lines must add up; values must match the ledger on read-back (the audit).
5. **File:** surviving values pass the validator into the ledger; duplicates are skipped; changed menu items are recorded as amendments.
6. **Packet:** the chat receives the week's figures against last week, what changed, open decisions, reviews on record, the game calendar (date, month, season and the hot/cold mix), corrections in force, and a list of what could be wrong this week.
7. **Answer:** the chat writes the analysis in a fixed shape; a filer rejects a thin one, checks dollar figures against the packet, and warns when a top-seller claim contradicts the week's ranking.

### Memory: plain text plus SQLite
- **Ledger:** about 450 append-only Markdown notes with sources. Corrections are new records; nothing is edited. Briefings (about 120) are dated history.
- **SQLite (ADR-009):** a derived database (46 tables counting full-text-search tables, plus views for week-over-week comparison, item ranking, open decisions and store comparison) rebuilt from the ledger in one transaction after every filing. Reads use it only while a ledger signature matches, otherwise they fall back to the ledger. It lives outside iCloud at `~/.coffee-inc-kb-work/coffee.db`, because SQLite's write-ahead logging needs all processes on one host. A daily CSV export in `wiki/db-export/` lets git rebuild it. A golden-answer test (`coffee golden check`) catches drift.
- **Why the model does not write SQL:** published text-to-SQL benchmarks show a large gap between models and people on realistic databases, and a confidently wrong query in a finance context is worse than no answer. The chat calls fixed commands (`facts`, `find`, `db`) that run fixed queries.

### Self-repair (so the maintainer is not needed every week)
- **`learn-layout`:** the chat describes a recurring settings-screen layout as data in `inbox/layout-paste.md`; the engine accepts the rule only if it reproduces the values the chat read by eye on the real screen text and does not also match a screen an existing parser reads. Rules live in `core/learned-layouts.json`.
- **`upkeep --fix`:** fixed repairs (refresh the database and export, delete old screenshots, clear harmless noise from the problem log, verify that every command and file named in the skill docs exists). Anything it cannot fix goes once into `wiki/outputs/engine-issues.md`.
- **`report-issue`:** the chat logs anything that needs real code.
- **Field guide:** `.agents/skills/coffee-week/references/capabilities.md` turns the CFO master prompt into a what-can-it-read, what-can-it-not, "when I see X, do Y" table, including the picture rule (judge images from the picture, never invent a scale).
- **Deliberate limit:** the chat cannot edit scripts. A chat with that permission is how the worst day of the project happened.

### Retention
Screenshots are kept for 3 days after filing and then deleted (only if their text is archived in `raw/ocr/screens/`). Every value is already in the ledger, so the vault went from 150 MB to 24 MB. `coffee week --reprocess` only works on screenshots still retained.

### Where it broke, and what each failure became
- **Week 7** was run from a coding assistant while the CEO meant to run it in the chat; it filed a garbled backfill of old weeks. Reset with approval; re-reads of archived screens are now logging-only.
- **Invented or unsupported claims:** a blend change read as a market price spike; advice to "train floor staff" (the game has no training); a top-seller claim that omitted the real best seller; a sales rise credited to a Wi-Fi upgrade when every item rose by the same percent. Each became a check or a rule.
- **Sandbox surprises:** the chat cannot run the OCR binary or open the database. Fixed with a worker that serves the chat and a database status that degrades quietly.
- **Instruction drift:** the chat skipped steps written into its rules (teaching layouts, sourcing percentages, comparing two pictures element by element before calling them identical). Lesson: a rule that matters belongs in code, not in prose.
- **Suspicious game data:** some category totals repeated to the dollar across weeks. They are flagged IDENTICAL TO LAST WEEK and treated as unverified.

### Known limits
- OCR cannot read icons. The blend flavor radar has no deterministic reader; it is logged as an open engine issue and the chat reads it by eye.
- How the chat behaves inside its own sandbox was verified only through the files it left behind.
- ADR-009 Sprint 8 (making the database the only source of truth) was deliberately not done.
- Only macOS was tested. This is an unofficial fan project.

### How this pattern applies to a real business
A knowledge base of readable documents and a SQL database do different jobs. Retrieval-augmented generation (Lewis et al., 2020, arXiv:2005.11401) pairs a model with a memory it can look things up in; the readable notes (decisions, reviews, policies, past reasoning) play that role, where narrative and provenance matter. A SQL database handles totals, joins and constraints, where the answer must be exact and reproducible. A finance team has the same pair in the close binder and the general ledger; support has ticket notes and a ticket table. The lessons carry over: let programs compute and the model judge; keep the record append-only so a correction is visible; keep the derived database rebuildable, with a fallback when stale; give the model a narrow validated door to the system of record, not a pen; and enforce in code the rules you cannot afford the model to forget. A portfolio write-up of the project is on the author's site.

## Why this exists

Chatting with an AI about a game has one big flaw: it forgets. Tomorrow you start from zero, re-explain your company, and re-upload the same screens. A CFO that forgets is useless.

This project fixes that by giving the chat a memory made of plain text files:

- **The chat is the interface.** You talk. You never type commands or open files.
- **The files are the memory.** Every number read from a screenshot becomes a dated ledger note. Every answer becomes a briefing. Every mechanic you learn becomes a wiki page with an honest confidence label.
- **Rules protect the memory.** The AI is not allowed to invent numbers, overwrite history, or present guesses as facts. A checker (plain Python, no AI) rejects any answer that breaks the rules before anything is saved.

## What you can do with it

Just talk. Examples of what to say, with what happens behind the scenes:

| You say | What runs in the background |
|---|---|
| "I'm choosing my first location. Here are the three options." (screenshots) | Location playbook: ranks options by rent, deposit, foot traffic, competitors and cash left over. Saves the candidates and your decision. |
| "Here is my week." (dashboard or income statement) | Weekly close: records revenue, costs, cash and debt, compares with last week, names the top three drivers. |
| "Got this newsletter." | Event log: what happened, severity, whether you need to act and by when. |
| "The bank offered me a loan." | Debt playbook: cost of debt, cash left after borrowing, the exact reason borrowing would or would not make sense. |
| "Should I open a second store?" | Expansion playbook with a gating checklist and the best alternative use of the cash. |
| "This store keeps losing money." | Turnaround playbook: fix, test, downsize or close, with a trigger. |
| "How does foot traffic actually work?" | Research with its own web search: sourced findings, labeled Confirmed, Community, Inference or Unknown by the toolchain, not the AI. |
| "What should I do next?" | Next three actions from your current data only. |

You never say which playbook. The CFO works it out from what you send.

## Recording instead of screenshots (many screens at once)
Chat apps cap attachments (Antigravity takes 5 images), and some decisions have dozens of screens: every exterior, every interior, every machine. Record instead:

1. On your iPhone, start Screen Recording (Control Center), open the options, and **pause about one second on each screen**. Scroll slowly.
2. Put the video file in the vault's `inbox` folder: Finder > iCloud Drive > Obsidian > coffee-inc-kb > inbox (on the iPhone: Share > Save to Files > that folder, unverified). **Do not attach it in the chat.** Antigravity's chat rejects video attachments (mp4 gives an unsupported-format error).
3. Tell the chat in words: "Video in the inbox, it shows every exterior option. Which should I pick?" If you forget, it still checks `inbox` for videos.

Behind the scenes `coffee frames` (uses ffmpeg) samples the video, finds the moments the screen holds still, and keeps one sharp frame per distinct screen, so a changed price or highlight counts as a new screen. The chat reads every frame file, which is not limited to 5, and files every option it read. Frames are scratch files and disappear after a day. The background worker also extracts frames automatically when a video lands in `inbox`.

If a screen is missing, record that part again more slowly, or run `coffee frames VIDEO --fps 4`. Tuned on synthetic recordings only, so check the first real one.

## When to start a new conversation
Plan on **one conversation per in-game week**. Each message re-reads the whole conversation, and every screen, video frame and filed briefing makes it longer. When a conversation gets heavy, replies slow down and can sit on "working". The vault is the memory, so a new conversation loses nothing.

- **How it knows:** a new conversation starts by running `session-start`, which marks the moment and the in-game week. After each filing the chat reports a health line that counts the load since that marker: 1 point per screen or video frame, 8 per filing, 0.5 per KB of briefings.
- **Still good** (under 100 points): it says so and how much room is left, roughly how many more screens.
- **NOTICE** (100 or more): finish what you are doing, then start a new one at your next pause.
- **START A NEW CONVERSATION NOW** (150 or more): do it before your next message.
- **NEW IN-GAME WEEK:** when the game moves to a new week, it tells you to start the conversation for that week.
- Also start a new one after you switch topics, or when a normal reply takes more than about 5 minutes with no progress (let any filing that is running finish first).
- You can run `coffee session-health` yourself any time. The thresholds come from a real stall: a week of about 65 screens and 4 filings scored about 120 and started to slow down.

## How it works: the original chat-only design

This is the first design, before the week engine. The filing path (validator, Python writes the files, append-only ledger) is unchanged; the reading and the arithmetic moved into programs as described above.

1. **You send a message** in the Antigravity desktop app with a screenshot and a few words.
2. **It gets up to speed.** It reads a short summary of your company (`wiki/outputs/state-digest.md`), then searches the wiki for notes related to your question. It does not depend on old chats.
3. **It routes your request.** Rules in `core/` map what you sent to a playbook (there are 15, A to O). "Choosing my first location" means Scenario A.
4. **It reads the screenshot** and extracts every visible number and fact, with a confidence label. Anything unreadable is marked `unreadable`, never guessed.
5. **It answers in simple words**: what to do, why in a few reasons, the runner-up, what not to do yet, and what to send next.
6. **It saves its full answer** to one inbox file and runs `coffee absorb`.
7. **A checker validates it.** No number may appear that was not in the screenshot or your words. Confidence labels are required. Existing weeks cannot be overwritten. Corrections need a reason. If anything fails, nothing is saved and the AI is told why.
8. **Python writes the files**: ledger notes, a dated briefing, an updated company summary, the wiki index and log. The AI never writes them directly.
9. **A backup is pushed** to your git remote, if you set one.
10. **Next conversation, it all still exists.**

Screenshots are kept for 3 days and then deleted. The extracted numbers and the full text of every screen (`raw/ocr/screens/`) are the permanent record, and the CFO reads key numbers back to you so a misread gets caught. A correction is saved as a dated amendment and the old value stays visible.

## What is remembered (the wiki)

```
wiki/ledger/        weeks, stores, cities, competitors, decisions, capital allocation,
                    loans, investments, acquisitions, events, assumptions. Append-only.
wiki/knowledge-base/  how the game works, one note per system, with sources and confidence
wiki/briefings/     every answer, dated
wiki/tests/         your in-game experiments and what they proved
wiki/decisions/     why the toolchain is built the way it is
raw/                immutable inputs: the master prompt, research outputs
exports/            two generated documents that assemble the whole wiki
```

Everything is plain Markdown that opens in Obsidian, but you never have to open it. The two files in `exports/` are generated on demand: `Pandas_Coffee_Coffee_Inc_2_Plus_Knowledge_Base.md` (the game manual) and `Pandas_Coffee_Company_Memory_and_Weekly_Ledger.md` (your company history).

## When something filed turns out to be wrong
History is never rewritten, but old information can be wrong or out of date (for example a briefing recommends a manager who could not be hired). Just tell the chat: "that's wrong, it's Tiffany Porter." It files a **correction** plus an amendment on the right record. Then:
- The affected briefings get a warning box at the top; their original text stays below it.
- The old records are flagged as corrected wherever they are listed, and stay as history.
- The correction appears under "Corrections in force" in the summary the AI reads first in every conversation, so it stops repeating the old claim.
- `coffee lint` fails if a correction is incomplete or a warning box is missing.
Old briefings are dated history, not today's facts: today's facts are in the state digest, the store dossiers and the latest week records.

## How the notes connect
Open Obsidian's graph view: every page hangs off the **Vault map** (`wiki/hubs/map`). Hub pages list each kind of record (briefings, weeks, decisions, events, the option catalog, stores, cities, competitors, knowledge, rules, archive), and each store has a generated dossier that ties its facts, built options, decisions and capital records together. Old records are linked from these pages because history is never edited; new records carry their own links. `coffee lint` fails if any page is isolated or unreachable from the map.

## Rules that never bend

- Never invent a number. Not visible means `not_shown`. Not readable means `unreadable`.
- Old Coffee Inc. 2 or community claims are never labeled Confirmed for Coffee Inc. 2+. The toolchain, not the AI, assigns the label: Confirmed needs an official source about 2+ and a word-for-word quote from it; `coffee audit` re-checks filed labels against the rules.
- The ledger is append-only. History is never replaced.
- Every unknown mechanic stays `Unknown / requires testing` until a source or an in-game test supports it.
- The CFO advises. You decide.

## Your first conversation

Do this once, before your first real decision. The knowledge base starts empty, so the CFO does not yet know how the game works beyond what a screenshot shows.

**Message 1: research (optional but recommended, about 10 minutes, 3 to 4 topics).** Send:

> I'm starting a new Coffee Inc. 2+ company on Normal difficulty with 2 competitors, USD, $800,000 starting capital. Before I decide anything, research how store locations, leases, rent, deposits and foot traffic work. Then research pricing, menu and product quality, then staffing. Do them one at a time and tell me what is confirmed and what is still unknown.

The chat searches the web itself, then hands the findings to a checker that assigns the labels. Each topic takes a few minutes and uses a small part of your allowance. Labels are conservative on purpose: most of what you get will be `Community` or `Unknown`, and that is honest. Skip research and the CFO still works from your screenshots, but it will say more things are Unknown.

**Message 2: your first packet.** Send these screenshots together (clear, uncropped):
1. The game setup screen (difficulty, competitors, currency, starting capital)
2. The company overview
3. The map or city selection
4. Every first-store location and lease option
5. Your cash and any initial financial report
6. Any tutorial messages or hints

and say:

> I'm starting my business and choosing my first location. Here are the options. Which do you recommend?

Expect a short answer like "Choose B because ..., runner-up A because ..., do not lease C yet because ...", then a line reading back the numbers it took. Say "that number is wrong" if one is off.

**After that:** just play. Send a screenshot of each new decision or each week's results and say what you are deciding. Say "weekly close" at the end of each in-game week.

## Requirements

- **Antigravity 2.0 desktop app** and the **Antigravity CLI (`agy`)**, signed in with a Google account. Everything runs on your account allowance. No API keys, no billing. The free tier is small and its limits are unpublished, so a Google AI plan is more comfortable. Check yours with `coffee doctor`.
- **Python 3.9 or newer.** The filing tools need nothing installed (a pure-Python copy of PyYAML is bundled in `scripts/_vendor`). `pillow` is only needed for the background worker's image conversion, and `pytest` to run tests.
- **macOS** for the optional background worker and phone workflow (they use launchd, `sips` and iCloud). The chat workflow and the checks need only Antigravity and Python.
- **Obsidian** is optional. Nothing needs it.
- **ffmpeg** is optional, only for screen recordings (`brew install ffmpeg`).
- **Git** is optional, for backup and history.

## Setup

1. Clone this repository and open a terminal in it.
2. Optional, for the background worker and tests: create an environment and install `pillow` and `pytest`:
   ```
   python3 -m venv .venv && .venv/bin/pip install pillow pytest
   ```
3. Install the Antigravity CLI from Google's official page and sign in by running `agy` once (a browser opens; paste the code back into the terminal).
4. Create the empty vault structure: `.venv/bin/python scripts/coffee.py seed`
5. Check everything: `.venv/bin/python scripts/coffee.py doctor`
6. Open this folder as a project in the Antigravity desktop app, choose **Local** (not a new worktree), keep auto-approve off, and start talking. The rules in `AGENTS.md` load automatically. That was tested for the CLI. For the desktop app it is expected but check it: ask "summarize your chat mode rules" once.
7. Optional: `git remote add origin <your private repo>` for backup. Use a private repository, because your company data is in it.

Tip: alias `coffee` to `.venv/bin/python scripts/coffee.py`.

## Optional layers

- **Inbox and background worker (macOS):** keep the vault in `iCloud Drive/Obsidian/` so files you save on the iPhone reach the `inbox` folder. `coffee install-agent` runs a small worker that keeps time, extracts frames from videos, backs up to git every 10 minutes, and reports the queue in `STATUS.md`. **The chat is the interface**: you drop screenshots, notes or videos in `inbox`, tell the chat, and it reviews them and files them. Everything it reviewed leaves the inbox: images go to `raw/screenshots/`, notes to `raw/notes/`, and videos to a temporary hidden folder that is emptied after 14 days (videos are never committed to git). Files it did not review stay put. Before reading anything, the chat runs an **iCloud sync check** (`coffee inbox-ready`): it waits until no placeholder files remain, no file is still growing, every image is complete, and (if you said how many you uploaded) all of them have arrived. It gives no answer until that check says READY. There is no phone-only fallback. Set `COFFEE_AUTO_INGEST=1` (then run `coffee install-agent` again) only if you want the worker to send inbox batches to Gemini on its own; it is off so it never competes with the chat.

## Commands (you rarely need them)

```
coffee week [--expect N]    read, check and file a whole week of screenshots, print the packet
coffee analysis-absorb      file the chat's analysis from inbox/analysis-paste.md
coffee review-file          file values read by hand from unrecognized screens (inbox/review-paste.md)
coffee learn-layout         teach the engine a screen layout from inbox/layout-paste.md
coffee upkeep [--fix]       show the upkeep queue, or run the automatic repairs
coffee report-issue TEXT    log an engine problem that needs real code
coffee facts TOPIC          structured history of an item, metric or decision
coffee find WORDS           search saved text, including every screen's text
coffee db [status|refresh|export|check]   the SQLite layer
coffee golden [save|check]  golden-answer regression test
coffee absorb [--by NAME]   validate and file an answer saved in inbox/answer-paste.md
coffee ingest [--note ""]   batch the inbox with one Gemini call
coffee ask "question"       ask against the wiki
coffee close                weekly close
coffee research "topic"     sourced research into the knowledge base (from a terminal)
coffee research-absorb      file research a chat agent saved in inbox/research-paste.md
coffee frames VIDEO         one frame per distinct screen from a screen recording (needs ffmpeg)
coffee audit                re-check filed research labels against the current rules
coffee coverage             list archived screens whose information was never recorded
coffee session-health       say whether it is time to start a new chat conversation
coffee export               regenerate the two master-prompt documents
coffee lint                 deterministic health checks, never calls Gemini
coffee doctor               sign-in, quota, keys, last call
coffee digest               print the company summary the AI reads
coffee sync                 commit and push to your git remote
coffee seed                 create the folders and knowledge-base stubs
coffee watch / install-agent   the background worker (macOS)
coffee relocate PATH        move the vault
```

## Safety and privacy

- Only the first-party `agy` and Antigravity ever touch your Google login. Do not use third-party tools that extract OAuth tokens: Google says that can trigger account restrictions.
- No API key belongs anywhere in this repo. A secret scanner blocks pushes that contain key-like strings.
- Text inside screenshots and notes is treated as data, never as instructions.
- Keep your backup repository private. It contains your company history.
- Git lives outside the vault when the vault is in iCloud, because iCloud can corrupt a `.git` folder.

## What has and has not been verified

Verified in testing (2026-09-29), including that the filing commands run on plain system Python with no home folder access, to match a sandboxed chat: sign-in and headless calls with the CLI, image reading, both context files loading, web search headless, quota reporting, a background worker under launchd, end-to-end ingest and research, validation rejecting an invented number, 129 automated tests at the final commit (26 at the first check).

Not verified: the desktop app loading `AGENTS.md` and accepting pasted images, saving screenshots from iPhone Files into the vault, iCloud edge cases, the worker with the screen locked, and anything on Windows or Linux. The research labels are proposed by the model and adjusted by rules, so read them as leads, not gospel.

## Project layout

`AGENTS.md` and `core/` are the CFO's rules, generated from `raw/assets/cfo-master-prompt.md` by `scripts/split_master.py`. `scripts/` is the toolchain (validator, ledger writer, digest, worker). `tests/` holds the pytest suite with synthetic fixtures. Run tests with `python -m pytest tests`.

## Disclaimer and terms

This is a decision aid, not financial, accounting, tax, legal or investment advice. The AI it uses can be wrong, and you must verify every figure before acting. It is provided as is, with no warranty, and Synteo LLC's liability is limited. Paid versions sold on Gumroad are final sale (no refunds). Commercial users are solely responsible for their use and indemnify Synteo LLC. Read `TERMS.md` for the full terms.

## License note

This project is released under the **PolyForm Noncommercial License 1.0.0** (full text in `LICENSE`).

- **Free:** personal use, hobby play, study, research and any other noncommercial use. You may modify it for yourself.
- **Not allowed without a separate license:** selling it or anything built from it, offering it as a paid service, or using it inside a business.
- **Commercial license:** a separate Commercial License (use in your own business or for your own clients, no resale) is sold by Synteo LLC alongside the paid Personal Kit.
- **Keep the notice:** anyone you share a copy with must get the license text and the `Required Notice:` line.
- **Unofficial fan project.** Not affiliated with, endorsed by or sponsored by Side Labs, Apple, Google or Obsidian. It contains no game assets or screenshots. Game and product names are trademarks of their owners and are used only to say what the tool works with.
- **No warranty.** It is provided as is; you are responsible for what you run, and for your own Google account terms when using Antigravity.

## License

PolyForm Noncommercial 1.0.0 (see `LICENSE`): free for personal, hobby, study and other noncommercial use. Commercial use needs a separate license. Required Notice: Copyright 2026 Synteo LLC.
