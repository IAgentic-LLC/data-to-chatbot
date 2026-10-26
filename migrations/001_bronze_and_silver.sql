-- Episodes 1 and 2: what we have seen (bronze) and what we could read (silver).
CREATE TABLE IF NOT EXISTS bronze_files (
  source      text        NOT NULL,
  path        text        NOT NULL,
  sha256      text        NOT NULL,
  size        bigint      NOT NULL,
  storage_key text        NOT NULL,
  run_id      text        NOT NULL,
  fetched_at  timestamptz NOT NULL,
  PRIMARY KEY (source, path, sha256)
);
CREATE TABLE IF NOT EXISTS source_files (
  source        text    NOT NULL,
  path          text    NOT NULL,
  present       boolean NOT NULL,
  last_seen_run text    NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source, path)
);

CREATE TABLE IF NOT EXISTS silver_docs (
  doc_key       text PRIMARY KEY,
  source        text NOT NULL,
  path          text NOT NULL,
  bronze_sha256 text NOT NULL,
  parser        text NOT NULL,
  title         text NOT NULL,
  text          text NOT NULL,
  text_sha256   text NOT NULL,
  meta          jsonb NOT NULL DEFAULT '{}',
  parsed_at     timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS silver_rejects (
  source text NOT NULL, path text NOT NULL, bronze_sha256 text NOT NULL,
  reason text NOT NULL, rejected_at timestamptz NOT NULL,
  PRIMARY KEY (source, path, bronze_sha256)
);
