"""Episode 8A: the agent as a graph.

A LangGraph graph is four ideas:
  STATE   a notebook every step can read and write (a typed dictionary)
  NODES   steps: plain Python functions that take the state and return the changes they make
  EDGES   which step comes next
  CONDITIONAL EDGES   a function looks at the state and CHOOSES the next step (this is where an agent decides)

        START -> route -> retrieve -> grade --sufficient--> answer -> END
                              ^          |
                              |          +--not enough, tries left--> rewrite --+
                              +-----------------------------------------------+
                                         +--not enough, no tries left--> idk -> END

Not every step is a model call: `route` is a plain rule (does the question name an incident, a policy change, an error code or a region?). Use a model only where a rule cannot do the job.
Safety rails: at most MAX_ATTEMPTS retrievals (no endless loops); an answer must cite chunk ids that were really retrieved (no invented sources); retrieved text is data, never instructions."""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from pipeline.graph import find_in_question

from .llm import Llm
from .schemas import IDK, MAX_ATTEMPTS, NOTICE
from .tools import Retriever


class AgentState(TypedDict, total=False):
    question: str
    current_query: str
    plan: str                                    # 'search' or 'both' (search plus the knowledge graph)
    chunks: list[dict]
    attempts: int
    grade: dict
    reply: dict                                  # what the user sees
    trace: Annotated[list[str], operator.add]    # the path taken. 'operator.add' is a REDUCER: each step's list is appended instead of replacing the last


def reply(text: str, sources: list[dict], mode: str, llm_name: str) -> dict:
    return {"text": text, "sources": sources, "mode": mode, "model": llm_name, "notice": NOTICE}


def build_agent(llm: Llm, retrieve: Retriever, checkpointer=None):
    def route(state: AgentState) -> dict:
        plan = "both" if find_in_question(state["question"]) else "search"
        return {"plan": plan, "current_query": state["question"], "attempts": 0, "trace": [f"route:{plan}"]}

    def retrieve_node(state: AgentState) -> dict:
        chunks = retrieve(state["current_query"], state["plan"])
        return {"chunks": chunks, "attempts": state["attempts"] + 1, "trace": [f"retrieve:{len(chunks)}"]}

    def grade_node(state: AgentState) -> dict:
        g = llm.grade(state["question"], state["chunks"]) if state["chunks"] else None
        ok = bool(g and g.sufficient)
        return {"grade": {"sufficient": ok, "reason": g.reason if g else "nothing was retrieved"}, "trace": [f"grade:{'enough' if ok else 'not enough'}"]}

    def after_grade(state: AgentState) -> str:               # the conditional edge: the agent's decision
        if state["grade"]["sufficient"]:
            return "answer"
        return "rewrite" if state["attempts"] < MAX_ATTEMPTS else "idk"

    def rewrite_node(state: AgentState) -> dict:
        return {"current_query": llm.rewrite(state["question"], state["current_query"]).query, "trace": ["rewrite"]}

    def answer_node(state: AgentState) -> dict:
        a = llm.write_answer(state["question"], state["chunks"])
        by_id = {c["chunk_id"]: c for c in state["chunks"]}
        if not a.cited_chunk_ids or any(i not in by_id for i in a.cited_chunk_ids):       # the guard: no citation, or a source that was never retrieved
            return {"reply": reply(IDK, [], "refused-uncited-answer", llm.name), "trace": ["guard:bad-citation"]}
        sources = [{"chunk_id": i, "doc": by_id[i]["doc_key"], "section": by_id[i]["section"]} for i in a.cited_chunk_ids]
        return {"reply": reply(a.text, sources, "answered", llm.name), "trace": ["answer"]}

    def idk_node(state: AgentState) -> dict:
        return {"reply": reply(IDK, [], "i-do-not-know", llm.name), "trace": ["idk"]}

    g = StateGraph(AgentState)
    for name, fn in (("route", route), ("retrieve", retrieve_node), ("grade", grade_node), ("rewrite", rewrite_node), ("answer", answer_node), ("idk", idk_node)):
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_edge("route", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade, {"answer": "answer", "rewrite": "rewrite", "idk": "idk"})
    g.add_edge("rewrite", "retrieve")
    g.add_edge("answer", END)
    g.add_edge("idk", END)
    return g.compile(checkpointer=checkpointer)


def ask(agent, question: str, thread_id: str = "default") -> dict:
    """Run the graph for one question. The thread id names the conversation: with a checkpointer, the same id continues where it stopped."""
    return agent.invoke({"question": question}, {"configurable": {"thread_id": thread_id}})
