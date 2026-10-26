# Runbook: a person asks to be deleted

Teaching template for a fictional company. Not legal advice: your lawyer or privacy lead decides deadlines, exceptions and wording for a real business.

**Why a runbook?** Code can delete the data. People still have to receive the request, check who is asking, decide what must be kept, tell the person the result and keep the proof. Write the steps down before the first request arrives, not during it.

## Steps
| # | Who | What | Evidence kept |
|---|---|---|---|
| 1 | Anyone who receives it | Forward the request to the privacy owner the same day. Do not reply with promises. | date received |
| 2 | Privacy owner | Check the requester is who they say they are (reply to the address on file, or another check proportionate to the risk). Never ask for more personal data than needed. | "identity checked" note, no copy of documents |
| 3 | Privacy owner | Decide scope: is there a legal reason to keep anything (tax records, a dispute, a legal hold)? Record each exception and its reason. | decision note |
| 4 | Pipeline operator | `python -m pipeline.cli find <identifier>` for every identifier the person has (each email, phone number, order id). | the "before" line |
| 5 | Pipeline operator | `python -m pipeline.cli erase <identifier>` for each. This redacts bronze, deletes old blobs, rebuilds silver and curated. | audit entry (hash of the identifier, never the identifier) |
| 6 | Pipeline operator | Rebuild the search index so no chunk keeps the text: `index_cli build`, run the evaluation, then `promote`. Older index versions that held the text are retired and dropped. | new index version in the audit log |
| 7 | Pipeline operator | `find` again for each identifier and confirm zero everywhere. | the "after" line |
| 8 | Privacy owner | Fix the SOURCE system too, or the data comes back on the next import. Tell the team that owns each feed. | tickets to those teams |
| 9 | Privacy owner | Look beyond the pipeline: backups (how long until they expire?), exports, analytics, email threads, any provider that received the data. Record what remains and when it will go. | list with dates |
| 10 | Privacy owner | Reply to the person in plain language: what was deleted, what was kept and why, what will disappear later (backups), and when. | copy of reply |
| 11 | Privacy owner | Close the request inside the deadline in your policy (the teaching policy says 30 days). | closing date |

## Known gaps in the automated part
- It matches the exact identifier. A name written in free text, or a description of the person without any identifier, is not found by code. A person reads a sample.
- It cannot reach copies outside the pipeline (step 9 is human work).
- Redacting changes the stored copy of the file. The original source system must be fixed by its owner (step 8).
