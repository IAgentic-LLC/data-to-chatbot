"""Changing a database that already holds data, safely.

A migration is a numbered SQL file in migrations/. This runner applies each file once, in order, and remembers which ones it has applied
(in the table schema_migrations). Two rules:
  1. Never edit a migration that has already been applied anywhere. To change a table, add a new file with the next number.
  2. Every change to the database is a file in version control, so a fresh machine ends up with exactly the same tables as yours.
This is exactly what the tool Alembic does (it adds Python scripting, auto-detection of model changes and downgrade paths).
We keep it to 40 lines so you can read all of it; the idea transfers directly."""
from pathlib import Path

from . import config

MIGRATIONS_DIR = config.ROOT / "migrations"
_done: set[str] = set()


def apply_pending(url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet applied. Returns the names it applied (usually none)."""
    import psycopg
    if url in _done:
        return []
    applied: list[str] = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        have = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for f in sorted(Path(directory).glob("*.sql")):
            if f.name in have:
                continue
            with conn.transaction():                       # all of a file, or none of it
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.name,))
            applied.append(f.name)
    _done.add(url)
    return applied
