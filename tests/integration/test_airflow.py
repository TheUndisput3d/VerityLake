import pytest

pytest.importorskip("airflow", reason="Airflow is validated in its separate Docker image/job")
from airflow.models import DagBag

pytestmark = pytest.mark.integration


def test_real_airflow_dag_import_and_edges():
    bag = DagBag(dag_folder="dags", include_examples=False)
    assert not bag.import_errors
    dag = bag.dags["veritylake_scrape_to_rag"]
    order = ["initialize", "scrape", "bronze", "silver", "gold", "embed", "publish"]
    assert set(order) == set(dag.task_ids)
    for before, after in zip(order, order[1:]):
        assert dag.get_task(before).downstream_task_ids == {after}
