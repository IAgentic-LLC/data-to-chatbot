"""Run one stage from the terminal:
  python -m pipeline.cli land | silver | curate | checks | review [list|approve KEY|reject KEY] | status | reset-db
  governance:  find EMAIL | erase EMAIL | audit
Index commands (episode 5) live in pipeline.index_cli:  python -m pipeline.index_cli build | list | promote N | search "question"
"""
import getpass
import sys
import uuid

from . import config
from .land import land
from .manifest import PgManifest
from .silver import PgSilver, build_silver
from .storage import S3Storage


def storage() -> S3Storage:
    return S3Storage(config.S3_ENDPOINT, config.S3_ACCESS_KEY, config.S3_SECRET_KEY, config.S3_BUCKET)


def actor() -> str:
    """Who is running this. The audit log records it with every action."""
    return getpass.getuser()


def audit_log():
    from .audit import PgAudit
    return PgAudit(config.DATABASE_URL)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    run_id = "cli-" + uuid.uuid4().hex[:8]
    if cmd == "land":
        rep = land(config.SOURCES_DIR, storage(), PgManifest(config.DATABASE_URL), run_id)
        print("landing:", rep)
        audit_log().record(actor(), "land", run_id, {"new": rep.new, "missing": rep.missing})
    elif cmd == "silver":
        print("silver:", build_silver(PgManifest(config.DATABASE_URL), storage(), PgSilver(config.DATABASE_URL)))
    elif cmd == "curate":
        from .curate import PgCurated, run_curation
        from .elt import install_views
        store = PgCurated(config.DATABASE_URL)
        counts = run_curation(PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL), store)
        install_views(store.conn)
        print("curated:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        audit_log().record(actor(), "curate", run_id, counts)
        for c in store.all():
            if c.status != "accepted":
                print(f"  {c.status:16} {c.doc_key}: {c.reason}")
    elif cmd == "checks":
        from .checks import run_all
        from .curate import PgCurated
        m, s, c = PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL), PgCurated(config.DATABASE_URL)
        results = run_all(m.all(), s.docs(), s.rejects(), c.all())
        for r in results:
            print(r)
        return 1 if any(not r.ok and r.blocking for r in results) else 0
    elif cmd == "review":
        from .curate import PgCurated
        store = PgCurated(config.DATABASE_URL)
        sub = argv[1] if len(argv) > 1 else "list"
        if sub == "list":
            decided = store.decisions()
            queue = [c for c in store.all() if c.status == "quarantined" and c.doc_key not in decided]
            print(f"{len(queue)} document(s) waiting for review")
            for c in queue:
                print(f"  {c.doc_key}: {c.reason}")
        elif sub in ("approve", "reject") and len(argv) > 2:
            store.decide(argv[2], sub, " ".join(argv[3:]))
            audit_log().record(actor(), "review." + sub, argv[2], {"note": " ".join(argv[3:])})
            print(f"{sub}{'d' if sub == 'approve' else 'ed'} {argv[2]}. Run 'curate' again to apply it.")
        else:
            print("usage: review [list | approve KEY | reject KEY]")
            return 2
    elif cmd in ("find", "erase") and len(argv) > 1:
        from .curate import PgCurated
        from .erasure import erase_subject, find_subject
        m, sv, cu = PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL), PgCurated(config.DATABASE_URL)
        who = argv[1]
        if cmd == "find":
            print("found in:", find_subject(who, m, storage(), sv, cu))
        else:
            print("before:", find_subject(who, m, storage(), sv, cu))
            print("erasing:", erase_subject(who, m, storage(), audit_log(), actor(), "erase-" + uuid.uuid4().hex[:8]))
            print("rebuilding silver and curated ...")
            build_silver(m, storage(), sv)
            from .curate import run_curation
            run_curation(m, sv, cu)
            print("after: ", find_subject(who, m, storage(), sv, cu))
    elif cmd == "audit":
        from .audit import verify
        entries = audit_log().entries()
        for e in entries[-15:]:
            print(f"  #{e.seq} {e.at:%Y-%m-%d %H:%M} {e.actor} {e.action} {e.target} {e.detail}")
        print("chain check:", *verify(entries))
    elif cmd == "status":
        m, s = PgManifest(config.DATABASE_URL), PgSilver(config.DATABASE_URL)
        print(f"bronze files recorded: {len(m.all())}   silver documents: {len(s.docs())}   rejected: {len(s.rejects())}")
        for r in s.rejects():
            print(f"  rejected {r.source}/{r.path}: {r.reason}")
    elif cmd == "reset-db":
        import psycopg
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as c:
            c.execute("DROP VIEW IF EXISTS v_curation_summary, v_review_queue, v_lineage, v_searchable_docs")
            c.execute("DROP TABLE IF EXISTS curated_docs, curation_decisions, silver_docs, silver_rejects, bronze_files, source_files")
            # the audit log is NOT dropped: it is append-only history, and it survives a reset on purpose
        print("tables dropped (bronze blobs in the lake are kept; the search index is kept)")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
