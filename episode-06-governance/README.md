# Episode 6: governance and compliance in practice

Goal: you can explain governance and compliance in plain words, and you can prove, by running code, that each control really works.

This is the film where the whole course's "responsible" thread is pulled together. The code already exists from episodes 4 and 5; this episode is about understanding it, running it as a drill, and writing the paperwork that code cannot write.

**Not legal advice.** We teach engineering controls that support compliance. Whether a real product is compliant depends on law, contracts, policy and people. Read the limits list in `governance/COMPLIANCE_MAP.md` out loud.

## Film outline (about 25 minutes)
1. **A customer writes "delete me."** Why a pile of documents suddenly becomes a legal and ethical problem. (A story, then the question: could you actually do it?)
2. **The words, plainly.** Governance, compliance, personal data, controller and processor, retention, erasure, audit trail, least privilege, lineage. Each with one example from our data.
3. **The policy file.** `governance/policy.yaml`: owner, classification, retention and purpose for every feed. Why it is code, and why changes to it get reviewed.
4. **Collect less.** Minimisation: the scrubber, the check that fails if an email gets through, and why we keep personal data in bronze and silver but never in the index.
5. **Keep it for less time.** Retention, with an injected "today" so you can watch tickets expire.
6. **The erasure drill.** `find`, `erase`, `find` again. What it changed, what it could not touch (backups, source system, free-text names).
7. **A record nobody can quietly edit.** The hash-chained audit log; forge an entry on screen and watch the chain break; why the database trigger exists; honest limits of tamper-evidence.
8. **Who can see what.** The chatbot login that is refused on everything but the index. Try five forbidden queries live.
9. **Where did this answer come from?** Lineage from a chunk back to the raw file and run.
10. **The paperwork.** `RECORD_OF_PROCESSING.md` and `ERASURE_RUNBOOK.md`: the parts that need people. Fill in one row together.
11. **Frameworks, translated.** GDPR, CCPA, EU AI Act, SOC 2, ISO 27001: what each wants in plain words, and which of our files is the evidence an auditor would ask for.
12. **What we did NOT do.** The seven-point limits list. Then the one-page checklist to take away.

## Run the drill (no Docker needed, about 10 seconds)
```bash
python scripts/governance_drill.py
```
It builds a private copy of the practice data in a temporary folder and verifies 12 controls: policy loads, personal data stays out of accepted text, instruction-like text is held back, the stale policy loses, a person can be found and then is found nowhere, the audit entry omits them, the audit chain verifies, a forged entry is detected, the injection screen and the scrubber behave, and the knowledge graph holds only accepted documents. Expected last line: `12 of 12 controls verified`.

## Files used in this episode
| File | Role |
|---|---|
| `governance/policy.yaml` | the policy |
| `governance/COMPLIANCE_MAP.md` | principle -> where it lives in the repo -> how to check it, plus the not-covered list |
| `governance/DATA_CARD.md` | one-page honest description of the dataset |
| `governance/RECORD_OF_PROCESSING.md` | template, filled in for this assistant |
| `governance/ERASURE_RUNBOOK.md` | the human steps around the code |
| `pipeline/audit.py`, `erasure.py`, `policy.py`, `pii.py`, `injection.py` | the controls |
| `scripts/governance_drill.py` | the proof |

## Exercises
1. Add a new feed to `policy.yaml` classified `personal` with a 30-day retention, then explain which tests you would add.
2. In `RECORD_OF_PROCESSING.md`, find the row that cannot be answered yet. What decision does it wait for?
3. Write step 9 of the erasure runbook for your own company: where else could the data be?
4. Break the drill on purpose (comment out the scrubber call in `curate.py`). Which controls fail, and which still pass? What does that tell you about testing one control at a time?
