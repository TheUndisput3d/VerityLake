"""Real MinIO + Delta + DuckDB + Chroma, deterministic model double. Opt in explicitly."""
import os
import time
from uuid import uuid4

import pytest

if os.environ.get("RUN_SERVICE_TESTS") != "1":
    pytest.skip("Set RUN_SERVICE_TESTS=1 and start the CI storage stack", allow_module_level=True)
pytest.importorskip("duckdb")
pytest.importorskip("deltalake")
pytest.importorskip("chromadb")

from veritylake.config import Settings
from veritylake.pipeline import Pipeline
from veritylake.storage import S3Store
from tests.helpers import FakeCrawler, FakeEmbedder

pytestmark = [pytest.mark.integration, pytest.mark.service]


def test_real_object_store_delta_and_vector_publication():
    import httpx

    for _ in range(60):
        try:
            httpx.get("http://127.0.0.1:8002/api/v2/heartbeat", timeout=2).raise_for_status()
            break
        except httpx.HTTPError:
            time.sleep(2)
    else:
        pytest.fail("Chroma service did not become ready")
    settings = Settings(_env_file=None, environment="test", s3_endpoint_url="http://127.0.0.1:9000",
        s3_bucket="veritylake-test-" + uuid4().hex[:12],
        aws_access_key_id=os.environ["MINIO_ROOT_USER"], aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        chroma_host="127.0.0.1", chroma_port=8002,
        max_pages=3, min_documents=2, max_fetches=10, min_text_chars=20)
    store = S3Store(settings)
    store.ensure_bucket()
    pipeline = Pipeline(settings, store=store, embedder=FakeEmbedder(), crawler_factory=FakeCrawler)
    report = pipeline.run()
    release = pipeline.publications.active()
    assert release["run_id"] == report["run_id"]
    assert len(pipeline.tables.read(release["tables"]["gold"])) == release["vector_count"]
    assert pipeline.index.count(release["collection"]) == release["vector_count"]
    assert release["catalog"]["uri"].startswith("s3://")
