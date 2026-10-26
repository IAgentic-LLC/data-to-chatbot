# Episode 0: the map

Goal: you can draw the whole system from memory and say what goes wrong at each box.

## What ETL means
Extract (get the files from where they live), Transform (turn them into something usable), Load (put the result where the next step can use it). A RAG chatbot is only as good as what is loaded into it, so the pipeline matters more than the model.

## The boxes
```
sources -> BRONZE -> SILVER -> GOLD -> chatbot -> monitoring
 messy      raw      clean     index     answers    traces, cost, feedback
```
| Layer | Holds | Rule |
|---|---|---|
| Bronze | the files exactly as they arrived | never edit; keep every version |
| Silver | clean text with metadata, plus a list of what was refused and why | rebuildable from bronze at any time |
| Gold | the search index (vectors plus keywords) | a new version is built beside the live one and swapped in only if it passes the tests |

## What breaks in real pipelines (we plant each of these in `data/sources`)
Duplicates that disagree, files nobody can open, text with damaged characters, web pages full of menus, PDFs with a footer on every page, personal data in free text, an old policy that contradicts the new one, and a document with a hidden instruction aimed at the model. `data/sources/TRAPS.md` lists each one and the right answer.

## Seven rules we keep
1. Raw is immutable. 2. Tasks are safe to repeat. 3. Only changed documents are reprocessed. 4. No index goes live unchecked. 5. Every answer traces back to a file and a run. 6. Documents are untrusted input. 7. Boring technology: one Postgres, not five services.

## Check
Run `docker compose up -d` and `python -m pytest -q`. If the tests pass and `docker compose ps` shows two healthy containers, your setup is ready for episode 1.
