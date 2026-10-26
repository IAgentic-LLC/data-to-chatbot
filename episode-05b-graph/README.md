# Episode 5B: a knowledge graph beside the search index (Neo4j)

Goal: understand what a graph database is, build one from the curated documents, ask it questions, and MEASURE whether it earns its place next to the search index.

## Concepts (every word explained)
- **Node**: a thing. Here: a document, an incident (INC-2047), a policy change (PC-12), an error code (E-4029), a region (EU).
- **Relationship (link)**: a named, directed connection between two nodes: `INC-2047 -LED_TO-> PC-12`. Links can carry facts: `PC-12 -APPLIES_TO {days: 14}-> EU`.
- **Graph database (Neo4j)**: stores nodes and links as the main thing, so "follow the links two steps" is fast and natural. **Cypher** is its query language: you draw the pattern you want, `MATCH (a)-[:LED_TO]->(b)`.
- **Hop**: one link walked. "Two hops" = a thing, its neighbour, and that neighbour's neighbour. Questions that need several hops are called multi-hop.
- **Extraction**: reading text and writing down the things and links in it. We use plain rules (patterns like `INC-nnnn` and "introduced after incident ..."), not a language model: cheap, predictable, same answer every run. The honest cost: a link phrased in a way no rule knows is missed.
- **Versioned like the index**: every node and link carries the graph version `v`; a new version is written beside the live one; a single `Alias` node says which is live. Neo4j Community has only one database, so the version is a property.

## Code
`pipeline/graph.py` (extraction, `MemoryGraph`, `Neo4jGraph`, the walk, the consistency check), `pipeline/graph_cli.py`, `migrations/006_graph_versions.sql`, `tests/test_graph.py`, DAG task `build_graph` (runs only when `GRAPH_ENABLED=1`).

## Run it
```bash
docker compose --profile graph up -d db graph       # first start can take minutes on a busy laptop (measured: about 9 minutes with the machine under memory pressure)
pip install -r requirements.txt
python -m pipeline.graph_cli build                  # built graph version 1: 26 nodes (16 Document, 4 ErrorCode, 2 Incident, 1 PolicyChange, 3 Region), 22 links
python -m pipeline.graph_cli promote 1
python -m pipeline.graph_cli build                  # again: same counts, nothing duplicated (safe to repeat)
python -m pipeline.graph_cli ask "Why does error E-4029 exist, and which runbook scales checkout?"
python -m pipeline.graph_cli ask "What did the incident behind PC-12 change for EU customers?"
python -m pipeline.graph_cli eval
```
Open http://127.0.0.1:7474 (user `neo4j`, password `dropline-local-pw`) and run `MATCH (n:Entity {v: 1})-[r]->(m) RETURN n, r, m` to see the graph and click around.

## What the measurement said (dev questions only, the 5 multi-hop ones)
```
search only     recall@5=0.93  all-found=0.80  avg chunks given to the model: 5.0
search + graph  recall@5=0.93  all-found=0.80  avg chunks given to the model: 5.2
```
**No gain on this corpus.** Reasons, in order of importance: 16 documents is too small for search to need help; the one missed chunk (`refund-policy#eu-customers` for question o01) comes from a question that names no incident, policy change or error code, so the graph has nothing to start from; and with only 5 questions a difference of one chunk is noise anyway (the episode 5 lesson). The graph earns its keep when questions name entities and the facts are spread over many documents. We did not tune the rules to the dev questions to make the number look better.

## Cost, said plainly
A second database to run, back up, secure and keep in step. Erasure and retention must reach it too: the graph is rebuilt from accepted documents only, personal data cannot become a node by construction (only ids matching our patterns do), and governance drill control 12 checks both.

## Checks
`python -m pytest tests/test_graph.py -q` (13 tests; the last one needs Neo4j and is skipped without it): the rules find INC-2047 -> PC-12 and INC-2051 -> E-4029, the days per region, document-to-document links, a two-hop walk, versions built beside the live one, and a refused document can never stay in the graph.

## Honest notes
- Throwaway password and a localhost-only port, like the rest of the local stack; episode 9 changes that.
- Neo4j's container prints that it sends anonymous usage data to Neo4j; check the current setting name in its documentation before production.
- The test split of the golden set was not used here; it stays untouched for the eval gate (episode 7).

## Exercises
1. Add a rule for a link phrased differently ("replaced by", "superseded by") and add a test before you run it.
2. Ask a question that names nothing in the graph. What does `ask` print, and why is that the right answer?
3. Delete a document from the curated set (retire it) and rebuild. Which nodes and links disappear?
