# Episode 2: parsing and cleaning (silver)

Goal: turn six kinds of raw file into clean text with a title and a little metadata, and keep an honest list of what we could not read and why.

## Concepts
- **Parser.** A function from bytes to text for one format (Markdown, HTML, PDF, JSON, CSV). Unreadable input raises a `ParseError` with a plain reason; it never crashes the run.
- **Text normalization.** One form for look-alike characters, curly quotes made plain, Windows line endings made Unix, control characters removed.
- **Mojibake.** Text that was decoded with the wrong character set, so "don't" with a curly quote becomes "donâ€™t". We detect the pattern and reverse it.
- **Boilerplate.** A line that appears in most documents of one feed (a page footer) is not content. We measure how many documents contain each line and drop the common ones. Limit: it needs at least three documents in the batch to judge.
- **Hidden content.** HTML comments are invisible to people but visible to a model. We remove and count them; episode 4 handles instructions hidden in visible text.
- **Rejects table.** Refusing a file is a result, not an error. We store the reason so a person can fix the source.

## Code
`pipeline/clean.py` (pure functions), `parse.py` (one parser per format), `silver.py` (reads bronze, writes `silver_docs` and `silver_rejects`).

## Run it
```bash
python -m pipeline.cli silver     # parsed=22 rejected=2 already_done=0 boilerplate_lines_removed=5
python -m pipeline.cli silver     # parsed=0 rejected=0 already_done=21 ...
python -m pipeline.cli status
```
Expected rejects: `uploads/empty.md` (empty file) and `uploads/scan-corrupt.pdf` (unreadable PDF).

## Checks
`python -m pytest -q` includes: mojibake repair, BOM and line endings, comment stripping, boilerplate needs enough documents, HTML keeps content and drops menus, every rejection has a reason, an empty ticket is skipped, and the whole bronze to silver run is repeatable.

## Known limits (said out loud on purpose)
- A PDF made of scanned images has no text; we reject it. OCR is out of scope here.
- Boilerplate detection judges only the current batch. A later batch of two documents will not be cleaned the same way.
- The stale refund policy and the exact duplicate both reach silver. Removing them is episode 4.

## Exercises
1. Add a `.docx` parser. What reason should an unsupported type give?
2. Make `find_boilerplate` use all of silver, not just the batch. What gets harder?
3. Open `silver_docs` in `psql` and compare the web version of the refund policy with the wiki version.
