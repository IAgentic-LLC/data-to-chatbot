# ETL or ELT? Both, and here is exactly where each one is

**ETL** = Extract, Transform, Load. Clean the data first, then store the clean result.
**ELT** = Extract, Load, Transform. Store the raw data first, then clean it later, inside the place that stores it.

The difference is only the order of the second and third letters, but it changes what you can recover when something goes wrong.

| | ETL | ELT |
|---|---|---|
| Raw data kept? | Often not. You stored only the cleaned version. | Yes. The raw copy is loaded first and kept. |
| If your cleaning had a bug | You may have to fetch the data again, if it still exists. | Fix the code and re-run on the raw copy you still have. |
| Where the work happens | In your own program (Python, a server of your own). | In the database or warehouse, usually written as SQL. |
| Good when | The data is sensitive and must be cleaned before it is stored anywhere; the target is small. | Storage is cheap, requirements change often, you want to re-do transformations. |

## This course uses both on purpose

```
EXTRACT  files arrive from different teams                                   (scripts/generate_sources.py plays the role of those teams)
LOAD     land them in bronze exactly as received                              <- ELT: raw is loaded and kept BEFORE any transformation
TRANSFORM, in Python (ETL-style):  parse PDFs/HTML, repair characters, remove footers, scrub personal data, find duplicates
TRANSFORM, in SQL    (ELT-style):  views inside Postgres: curation summary, review queue, lineage, "which documents may be searched"
LOAD     build the search index from the accepted documents
```

Why not pure ETL? Because "raw is immutable" (rule 1) means we load before we transform. If tomorrow we decide the dedupe rule was wrong, we do not need the original teams to send everything again.

Why not pure ELT? Two honest reasons:
1. **Parsing a PDF is not a job for SQL.** Some transformations need a real programming language.
2. **Personal data.** In pure ELT, raw personal data sits in your warehouse until it is transformed. We do hold it in bronze and silver (the policy says so), and we scrub it before anything reaches the search index or a model. The erasure workflow in episode 4 exists because of this choice.

## Tools you will meet (and why we do not use them here)
- **dbt** is the standard tool for the SQL "T" in ELT: your views and tables become tested, versioned files. We write two or three views by hand (`pipeline/elt.py`) so you see the idea first. Learn dbt after this course.
- **Spark, Kafka, Flink, Fivetran, Airbyte** exist for data too big for one machine, for streams that never stop, or for ready-made connectors to hundreds of systems. Our data is about 20 files, and the right tool is the one you can read in an afternoon.

## One-sentence summary to remember
Load first and keep the raw copy so you can always redo the work; transform in whatever language fits the job; scrub personal data before anything reaches a search index or a model.
