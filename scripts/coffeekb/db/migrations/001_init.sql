-- 001: the schema. Every fact is keyed by store and week. Nothing here holds prose except short text fields.
CREATE TABLE store (
  store_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, city TEXT, opened_week INTEGER, manager TEXT, manager_salary REAL
);
CREATE TABLE week (week INTEGER PRIMARY KEY, game_date TEXT);

CREATE TABLE source (            -- every screen that was ever read; its full text is searchable
  source_id INTEGER PRIMARY KEY, file TEXT NOT NULL UNIQUE, week INTEGER, kind TEXT, sha1 TEXT, ocr_text TEXT
);
CREATE TABLE reading (           -- catch-all: any labeled value, so nothing shown is dropped
  reading_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES source(source_id), label TEXT NOT NULL, value TEXT, confidence TEXT
);

CREATE TABLE company_week (
  week INTEGER PRIMARY KEY REFERENCES week(week), revenue REAL, net_income REAL, operating_cf REAL, investing_cf REAL, financing_cf REAL,
  cash_flow REAL, ending_cash REAL, debt REAL
);

CREATE TABLE blend (blend_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, supplier TEXT, aroma INTEGER, flavor INTEGER, acidity INTEGER, bitterness INTEGER, body INTEGER, notes TEXT);
CREATE TABLE blend_price (blend_id INTEGER NOT NULL REFERENCES blend(blend_id), week INTEGER NOT NULL REFERENCES week(week), price_per_lb REAL NOT NULL, PRIMARY KEY (blend_id, week));

CREATE TABLE store_week (
  store_id INTEGER NOT NULL REFERENCES store(store_id), week INTEGER NOT NULL REFERENCES week(week),
  sales REAL, hot_sales REAL, cold_sales REAL, food_sales REAL, cogs REAL, coffee_beans REAL, payroll REAL, rent REAL, marketing REAL,
  depreciation REAL, admin_cost REAL, total_expenses REAL, operating_profit REAL, net_profit REAL,
  cups_hot INTEGER, cups_cold INTEGER, staff_count INTEGER, wage REAL, staff_skill INTEGER, staff_morale INTEGER,
  rating_overall REAL, rating_price REAL, rating_product REAL, rating_service REAL, rating_atmosphere REAL, review_count INTEGER,
  blend_id INTEGER REFERENCES blend(blend_id),
  PRIMARY KEY (store_id, week)
);

CREATE TABLE menu_item (item_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, grp TEXT NOT NULL CHECK (grp IN ('hot','cold','food','')));
CREATE TABLE menu_week (
  store_id INTEGER NOT NULL REFERENCES store(store_id), week INTEGER NOT NULL REFERENCES week(week), item_id INTEGER NOT NULL REFERENCES menu_item(item_id),
  price REAL, unit_cost REAL, margin REAL, units_sold INTEGER, units_change TEXT, PRIMARY KEY (store_id, week, item_id)
);

CREATE TABLE campaign (campaign_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE store_campaign_week (
  store_id INTEGER NOT NULL REFERENCES store(store_id), week INTEGER NOT NULL REFERENCES week(week), campaign_id INTEGER NOT NULL REFERENCES campaign(campaign_id),
  cost_per_week REAL, PRIMARY KEY (store_id, week, campaign_id)
);

CREATE TABLE review (
  review_id INTEGER PRIMARY KEY, review_key TEXT NOT NULL UNIQUE, store_id INTEGER NOT NULL REFERENCES store(store_id), week INTEGER, text TEXT NOT NULL, theme TEXT
);
CREATE TABLE review_rating (   -- per-review stars, when a screen ever shows them
  review_id INTEGER NOT NULL REFERENCES review(review_id), category TEXT NOT NULL, stars REAL, PRIMARY KEY (review_id, category)
);

CREATE TABLE decision (
  decision_id INTEGER PRIMARY KEY, decision_key TEXT NOT NULL UNIQUE, week INTEGER, store_id INTEGER REFERENCES store(store_id),
  title TEXT NOT NULL, recommendation TEXT, options TEXT, status TEXT NOT NULL CHECK (status IN ('open','done','not possible','superseded','unknown')), ceo_note TEXT
);
CREATE TABLE decision_event (event_id INTEGER PRIMARY KEY, decision_id INTEGER NOT NULL REFERENCES decision(decision_id), at TEXT, status TEXT, note TEXT);

CREATE TABLE lever (lever_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, keywords TEXT, exists_in_game INTEGER NOT NULL CHECK (exists_in_game IN (0,1)), notes TEXT);
CREATE TABLE game_fact (fact_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, keywords TEXT, fact TEXT NOT NULL, source TEXT, at TEXT);
CREATE TABLE unknown (unknown_id INTEGER PRIMARY KEY, unknown_key TEXT NOT NULL UNIQUE, text TEXT NOT NULL, detail TEXT, opened_at TEXT, resolved_at TEXT, resolution TEXT);
CREATE TABLE correction (correction_id INTEGER PRIMARY KEY, claim TEXT NOT NULL, truth TEXT NOT NULL, applies_to TEXT, at TEXT, UNIQUE (claim, truth));

CREATE TABLE competitor (competitor_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, city TEXT, known_stores INTEGER, threat_level TEXT);
CREATE TABLE competitor_move (move_id INTEGER PRIMARY KEY, competitor_id INTEGER NOT NULL REFERENCES competitor(competitor_id), city TEXT, move TEXT NOT NULL, UNIQUE (competitor_id, move));
CREATE TABLE event (event_id INTEGER PRIMARY KEY, headline TEXT NOT NULL UNIQUE, category TEXT, severity TEXT);

CREATE TABLE option_catalog (option_id INTEGER PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL, cost TEXT, stats_json TEXT, notes TEXT, UNIQUE (category, name));
CREATE TABLE capital_item (item_id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('capital','loan','investment','acquisition')), name TEXT NOT NULL, amount REAL, week INTEGER, status TEXT, notes TEXT);

CREATE TABLE document (           -- prose that stays as files: the database only indexes it, for search
  doc_id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, kind TEXT, title TEXT, week INTEGER, body TEXT
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
