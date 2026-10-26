# Episode 8A: LangChain and LangGraph from zero (the chatbot as an agent)

Goal: understand what a language model call, a tool, an agent and a graph of steps are, then build the Dropline chatbot as a graph you can draw, stop, restart and test.

## Concepts, in the order the film teaches them
- **Language model call**: a function, text in and text out. Nothing more.
- **Tool**: a function the model may ASK us to run. The model never touches the database; our code runs the tool and hands back the result. Ours are read-only on purpose.
- **Agent**: a loop. Think, maybe use a tool, look at the result, repeat or answer. A loop with no stopping rule can run forever and cost money.
- **LangChain**: the toolkit around the model: one way to call any chat model (`init_chat_model`), a `@tool` decorator, and `with_structured_output(SomePydanticClass)` so the model must return a checked object. `create_agent` builds a whole agent loop in a few lines.
- **LangGraph**: draw the agent's steps as a graph and run it. The ideas: **state** (a notebook every step reads and writes), **nodes** (steps, plain functions), **edges** (what comes next), **conditional edges** (a function picks the next step: where an agent decides), **checkpointer** (saves the state after every step), **interrupt** (pause for a person).
- **Reducer**: how a state field combines updates. `Annotated[list, operator.add]` means "append". We use it to record the path taken (`trace`).

## The graph (drawn from the real compiled graph by `python -m chatbot.cli draw`)
`route -> retrieve -> grade -> answer | rewrite -> retrieve | idk`. `route` is a plain rule (no model): does the question name an incident, policy change, error code or region? If yes, the knowledge graph from episode 5B is used as well as search.

## Safety rails (each has a test)
At most 2 retrievals, then "I do not know" (no endless loop). An answer must cite chunk ids that were really retrieved, or it is refused. Retrieved text is wrapped as data and the model has no tool that writes or sends anything. Every reply carries the AI notice and names its mode (`scripted` offline, or the real model).

## Code
`chatbot/schemas.py` (Pydantic shapes), `llm.py` (scripted and LangChain models behind one interface), `tools.py` (retriever and LangChain tools), `agent.py` (the graph), `review.py` (the pause-and-resume review graph from episode 4), `cli.py`, `tests/test_agent.py` (12 offline tests), `create_agent_version.py` (the short way, for comparison).

## Run it
```bash
pip install -r requirements.txt
python -m pytest tests/test_agent.py -q                      # 12 passed, no key and no database needed
docker compose --profile graph up -d db graph                # the index and the graph
python -m chatbot.cli draw                                   # the flowchart
python -m chatbot.cli ask "How many days does a US customer have to return a limited drop item?"            # scripted, offline
export DEEPSEEK_API_KEY=...                                  # your own key; never put it in a file in the repo
python -m chatbot.cli ask "Why does error E-4029 exist, and what was done about it?" --llm deepseek:deepseek-chat --thread demo
python -m chatbot.cli state --thread demo                    # the saved conversation, read back from Postgres
python episode-08a-agent/create_agent_version.py "Why does error E-4029 exist?"
```

## What a real run did (2026-10-25, deepseek-chat, about a dozen short calls in total)
- "Why does error E-4029 exist, and what was done about it?": path `route:both -> retrieve:6 -> grade:enough -> answer`, three cited sources including the incident postmortem, correct.
- "What is the airspeed of a laden swallow?": two retrievals, two "not enough" grades, a rewrite, then `idk`. It did not make something up.
- The short `create_agent` version answered the E-4029 question less completely (it did not follow the link to the incident). One question proves nothing; the evaluation gate (episode 7) is where such comparisons are measured properly.

## Honest notes
- The grade and the answer are model calls, so they can be wrong. The graph limits the damage (retries are capped, citations are checked); it does not make the model right.
- `route` treats the word "us" as the region US. A question like "tell us about returns" is routed to the graph needlessly: harmless here (extra chunks), worth fixing with a stricter rule before production.
- Keys are read from environment variables only.

## Exercises
1. Change MAX_ATTEMPTS to 5 and ask the swallow question. What does it cost? Why is the cap a safety feature, not a tuning knob?
2. Add a node that logs the path to the audit log (episode 6).
3. Make the review graph ask for a reason as well as a decision. What must stay safe to repeat?
