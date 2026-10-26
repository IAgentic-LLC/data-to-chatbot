"""Episode 5: the gold layer. Build a searchable index, keep every version, search it, and switch the live one safely.

How a version is built:     curated documents -> chunks -> vectors (re-using cached ones) -> a NEW table chunks_vN -> status 'ready'
How a version goes live:    promote(N) changes one row (the alias 'live' now points at N). The old table stays, so rollback is promote(old).
Nothing here edits a table the chatbot is reading. That is what makes a bad build harmless."""
import re
from dataclasses import dataclass
from typing import Callable

from .chunk import Chunk, chunk_all
from .embed import Embedder
from .hashing import sha256_text

RRF_K = 60            # how strongly a top rank counts in the fusion (the usual default)


@dataclass
class BuildResult:
    version: int
    n_chunks: int
    n_embedded: int          # chunks that needed a new embedding
    reused: bool = False     # True: nothing changed since the last version, so we did not build another


@dataclass
class Hit:
    chunk_id: str
    score: float
    text: str
    doc_key: str
    source: str
    title: str
    section: str
    via: str                 # which search found it: vector, keyword or both


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def table(version: int) -> str:
    return f"chunks_v{int(version)}"         # int() so a table name can never carry anything but a number


def snapshot_sha(chunks: list[Chunk], chunker: str, model: str) -> str:
    """A fingerprint of everything that decides what the index contains. Same fingerprint -> same index, no need to rebuild."""
    parts = sorted(f"{c.chunk_id}:{sha256_text(c.for_search())}" for c in chunks)
    return sha256_text("|".join([chunker, model] + parts))


def build_index(conn, curated_docs, embedder: Embedder, chunker: str = "section", run_id: str = "") -> BuildResult:
    chunks = chunk_all([d for d in curated_docs if d.status == "accepted"], chunker)
    if not chunks:
        raise ValueError("nothing to index: no accepted documents")
    snap = snapshot_sha(chunks, chunker, embedder.name)
    same = conn.execute("SELECT version, n_chunks FROM index_versions WHERE snapshot_sha=%s AND status IN ('ready','live') ORDER BY version DESC LIMIT 1", (snap,)).fetchone()
    if same:
        return BuildResult(same[0], same[1], 0, reused=True)

    version = (conn.execute("SELECT coalesce(max(version), 0) FROM index_versions").fetchone()[0]) + 1
    conn.execute("INSERT INTO index_versions (version,status,embed_model,dim,chunker,snapshot_sha,run_id) VALUES (%s,'building',%s,%s,%s,%s,%s)",
                 (version, embedder.name, embedder.dim, chunker, snap, run_id))
    try:
        return _build(conn, chunks, embedder, chunker, version)
    except Exception:
        conn.execute("UPDATE index_versions SET status='failed' WHERE version=%s", (version,))     # never leave a build looking like it is still running
        raise


def _build(conn, chunks, embedder, chunker, version) -> BuildResult:
    shas = [sha256_text(c.for_search()) for c in chunks]
    have = {r[0]: r[1] for r in conn.execute(
        "SELECT text_sha256, embedding::text FROM embedding_cache WHERE model=%s AND text_sha256 = ANY(%s)", (embedder.name, shas)).fetchall()}
    todo = sorted({s for s in shas if s not in have})
    by_sha = {s: c for s, c in zip(shas, chunks)}
    new_vecs: dict[str, str] = {}
    for i in range(0, len(todo), 32):
        batch = todo[i:i + 32]
        for s, v in zip(batch, embedder.embed([by_sha[s].for_search() for s in batch])):
            new_vecs[s] = _vec(v)
            conn.execute("INSERT INTO embedding_cache (text_sha256,model,embedding) VALUES (%s,%s,%s::vector) ON CONFLICT DO NOTHING", (s, embedder.name, new_vecs[s]))
    t = table(version)
    with conn.transaction():
        conn.execute(f"""CREATE TABLE {t} (
            chunk_id text PRIMARY KEY, doc_key text NOT NULL, source text NOT NULL, title text, section text, text text NOT NULL,
            text_sha256 text NOT NULL, embedding vector({int(embedder.dim)}) NOT NULL, meta jsonb NOT NULL DEFAULT '{{}}',
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(section,'') || ' ' || text)) STORED)""")
        import json
        for c, s in zip(chunks, shas):
            vec = new_vecs.get(s) or have[s]
            conn.execute(f"INSERT INTO {t} (chunk_id,doc_key,source,title,section,text,text_sha256,embedding,meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector,%s)",
                         (c.chunk_id, c.doc_key, c.source, c.title, c.section, c.text, s, vec, json.dumps(c.meta)))
        conn.execute(f"CREATE INDEX ON {t} USING gin (tsv)")                          # keyword search
        conn.execute(f"CREATE INDEX ON {t} USING hnsw (embedding vector_cosine_ops)")   # fast nearest-neighbour search (pointless at 50 rows, essential at 5 million)
        conn.execute(f"GRANT SELECT ON {t} TO chatbot_ro")                            # least privilege: the chatbot may read this table, nothing else
        conn.execute("UPDATE index_versions SET status='ready', n_chunks=%s, n_embedded=%s WHERE version=%s", (len(chunks), len(todo), version))
    return BuildResult(version, len(chunks), len(todo))


def live_version(conn) -> int | None:
    row = conn.execute("SELECT version FROM index_alias WHERE name='live'").fetchone()
    return row[0] if row else None


def promote(conn, version: int, audit=None, actor: str = "system") -> int | None:
    """Make `version` the one the chatbot searches. Returns the version it replaced. Rollback is promote(<old version>)."""
    row = conn.execute("SELECT status FROM index_versions WHERE version=%s", (version,)).fetchone()
    if not row or row[0] not in ("ready", "live", "retired"):
        raise ValueError(f"version {version} is not built (status: {row[0] if row else 'missing'})")
    old = live_version(conn)
    with conn.transaction():
        if old is not None and old != version:
            conn.execute("UPDATE index_versions SET status='retired' WHERE version=%s", (old,))
        conn.execute("UPDATE index_versions SET status='live' WHERE version=%s", (version,))
        conn.execute("INSERT INTO index_alias (name,version) VALUES ('live',%s) ON CONFLICT (name) DO UPDATE SET version=EXCLUDED.version, updated_at=now()", (version,))
    if audit:
        audit.record(actor, "index.promote", f"v{version}", {"replaced": old})
    return old


def _keyword_query(q: str) -> str | None:
    words = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 1]
    return " | ".join(dict.fromkeys(words)) or None          # OR between words; the 'english' setting drops filler words like "the"


def search(conn, embedder: Embedder, query: str, version: int | None = None, k: int = 5, mode: str = "hybrid", source: str | None = None) -> list[Hit]:
    version = version or live_version(conn)
    if version is None:
        raise ValueError("no live index yet: build one and promote it")
    t = table(version)
    where, params = ("WHERE source = %s", [source]) if source else ("", [])
    cols = "chunk_id, text, doc_key, source, title, section"
    vec_rows, kw_rows = [], []
    if mode in ("vector", "hybrid"):
        qv = _vec(embedder.embed_query(query))
        vec_rows = conn.execute(f"SELECT {cols} FROM {t} {where} ORDER BY embedding <=> %s::vector LIMIT %s", params + [qv, 20]).fetchall()
    if mode in ("keyword", "hybrid"):
        tsq = _keyword_query(query)
        if tsq:
            w = f"{where} AND" if where else "WHERE"
            kw_rows = conn.execute(
                f"SELECT {cols} FROM {t} {w} tsv @@ to_tsquery('english', %s) ORDER BY ts_rank_cd(tsv, to_tsquery('english', %s)) DESC LIMIT %s",
                params + [tsq, tsq, 20]).fetchall()
    # Reciprocal rank fusion: a chunk earns 1/(60+rank) from each list it appears in. High in both lists wins.
    scores: dict[str, float] = {}
    rows: dict[str, tuple] = {}
    via: dict[str, set] = {}
    for name, lst in (("vector", vec_rows), ("keyword", kw_rows)):
        for rank, r in enumerate(lst, 1):
            scores[r[0]] = scores.get(r[0], 0.0) + 1.0 / (RRF_K + rank)
            rows[r[0]] = r
            via.setdefault(r[0], set()).add(name)
    top = sorted(scores, key=lambda c: -scores[c])[:k]
    return [Hit(c, scores[c], rows[c][1], rows[c][2], rows[c][3], rows[c][4], rows[c][5], "+".join(sorted(via[c]))) for c in top]


def explain(conn, version: int, chunk_id: str) -> dict | None:
    """Lineage for one chunk: which document, which raw file (by hash), which pipeline run brought it in."""
    t = table(version)
    row = conn.execute(f"SELECT doc_key, source FROM {t} WHERE chunk_id=%s", (chunk_id,)).fetchone()
    if not row:
        return None
    lin = conn.execute("SELECT run_id, fetched_at, raw_sha256, storage_key FROM v_lineage WHERE doc_key=%s", (row[0],)).fetchone()
    return {"chunk": chunk_id, "document": row[0], "feed": row[1], "index_version": version,
            "pipeline_run": lin[0] if lin else None, "raw_file_fetched_at": lin[1] if lin else None,
            "raw_file_hash": lin[2] if lin else None, "stored_at": lin[3] if lin else None}


def chunk_texts(conn, version: int) -> list[tuple[str, str]]:
    """(chunk id, text) for every chunk of a version; used by the erasure check to prove nobody is left in the index."""
    return conn.execute(f"SELECT chunk_id, text FROM {table(version)}").fetchall()
