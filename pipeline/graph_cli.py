"""Episode 5B commands (the graph is built from the same curated documents as the search index, and carries the same version number):
  python -m pipeline.graph_cli build   [--version N] [--store neo4j|memory]     build graph version N (default: the live index version)
  python -m pipeline.graph_cli promote N                                         make graph version N the live one
  python -m pipeline.graph_cli status
  python -m pipeline.graph_cli ask "your question" [--hops 2]                    which links the question touches, and which documents they lead to
  python -m pipeline.graph_cli eval [--k 5]                                      does adding the graph find more of the right chunks? (dev questions only, multi-hop ones)
"""
import argparse
import sys
import uuid

import psycopg

from . import config
from .cli import actor, audit_log
from .curate import PgCurated
from .embed import get_embedder
from .evalset import load_golden, reference_chunks, retrieval_eval
from .graph import MemoryGraph, Neo4jGraph, check_consistent, expand, extract_graph, find_in_question
from .index import Hit, live_version, search, table
from .migrate import apply_pending

EXTRA = 3        # the graph may add at most this many chunks to what search found, so the comparison stays honest and the prompt stays small


def open_store(kind: str):
    if kind == "memory":
        return MemoryGraph()
    g = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
    if not g.ping():
        raise SystemExit("cannot reach Neo4j at " + config.NEO4J_URI + ". Start it with:  docker compose --profile graph up -d graph   (or use --store memory)")
    return g


def graph_chunks(conn, index_version: int, answer, limit: int = EXTRA) -> list[Hit]:
    """Chunks of the documents the graph pointed at that actually mention the things the walk touched. The graph says WHERE to read; Postgres holds the text."""
    if not answer.documents:
        return []
    terms = [t for t in answer.terms]
    if not terms:
        return []
    rows = conn.execute(f"SELECT chunk_id, text, doc_key, source, title, section FROM {table(index_version)} WHERE doc_key = ANY(%s)", (answer.documents,)).fetchall()
    scored = []
    for r in rows:
        hay = (r[1] + " " + (r[5] or "")).lower()
        s = sum(1 for t in terms if t.lower() in hay or (t in ("EU", "UK", "US") and f"{t.lower()} " in hay))
        if s:
            scored.append((s, -answer.documents.index(r[2]), r))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [Hit(r[0], float(s), r[1], r[2], r[3], r[4], r[5], "graph") for s, _, r in scored[:limit]]


def search_with_graph(conn, emb, store, gversion: int, index_version: int, question: str, k: int, hops: int = 2) -> list[Hit]:
    hits = search(conn, emb, question, index_version, k, "hybrid")
    ans = expand(store, gversion, find_in_question(question), hops)
    have = {h.chunk_id for h in hits}
    return hits + [h for h in graph_chunks(conn, index_version, ans) if h.chunk_id not in have]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="graph_cli", usage=__doc__)
    ap.add_argument("cmd", choices=["build", "promote", "status", "ask", "eval"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--version", type=int, default=None)
    ap.add_argument("--store", default="neo4j")
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args(argv)

    apply_pending(config.DATABASE_URL)
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)

    if a.cmd == "build":
        iv = a.version or live_version(conn)
        if iv is None:
            print("no search index yet: build and promote one first (episode 5)")
            return 1
        curated = PgCurated(config.DATABASE_URL).all()
        data = extract_graph(curated)
        problems = check_consistent(data, curated)
        if problems:
            print("refusing to build, the graph would be inconsistent:\n  " + "\n  ".join(problems))
            return 1
        store = open_store(a.store)
        conn.execute("INSERT INTO graph_versions (version,index_version,status,run_id) VALUES (%s,%s,'building',%s) ON CONFLICT (version) DO UPDATE SET status=CASE WHEN graph_versions.status='live' THEN 'live' ELSE 'building' END, run_id=EXCLUDED.run_id",
                     (iv, iv, "graph-" + uuid.uuid4().hex[:8]))
        try:
            store.replace_version(iv, data)
            n, e = store.counts(iv)
        except Exception:
            conn.execute("UPDATE graph_versions SET status='failed' WHERE version=%s", (iv,))
            raise
        conn.execute("UPDATE graph_versions SET status=CASE WHEN status='live' THEN 'live' ELSE 'ready' END, n_nodes=%s, n_edges=%s WHERE version=%s", (n, e, iv))
        kinds = {}
        for node in data.nodes.values():
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        print(f"built graph version {iv}: {n} nodes ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}), {e} links, from {sum(1 for d in curated if d.status == 'accepted')} accepted documents")
        audit_log().record(actor(), "graph.build", f"v{iv}", {"nodes": n, "edges": e})
    elif a.cmd == "promote":
        store = open_store(a.store)
        v = int(a.arg)
        old = store.promote(v)
        conn.execute("UPDATE graph_versions SET status='retired' WHERE status='live'")
        conn.execute("UPDATE graph_versions SET status='live' WHERE version=%s", (v,))
        audit_log().record(actor(), "graph.promote", f"v{v}", {"replaced": old})
        print(f"graph version {v} is now live (replaced {old})")
    elif a.cmd == "status":
        print("graph  index   status    nodes  links  built")
        for v, iv, st, n, e, ts in conn.execute("SELECT version,index_version,status,n_nodes,n_edges,built_at FROM graph_versions ORDER BY version"):
            print(f"{v:>5}  {iv:>5}   {st:<8}  {n:>5}  {e:>5}  {ts:%Y-%m-%d %H:%M}")
    elif a.cmd == "ask":
        store = open_store(a.store)
        gv = store.live_version()
        if gv is None:
            print("no live graph: run 'build' then 'promote N'")
            return 1
        seeds = find_in_question(a.arg)
        ans = expand(store, gv, seeds, a.hops)
        print(f"things the question names: {', '.join(seeds) or 'none'}   (found in the graph: {', '.join(ans.seeds) or 'none'})")
        for p in ans.paths:
            print("  link:", p)
        print("documents the links lead to:", ", ".join(ans.documents) or "none")
        for h in graph_chunks(conn, live_version(conn), ans):
            print(f"  chunk {h.chunk_id}: {h.text[:100].replace(chr(10), ' ')}")
    elif a.cmd == "eval":
        store = open_store(a.store)
        iv = a.version or live_version(conn)
        gv = store.live_version() if a.store != "memory" else None
        if a.store == "memory":                              # a throwaway in-memory graph built right now
            store.replace_version(iv, extract_graph(PgCurated(config.DATABASE_URL).all())); gv = iv
        if gv is None:
            print("no live graph: run 'build' then 'promote N'")
            return 1
        row = conn.execute("SELECT embed_model FROM index_versions WHERE version=%s", (iv,)).fetchone()
        emb = get_embedder("hash" if row[0].startswith("hash") else "fastembed")
        golden = [g for g in load_golden(split="dev") if g.get("hops", 1) >= 2]
        ref = reference_chunks(PgCurated(config.DATABASE_URL).all())
        sizes = {"search": [], "search+graph": []}

        def plain(q, k):
            h = search(conn, emb, q, iv, k, "hybrid"); sizes["search"].append(len(h)); return h

        def withg(q, k):
            h = search_with_graph(conn, emb, store, gv, iv, q, k, a.hops); sizes["search+graph"].append(len(h)); return h
        r1, r2 = retrieval_eval(plain, golden, ref, a.k), retrieval_eval(withg, golden, ref, a.k)
        print(f"multi-hop dev questions: {r1.questions}  (index v{iv}, graph v{gv}, k={a.k})")
        for name, key, r in (("search only   ", "search", r1), ("search + graph", "search+graph", r2)):
            n = sizes[key]
            print(f"  {name} {r}   avg chunks given to the model: {sum(n) / max(1, len(n)):.1f}")
        for qid, missing in r2.misses:
            print(f"  still missed with the graph: {qid}: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
