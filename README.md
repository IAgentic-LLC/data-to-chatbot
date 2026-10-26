# Data to Chatbot: build a RAG data pipeline from scratch

Working repo for the course. You start with a folder of messy company files and end with a support chatbot that real users query, with every step in between built, tested and explained from zero. The company is the fictional Dropline from the Agentic RAG series. No prior data-engineering knowledge is assumed: every new word is explained where it first appears, and `docs/GLOSSARY.md` collects them.

```
sources (messy) -> BRONZE (raw, as received) -> SILVER (clean text) -> CURATED (allowed to be searched) -> GOLD (search index) -> chatbot -> monitoring
                     orchestrated by Airflow, checked by tests, governed by a written policy, recorded in an audit log
```

## Status
| Episode | Folder | State |
|---|---|---|
| 0 The map (also ETL vs ELT) | `episode-00-map/` | written |
| 1 Landing the data (bronze) | `episode-01-bronze/` | runs, tested |
| 2 Parsing and cleaning (silver) | `episode-02-silver/` | runs, tested |
| 3 Airflow from zero | `episode-03-airflow/` | DAG runs end to end in Docker |
| 4 Quality, curation, governance | `episode-04-quality-curation/` | runs, tested |
| 5 Chunk, embed, index (gold) | `episode-05-gold-index/` | runs, tested, measured |
| 5B The knowledge graph (Neo4j) | `episode-05b-graph/` | runs, tested, measured (no gain on 16 documents, said so) |
| 8A LangChain + LangGraph agent | `episode-08a-agent/` | runs, 12 offline tests, tried live with a hosted model |
| 6 Governance and compliance in practice | `episode-06-governance/` | drill runs (12 of 12 controls verified); runbook and record templates written |
| 7 and 8B to 11 | not built yet | eval gate, serving (8B), going live, monitoring, day 2 |

Governance material lives in `governance/` (`policy.yaml`, `COMPLIANCE_MAP.md`, `DATA_CARD.md`).

## Quick start
You need Python 3.12 and Docker. About 6 GB of disk for the images and the embedding model, and 2 GB of free RAM once Airflow is running (measured: the five containers use roughly 1 GB idle; the embedding model adds a little more while it runs).
```bash
pip install -r requirements.txt
python scripts/generate_sources.py          # builds the messy practice files in data/sources
python -m pytest -q                         # 68 tests; the 8 that need the database are skipped if Docker is not running
docker compose up -d                        # database + data lake

python -m pipeline.cli land                 # episode 1
python -m pipeline.cli silver               # episode 2
python -m pipeline.cli curate               # episode 4
python -m pipeline.cli checks
python -m pipeline.index_cli build          # episode 5 (the first run downloads the ~130 MB embedding model)
python -m pipeline.index_cli promote 1
python -m pipeline.index_cli search "Can a German customer return a drop item after 12 days?"
docker compose --profile graph up -d graph  # episode 5B: python -m pipeline.graph_cli build, then promote 1

docker compose --profile airflow up -d --build    # episode 3, then open http://127.0.0.1:8080
```
Run any stage a second time and watch nothing change. That property (safe to repeat) is the most important idea in the course.

## What is where
| Path | What it is |
|---|---|
| `scripts/generate_sources.py` | makes the practice files, including the traps (`data/sources/TRAPS.md` is the answer key) |
| `pipeline/land.py`, `storage.py`, `manifest.py` | episode 1 |
| `pipeline/parse.py`, `clean.py`, `silver.py` | episode 2 |
| `pipeline/curate.py`, `pii.py`, `injection.py`, `dedupe.py`, `checks.py`, `elt.py` | episode 4 |
| `pipeline/audit.py`, `policy.py`, `erasure.py`, `governance/`, `scripts/governance_drill.py` | governance (episodes 4 and 6) |
| `pipeline/chunk.py`, `embed.py`, `index.py`, `index_cli.py`, `evalset.py` | episode 5 |
| `pipeline/graph.py`, `graph_cli.py`, `migrations/006_graph_versions.sql` | episode 5B |
| `chatbot/` (agent, tools, review graph, CLI) | episode 8A |
| `pipeline/migrate.py`, `migrations/` | changing the database safely |
| `episode-03-airflow/dags/dropline_ingest.py` | the whole pipeline as one scheduled workflow |
| `docker-compose.yml`, `docker/airflow/` | the local stack |
| `tests/` | 68 tests |

## Choices we made, and the honest alternatives
- **Postgres for everything (with pgvector and full-text search).** One database to understand and operate. A document database (MongoDB) suits shapeless data read one record at a time; ours is full of relationships and needs transactions, so it would be the wrong fit. A dedicated vector database is for tens of millions of vectors.
- **Plain SQL through `psycopg`, with numbered migration files, not an ORM.** You can read every query. Alembic and SQLAlchemy are the professional tools for the same job and are worth learning next; the migration idea is identical.
- **Python dataclasses and plain functions, not Flask or Django.** The pipeline has no web pages. The chatbot in episode 8 uses FastAPI, as in the Agentic RAG series, which brings Pydantic with it (typed, validated request and response shapes).
- **Data lake: SeaweedFS** (speaks the S3 protocol). MinIO is the usual teaching choice, but its official Docker image is no longer published.
- **Embeddings run locally** (`fastembed`), so no document text is sent to a provider and there is no account or cost.
- **Versions pinned where it matters**: Airflow 3.3.2, Postgres 17 with pgvector 0.8.7. Check for newer ones before copying this into a real project.

## Honest notes
- Everything here is for learning on your own machine. Passwords in the compose file are throwaway, ports are bound to localhost, nothing is encrypted, and Airflow runs with every visitor as admin. Episode 9 changes all of that before anything is put on the internet.
- This is a teaching repository about governance and compliance, not legal advice. See `governance/COMPLIANCE_MAP.md`, especially its list of what is NOT covered.
- The data is fictional. The practice traps are deliberate.
