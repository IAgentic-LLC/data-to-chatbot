"""Episode 8A commands:
  python -m chatbot.cli ask "your question" [--llm scripted|deepseek:deepseek-chat] [--thread NAME] [--no-graph]
  python -m chatbot.cli draw                                  print the agent as a Mermaid flowchart
  python -m chatbot.cli state --thread NAME                   show what a saved conversation holds (proof that it survives a restart)
Keys come from environment variables (DEEPSEEK_API_KEY and so on), never from a file in the repository."""
import argparse
import json
import sys

import psycopg
from psycopg.rows import dict_row

from pipeline import config
from pipeline.embed import get_embedder
from pipeline.graph import Neo4jGraph
from pipeline.index import live_version

from .agent import ask, build_agent
from .llm import get_llm
from .tools import make_retriever


def connect_graph(enabled: bool):
    if not enabled:
        return None
    g = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
    return g if g.ping() else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="chatbot.cli", usage=__doc__)
    ap.add_argument("cmd", choices=["ask", "draw", "state"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--llm", default=None)
    ap.add_argument("--thread", default="demo")
    ap.add_argument("--no-graph", action="store_true")
    a = ap.parse_args(argv)

    from langgraph.checkpoint.postgres import PostgresSaver
    # the saver needs its own connection: autocommit, and rows as dictionaries (this is what the package documents)
    with psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row) as ck_conn:
        saver = PostgresSaver(ck_conn)
        saver.setup()                                               # creates the checkpoint tables the first time, does nothing after
        conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
        iv = live_version(conn)
        row = conn.execute("SELECT embed_model FROM index_versions WHERE version=%s", (iv,)).fetchone()
        emb = get_embedder("hash" if row[0].startswith("hash") else "fastembed")
        graph = connect_graph(not a.no_graph)
        agent = build_agent(get_llm(a.llm), make_retriever(conn, emb, graph), saver)
        if a.cmd == "draw":
            print(agent.get_graph().draw_mermaid())
        elif a.cmd == "state":
            print(json.dumps(agent.get_state({"configurable": {"thread_id": a.thread}}).values.get("reply"), indent=2, default=str))
        else:
            out = ask(agent, a.arg, a.thread)
            r = out["reply"]
            print("path:   ", " -> ".join(out["trace"]))
            print("graph:  ", "knowledge graph used" if out["plan"] == "both" and graph else "search only")
            print(f"model:   {r['model']}   mode: {r['mode']}")
            print(f"\n{r['text']}\n")
            for s in r["sources"]:
                print(f"  source: {s['chunk_id']}  ({s['doc']})")
            print(f"\n{r['notice']}")
        if graph:
            graph.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
