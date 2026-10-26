-- Episode 5: the gold layer. One row per index version, an embedding cache, and the "live" pointer.
-- The chunk tables themselves (chunks_v1, chunks_v2, ...) are created by the build step, one per version.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS index_versions (
  version      integer PRIMARY KEY,
  created_at   timestamptz NOT NULL DEFAULT now(),
  status       text NOT NULL CHECK (status IN ('building', 'ready', 'live', 'retired')),
  embed_model  text NOT NULL,
  dim          integer NOT NULL,
  chunker      text NOT NULL,
  snapshot_sha text NOT NULL,           -- fingerprint of the exact documents this version was built from
  n_chunks     integer NOT NULL DEFAULT 0,
  n_embedded   integer NOT NULL DEFAULT 0,   -- how many chunks needed a NEW embedding (the rest came from the cache)
  run_id       text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS embedding_cache (
  text_sha256 text NOT NULL,
  model       text NOT NULL,
  embedding   vector NOT NULL,
  PRIMARY KEY (text_sha256, model)
);

-- name -> version. Serving always asks for the name 'live'. Promoting a new version is changing this one row.
CREATE TABLE IF NOT EXISTS index_alias (
  name       text PRIMARY KEY,
  version    integer NOT NULL REFERENCES index_versions(version),
  updated_at timestamptz NOT NULL DEFAULT now()
);
