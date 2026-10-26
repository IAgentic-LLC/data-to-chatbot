"""Episode 5B tests. The extraction tests read the REAL practice files, so a change to the rules or to the files shows up here.
The last test talks to a live Neo4j and is skipped when it is not running."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import config
from pipeline.graph import (GraphData, MemoryGraph, Neo4jGraph, check_consistent, expand, extract_graph, find_in_question)
from pipeline.parse import parse

SRC = config.ROOT / "data" / "sources"


def real_docs():
    docs = []
    for rel in ["wiki/refund-policy.md", "wiki/checkout-errors.md", "wiki/drop-day-runbook.md", "wiki/on-call.md", "pdf/inc-2047-postmortem.pdf", "pdf/inc-2051-postmortem.pdf"]:
        source, path = rel.split("/", 1)
        for p in parse(source, path, (SRC / rel).read_bytes()):
            docs.append(SimpleNamespace(doc_key=p.doc_key, title=p.title, text=p.text, status="accepted"))
    return docs


@pytest.fixture(scope="module")
def graph():
    data = extract_graph(real_docs())
    store = MemoryGraph(); store.replace_version(1, data); store.promote(1)
    return data, store


def links(data, rel):
    return {(e.src, e.dst) for e in data.edges if e.rel == rel}


def test_incident_led_to_policy_change(graph):
    assert ("INC-2047", "PC-12") in links(graph[0], "LED_TO")


def test_incident_led_to_error_code(graph):
    assert ("INC-2051", "E-4029") in links(graph[0], "LED_TO")


def test_policy_change_applies_to_regions_with_days(graph):
    days = {(e.dst, e.days) for e in graph[0].edges if e.rel == "APPLIES_TO" and e.src == "PC-12"}
    assert days == {("EU", 14), ("UK", 7), ("US", 7)}


def test_see_the_runbook_becomes_a_document_link(graph):
    assert ("pdf/inc-2051-postmortem.pdf", "wiki/drop-day-runbook.md") in links(graph[0], "REFERENCES")


def test_every_link_names_the_document_it_was_read_from(graph):
    assert all(e.evidence for e in graph[0].edges)


def test_question_names_things():
    assert find_in_question("What does E-4029 mean and which incident caused it? Is the EU different?") == ["E-4029", "EU"]
    assert find_in_question("hello there") == []


def test_two_hop_walk_reaches_the_runbook(graph):
    """E-4029 -> INC-2051 -> the postmortem and, one more link on, the runbook it points to. No single paragraph says all of this."""
    data, store = graph
    ans = expand(store, 1, ["E-4029"], hops=2)
    assert "pdf/inc-2051-postmortem.pdf" in ans.documents
    assert "INC-2051" in ans.terms
    assert any("INC-2051 -LED_TO-> E-4029" in p for p in ans.paths)


def test_walk_from_an_unknown_thing_returns_nothing(graph):
    ans = expand(graph[1], 1, ["INC-9999"], hops=2)
    assert ans.documents == [] and ans.seeds == []


def test_graph_never_contains_a_refused_document():
    docs = real_docs()
    data = extract_graph(docs)
    assert check_consistent(data, docs) == []
    docs[0].status = "quarantined"                     # the curation step refuses it later...
    assert check_consistent(data, docs), "...and the old graph is now inconsistent, which the check must notice"


def test_personal_data_cannot_become_a_node():
    d = SimpleNamespace(doc_key="tickets/t.json#T-1", title="Ticket", status="accepted", text="Call maria.k@example.com or +1 555 0100 about INC-2047.")
    keys = set(extract_graph([d]).nodes)
    assert keys == {"tickets/t.json#T-1", "INC-2047"}


def test_a_new_version_is_built_beside_the_live_one():
    store = MemoryGraph()
    store.replace_version(1, extract_graph(real_docs())); store.promote(1)
    store.replace_version(2, GraphData())              # a bad, empty build
    assert store.live_version() == 1 and store.counts(2) == (0, 0)
    assert store.promote(1) == 1                       # rollback is promote(old)


def test_deleting_a_document_removes_its_links(graph):
    data = extract_graph(real_docs()); store = MemoryGraph(); store.replace_version(1, data)
    store.delete_document(1, "pdf/inc-2047-postmortem.pdf")
    assert all("inc-2047-postmortem" not in k for k in store.versions[1].nodes)
    assert all(e.evidence != "pdf/inc-2047-postmortem.pdf" for e in store.versions[1].edges)


def neo4j_up():
    try:
        g = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
        ok = g.ping(); g.close(); return ok
    except Exception:
        return False


@pytest.mark.skipif(not neo4j_up(), reason="Neo4j is not running (docker compose --profile graph up -d graph)")
def test_neo4j_gives_the_same_answers_as_memory():
    data = extract_graph(real_docs())
    mem = MemoryGraph(); mem.replace_version(99, data)
    neo = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
    try:
        neo.replace_version(99, data); neo.replace_version(99, data)          # twice: building a version again must not duplicate anything
        assert neo.counts(99) == mem.counts(99)
        a, b = expand(mem, 99, ["E-4029"], 2), expand(neo, 99, ["E-4029"], 2)
        assert (a.documents, a.terms) == (b.documents, b.terms)
    finally:
        neo._run("MATCH (n:Entity {v: 99}) DETACH DELETE n")
        neo.close()
