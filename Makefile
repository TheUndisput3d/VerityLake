SHELL := /bin/bash
COMPOSE := docker compose
RUN_ID ?=
QUESTION ?= What is the listed price of A Light in the Attic?

.PHONY: init up down status logs models trigger run scrape etl embed publish catalog history rollback ask smoke benchmark evaluate install test lint format check dag-test observe backup restore
init:
	python3 scripts/bootstrap.py
up: init
	$(COMPOSE) up --build -d
down:
	$(COMPOSE) down
status:
	$(COMPOSE) ps
logs:
	$(COMPOSE) logs --tail=100 -f api airflow-scheduler
models:
	$(COMPOSE) run --rm model-init
trigger:
	$(COMPOSE) exec airflow-scheduler airflow dags trigger veritylake_scrape_to_rag
run:
	$(COMPOSE) run --rm tools run
scrape:
	@test -n "$(RUN_ID)" || (echo 'Set RUN_ID; first run: docker compose run --rm tools new-run'; exit 1)
	$(COMPOSE) run --rm tools stage scrape --run-id "$(RUN_ID)"
etl:
	@test -n "$(RUN_ID)" || (echo 'RUN_ID is required'; exit 1)
	$(COMPOSE) run --rm tools stage bronze --run-id "$(RUN_ID)"
	$(COMPOSE) run --rm tools stage silver --run-id "$(RUN_ID)"
	$(COMPOSE) run --rm tools stage gold --run-id "$(RUN_ID)"
embed:
	$(COMPOSE) run --rm tools stage embed --run-id "$(RUN_ID)"
publish:
	$(COMPOSE) run --rm tools stage publish --run-id "$(RUN_ID)"
catalog:
	$(COMPOSE) run --rm tools catalog
history:
	$(COMPOSE) run --rm tools history
rollback:
	@test -n "$(RUN_ID)" || (echo 'RUN_ID is required'; exit 1)
	$(COMPOSE) run --rm tools rollback --run-id "$(RUN_ID)"
ask:
	python3 scripts/ask.py "$(QUESTION)"
smoke:
	python3 scripts/smoke.py
benchmark:
	$(COMPOSE) run --rm tools run --output /work/reports/benchmark.json
evaluate:
	$(COMPOSE) run --rm tools evaluate --dataset /work/eval/retrieval.jsonl --output /work/reports/retrieval-evaluation.json
install:
	python3 -m pip install -r requirements-dev.txt -e .
test:
	python3 -m pytest --cov=veritylake --cov-report=term-missing
lint:
	python3 -m ruff check src tests dags scripts
format:
	python3 -m ruff check --fix src tests dags scripts
	python3 -m ruff format src tests dags scripts
check: lint test
	python3 scripts/check_static.py
dag-test:
	$(COMPOSE) run --rm --no-deps airflow-scheduler python /opt/veritylake/scripts/check_dag.py
observe:
	$(COMPOSE) --profile observability up -d prometheus grafana
backup:
	bash scripts/backup.sh
restore:
	@test -n "$(BACKUP)" || (echo 'BACKUP is required'; exit 1)
	bash scripts/restore.sh "$(BACKUP)"

serve:
	$(COMPOSE) up -d api

benchmark-airflow:
	python3 scripts/benchmark_airflow.py
