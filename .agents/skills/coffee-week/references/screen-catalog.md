# The screens of a normal week

A normal upload is 25 to 28 screenshots. The exact set depends on the week's Cafe Street Journal and what the CEO looked at. This is what each kind is, what the engine does with it, and how many to expect.

| Screen | Typical count | Engine reads | Goes to |
|---|---|---|---|
| Weekly results (with the newspaper) | 1 | revenue, net income, cash flows, newspaper headlines | week record, events, competitor records |
| Store performance | 1 | hot and cold cups sold with change, coffee blend in use and its price | store record (by week) |
| Store income statement, top | 1 | revenue lines | store record |
| Store income statement, full | 1 | every revenue and expense line, operating and net income | store record (by week) |
| Customer reviews | 4 to 5 | ratings for price, product, service, atmosphere; review count; floor staff skill, morale, wage; each visible review card | store record, one review record per card |
| Menu item screens | 13 to 16 | price, unit cost, margin, sales with change | catalog amends when values changed |
| Store blend view | 0 to 1 | blend name and price | store record |
| Store marketing | 0 to 1 | active campaigns and per-week cost | store record |
| Manager screen | 0 to 1 | skills, salary, delegation | store record |
| Supplier (roaster) blend cards | 0 to 3, only when shopping | blend name and price; the flavor icon needs an image look | catalog |
| Equipment, exterior, interior, marketing options | only when building or changing | every option with its stats | catalog |

Not yet parsed (they will appear in NEEDS EYES and in `references/parser-gaps.md`): employee lists and hiring pools, staff schedules, inventory and storage, loans and investments, balance sheet and cash flow statements, competitor comparison, city and location maps, research and upgrades.

## Menu items are the usual source of "unrecognized" screens
The 16 menu items are: Brewed Coffee, Espresso, Cappuccino, Cafe Latte, Mocha, Macchiato, Iced Coffee, Iced Latte, Iced Mocha, Iced Macchiato, Coffee Frappe, Cold Brew, Muffin, Donuts, Loaf Cake, Spring Water. If fewer than 16 are recognized, check which ones are missing; Spring Water and the food items have a shorter layout.

## What "read" means
Screens are read by macOS Vision on the Mac (not by you) and cached before you start. You cannot run the reader from the chat. If the packet shows a screen with no text, the worker had not read it yet: run `sh scripts/run.sh week` again once.

## The count check
If the inbox has fewer than 25 screens, do not analyze yet: tell the CEO how many arrived and ask whether the upload finished. If it has 25 or more, treat every screen as present; never assume some were not read.
