-- 004: keyword search with ranking over reviews, every screen's text, and the briefings and knowledge pages.
CREATE VIRTUAL TABLE review_fts   USING fts5(text, tokenize='porter unicode61');
CREATE VIRTUAL TABLE source_fts   USING fts5(text, tokenize='porter unicode61');
CREATE VIRTUAL TABLE document_fts USING fts5(text, tokenize='porter unicode61');
