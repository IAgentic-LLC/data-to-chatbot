# Episode 5: chunk, embed, index (the gold layer)

Goal: turn the accepted documents into a search index you can build safely beside the live one, measure, switch to, and roll back.

## The pieces, from zero
- **Chunk.** A piece of a document. A search that returns a whole 20-page file for every question is a bad search, and a model can only read so much. We cut at headings, because a heading is where the author already decided one idea ends. `chunk.py` also has a "fixed window" cutter so we can compare the two.
- **Embedding.** A list of numbers (384 of them here) that stands for the meaning of a text. Texts about similar things get lists that point in similar directions. The model that makes them runs on your own computer (`fastembed`, free, no account, no data leaves the machine). A toy `hash` embedder exists so the tests run with nothing installed.
- **Vector search.** Find the chunks whose list of numbers is closest to the question's. In Postgres, with the `pgvector` extension, that is one operator: `embedding <=> question_vector`.
- **Keyword search.** Find chunks containing the question's words, ranked by how well they match. Postgres does this natively (`tsvector`). It finds error codes like `E-4029` that meaning-based search can blur.
- **Hybrid search.** Run both, then merge the two ranked lists with **reciprocal rank fusion**: each list gives a chunk `1 / (60 + rank)` points and the points add up. A chunk that is high in both lists wins.
- **Index version.** Each build creates a NEW table `chunks_vN`. The live table is never edited. `index_alias` has one row, `live`, that says which version the chatbot should search.
- **Promote and rollback.** Going live is changing that one row. Rolling back is changing it back. No data moves.
- **Embedding cache.** Embeddings are stored by the hash of the text. Rebuilding with one changed document embeds only the changed chunks. With a paid embedding service you would be billed per text, so this is real money. Even a crashed build keeps what it already embedded.
- **Snapshot fingerprint.** A hash of exactly what an index contains. If the data has not changed, `build` says so and builds nothing.

## Changing the database safely: migrations
So far each class created its own tables. That does not scale: how do you change a table that already holds data, on every machine, in the same way?
A **migration** is a numbered SQL file. `pipeline/migrate.py` (40 lines) applies each once, in order, and records it. The rule: **never edit a file that has been applied; add the next number.** You can see this rule used for real: `005_index_failed_status.sql` exists because a build crashed during development and left a row stuck as "building"; instead of editing `003` we added a new file.
The grown-up version of the same idea is **Alembic** (Python-based, can detect changes from your table classes, can run backwards). Learn it after this; the concept is identical.

## Governance in this episode
- **Least privilege.** `migrations/004_chatbot_role.sql` creates `chatbot_ro`. Each new `chunks_vN` table is granted to it, and nothing else is. Test it yourself (`tests/test_index.py::test_chatbot_role_...`): it can read the index and is refused on raw files, silver, curation records and the audit log, and cannot write.
- **Lineage.** `python -m pipeline.index_cli explain "refund-policy#eu-customers"` prints the document, the raw file's hash, the time it was fetched and the pipeline run that brought it in.
- **Auditability.** Builds and promotions are written to the audit log.
- **No data leaves.** Embeddings are computed locally; see `COMPLIANCE_MAP.md`.

## Run it
```bash
python -m pipeline.cli curate
python -m pipeline.index_cli build                       # built version 1: 46 chunks, 46 newly embedded
python -m pipeline.index_cli build                       # nothing changed since version 1: no new index built (0 texts embedded)
python -m pipeline.index_cli promote 1
python -m pipeline.index_cli search "Can a German customer return a drop item after 12 days?" --k 3
python -m pipeline.index_cli eval --mode vector          # compare vector / keyword / hybrid
python -m pipeline.index_cli build --chunker fixed       # a second index to compare
python -m pipeline.index_cli list
```

## What the numbers said (30 scorable dev questions, top 5)
| Index | vector | keyword | hybrid |
|---|---|---|---|
| section chunks (version 1) | 0.95 | 0.79 | 0.92 |
| fixed 400-character windows (version 3) | 0.86 | 0.92 | 0.96 |

And for the section index with hybrid search, how many results you look at matters more than anything else: top 3 = 0.81, top 5 = 0.92, top 8 = 0.96.

**How to read this honestly:** with 30 questions, one question is 3.3 points. Differences of 0.04 between rows (0.92 vs 0.96) are one or two questions. You are NOT entitled to conclude that fixed windows beat sections, or that vector beats hybrid. What the table does support: keyword-only search is clearly weakest on section chunks, vector-only is clearly weaker on small fixed windows, and hybrid is never far from the best option in either index, which is why it is the default. Episode 7 gives these scores error bars and runs the final test split exactly once.
Eleven of the 41 dev questions are skipped because they ask about documents that are not in this small corpus; scoring them would blame search for a document that is not there.
We tune on the `dev` questions only. The `test` questions are for the final check; looking at them while tuning would make the score a lie.

## Checks (`tests/test_index.py`)
Chunk ids are stable and unique; long sections split at paragraph breaks; the toy embedder is deterministic and prefers shared words; the evaluator counts recall correctly and skips questions about missing documents. With the database up (in a throwaway database that is created and dropped by the test): migrations apply once; rebuilding is a no-op; changing one document embeds only the new piece; rejected, duplicate and personal text never reaches the index; promote and rollback work; a crashed build is marked `failed`; the chatbot login is boxed in; the audit table refuses edits.

## Exercises
1. Change `max_chars` in `chunk.py` to 400 and rebuild. How many chunks now? Does recall move by more than one question?
2. Add one sentence to `data/sources/wiki/on-call.md`, run `land`, `silver`, `curate`, `build`. How many texts were newly embedded?
3. Promote version 3, search the same question, promote version 1 again. What did the chatbot see in between?
4. Why does `hnsw` not matter for 46 chunks, and what would you check before using it on 5 million?

## Alternatives, and when you would pick them
- **NoSQL / document databases (MongoDB).** Good for data without a fixed shape that you mostly read and write one record at a time. Our data has strong relationships (document, chunk, raw file, run, decision) and we need transactions ("swap the live index or do nothing"), joins for lineage, and a permissions system. Postgres also stores JSON (`jsonb`) when we need flexible fields, and vectors, and full-text search. One system to learn and operate beats four.
- **Dedicated vector databases (Qdrant, Weaviate, Pinecone) and search engines (Elasticsearch/OpenSearch).** Pick one when you reach tens of millions of vectors, need very fast filtering at scale, or your team already runs one. Not before.
