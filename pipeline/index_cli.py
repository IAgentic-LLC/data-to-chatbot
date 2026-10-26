"""Episode 5 commands:
  python -m pipeline.index_cli build   [--chunker section|fixed] [--embedder fastembed|hash]
  python -m pipeline.index_cli list
  python -m pipeline.index_cli promote N
  python -m pipeline.index_cli search "your question" [--mode hybrid|vector|keyword] [--version N] [--k 5]
  python -m pipeline.index_cli eval [--version N] [--mode hybrid|vector|keyword] [--k 5]       (dev questions only)
  python -m pipeline.index_cli explain CHUNK_ID [--version N]
  python -m pipeline.index_cli grant-chatbot                                                    (give the read-only chatbot login a password)
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
from .index import build_index, explain, live_version, promote, search
from .migrate import apply_pending


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="index_cli", usage=__doc__)
    ap.add_argument("cmd", choices=["build", "list", "promote", "search", "eval", "explain", "grant-chatbot"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--chunker", default="section")
    ap.add_argument("--embedder", default=None)
    ap.add_argument("--mode", default="hybrid")
    ap.add_argument("--version", type=int, default=None)
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args(argv)

    apply_pending(config.DATABASE_URL)
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)

    if a.cmd == "build":
        emb = get_embedder(a.embedder)
        res = build_index(conn, PgCurated(config.DATABASE_URL).all(), emb, a.chunker, run_id="idx-" + uuid.uuid4().hex[:8])
        if res.reused:
            print(f"nothing changed since version {res.version}: no new index built (0 texts embedded)")
        else:
            print(f"built version {res.version}: {res.n_chunks} chunks, {res.n_embedded} newly embedded, {res.n_chunks - res.n_embedded} reused from the cache")
            audit_log().record(actor(), "index.build", f"v{res.version}", {"chunks": res.n_chunks, "embedded": res.n_embedded, "chunker": a.chunker, "model": emb.name})
    elif a.cmd == "list":
        live = live_version(conn)
        print("version  status    chunker  model                   chunks  new-embeds  created")
        for v, st, ch, mo, n, ne, ts in conn.execute("SELECT version,status,chunker,embed_model,n_chunks,n_embedded,created_at FROM index_versions ORDER BY version"):
            print(f"{v:>7}  {st:<8}  {ch:<7}  {mo:<22}  {n:>6}  {ne:>10}  {ts:%Y-%m-%d %H:%M}" + ("   <- live" if v == live else ""))
    elif a.cmd == "promote":
        old = promote(conn, int(a.arg), audit_log(), actor())
        print(f"version {a.arg} is now live (replaced {old})")
    elif a.cmd in ("search", "eval", "explain"):
        version = a.version or live_version(conn)
        if version is None:
            print("no live index: run 'build' then 'promote N'")
            return 1
        row = conn.execute("SELECT embed_model FROM index_versions WHERE version=%s", (version,)).fetchone()
        emb = get_embedder("hash" if row[0].startswith("hash") else "fastembed")
        if a.cmd == "search":
            for h in search(conn, emb, a.arg, version, a.k, a.mode):
                print(f"{h.score:.4f}  {h.chunk_id:<46} [{h.via}]\n         {h.text[:110].replace(chr(10), ' ')}")
        elif a.cmd == "explain":
            for k, v in (explain(conn, version, a.arg) or {"error": "no such chunk in that version"}).items():
                print(f"  {k}: {v}")
        else:
            golden = load_golden(split="dev")
            ref = reference_chunks(PgCurated(config.DATABASE_URL).all())
            rep = retrieval_eval(lambda q, k: search(conn, emb, q, version, k, a.mode), golden, ref, a.k)
            print(f"version {version}, mode {a.mode}: {rep}")
            for qid, missing in rep.misses:
                print(f"  {qid} missed: {', '.join(missing)}")
    elif a.cmd == "grant-chatbot":
        pw = a.arg or "chatbot-dev-only"
        conn.execute(f"ALTER ROLE chatbot_ro LOGIN PASSWORD '{pw.replace(chr(39), '')}'")
        print("chatbot_ro can now log in (read-only on the search index). Dev password; episode 9 sets a real one from a secret.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
