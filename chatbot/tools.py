"""The agent's two ways of looking things up, written as plain functions first and then wrapped as LangChain tools.

A TOOL is a function the model may ask us to run. The model never touches the database: it asks, our code runs the function, and the result goes back.
Both tools are read-only. That is a security choice, not an accident: an agent that can only read can be tricked into saying something wrong, but not into doing something harmful."""
from typing import Callable

Retriever = Callable[[str, str], list[dict]]        # (query, plan) -> chunks as dicts


def hit_to_dict(h) -> dict:
    return {"chunk_id": h.chunk_id, "text": h.text, "doc_key": h.doc_key, "title": h.title, "section": h.section, "via": h.via}


def make_retriever(conn, embedder, graph_store=None, index_version: int | None = None, graph_version: int | None = None, k: int = 5) -> Retriever:
    """The real retriever: hybrid search in Postgres, plus the knowledge graph when the plan says the question names an incident, policy change, error code or region."""
    from pipeline.graph import expand, find_in_question
    from pipeline.graph_cli import graph_chunks
    from pipeline.index import live_version, search

    def retrieve(query: str, plan: str) -> list[dict]:
        iv = index_version or live_version(conn)
        out = [hit_to_dict(h) for h in search(conn, embedder, query, iv, k, "hybrid")]
        if plan == "both" and graph_store is not None:
            gv = graph_version or graph_store.live_version()
            if gv is not None:
                have = {c["chunk_id"] for c in out}
                out += [hit_to_dict(h) for h in graph_chunks(conn, iv, expand(graph_store, gv, find_in_question(query), 2)) if h.chunk_id not in have]
        return out
    return retrieve


def as_langchain_tools(retrieve: Retriever):
    """The same retriever as two LangChain tools, for create_agent (the short way, shown beside our explicit graph)."""
    from langchain_core.tools import tool

    @tool
    def search_documents(query: str) -> list[dict]:
        """Search the Dropline documents (policies, runbooks, postmortems, tickets) by meaning and keywords. Returns chunks with their ids."""
        return retrieve(query, "search")

    @tool
    def follow_links(query: str) -> list[dict]:
        """Use when the question names an incident (INC-nnnn), policy change (PC-nn), error code (E-nnnn) or region: follows the links between them to the documents that explain them."""
        return retrieve(query, "both")
    return [search_documents, follow_links]
