"""The manifest is the pipeline's memory: one row per (source, path, content hash) ever seen, plus which paths exist right now."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .migrate import apply_pending


@dataclass
class FileRecord:
    source: str          # which feed it came from: wiki, web, pdf, tickets, prices, uploads
    path: str            # path relative to the source folder
    sha256: str          # hash of the exact bytes
    size: int
    storage_key: str     # where the bytes are kept in bronze
    run_id: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Manifest(Protocol):
    def seen(self, source: str, path: str, sha256: str) -> bool: ...
    def add(self, rec: FileRecord) -> None: ...
    def all(self) -> list[FileRecord]: ...
    def latest(self) -> list[FileRecord]: ...
    def set_present(self, present: set[tuple[str, str]], run_id: str) -> list[tuple[str, str]]: ...
    def present(self) -> set[tuple[str, str]]: ...


class MemoryManifest:
    def __init__(self):
        self.rows: dict[tuple, FileRecord] = {}
        self._order: list[tuple] = []
        self._present: dict[tuple[str, str], bool] = {}

    def seen(self, source, path, sha256):
        return (source, path, sha256) in self.rows

    def add(self, rec):
        key = (rec.source, rec.path, rec.sha256)
        if key not in self.rows:
            self._order.append(key)
        self.rows[key] = rec

    def all(self):
        return [self.rows[k] for k in self._order]

    def latest(self):
        """Newest version of every file. Older versions stay in the manifest (history) but are not the current truth."""
        newest: dict[tuple[str, str], FileRecord] = {}
        for k in self._order:
            r = self.rows[k]
            newest[(r.source, r.path)] = r        # later insertions win
        return list(newest.values())

    def set_present(self, present, run_id):
        gone = [k for k, v in self._present.items() if v and k not in present]
        for k in present:
            self._present[k] = True
        for k in gone:
            self._present[k] = False
        return sorted(gone)

    def present(self):
        return {k for k, v in self._present.items() if v}




class PgManifest:
    def __init__(self, url: str):
        import psycopg
        apply_pending(url)                                   # tables come from migrations/, not from this file
        self.conn = psycopg.connect(url, autocommit=True)

    def seen(self, source, path, sha256):
        row = self.conn.execute("SELECT 1 FROM bronze_files WHERE source=%s AND path=%s AND sha256=%s",
                                (source, path, sha256)).fetchone()
        return row is not None

    def add(self, rec):
        self.conn.execute(
            "INSERT INTO bronze_files (source,path,sha256,size,storage_key,run_id,fetched_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (rec.source, rec.path, rec.sha256, rec.size, rec.storage_key, rec.run_id, rec.fetched_at))

    def all(self):
        rows = self.conn.execute("SELECT source,path,sha256,size,storage_key,run_id,fetched_at FROM bronze_files ORDER BY source,path,fetched_at").fetchall()
        return [FileRecord(*r) for r in rows]

    def latest(self):
        rows = self.conn.execute(
            "SELECT DISTINCT ON (source,path) source,path,sha256,size,storage_key,run_id,fetched_at "
            "FROM bronze_files ORDER BY source,path,fetched_at DESC").fetchall()
        return [FileRecord(*r) for r in rows]

    def set_present(self, present, run_id):
        was = {(s, p) for s, p in self.conn.execute("SELECT source,path FROM source_files WHERE present").fetchall()}
        gone = sorted(was - present)
        with self.conn.transaction():
            for s, p in present:
                self.conn.execute(
                    "INSERT INTO source_files (source,path,present,last_seen_run) VALUES (%s,%s,true,%s) "
                    "ON CONFLICT (source,path) DO UPDATE SET present=true, last_seen_run=EXCLUDED.last_seen_run, updated_at=now()", (s, p, run_id))
            for s, p in gone:
                self.conn.execute("UPDATE source_files SET present=false, updated_at=now() WHERE source=%s AND path=%s", (s, p))
        return gone

    def present(self):
        return {(s, p) for s, p in self.conn.execute("SELECT source,path FROM source_files WHERE present").fetchall()}
