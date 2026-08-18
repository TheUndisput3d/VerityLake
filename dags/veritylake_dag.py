"""No database/network/model work at parse time. XComs carry only a run ID."""
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="veritylake_scrape_to_rag",
    description="Robots-aware source ingestion -> Delta medallion -> quality-gated RAG release",
    schedule="@once",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    is_paused_upon_creation=False,
    max_active_runs=1,
    max_active_tasks=1,
    dagrun_timeout=timedelta(minutes=20),
    default_args={"owner": "data-platform", "retries": 2, "retry_delay": timedelta(seconds=30),
                  "execution_timeout": timedelta(minutes=12)},
    tags=["lakehouse", "dataops", "rag", "governance"],
)
def veritylake_scrape_to_rag():
    @task
    def initialize() -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline

        context = get_current_context()
        pipeline_run_id = uuid5(NAMESPACE_URL, "veritylake:" + context["run_id"]).hex
        return Pipeline(Settings()).new_run(pipeline_run_id)

    @task
    def scrape(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).scrape(pipeline_run_id)
        return pipeline_run_id

    @task
    def bronze(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).bronze(pipeline_run_id)
        return pipeline_run_id

    @task
    def silver(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).silver(pipeline_run_id)
        return pipeline_run_id

    @task
    def gold(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).gold(pipeline_run_id)
        return pipeline_run_id

    @task
    def embed(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).embed(pipeline_run_id)
        return pipeline_run_id

    @task
    def publish(pipeline_run_id: str) -> str:
        from veritylake.config import Settings
        from veritylake.pipeline import Pipeline
        Pipeline(Settings()).publish(pipeline_run_id)
        return pipeline_run_id

    pipeline_run_id = initialize()
    scraped = scrape(pipeline_run_id)
    bronze_id = bronze(scraped)
    silver_id = silver(bronze_id)
    gold_id = gold(silver_id)
    embedded = embed(gold_id)
    publish(embedded)


veritylake_scrape_to_rag()
