"""Episode 1: land raw files in bronze exactly as received. Safe to run twice: nothing is stored or recorded again.
Episode 4 adds one thing: we also note which files are present right now, so a file that disappears becomes a tombstone."""
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_bytes
from .manifest import FileRecord, Manifest
from .storage import Storage


@dataclass
class LandReport:
    new: int = 0          # (source, path, content) combinations never seen before
    unchanged: int = 0    # already in the manifest: skipped
    stored: int = 0       # distinct byte blobs actually written (identical files share one)
    missing: int = 0      # files that were here last time and are gone now (tombstones)

    def __str__(self):
        return f"new={self.new} unchanged={self.unchanged} blobs_written={self.stored} missing={self.missing}"


def bronze_key(sha: str) -> str:
    # Content-addressed: the key is the hash, so identical bytes are stored once no matter how many names they arrive under.
    return f"blobs/{sha[:2]}/{sha}"


def land(sources_dir: Path, storage: Storage, manifest: Manifest, run_id: str) -> LandReport:
    rep = LandReport()
    present: set[tuple[str, str]] = set()
    for src in sorted(p for p in Path(sources_dir).iterdir() if p.is_dir()):
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            data = f.read_bytes()
            sha = sha256_bytes(data)
            rel = f.relative_to(src).as_posix()
            present.add((src.name, rel))
            if manifest.seen(src.name, rel, sha):
                rep.unchanged += 1
                continue
            key = bronze_key(sha)
            if not storage.exists(key):
                storage.put(key, data)
                rep.stored += 1
            manifest.add(FileRecord(src.name, rel, sha, len(data), key, run_id))
            rep.new += 1
    rep.missing = len(manifest.set_present(present, run_id))
    return rep
