# Episode 1: landing the data (bronze)

Goal: copy every incoming file into storage exactly as it arrived, remember what we have seen, and make running it twice harmless.

## Concepts
- **Content hash.** A short fingerprint of a file's bytes (SHA-256). Same bytes give the same hash; change one letter and it changes completely.
- **Content-addressed storage.** The storage key is the hash. Two files with identical bytes are stored once, however many names they arrive under.
- **Manifest.** A table with one row per (feed, path, hash) ever seen. It is the pipeline's memory, and later the proof of where every answer came from.
- **Idempotent.** Run it twice, get the same result. We check the manifest first and skip what is known.

## Code
`scripts/generate_sources.py` (the practice files), `pipeline/hashing.py`, `storage.py` (local folder and S3), `manifest.py` (memory and Postgres), `land.py` (about 30 lines of logic).

## Run it
```bash
python scripts/generate_sources.py
docker compose up -d
python -m pipeline.cli land      # landing: new=21 unchanged=0 blobs_written=20
python -m pipeline.cli land      # landing: new=0 unchanged=21 blobs_written=0
```
20 blobs for 21 files: `uploads/refund-policy-copy.md` is a byte-for-byte copy of `wiki/refund-policy.md`, so it shares one blob.

## Checks (all in `tests/test_bronze_silver.py`)
- landing twice changes nothing
- identical bytes are stored once
- a changed file is recorded as a new version and the old bytes are kept

## Exercises
1. Edit a line in `data/sources/wiki/on-call.md` and land again. What changes in the numbers?
2. Delete a source file and land again. Why does the manifest still list it? (Episode 4 turns this into a deliberate choice.)
3. Use `docker compose exec db psql -U pipeline -d pipeline -c "select * from bronze_files"` and find the two paths that share a hash.
