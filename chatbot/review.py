"""Episode 4/8A: the human review queue as a graph that PAUSES.

Some documents are borderline (the injection screen was not sure). A person must decide. The graph runs until `ask_human`, calls interrupt(), and stops.
Its whole state is saved by the checkpointer, so the program can end, the machine can restart, and a day later a person resumes it with their decision:
    graph.invoke(Command(resume="approve"), config)
When it resumes, the paused node starts again from its first line, so everything before interrupt() must be safe to repeat (the same rule as Airflow tasks).

        START -> propose -> ask_human --(waits for a person)--> apply -> END"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class ReviewState(TypedDict, total=False):
    doc_key: str
    why: str
    decision: str          # 'approve' or 'reject'
    applied: bool


def build_review(decide, checkpointer):
    """`decide(doc_key, decision)` records the decision (in the pipeline: PgCurated.decide)."""
    def propose(state: ReviewState) -> dict:
        return {"why": state.get("why", "held for review")}

    def ask_human(state: ReviewState) -> dict:
        answer = interrupt({"doc_key": state["doc_key"], "why": state["why"], "options": ["approve", "reject"]})     # JSON-serialisable, shown to the reviewer
        if answer not in ("approve", "reject"):
            raise ValueError(f"decision must be approve or reject, not {answer!r}")
        return {"decision": answer}

    def apply(state: ReviewState) -> dict:
        decide(state["doc_key"], state["decision"])
        return {"applied": True}

    g = StateGraph(ReviewState)
    g.add_node("propose", propose)
    g.add_node("ask_human", ask_human)
    g.add_node("apply", apply)
    g.add_edge(START, "propose")
    g.add_edge("propose", "ask_human")
    g.add_edge("ask_human", "apply")
    g.add_edge("apply", END)
    return g.compile(checkpointer=checkpointer)
