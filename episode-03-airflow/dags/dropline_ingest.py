"""The pipeline as one scheduled workflow. Built up over episodes 3, 4 and 5.

    migrate -> check_sources -> land_bronze -> build_silver -> curate -> run_checks -> build_index  (-> build_graph when GRAPH_ENABLED=1)
                                                                                          (promote comes in episode 7, behind a quality gate)

A DAG is a set of tasks plus the order they must run in. The scheduler runs it; you watch it in the web UI.
Rule of this course: tasks pass small facts (counts, ids) to each other, never the data itself. The data lives in the lake and the database.
"""
from datetime import datetime, timedelta

from airflow.sdk import dag, get_current_context, task

DEFAULT_ARGS = {
    "retries": 2,                          # a flaky network call gets two more tries...
    "retry_delay": timedelta(seconds=20),  # ...20 seconds apart
}


@dag(
    dag_id="dropline_ingest",
    schedule="@daily",                     # every day at midnight UTC; you can also trigger it by hand
    start_date=datetime(2026, 10, 1),
    catchup=False,                         # do not run every missed day since start_date
    max_active_runs=1,                     # two runs at once would fight over the same files
    default_args=DEFAULT_ARGS,
    tags=["course", "bronze", "silver", "curated", "gold"],
    doc_md=__doc__,
)
def dropline_ingest():
    @task
    def migrate() -> list:
        """Bring the database up to date before anything reads or writes it (the numbered files in migrations/)."""
        from pipeline import config
        from pipeline.migrate import apply_pending
        return apply_pending(config.DATABASE_URL)

    @task
    def check_sources() -> int:
        """Stop early, with a clear message, if the feeds are empty or missing."""
        from pipeline import config
        files = [p for p in config.SOURCES_DIR.rglob("*") if p.is_file()] if config.SOURCES_DIR.exists() else []
        if not files:
            raise ValueError(f"no source files found under {config.SOURCES_DIR}")
        return len(files)

    @task
    def land_bronze() -> dict:
        """Copy raw files into bronze exactly as received. Running it twice changes nothing (idempotent)."""
        from pipeline import config
        from pipeline.cli import audit_log, storage
        from pipeline.land import land
        from pipeline.manifest import PgManifest
        rid = get_current_context()["run_id"]       # the unique name of this DAG run, recorded in the manifest
        rep = land(config.SOURCES_DIR, storage(), PgManifest(config.DATABASE_URL), rid)
        audit_log().record("airflow", "land", rid, {"new": rep.new, "missing": rep.missing})
        return {"new": rep.new, "unchanged": rep.unchanged, "blobs_written": rep.stored, "missing": rep.missing}

    @task
    def build_silver(landed: dict) -> dict:
        """Parse and clean whatever bronze has that silver has not seen yet."""
        from pipeline import config
        from pipeline.cli import storage
        from pipeline.manifest import PgManifest
        from pipeline.silver import PgSilver, build_silver as run
        rep = run(PgManifest(config.DATABASE_URL), storage(), PgSilver(config.DATABASE_URL))
        return {"parsed": rep.parsed, "rejected": rep.rejected, "already_done": rep.skipped}

    @task
    def curate(silver: dict) -> dict:
        """Decide what may be searched: duplicates, old versions, personal data, instructions aimed at the model, retention, deletions."""
        from pipeline import config
        from pipeline.cli import audit_log
        from pipeline.curate import PgCurated, run_curation
        from pipeline.elt import install_views
        from pipeline.manifest import PgManifest
        from pipeline.silver import PgSilver
        store = PgCurated(config.DATABASE_URL)
        counts = run_curation(PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL), store)
        install_views(store.conn)
        audit_log().record("airflow", "curate", get_current_context()["run_id"], counts)
        return counts

    @task
    def run_checks(curated: dict) -> list:
        """Data quality checks. A failing blocking check stops the run here, so a bad batch can never reach the index."""
        from pipeline import config
        from pipeline.checks import run_all
        from pipeline.curate import PgCurated
        from pipeline.manifest import PgManifest
        from pipeline.silver import PgSilver
        m, s, c = PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL), PgCurated(config.DATABASE_URL)
        results = run_all(m.all(), s.docs(), s.rejects(), c.all())
        for r in results:
            print(r)
        failed = [r.name for r in results if not r.ok and r.blocking]
        if failed:
            raise ValueError("blocking checks failed: " + "; ".join(failed))
        return [str(r) for r in results]

    @task
    def build_index(checks: list) -> dict:
        """Build a NEW search index version beside the live one. Unchanged data builds nothing; unchanged chunks cost no embedding."""
        import psycopg
        from pipeline import config
        from pipeline.cli import audit_log
        from pipeline.curate import PgCurated
        from pipeline.embed import get_embedder
        from pipeline.index import build_index as build
        rid = get_current_context()["run_id"]
        conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
        emb = get_embedder()
        res = build(conn, PgCurated(config.DATABASE_URL).all(), emb, "section", run_id=rid)
        if not res.reused:
            audit_log().record("airflow", "index.build", f"v{res.version}", {"chunks": res.n_chunks, "embedded": res.n_embedded, "model": emb.name})
        return {"version": res.version, "chunks": res.n_chunks, "newly_embedded": res.n_embedded, "nothing_changed": res.reused}

    @task
    def build_graph(index: dict) -> dict:
        """Episode 5B: build the knowledge graph beside the search index (same version number), from the same curated documents. Only runs when GRAPH_ENABLED=1."""
        from pipeline import config
        from pipeline.cli import audit_log
        from pipeline.curate import PgCurated
        from pipeline.graph import Neo4jGraph, check_consistent, extract_graph
        curated = PgCurated(config.DATABASE_URL).all()
        data = extract_graph(curated)
        problems = check_consistent(data, curated)
        if problems:
            raise ValueError("graph would be inconsistent: " + "; ".join(problems))
        store = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
        store.replace_version(index["version"], data)
        n, e = store.counts(index["version"])
        audit_log().record("airflow", "graph.build", f"v{index['version']}", {"nodes": n, "edges": e})
        return {"version": index["version"], "nodes": n, "links": e}

    ready = migrate()
    found = check_sources()
    ready >> found                         # ">>" means "then"
    landed = land_bronze()
    found >> landed
    silver = build_silver(landed)
    curated = curate(silver)
    checked = run_checks(curated)
    built = build_index(checked)
    from pipeline import config as _cfg
    if _cfg.GRAPH_ENABLED:                 # episode 5B turns this on; until then the DAG has the seven tasks shown in episode 3
        build_graph(built)


dropline_ingest()
