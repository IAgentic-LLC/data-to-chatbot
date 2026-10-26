# Compliance and governance, in plain words, mapped to this repo

**Read this first.** This is an engineering teaching document, not legal advice, and no repository can make a company "compliant" by itself. Compliance is a mix of legal basis, contracts, policies, training, people and technical controls. What we can show well is the technical controls and how to prove they work. For a real product, have a lawyer or privacy professional review your situation and check the current text of any law or standard named here; they change.

## Vocabulary (what the words mean)
- **Governance**: who owns each piece of data, what it may be used for, how long it may be kept, and who can see it. Written down, enforced, and checked.
- **Compliance**: showing that you follow the rules that apply to you (laws, contracts, standards, your own policy).
- **Personal data**: any information about an identifiable person (an email, a phone number, an order that can be tied to someone).
- **Data subject**: the person the data is about.
- **Controller / processor**: the controller decides why and how personal data is used; a processor handles it on the controller's behalf (for example a cloud or model provider). Using a processor normally needs a written contract.
- **Retention**: how long you keep data. **Erasure**: deleting a person's data when they ask (and the law allows).
- **Audit trail**: a record of who did what and when, that nobody can quietly edit.
- **Least privilege**: every person and program gets only the access it needs.
- **Lineage**: the path from an answer back to the raw file it came from.

## The principles, and where each one lives in this repo
| Principle (plain meaning) | Where it is in the code | How to check it yourself |
|---|---|---|
| **Know your data**: every feed has an owner, a classification and a purpose | `governance/policy.yaml` | `python -c "from pipeline.policy import load; print(load())"` |
| **Collect only what you need (minimisation)**: personal data is replaced before it can be indexed | `pipeline/pii.py`, used in `curate.py`; check `no_personal_data` in `checks.py` | `python -m pipeline.cli checks` |
| **Do not keep data forever (storage limitation)**: per-feed retention, expired documents leave the index | `retention_days` in policy, status `expired` in `curate.py` | `tests/test_curate_governance.py::test_retention_*` |
| **Delete on request (erasure)**: find the person everywhere, redact, delete old bytes, rebuild, prove zero hits | `pipeline/erasure.py`, `cli find` / `cli erase` | run `cli find EMAIL`, `cli erase EMAIL`, `cli find EMAIL` |
| **Be able to show what happened (accountability)**: append-only, hash-chained audit log; identifiers stored only as hashes | `pipeline/audit.py`, trigger blocks UPDATE and DELETE | `python -m pipeline.cli audit` |
| **Least privilege**: the chatbot's database login can read the index and nothing else | `migrations/004_chatbot_role.sql`, `GRANT` in `index.py` | `tests/test_index.py::test_chatbot_role_*` |
| **Human in the loop for risky content**: suspected prompt injection is held back until a person decides | `pipeline/injection.py`, `cli review` | `cli review list` |
| **Traceability (lineage)**: any chunk back to its raw file and the run that fetched it | `v_lineage` view, `index.explain` | `python -m pipeline.index_cli explain "refund-policy#eu-customers"` |
| **Controlled change**: every database change is a numbered file in version control | `migrations/`, `pipeline/migrate.py` | `select * from schema_migrations` |
| **Do not send data to third parties without knowing**: embeddings are computed locally | `pipeline/embed.py`, policy `data_sent_to_third_parties` | no network call is made to embed text |
| **Tell people they are talking to a machine** | serving episode (8) | not built yet |
| **Encryption, backups, secrets** | going-live episode (9) | not built yet; the local demo is NOT encrypted |

## Which real-world frameworks these map to (to look up, not to rely on)
- **GDPR (EU) / UK GDPR**: principles of minimisation, storage limitation, integrity and confidentiality, accountability; the right to erasure; records of processing; data protection by design; contracts with processors; rules on sending data outside the EU. A DPIA (data protection impact assessment) is needed for risky processing.
- **CCPA/CPRA (California)**: rights to know, delete and opt out.
- **EU AI Act**: people must be told when they interact with an AI system such as a chatbot; further duties depend on the risk level of the use.
- **SOC 2**: an audit of your controls for security, availability and confidentiality. Auditors ask for evidence: access lists, change records and logs. Our migrations, roles and audit log are exactly that kind of evidence.
- **ISO 27001**: a management-system standard for information security.

## What this repo does NOT do (read this list out loud)
1. It finds an exact identifier you give it. It does not find the same person written as a name inside free text, in a screenshot, or in a PDF scan.
2. It cannot reach copies outside the pipeline: your backups, exports, laptop files, logs, or any provider that already received the data.
3. The audit log is tamper-**evident** (edits show up when you verify), not tamper-proof; someone with full database control could rebuild the whole chain. Production keeps a second copy elsewhere.
4. Regex-based personal-data detection misses things (names, street addresses, unusual number formats). Real projects add a trained detector and sample-check the result.
5. The prompt-injection screen catches lazy attacks only. The real defence is giving the model no powers and no secrets it should not have (episode 8).
6. There is no encryption at rest or in transit in the local demo, no real login on Airflow, and the passwords in the compose file are throwaways.
7. The data is fictional. Real data brings real contracts, a lawful basis for each use, and people who are accountable for the answers.
