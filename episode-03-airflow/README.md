# Episode 3: Airflow from zero

Goal: run episodes 1 and 2 as a scheduled, retrying, observable workflow instead of commands you type.

## Concepts
- **Orchestrator.** A program that runs your steps in the right order, on a schedule, retries failures, and shows you what happened.
- **DAG.** A set of tasks and the order between them, with no loops (a directed acyclic graph). One DAG file here: `dags/dropline_ingest.py`.
- **Task, schedule, run.** A task is one step. The schedule says when to run. A run is one execution of the whole DAG with its own id (we store that id in the manifest, so every file traces to a run).
- **Retries.** `retries=2`, 20 seconds apart, for flaky network calls.
- **Idempotency matters more here.** Airflow may run a task again. Because landing and parsing are safe to repeat, a retry or a manual re-run cannot duplicate anything.
- **Data stays out of Airflow.** Tasks pass counts, not documents. The data lives in the lake and Postgres.
- **Quality stop.** The `run_checks` task fails the run if a blocking check fails. One of them is the reject rate: if more than half of the files are rejected, the run stops, so a broken feed cannot quietly produce an empty index.
- **The five parts.** In Airflow 3 the web UI and API (`airflow-api`), the scheduler, and the DAG processor are separate programs; here each is one container, with the metadata kept in a second database named `airflow` in the same Postgres.

## Run it
```bash
docker compose --profile airflow up -d --build     # first build downloads about 3 GB
# open http://127.0.0.1:8080  (local mode: no password; episode 9 turns real login on)
docker compose exec airflow-scheduler airflow dags unpause dropline_ingest
docker compose exec airflow-scheduler airflow dags trigger dropline_ingest
```
Watch the seven tasks go green: `migrate` -> `check_sources` -> `land_bronze` -> `build_silver` -> `curate` -> `run_checks` -> `build_index`.

Measured on the author's machine (2026-10-26): the five containers (database, data lake, web/API, scheduler, DAG processor) used about 1 GB of RAM (999 MiB); one full run took 1 min 10 s when the laptop was quiet and 2 min 18 s when it was busy.

## Exercises
1. Run it again from the UI. What do `land_bronze` and `build_silver` report now?
2. Put one corrupt file in `data/sources/uploads` and run. Does the reject-rate check fire? Add twenty-five corrupt files (measured: 27 of 49 rejected = 55%, limit 50%) and run again. With twenty it still passes: 22 of 44 is exactly 50%, not more.
3. Stop the `lake` container mid-run and watch retries. Start it again.
4. Change `catchup` to `True` and explain what Airflow would now do on the first start.

## Known limits
- `SIMPLE_AUTH_MANAGER_ALL_ADMINS=True` means anyone who can reach port 8080 is an admin. It is bound to localhost only; do not expose it.
- LocalExecutor runs tasks on one machine. Fine for this course; Celery or Kubernetes executors are for scaling out.
