-- 002: keep every field of a decision (do-not-yet, risks, ...) so decision search reads the same text as the ledger did.
ALTER TABLE decision ADD COLUMN detail_json TEXT;
