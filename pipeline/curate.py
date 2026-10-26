"""Episode 4: silver -> curated. Decide, for every clean document, whether it may be searched, and write the reason down.

Statuses:  accepted | duplicate | superseded | quarantined | rejected_quality | rejected_review | expired | deleted
`curate()` is a pure function (documents in, decisions out, no database), so every rule can be tested alone.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from datetime import date
from typing import Protocol

from .migrate import apply_pending

from . import dedupe, injection, pii, policy as policy_mod
from .silver import SilverDoc

MIN_CHARS = 80          # shorter than this is a scrap, not knowledge
ACCEPTED = "accepted"


@dataclass
class Curated:
    doc_key: str
    source: str
    path: str
    status: str
    reason: str
    text: str                                  # the text that may be indexed (personal data already replaced)
    title: str
    canonical_key: str | None = None           # for duplicate/superseded: the document that replaces this one
    doc_date: str | None = None
    pii: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    bronze_sha256: str = ""
    curated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def curate(docs: list[SilverDoc], present: set[tuple[str, str]], decisions: dict[str, str], min_chars: int = MIN_CHARS,
           policies: dict | None = None, today: date | None = None) -> list[Curated]:
    policies = policies or {}
    today = today or date.today()
    out: dict[str, Curated] = {}
    survivors: list[Curated] = []
    for d in docs:
        base = dict(doc_key=d.doc_key, source=d.source, path=d.path, title=d.title, bronze_sha256=d.bronze_sha256,
                    doc_date=dedupe.doc_date(d.text, d.meta))
        # 1. tombstone: the source file is gone, so what it said must leave the index
        if (d.source, d.path) not in present:
            out[d.doc_key] = Curated(status="deleted", reason="source file no longer exists", text="", **base)
            continue
        # 1b. retention: the policy for this source says how long we may keep a document
        sp = policies.get(d.source)
        if sp and policy_mod.is_expired(sp, base["doc_date"], today):
            out[d.doc_key] = Curated(status="expired", reason=f"older than the {sp.retention_days}-day retention limit for '{d.source}'", text="", **base)
            continue
        # 2. a human already decided about this exact document
        decision = decisions.get(d.doc_key)
        if decision == "reject":
            out[d.doc_key] = Curated(status="rejected_review", reason="rejected by a reviewer", text="", **base)
            continue
        # 3. size and shape
        if len(d.text) < min_chars:
            out[d.doc_key] = Curated(status="rejected_quality", reason=f"too short: {len(d.text)} characters (minimum {min_chars})", text="", **base)
            continue
        # 4. instructions aimed at the model, in the visible text or in comments we removed
        hits = injection.scan(d.text, *d.meta.get("hidden_comments", []))
        if hits and decision != "approve":
            out[d.doc_key] = Curated(status="quarantined", reason="possible prompt injection: " + ", ".join(hits) + " (needs a human decision)",
                                     text="", flags=["injection:" + h for h in hits], **base)
            continue
        # 5. personal data out
        text, found = pii.scrub(d.text)
        c = Curated(status=ACCEPTED, reason="passed checks", text=text, pii=found, flags=(["approved-by-reviewer"] if hits else []), **base)
        out[d.doc_key] = c
        survivors.append(c)

    # 6. duplicates and old versions: keep one document per group of near-identical ones
    items = [dedupe.Item(c.doc_key, c.source, c.text, _sha(c.text), c.doc_date) for c in survivors]
    for group in dedupe.clusters(items):
        if len(group) == 1:
            continue
        win = dedupe.winner(group)
        for it in group:
            if it.key == win.key:
                continue
            c = out[it.key]
            c.canonical_key = win.key
            c.text = ""
            older = it.date is not None and win.date is not None and it.date < win.date
            if older:
                c.status = "superseded"
                diff = ", ".join(dedupe.changed_words(it.text, win.text))
                c.reason = f"older version of {win.key} ({it.date} vs {win.date}); differing words: {diff}"
            else:
                c.status = "duplicate"
                c.reason = f"same content as {win.key}"
    return sorted(out.values(), key=lambda c: c.doc_key)


def _sha(text: str) -> str:
    from .hashing import sha256_text
    return sha256_text(text)


class CuratedStore(Protocol):
    def replace_all(self, rows: list[Curated]) -> None: ...
    def all(self) -> list[Curated]: ...
    def decisions(self) -> dict[str, str]: ...
    def decide(self, doc_key: str, decision: str, note: str = "") -> None: ...


class MemoryCurated:
    def __init__(self):
        self.rows: list[Curated] = []
        self._dec: dict[str, str] = {}

    def replace_all(self, rows):
        self.rows = list(rows)

    def all(self):
        return list(self.rows)

    def decisions(self):
        return dict(self._dec)

    def decide(self, doc_key, decision, note=""):
        self._dec[doc_key] = decision




class PgCurated:
    def __init__(self, url: str):
        import psycopg
        apply_pending(url)                                   # tables come from migrations/, not from this file
        self.conn = psycopg.connect(url, autocommit=True)

    def replace_all(self, rows):
        with self.conn.transaction():
            self.conn.execute("DELETE FROM curated_docs")
            for c in rows:
                self.conn.execute(
                    "INSERT INTO curated_docs (doc_key,source,path,status,reason,title,text,canonical_key,doc_date,pii,flags,bronze_sha256,curated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (c.doc_key, c.source, c.path, c.status, c.reason, c.title, c.text, c.canonical_key, c.doc_date,
                     json.dumps(c.pii), json.dumps(c.flags), c.bronze_sha256, c.curated_at))

    def all(self):
        rows = self.conn.execute("SELECT doc_key,source,path,status,reason,title,text,canonical_key,doc_date,pii,flags,bronze_sha256,curated_at "
                                 "FROM curated_docs ORDER BY doc_key").fetchall()
        return [Curated(doc_key=r[0], source=r[1], path=r[2], status=r[3], reason=r[4], title=r[5], text=r[6], canonical_key=r[7],
                        doc_date=r[8], pii=r[9], flags=r[10], bronze_sha256=r[11], curated_at=r[12]) for r in rows]

    def decisions(self):
        return dict(self.conn.execute("SELECT doc_key, decision FROM curation_decisions").fetchall())

    def decide(self, doc_key, decision, note=""):
        self.conn.execute(
            "INSERT INTO curation_decisions (doc_key,decision,note) VALUES (%s,%s,%s) "
            "ON CONFLICT (doc_key) DO UPDATE SET decision=EXCLUDED.decision, note=EXCLUDED.note, decided_at=now()", (doc_key, decision, note))


def run_curation(manifest, silver, store: CuratedStore, today: date | None = None) -> dict:
    """Read silver, apply every rule, replace the curated set. Cheap and repeatable: it recomputes the whole picture each time,
    because duplicates can only be judged by looking at all documents together."""
    rows = curate(silver.docs(), manifest.present(), store.decisions(), policies=policy_mod.load(), today=today)
    store.replace_all(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts
