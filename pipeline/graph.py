"""Episode 5B: a knowledge graph beside the search index.

Plain words first. A graph is a set of THINGS (nodes) and the LINKS between them (relationships), stored as data.
    (INC-2047 incident) --LED_TO--> (PC-12 policy change) --APPLIES_TO {days: 14}--> (EU customers)
A search index finds text that LOOKS like your question. A graph follows links, so it can answer "what did that incident change, and for whom?"
even when no single paragraph says all of it.

What this module does
  1. extract_graph(documents)   read the curated documents and pull out things and links with plain, readable RULES (no model, no cost, same answer every time)
  2. a store that keeps them     MemoryGraph (for tests and for learning) or Neo4jGraph (the real database), both versioned like the search index
  3. find_in_question + expand   find the things a question names, walk the links, return the documents that explain them
  4. check_consistent            the graph must never hold anything the curation step refused

Honest limits (said out loud)
  * With 16 documents a graph is not NEEDED. The eval in graph_cli.py measures whether it helps; if it does not, we say so.
  * Rules only see the patterns we wrote down (INC-nnnn, PC-nn, E-nnnn, 'after incident', 'see the ...'). A link phrased some other way is missed.
  * A language model could extract more, but it can also invent links, so it would need a human check (see the plan for the agent film).
  * Personal data cannot enter this graph by construction: only ids that match the patterns above become nodes."""
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

# Only these link types may be written. Neo4j cannot take a link type as a parameter, so we build the query text from this fixed list (never from user input).
REL_TYPES = ("MENTIONS", "LED_TO", "APPLIES_TO", "REFERENCES")
KINDS = ("Document", "Incident", "PolicyChange", "ErrorCode", "Region")

RX_INC = re.compile(r"\bINC-\d{4}\b")
RX_PC = re.compile(r"\bPC-\d+\b")
RX_ERR = re.compile(r"\bE-\d{4}\b")
RX_AFTER = re.compile(r"\bafter (?:incident )?(INC-\d{4})\b", re.I)
RX_SEE = re.compile(r"\(see the ([a-z][a-z \-]+?)\)", re.I)
RX_DAYS = re.compile(r"(\d+)-day")
REGION_HEADINGS = {"eu customers": ["EU"], "uk and us customers": ["UK", "US"]}


@dataclass(frozen=True)
class Node:
    key: str                  # the thing's id, e.g. 'INC-2047' or 'wiki/refund-policy.md'
    kind: str                 # one of KINDS
    label: str = ""           # human text (a document's title)


@dataclass(frozen=True)
class Edge:
    src: str
    rel: str
    dst: str
    evidence: str = ""        # the document the link was read from, so every link can be traced
    days: int | None = None   # only for APPLIES_TO


@dataclass
class GraphData:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[Edge] = field(default_factory=set)

    def node(self, key: str, kind: str, label: str = "") -> None:
        if key not in self.nodes or (label and not self.nodes[key].label):
            self.nodes[key] = Node(key, kind, label)

    def edge(self, src: str, rel: str, dst: str, evidence: str = "", days: int | None = None) -> None:
        assert rel in REL_TYPES
        self.edges.add(Edge(src, rel, dst, evidence, days))


def _kind_of(key: str) -> str:
    return "Incident" if RX_INC.fullmatch(key) else "PolicyChange" if RX_PC.fullmatch(key) else "ErrorCode" if RX_ERR.fullmatch(key) else "Region"


def _sections(text: str) -> list[tuple[str, str]]:
    """[(heading, body)] split at '## ' lines; text before the first heading has the heading ''."""
    parts = re.split(r"(?m)^##+ +(.+)$", text)
    out = [("", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def extract_graph(docs) -> GraphData:
    """docs: curated documents with .doc_key .title .text .status. Only 'accepted' ones are read."""
    docs = [d for d in docs if d.status == "accepted"]
    g = GraphData()
    by_title = {_norm_title(d.title): d.doc_key for d in docs}
    for d in docs:
        g.node(d.doc_key, "Document", d.title)
        # which incident is this document ABOUT? (a postmortem names it in its title)
        about = (RX_INC.findall(d.title) or [None])[0] if "postmortem" in d.title.lower() else None
        pcs_in_doc = sorted(set(RX_PC.findall(d.text)))
        for heading, body in _sections(d.text):
            ctx = f"{heading}\n{body}"
            for key in sorted(set(RX_INC.findall(ctx)) | set(RX_PC.findall(ctx)) | set(RX_ERR.findall(ctx))):
                g.node(key, _kind_of(key))
                g.edge(d.doc_key, "MENTIONS", key, d.doc_key)
            for sentence in re.split(r"(?<=[.!?])\s+", body):
                # rule 1: "... PC-12 ... after incident INC-2047"   or   (heading E-4029) "Introduced after INC-2051."
                m = RX_AFTER.search(sentence)
                if m:
                    inc = m.group(1)
                    subjects = RX_PC.findall(sentence) or RX_ERR.findall(sentence) or RX_ERR.findall(heading) or RX_PC.findall(heading)
                    for s in subjects:
                        g.node(inc, "Incident"); g.node(s, _kind_of(s)); g.edge(inc, "LED_TO", s, d.doc_key)
                # rule 2: a postmortem says what its incident led to: "became policy change PC-12", "returning error E-4029"
                if about:
                    for s in RX_PC.findall(sentence) if re.search(r"became|introduced|policy change", sentence, re.I) else []:
                        g.node(about, "Incident"); g.node(s, "PolicyChange"); g.edge(about, "LED_TO", s, d.doc_key)
                    for s in RX_ERR.findall(sentence) if re.search(r"error|returning", sentence, re.I) else []:
                        g.node(about, "Incident"); g.node(s, "ErrorCode"); g.edge(about, "LED_TO", s, d.doc_key)
                # rule 3: "(see the drop-day runbook)" links this document to that document
                for m2 in RX_SEE.finditer(sentence):
                    target = by_title.get(_norm_title(m2.group(1)))
                    if target and target != d.doc_key:
                        g.edge(d.doc_key, "REFERENCES", target, d.doc_key)
            # rule 4: a policy document with one policy change and a section per region says who the change applies to, and for how many days
            regions = REGION_HEADINGS.get(heading.lower())
            if regions and len(pcs_in_doc) == 1:
                days = RX_DAYS.search(body)
                for r in regions:
                    g.node(r, "Region", r)
                    g.edge(pcs_in_doc[0], "APPLIES_TO", r, d.doc_key, int(days.group(1)) if days else None)
    return g


# ---------------------------------------------------------------- stores
class MemoryGraph:
    """The same interface as Neo4jGraph, held in Python dictionaries. Used by the tests and by anyone without Docker."""
    def __init__(self):
        self.versions: dict[int, GraphData] = {}
        self.live: int | None = None

    def replace_version(self, version: int, data: GraphData) -> None:
        self.versions[version] = data

    def promote(self, version: int) -> int | None:
        if version not in self.versions:
            raise ValueError(f"graph version {version} is not built")
        old, self.live = self.live, version
        return old

    def live_version(self) -> int | None:
        return self.live

    def counts(self, version: int) -> tuple[int, int]:
        d = self.versions[version]
        return len(d.nodes), len(d.edges)

    def neighbours(self, version: int, key: str) -> list[tuple[Edge, str]]:
        """every (edge, other end) that touches `key`, in either direction"""
        out = []
        for e in self.versions[version].edges:
            if e.src == key:
                out.append((e, e.dst))
            elif e.dst == key:
                out.append((e, e.src))
        return sorted(out, key=lambda x: (x[0].rel, x[1]))

    def node(self, version: int, key: str) -> Node | None:
        return self.versions[version].nodes.get(key)

    def delete_document(self, version: int, doc_key: str) -> None:
        d = self.versions[version]
        d.nodes.pop(doc_key, None)
        d.edges = {e for e in d.edges if e.src != doc_key and e.dst != doc_key and e.evidence != doc_key}


class Neo4jGraph:
    """The real thing. Every node and link carries `v`, the graph version, so a new version is written BESIDE the live one and a single :Alias node says which is live
    (the same blue/green idea as the search index; Neo4j Community has only one database, so the version lives in a property, not in a second database)."""
    def __init__(self, uri: str, user: str, password: str):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF")      # the 'label does not exist yet' warnings are noise on an empty database

    def close(self) -> None:
        self.driver.close()

    def _run(self, cypher: str, **params):
        return self.driver.execute_query(cypher, parameters_=params).records

    def ping(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def setup(self) -> None:
        self._run("CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (n:Entity) REQUIRE (n.key, n.v) IS UNIQUE")

    def replace_version(self, version: int, data: GraphData) -> None:
        self.setup()
        self._run("MATCH (n:Entity {v: $v}) DETACH DELETE n", v=version)           # idempotent: building the same version twice gives the same graph
        self._run("UNWIND $rows AS r CREATE (n:Entity {key: r.key, kind: r.kind, label: r.label, v: $v})",
                  rows=[{"key": n.key, "kind": n.kind, "label": n.label} for n in data.nodes.values()], v=version)
        for rel in REL_TYPES:                                                       # the type name comes from our fixed list, never from outside
            rows = [{"s": e.src, "d": e.dst, "ev": e.evidence, "days": e.days} for e in data.edges if e.rel == rel]
            if rows:
                self._run(f"UNWIND $rows AS r MATCH (a:Entity {{key: r.s, v: $v}}), (b:Entity {{key: r.d, v: $v}}) CREATE (a)-[:{rel} {{evidence: r.ev, days: r.days, v: $v}}]->(b)", rows=rows, v=version)

    def promote(self, version: int) -> int | None:
        if not self._run("MATCH (n:Entity {v: $v}) RETURN n LIMIT 1", v=version):
            raise ValueError(f"graph version {version} is not built")
        old = self.live_version()
        self._run("MERGE (a:Alias {name: 'live'}) SET a.version = $v", v=version)
        return old

    def live_version(self) -> int | None:
        r = self._run("MATCH (a:Alias {name: 'live'}) RETURN a.version AS v")
        return r[0]["v"] if r else None

    def counts(self, version: int) -> tuple[int, int]:
        n = self._run("MATCH (n:Entity {v: $v}) RETURN count(n) AS c", v=version)[0]["c"]
        e = self._run("MATCH (:Entity {v: $v})-[r]->(:Entity {v: $v}) RETURN count(r) AS c", v=version)[0]["c"]
        return n, e

    def neighbours(self, version: int, key: str) -> list[tuple[Edge, str]]:
        out = []
        for r in self._run("MATCH (a:Entity {key: $k, v: $v})-[r]-(b:Entity {v: $v}) RETURN a.key AS a, type(r) AS t, b.key AS b, startNode(r).key AS s, r.evidence AS ev, r.days AS days", k=key, v=version):
            src, dst = (r["a"], r["b"]) if r["s"] == r["a"] else (r["b"], r["a"])
            out.append((Edge(src, r["t"], dst, r["ev"] or "", r["days"]), r["b"]))
        return sorted(out, key=lambda x: (x[0].rel, x[1]))

    def node(self, version: int, key: str) -> Node | None:
        r = self._run("MATCH (n:Entity {key: $k, v: $v}) RETURN n.kind AS kind, n.label AS label", k=key, v=version)
        return Node(key, r[0]["kind"], r[0]["label"] or "") if r else None

    def delete_document(self, version: int, doc_key: str) -> None:
        self._run("MATCH (n:Entity {key: $k, v: $v}) DETACH DELETE n", k=doc_key, v=version)
        self._run("MATCH (:Entity {v: $v})-[r {evidence: $k}]->(:Entity) DELETE r", k=doc_key, v=version)


# ---------------------------------------------------------------- asking the graph
REGION_WORDS = {"eu": "EU", "europe": "EU", "european": "EU", "uk": "UK", "us": "US"}


def find_in_question(question: str) -> list[str]:
    """The things a question names: ids like INC-2047 / PC-12 / E-4029 and region words like EU."""
    keys = [k.upper() for rx in (RX_INC, RX_PC, RX_ERR) for k in rx.findall(question.upper())]
    keys += [REGION_WORDS[w] for w in re.findall(r"[a-z]+", question.lower()) if w in REGION_WORDS]
    return list(dict.fromkeys(keys))


@dataclass
class GraphAnswer:
    seeds: list[str]                                   # the things the question named that exist in the graph
    documents: list[str]                               # documents reached by walking the links, nearest first
    paths: list[str]                                   # the links walked, as readable lines (this is the explanation)
    terms: list[str]                                   # entity ids reached; chunks mentioning them are the relevant sections


def expand(store, version: int, seeds: list[str], hops: int = 2) -> GraphAnswer:
    """Breadth-first walk from the seeds, up to `hops` links away, in either direction. MENTIONS links are how a thing leads to its documents."""
    seen = {s: 0 for s in seeds if store.node(version, s)}
    queue = deque(seen)
    paths: list[str] = []
    docs: dict[str, int] = {}
    while queue:
        cur = queue.popleft()
        if seen[cur] >= hops:
            continue
        for e, other in store.neighbours(version, cur):
            line = f"{e.src} -{e.rel}{'(' + str(e.days) + ' days)' if e.days else ''}-> {e.dst}"
            if line not in paths:
                paths.append(line)
            node = store.node(version, other)
            if node and node.kind == "Document":
                docs.setdefault(other, seen[cur] + 1)
            elif other not in seen:
                seen[other] = seen[cur] + 1
                queue.append(other)
    # a document that holds the evidence for a link is also relevant
    for line_edge in [e for k in list(seen) for e, _ in store.neighbours(version, k)]:
        if line_edge.evidence and store.node(version, line_edge.evidence):
            docs.setdefault(line_edge.evidence, hops)
    ordered = [d for d, _ in sorted(docs.items(), key=lambda x: (x[1], x[0]))]
    return GraphAnswer(list(seen)[:len(seeds)], ordered, paths, [k for k in seen if store.node(version, k).kind != "Document"])


def check_consistent(data: GraphData, curated_docs) -> list[str]:
    """Problems found (empty list = fine): the graph may only contain accepted documents, and no node id may look like personal data."""
    ok = {d.doc_key for d in curated_docs if d.status == "accepted"}
    problems = [f"document {n.key} is in the graph but is not accepted" for n in data.nodes.values() if n.kind == "Document" and n.key not in ok]
    problems += [f"node {n.key} is not an id we extract" for n in data.nodes.values() if n.kind != "Document" and not (RX_INC.fullmatch(n.key) or RX_PC.fullmatch(n.key) or RX_ERR.fullmatch(n.key) or n.key in set(REGION_WORDS.values()))]
    return problems
