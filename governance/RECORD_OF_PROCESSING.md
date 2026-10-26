# Record of processing (template, filled in for the Dropline support assistant)

Many privacy regimes expect organisations to keep a written record of what personal data they handle and why. This template shows the kind of table people ask to see. It is a teaching example, not legal advice, and a real one is completed with your privacy lead.

| Question | Answer for this system |
|---|---|
| What is the activity? | A support assistant that answers staff and customers using the company's own documents. |
| Why do we process personal data at all? | Only the `tickets` feed contains it, to learn from resolved cases. Everything else is business documents. |
| Which people does the data describe? | Customers who contacted support. |
| Which kinds of data? | Email addresses, phone numbers and order ids in free text. |
| Legal basis (to be decided with a lawyer) | Write it down per purpose before launch. The assistant must still work if a person refuses a purpose that needs their consent. |
| Where is it stored? | Raw files in the data lake (bronze), parsed text in the database (silver). Not in the search index (replaced by `[EMAIL]` and `[PHONE]`). |
| Who can access it? | Pipeline operators. The chatbot's database login cannot. |
| Who else receives it? | Nobody. Embeddings are computed locally. The chat model provider is chosen in episode 8 and added here before launch, with its location and retention terms. |
| Is any of it sent abroad? | Not in the local demo. Re-check when a hosted model or server is chosen. |
| How long is it kept? | 365 days for tickets (`governance/policy.yaml`). |
| How are people's rights handled? | `governance/ERASURE_RUNBOOK.md`; access requests use `find` plus a human review of the result. |
| How is it protected? | Least-privilege roles, audit log, personal data scrubbed before indexing. Encryption, backups and secrets management are added in the deployment episode and NOT present in the local demo. |
| Was a risk assessment needed? | Decide with a privacy professional. Triggers include large scale, sensitive categories, or automated decisions about people. This assistant makes no decisions about individuals. |
| Does the assistant tell people it is an AI? | Required by design in the serving episode (a visible notice in the chat window). |
| Who owns this record, and when is it reviewed? | Name a person and a date. A record nobody owns is out of date within a year. |
