import pytest

pytest.importorskip("chromadb", reason="Native Chroma not installed in this test environment")

from veritylake.vectors import ChromaIndex
from veritylake.text import chunk_document
from tests.helpers import FakeEmbedder, document

pytestmark = pytest.mark.integration


def test_real_persistent_chroma_roundtrip(settings, tmp_path):
    settings.chroma_mode = "local"
    settings.chroma_dir = tmp_path / "chroma"
    index = ChromaIndex(settings)
    chunks = chunk_document(document())
    encoder = FakeEmbedder()
    vectors = encoder.embed([c["text"] for c in chunks])
    index.write("fixture_collection", chunks, vectors, encoder.identity())
    assert index.count("fixture_collection") == len(chunks)
    assert index.query("fixture_collection", vectors[0], 1)[0]["id"] == chunks[0]["chunk_id"]
    reopened = ChromaIndex(settings)
    assert reopened.count("fixture_collection") == len(chunks)
