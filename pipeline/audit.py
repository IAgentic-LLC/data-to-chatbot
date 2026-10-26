"""Governance: an append-only audit log where every entry carries the hash of the one before it.
If anyone edits or deletes an old row, every hash after it stops matching and `verify()` says exactly where the chain breaks.
This is tamper-EVIDENT, not tamper-proof: someone with full database access could rewrite the whole chain. Production adds an external copy (episode 9).
Rule: never put personal data in an audit entry. Log the hash of an identifier, not the identifier."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .migrate import apply_pending

GENESIS = "0" * 64


@dataclass
class Entry:
    seq: int
    at: datetime
    actor: str
    action: str
    target: str
    detail: dict
    prev_hash: str
    hash: str


def compute_hash(prev_hash: str, at: datetime, actor: str, action: str, target: str, detail: dict) -> str:
    body = json.dumps([prev_hash, at.isoformat(), actor, action, target, detail], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def hash_identifier(identifier: str) -> str:
    """For logging WHO a request was about without storing who."""
    return hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()[:16]


class AuditLog(Protocol):
    def record(self, actor: str, action: str, target: str = "", detail: dict | None = None) -> Entry: ...
    def entries(self) -> list[Entry]: ...


class MemoryAudit:
    def __init__(self):
        self._e: list[Entry] = []

    def record(self, actor, action, target="", detail=None):
        detail = detail or {}
        prev = self._e[-1].hash if self._e else GENESIS
        at = datetime.now(timezone.utc)
        e = Entry(len(self._e) + 1, at, actor, action, target, detail, prev, compute_hash(prev, at, actor, action, target, detail))
        self._e.append(e)
        return e

    def entries(self):
        return list(self._e)




class PgAudit:
    def __init__(self, url: str):
        import psycopg
        apply_pending(url)                                   # tables come from migrations/, not from this file
        self.conn = psycopg.connect(url, autocommit=True)

    def record(self, actor, action, target="", detail=None):
        detail = detail or {}
        with self.conn.transaction():
            self.conn.execute("LOCK TABLE audit_log IN EXCLUSIVE MODE")          # one writer at a time keeps the chain in order
            row = self.conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            at = datetime.now(timezone.utc)
            h = compute_hash(prev, at, actor, action, target, detail)
            seq = self.conn.execute(
                "INSERT INTO audit_log (at,actor,action,target,detail,prev_hash,hash) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING seq",
                (at, actor, action, target, json.dumps(detail), prev, h)).fetchone()[0]
        return Entry(seq, at, actor, action, target, detail, prev, h)

    def entries(self):
        rows = self.conn.execute("SELECT seq,at,actor,action,target,detail,prev_hash,hash FROM audit_log ORDER BY seq").fetchall()
        return [Entry(*r) for r in rows]


def verify(entries: list[Entry]) -> tuple[bool, str]:
    prev = GENESIS
    for e in entries:
        if e.prev_hash != prev:
            return False, f"entry {e.seq}: does not link to the one before it (a row was removed or reordered)"
        if compute_hash(e.prev_hash, e.at, e.actor, e.action, e.target, e.detail) != e.hash:
            return False, f"entry {e.seq}: contents do not match their hash (the row was edited)"
        prev = e.hash
    return True, f"{len(entries)} entries, chain intact"
