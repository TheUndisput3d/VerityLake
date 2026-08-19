from airflow.models import DagBag

bag = DagBag(dag_folder="/opt/airflow/dags", include_examples=False)
assert not bag.import_errors, bag.import_errors
assert "veritylake_scrape_to_rag" in bag.dags
pipeline = bag.dags["veritylake_scrape_to_rag"]
expected = ["initialize", "scrape", "bronze", "silver", "gold", "embed", "publish"]
assert set(pipeline.task_ids) == set(expected)
for previous, following in zip(expected, expected[1:]):
    assert pipeline.get_task(previous).downstream_task_ids == {following}
assert pipeline.max_active_runs == 1
print("Airflow DAG imports and the seven-stage dependency chain is valid.")
