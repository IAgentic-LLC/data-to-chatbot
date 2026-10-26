# Data card: the Dropline support knowledge base

A data card is a one-page honest description of a dataset, so the next person (or auditor) does not have to guess.

| | |
|---|---|
| **Purpose** | Answer customer-support questions for the fictional company Dropline, from its own policies, runbooks, postmortems and resolved tickets. |
| **Not for** | Legal advice, anything about a named person, decisions that affect someone's rights or money without a human. |
| **Feeds** | wiki (internal), web (public help pages), pdf (internal), prices (public), tickets (personal data), uploads (unowned). See `governance/policy.yaml` for owner, classification and retention of each. |
| **Size** | 21 files in, 16 documents searchable, 46 chunks (section chunker). |
| **Personal data** | Present in raw `tickets` (emails, phone numbers). Replaced by `[EMAIL]` and `[PHONE]` before documents are curated for search. Present in bronze and silver until retention or erasure removes it. Not present in the search index (checked by `no_personal_data`). |
| **Known quality issues, handled** | Exact duplicates, a stale policy that contradicts the current one, damaged characters, page furniture, an empty file, a corrupt PDF, a scrap note, a document with a hidden instruction. Answer key: `data/sources/TRAPS.md`. |
| **Known quality issues, NOT handled** | Facts that are wrong but not contradicted by anything; policies that changed but whose old copy was never uploaded; scanned PDFs with no text. |
| **Freshness** | A feed is flagged (warning) if it delivers nothing for 48 hours. Documents carry their own date when they state one. |
| **Retention** | tickets 365 days, uploads 365 days, others unlimited (teaching values). |
| **Who can read what** | The chatbot's database login: the search index only. Pipeline operators: everything. |
| **Third parties** | None for embeddings (computed locally). The chat model provider is chosen in episode 8 and recorded here before use. |
| **Evaluation** | Retrieval recall on the dev questions (episode 5); full answer evaluation with an eval gate (episode 7). |
| **Contact / owner** | Named per feed in `policy.yaml`. In a real project this page also names a person who answers for the whole dataset. |
