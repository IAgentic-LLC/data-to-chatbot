-- Episode 4: curation decisions, the human review record, and the tamper-evident audit log.
CREATE TABLE IF NOT EXISTS curated_docs (
  doc_key text PRIMARY KEY, source text NOT NULL, path text NOT NULL, status text NOT NULL, reason text NOT NULL,
  title text NOT NULL, text text NOT NULL, canonical_key text, doc_date text, pii jsonb NOT NULL DEFAULT '{}',
  flags jsonb NOT NULL DEFAULT '[]', bronze_sha256 text NOT NULL, curated_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS curation_decisions (
  doc_key text PRIMARY KEY, decision text NOT NULL CHECK (decision IN ('approve','reject')), note text, decided_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
  seq bigserial PRIMARY KEY, at timestamptz NOT NULL, actor text NOT NULL, action text NOT NULL, target text NOT NULL,
  detail jsonb NOT NULL, prev_hash text NOT NULL, hash text NOT NULL
);
-- Nothing may rewrite history: block UPDATE and DELETE at the database level.
CREATE OR REPLACE FUNCTION audit_log_no_edit() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_log_no_edit ON audit_log;
CREATE TRIGGER audit_log_no_edit BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_log_no_edit();
