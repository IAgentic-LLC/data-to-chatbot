# Needs `make` (macOS/Linux, or Git Bash / WSL on Windows). Every target is one plain command you can also copy and run yourself.
.PHONY: sources test up down land silver curate checks index promote status reset airflow-up airflow-down
sources: ; python scripts/generate_sources.py
test:    ; python -m pytest -q
up:      ; docker compose up -d
down:    ; docker compose down
land:    ; python -m pipeline.cli land
silver:  ; python -m pipeline.cli silver
curate:  ; python -m pipeline.cli curate
checks:  ; python -m pipeline.cli checks
index:   ; python -m pipeline.index_cli build
status:  ; python -m pipeline.cli status
reset:   ; python -m pipeline.cli reset-db
airflow-up:   ; docker compose --profile airflow up -d --build
airflow-down: ; docker compose --profile airflow down
