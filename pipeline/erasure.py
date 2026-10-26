"""Governance: honour a person's request to be forgotten (GDPR Art. 17 style). Four steps, in this order:
  1. FIND  every place their identifier appears (bronze files, silver text, curated text, search index chunks)
  2. REDACT the files that hold it, writing a new bronze version and deleting every old blob that contained it
  3. REBUILD downstream (the caller runs silver, curate, index; the audit trail says when)
  4. PROVE it: search again and show zero hits, then log the request WITHOUT the identifier (only its hash)

The tension this resolves: "raw data is immutable" has ONE legal exception. We keep every other promise of bronze and break this one on purpose, openly, with a record.
Limits (said out loud): this finds the exact identifier you give it (an email, an order id). It will not find the same person written as a name in free text,
and it cannot reach copies outside the pipeline (backups, exports, logs, model providers). A real erasure process lists those too."""
import re
from dataclasses import dataclass, field

from . import audit as audit_mod
from .hashing import sha256_bytes
from .land import bronze_key
from .manifest import FileRecord


@dataclass
class Findings:
    bronze_blobs: list[str] = field(default_factory=list)       # storage keys
    silver_docs: list[str] = field(default_factory=list)
    curated_docs: list[str] = field(default_factory=list)
    index_chunks: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.bronze_blobs) + len(self.silver_docs) + len(self.curated_docs) + len(self.index_chunks)

    def __str__(self):
        return (f"bronze blobs={len(self.bronze_blobs)} silver docs={len(self.silver_docs)} "
                f"curated docs={len(self.curated_docs)} index chunks={len(self.index_chunks)}")


def _has(identifier: str, text: str) -> bool:
    return identifier.lower() in text.lower()


def find_subject(identifier: str, manifest, storage, silver, curated, index_chunks=None) -> Findings:
    f = Findings()
    for key in sorted({r.storage_key for r in manifest.all()}):
        if storage.exists(key) and _has(identifier, storage.get(key).decode("utf-8", errors="replace")):
            f.bronze_blobs.append(key)
    f.silver_docs = [d.doc_key for d in silver.docs() if _has(identifier, d.text) or _has(identifier, d.title)]
    f.curated_docs = [c.doc_key for c in curated.all() if _has(identifier, c.text)]
    if index_chunks is not None:
        f.index_chunks = [cid for cid, text in index_chunks if _has(identifier, text)]
    return f


def erase_subject(identifier: str, manifest, storage, audit, actor: str, run_id: str, token: str = "[ERASED]") -> dict:
    """Redact the identifier everywhere in bronze. Does NOT rebuild silver/curated/index: run those stages next."""
    rx = re.compile(re.escape(identifier), re.I)
    latest = {(r.source, r.path): r for r in manifest.latest()}
    bad_keys = {k for k in {r.storage_key for r in manifest.all()}
                if storage.exists(k) and _has(identifier, storage.get(k).decode("utf-8", errors="replace"))}
    redacted = 0
    for rec in latest.values():
        if rec.storage_key in bad_keys:
            new = rx.sub(token, storage.get(rec.storage_key).decode("utf-8", errors="replace")).encode("utf-8")
            sha = sha256_bytes(new)
            key = bronze_key(sha)
            if not storage.exists(key):
                storage.put(key, new)
            manifest.add(FileRecord(rec.source, rec.path, sha, len(new), key, run_id))      # the current version of that file, now redacted
            redacted += 1
    deleted = 0
    for k in bad_keys:
        storage.delete(k)                                  # the old bytes, and every older version that held the identifier
        deleted += 1
    audit.record(actor, "erasure", "subject:" + audit_mod.hash_identifier(identifier),
                 {"files_redacted": redacted, "blobs_deleted": deleted, "run_id": run_id})
    return {"files_redacted": redacted, "blobs_deleted": deleted}
