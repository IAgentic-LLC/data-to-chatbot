"""Episode 2: bronze -> silver. Read each landed file, parse and clean it, keep the result, and write down why anything was refused.
Safe to run twice: a file that already has a silver result (or a recorded rejection) is skipped."""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from .migrate import apply_pending

from .clean import find_boilerplate, remove_lines
from .hashing import sha256_text
from .manifest import FileRecord, Manifest
from .parse import ParseError, Parsed, parse
from .storage import Storage


@dataclass
class SilverDoc:
    doc_key: str
    source: str
    path: str
    bronze_sha256: str
    parser: str
    title: str
    text: str
    text_sha256: str
    meta: dict = field(default_factory=dict)
    parsed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Reject:
    source: str
    path: str
    bronze_sha256: str
    reason: str
    rejected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SilverStore(Protocol):
    def done(self, source: str, path: str, sha256: str) -> bool: ...
    def put_doc(self, doc: SilverDoc) -> None: ...
    def put_reject(self, rej: Reject) -> None: ...
    def docs(self) -> list[SilverDoc]: ...
    def rejects(self) -> list[Reject]: ...


class MemorySilver:
    def __init__(self):
        self._docs: dict[str, SilverDoc] = {}
        self._rej: dict[tuple, Reject] = {}

    def done(self, source, path, sha256):
        return (source, path, sha256) in self._rej or any(
            d.source == source and d.path == path and d.bronze_sha256 == sha256 for d in self._docs.values())

    def put_doc(self, doc):
        self._docs[doc.doc_key] = doc

    def put_reject(self, rej):
        self._rej[(rej.source, rej.path, rej.bronze_sha256)] = rej

    def docs(self):
        return list(self._docs.values())

    def rejects(self):
        return list(self._rej.values())




class PgSilver:
    def __init__(self, url: str):
        import psycopg
        apply_pending(url)                                   # tables come from migrations/, not from this file
        self.conn = psycopg.connect(url, autocommit=True)

    def done(self, source, path, sha256):
        q = ("SELECT 1 FROM silver_docs WHERE source=%s AND path=%s AND bronze_sha256=%s UNION ALL "
             "SELECT 1 FROM silver_rejects WHERE source=%s AND path=%s AND bronze_sha256=%s")
        return self.conn.execute(q, (source, path, sha256, source, path, sha256)).fetchone() is not None

    def put_doc(self, d):
        self.conn.execute(
            "INSERT INTO silver_docs (doc_key,source,path,bronze_sha256,parser,title,text,text_sha256,meta,parsed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (doc_key) DO UPDATE SET bronze_sha256=EXCLUDED.bronze_sha256, "
            "parser=EXCLUDED.parser, title=EXCLUDED.title, text=EXCLUDED.text, text_sha256=EXCLUDED.text_sha256, "
            "meta=EXCLUDED.meta, parsed_at=EXCLUDED.parsed_at",
            (d.doc_key, d.source, d.path, d.bronze_sha256, d.parser, d.title, d.text, d.text_sha256, json.dumps(d.meta), d.parsed_at))

    def put_reject(self, r):
        self.conn.execute(
            "INSERT INTO silver_rejects (source,path,bronze_sha256,reason,rejected_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (r.source, r.path, r.bronze_sha256, r.reason, r.rejected_at))

    def docs(self):
        rows = self.conn.execute("SELECT doc_key,source,path,bronze_sha256,parser,title,text,text_sha256,meta,parsed_at FROM silver_docs ORDER BY doc_key").fetchall()
        return [SilverDoc(*r) for r in rows]

    def rejects(self):
        rows = self.conn.execute("SELECT source,path,bronze_sha256,reason,rejected_at FROM silver_rejects ORDER BY source,path").fetchall()
        return [Reject(*r) for r in rows]


@dataclass
class SilverReport:
    parsed: int = 0
    rejected: int = 0
    skipped: int = 0
    boilerplate_lines: int = 0

    def __str__(self):
        return f"parsed={self.parsed} rejected={self.rejected} already_done={self.skipped} boilerplate_lines_removed={self.boilerplate_lines}"


def build_silver(manifest: Manifest, storage: Storage, silver: SilverStore) -> SilverReport:
    rep = SilverReport()
    batch: dict[str, list[tuple[FileRecord, Parsed]]] = {}
    for rec in manifest.latest():          # only the newest version of each file is the current truth
        if silver.done(rec.source, rec.path, rec.sha256):
            rep.skipped += 1
            continue
        try:
            parsed = parse(rec.source, rec.path, storage.get(rec.storage_key))
        except ParseError as e:
            silver.put_reject(Reject(rec.source, rec.path, rec.sha256, str(e)))
            rep.rejected += 1
            continue
        batch.setdefault(rec.source, []).extend((rec, p) for p in parsed)

    for source, items in batch.items():
        # Lines repeated across most documents of one feed (page footers, banners) are not content.
        boiler = find_boilerplate([p.text for _, p in items])
        for rec, p in items:
            text = remove_lines(p.text, boiler)
            rep.boilerplate_lines += len(p.text.splitlines()) - len(text.splitlines())
            if not text:
                silver.put_reject(Reject(rec.source, rec.path, rec.sha256, "nothing left after cleaning"))
                rep.rejected += 1
                continue
            silver.put_doc(SilverDoc(p.doc_key, rec.source, rec.path, rec.sha256, p.parser, p.title, text, sha256_text(text), p.meta))
            rep.parsed += 1
    return rep
