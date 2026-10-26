"""Episode 5 tests. The first half needs nothing but Python. The second half uses the Postgres from `docker compose up -d`, in a THROWAWAY database
that is created and dropped by the test, so your real data is never touched. If Docker is not running those tests are skipped, not failed."""
import dataclasses
import math
import uuid
from datetime import date

import pytest

from pipeline import config
from pipeline.chunk import chunk_all, chunk_by_section, chunk_fixed, doc_stem, slug
from pipeline.curate import curate
from pipeline.embed import HashEmbedder
from pipeline.evalset import covers, retrieval_eval
from pipeline.index import Hit, build_index, explain, live_version, promote, search
from pipeline.land import land
from pipeline.manifest import MemoryManifest
from pipeline.migrate import apply_pending
from pipeline.policy import load
from pipeline.silver import MemorySilver, build_silver
from pipeline.storage import LocalStorage
from tests.test_bronze_silver import sources  # noqa: F401

DOC = "# Refund Policy\nOwner: CX.\n\n## Standard returns\nThirty days for normal items.\n\n## Limited drops\nSeven days for drop items.\n"


# ---- chunking ------------------------------------------------------------------------------------------------

def test_doc_stem_and_slug():
    assert doc_stem("wiki/refund-policy.md") == ("refund-policy", None)
    assert doc_stem("tickets/tickets_2026-05.json#T-1001") == ("tickets_2026-05", "T-1001")
    assert slug("Limited drops (EU)") == "limited-drops-eu"


def test_section_chunker_makes_one_chunk_per_heading_with_stable_ids():
    ids = [c.chunk_id for c in chunk_by_section("wiki/refund-policy.md", "wiki", "Refund Policy", DOC)]
    assert ids == ["refund-policy#overview", "refund-policy#standard-returns", "refund-policy#limited-drops"]


def test_long_sections_are_split_at_paragraph_breaks():
    long = "# T\n\n## Big\n" + "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(8))
    cs = chunk_by_section("wiki/t.md", "wiki", "T", long, max_chars=500)
    assert len(cs) > 1 and all(len(c.text) <= 700 for c in cs)
    assert cs[1].chunk_id == "t#big-2"


def test_fixed_chunker_overlaps_and_ids_are_unique_across_tickets():
    cs = chunk_fixed("wiki/a.md", "wiki", "A", "x" * 1000, size=400, overlap=100)
    assert [len(c.text) for c in cs][:2] == [400, 400] and cs[0].text[-100:] == cs[1].text[:100]

    class D:  # a minimal stand-in for a curated document
        def __init__(self, key):
            self.doc_key, self.source, self.title, self.text, self.doc_date, self.status = key, "tickets", "t", "some ticket text " * 5, None, "accepted"
    ids = [c.chunk_id for c in chunk_all([D("tickets/t.json#T-1"), D("tickets/t.json#T-2")], "fixed")]
    assert len(ids) == len(set(ids))


# ---- embeddings and evaluation helpers ---------------------------------------------------------------------

def test_hash_embedder_is_deterministic_unit_length_and_prefers_shared_words():
    e = HashEmbedder()
    a, b, c = e.embed(["return window for drop items", "drop items return window", "shipping rates to Germany"])
    assert a == e.embed(["return window for drop items"])[0]
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))  # noqa: E731
    assert dot(a, b) > dot(a, c)
    assert e.texts_embedded == 4


def test_covers_is_about_shared_words_not_ids():
    ref = "Customers with an EU delivery address always keep the legal 14-day right of withdrawal, including for limited drops."
    assert covers(ref, "Note: " + ref + " More text.")
    assert not covers(ref, "Shipping takes three to five days.")


def test_eval_scores_recall_and_skips_questions_about_missing_documents():
    ref = {"a#x": "alpha beta gamma delta epsilon zeta eta theta", "b#y": "one two three four five six seven eight"}
    golden = [{"id": "q1", "q": "?", "expect": ["a#x"]}, {"id": "q2", "q": "?", "expect": ["a#x", "b#y"]}, {"id": "q3", "q": "?", "expect": ["gone#z"]}]
    rep = retrieval_eval(lambda q, k: [ref["a#x"]], golden, ref, k=5)
    assert rep.questions == 2 and rep.skipped == ["q3"]
    assert rep.recall == pytest.approx((1.0 + 0.5) / 2) and rep.all_found == 0.5 and rep.misses == [("q2", ["b#y"])]


# ---- database part ------------------------------------------------------------------------------------------

def _server_up() -> bool:
    try:
        import psycopg
        psycopg.connect(config.DATABASE_URL, connect_timeout=3).close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _server_up(), reason="start the database first: docker compose up -d")


@pytest.fixture()
def conn():
    import psycopg
    name = "t_" + uuid.uuid4().hex[:10]
    admin = psycopg.connect(config.DATABASE_URL, autocommit=True)
    admin.execute(f"CREATE DATABASE {name}")
    url = config.DATABASE_URL.rsplit("/", 1)[0] + "/" + name
    apply_pending(url)
    c = psycopg.connect(url, autocommit=True)
    yield c
    c.close()
    admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


@pytest.fixture()
def curated(sources, tmp_path):  # noqa: F811
    st, m, s = LocalStorage(tmp_path / "b"), MemoryManifest(), MemorySilver()
    land(sources, st, m, "r")
    build_silver(m, st, s)
    return curate(s.docs(), m.present(), {}, policies=load(), today=date(2026, 10, 25))


@needs_db
def test_migrations_apply_once_and_create_the_tables(conn):
    names = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    assert {"001_bronze_and_silver.sql", "004_chatbot_role.sql", "005_index_failed_status.sql"} <= names
    assert apply_pending(config.DATABASE_URL.rsplit("/", 1)[0] + "/" + conn.info.dbname) == []      # second time: nothing to do


@needs_db
def test_build_is_idempotent_and_incremental(conn, curated):
    emb = HashEmbedder()
    first = build_index(conn, curated, emb, "section")
    assert first.n_chunks > 20 and first.n_embedded == first.n_chunks and not first.reused
    again = build_index(conn, curated, emb, "section")
    assert again.reused and again.version == first.version
    changed = [dataclasses.replace(c, text=c.text + "\n\n## Extra\nA brand new fact about parcels.") if c.doc_key == "wiki/on-call.md" else c for c in curated]
    third = build_index(conn, changed, emb, "section")
    assert third.version == first.version + 1 and 0 < third.n_embedded <= 3          # only the new piece paid for an embedding


@needs_db
def test_only_accepted_documents_reach_the_index(conn, curated):
    build_index(conn, curated, HashEmbedder(), "section")
    keys = {r[0] for r in conn.execute("SELECT DISTINCT doc_key FROM chunks_v1").fetchall()}
    assert "uploads/partner-faq.md" not in keys and "uploads/refund-policy-OLD-2026-01.md" not in keys and "web/refund-policy.html" not in keys
    assert "wiki/refund-policy.md" in keys
    text = " ".join(r[0] for r in conn.execute("SELECT text FROM chunks_v1").fetchall())
    assert "maria.santos" not in text and "7700 900123" not in text


@needs_db
def test_search_promote_and_rollback(conn, curated):
    emb = HashEmbedder()
    v1 = build_index(conn, curated, emb, "section").version
    with pytest.raises(ValueError):
        search(conn, emb, "return window", None)                                    # nothing live yet
    assert promote(conn, v1) is None and live_version(conn) == v1
    top = search(conn, emb, "EU customers right of withdrawal 14 days drop", k=3)
    assert isinstance(top[0], Hit) and any(h.chunk_id == "refund-policy#eu-customers" for h in top)
    assert {h.via for h in search(conn, emb, "checkout error E-4029", mode="keyword")} == {"keyword"}
    smaller = [c for c in curated if c.source != "tickets"]
    v2 = build_index(conn, smaller, emb, "section").version
    assert promote(conn, v2) == v1 and live_version(conn) == v2
    assert promote(conn, v1) == v2 and live_version(conn) == v1                       # rollback is just promoting the old version
    assert conn.execute("SELECT status FROM index_versions WHERE version=%s", (v2,)).fetchone()[0] == "retired"


@needs_db
def test_failed_build_is_marked_failed(conn, curated, monkeypatch):
    emb = HashEmbedder()
    monkeypatch.setattr(emb, "_embed", lambda texts: (_ for _ in ()).throw(RuntimeError("provider down")))
    with pytest.raises(RuntimeError):
        build_index(conn, curated, emb, "section")
    assert conn.execute("SELECT status FROM index_versions").fetchone()[0] == "failed"


@needs_db
def test_chatbot_role_can_read_the_index_and_nothing_else(conn, curated):
    import psycopg
    build_index(conn, curated, HashEmbedder(), "section")
    conn.execute("ALTER ROLE chatbot_ro LOGIN PASSWORD 'test-only'")
    url = config.DATABASE_URL.rsplit("/", 1)[0].replace("pipeline:pipeline", "chatbot_ro:test-only") + "/" + conn.info.dbname
    bot = psycopg.connect(url, autocommit=True)
    assert bot.execute("SELECT count(*) FROM chunks_v1").fetchone()[0] > 0
    for forbidden in ("silver_docs", "bronze_files", "curated_docs", "audit_log"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            bot.execute(f"SELECT * FROM {forbidden}")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        bot.execute("DELETE FROM chunks_v1")
    bot.close()
    conn.execute("ALTER ROLE chatbot_ro NOLOGIN")


@needs_db
def test_audit_log_blocks_edits_in_the_database_itself(conn):
    import psycopg
    from pipeline.audit import PgAudit
    log = PgAudit(config.DATABASE_URL.rsplit("/", 1)[0] + "/" + conn.info.dbname)
    log.record("t", "x", "y", {})
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE audit_log SET actor='mallory'")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM audit_log")
