import pytest

from veritylake.config import Settings
from veritylake.pipeline import Pipeline
from veritylake.storage import LocalStore

from tests.helpers import FakeCrawler, FakeEmbedder, FakeIndex, FakeTables


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, environment="test", storage_backend="local", local_lake_dir=tmp_path / "lake",
                    max_pages=3, min_documents=2, max_fetches=10, min_text_chars=20,
                    api_key="k" * 48, source_adapter="generic", source_url="https://example.org/",
                    source_record_pattern=".*", allow_private_sources=True)


@pytest.fixture
def store(settings):
    return LocalStore(settings.local_lake_dir)


@pytest.fixture
def pipeline(settings, store):
    return Pipeline(settings, store=store, tables=FakeTables(), embedder=FakeEmbedder(),
                    index=FakeIndex(), crawler_factory=FakeCrawler)
