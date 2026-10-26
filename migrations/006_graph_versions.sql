-- Episode 5B: a log of every knowledge-graph build. The graph itself lives in Neo4j; this table is the record that ties each graph version
-- to the search index version it was built beside, so "which graph was live when this answer was given" can always be answered from Postgres.
CREATE TABLE graph_versions (
    version        int PRIMARY KEY,
    index_version  int,                                   -- the search index built from the same curated snapshot
    n_nodes        int NOT NULL DEFAULT 0,
    n_edges        int NOT NULL DEFAULT 0,
    status         text NOT NULL CHECK (status IN ('building', 'ready', 'live', 'retired', 'failed')),
    run_id         text,
    built_at       timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON graph_versions TO chatbot_ro;
