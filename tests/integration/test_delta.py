import pytest

pytest.importorskip("duckdb", reason="Native DuckDB not installed in this test environment")
pytest.importorskip("deltalake", reason="Native Delta library not installed in this test environment")
pytest.importorskip("pyarrow", reason="PyArrow not installed in this test environment")

from veritylake.tables import DeltaTables
from veritylake.quality import prepare_documents
from tests.helpers import document

pytestmark = pytest.mark.integration


def test_real_delta_roundtrip_and_duckdb_catalog(store, settings):
    tables = DeltaTables(store)
    rows, _ = prepare_documents([document(1), document(2)], settings)
    descriptor = tables.write("bronze/test/documents", rows, "documents")
    assert tables.read(descriptor) == rows
    assert descriptor["version"] == 0
    second = tables.write("bronze/test/documents", rows[:1], "documents")
    assert second["version"] == 1
    assert len(tables.read(descriptor)) == 2  # pinned historical version
    dedup = tables.deduplicate(rows + [dict(rows[0], doc_id="duplicate", url="https://z.example.org")])
    assert len(dedup) == 2
    catalog = tables.build_catalog("test", {"bronze": descriptor},
                {"silver": {"checks": [{"name": "fixture", "passed": True}]}})
    assert len(store.get(catalog["key"])) > 0
