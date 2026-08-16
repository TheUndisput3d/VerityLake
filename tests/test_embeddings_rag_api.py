import json
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from veritylake.api import RequestBudget, create_app
from veritylake.embeddings import EmbeddingCache, ModelUnavailable, OllamaEmbedder, validate_vectors
from veritylake.publication import Publications
from veritylake.rag import Citation, GeneratedAnswer, RAGService, validate_citations
from tests.helpers import FakeEmbedder, valid_release


@pytest.mark.parametrize("vectors,count", [([], 1), ([[0.0, 0.0]], 1), ([[float('nan')]], 1),
                                           ([[1.0], [1.0, 2.0]], 2), ([[1.0]], 2), ([[float('inf')]], 1)])
def test_embedding_contract_rejects_bad_vectors(vectors, count):
    with pytest.raises(ValueError):
        validate_vectors(vectors, count)


def test_ollama_http_contract(settings):
    seen = []
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": settings.embedding_model, "digest": "sha"}]})
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.8]] * len(body["input"])})
    client = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(handler))
    encoder = OllamaEmbedder(settings, client)
    assert encoder.identity()["digest"] == "sha"
    encoder.embed(["document"])
    encoder.embed(["question"], query=True)
    assert seen[0]["input"] == ["search_document: document"]
    assert seen[1]["input"] == ["search_query: question"]
    assert seen[0]["truncate"] is False


def test_embedding_cache_key_includes_model_digest(store):
    encoder = FakeEmbedder()
    cache = EmbeddingCache(store, encoder, 1)
    a, stats = cache.encode(["one", "two"], encoder.identity())
    assert stats["cache_misses"] == 2
    b, stats = cache.encode(["one", "two"], encoder.identity())
    assert a == b and stats["cache_hits"] == 2
    encoder.model_digest = "changed"
    _, stats = cache.encode(["one", "two"], encoder.identity())
    assert stats["cache_misses"] == 2


def source():
    return {"source_id": "S1", "id": "chunk1", "doc_id": "doc1", "title": "A Book", "url": "https://example.org/a",
            "text": "The listed price of the book is GBP 10.00 and it is in stock.", "char_start": 0,
            "char_end": 61, "fetched_at": "2026-09-18T00:00:00+00:00", "distance": 0.1}


def test_valid_citation_and_quote():
    generated = GeneratedAnswer(answer="The listed price is GBP 10.00 [S1].", abstain=False,
        citations=[Citation(source_id="S1", quote="The listed price of the book is GBP 10.00")])
    assert validate_citations(generated, [source()])[0].url == "https://example.org/a"


@pytest.mark.parametrize("text,cid,quote", [
    ("Price is 10 [S9]", "S9", "The listed price"),
    ("Price is 10 [S1]", "S1", "The book costs GBP 500.00"),
    ("Price is 10", "S1", "The listed price"),
])
def test_fabricated_citations_rejected(text, cid, quote):
    with pytest.raises(ValueError):
        validate_citations(GeneratedAnswer(answer=text, citations=[Citation(source_id=cid, quote=quote)], abstain=False), [source()])


class Index:
    distance = 0.1
    def count(self, name):
        return 1
    def query(self, name, vector, top_k):
        return [dict(source(), distance=self.distance)]


class Generator:
    bad = False
    def health(self):
        pass
    def generate(self, question, sources):
        return GeneratedAnswer(answer="It costs GBP 10.00 [S1].", abstain=False,
            citations=[Citation(source_id="S1", quote="not present in the evidence" if self.bad else "The listed price of the book is GBP 10.00")])


def service(settings, store):
    pubs = Publications(store)
    pubs.publish(valid_release(uuid4().hex), None)
    return RAGService(settings, pubs, FakeEmbedder(), Index(), Generator())


def test_rag_abstains_on_bad_citation(settings, store):
    rag = service(settings, store)
    rag.generator.bad = True
    result = rag.ask("Price?")
    assert result.status == "abstained" and result.reason == "citation_validation_failed"


def test_rag_abstains_when_no_relevant_hit(settings, store):
    rag = service(settings, store)
    rag.index.distance = 1.8
    assert rag.ask("unrelated").reason == "insufficient_retrieval"


def test_model_drift_is_not_silently_mixed(settings, store):
    rag = service(settings, store)
    rag.embedder.model_digest = "different"
    with pytest.raises(ModelUnavailable):
        rag.ask("Price?")


def test_api_auth_query_bounds_and_citations(settings, store):
    with TestClient(create_app(settings, service(settings, store))) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/ask", params={"question": "price"}).status_code == 401
        headers = {"X-API-Key": settings.api_key.get_secret_value()}
        assert client.get("/ask", params={"question": "price", "top_k": 99}, headers=headers).status_code == 422
        response = client.post("/ask", json={"question": "Price?"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "answered"
        assert response.json()["sources"][0]["source_id"] == "S1"
        assert "X-Request-ID" in response.headers
        assert client.get("/catalog", headers=headers).status_code == 200
        assert client.get("/readyz").status_code == 200
        assert "veritylake_answers_total" in client.get("/metrics").text
        assert client.get("/").status_code == 200


def test_budget_enforces_rate_and_concurrency():
    now = [0.0]
    budget = RequestBudget(1, 1, clock=lambda: now[0])
    budget.acquire()
    with pytest.raises(HTTPException) as error:
        budget.acquire()
    assert error.value.status_code == 429
    budget.release()
    now[0] = 61
    budget.acquire()
    budget.release()


def test_api_whitespace_and_long_question(settings, store):
    with TestClient(create_app(settings, service(settings, store))) as client:
        headers = {"X-API-Key": settings.api_key.get_secret_value()}
        assert client.post("/ask", json={"question": "  "}, headers=headers).status_code == 422
        assert client.post("/ask", json={"question": "x" * 1001}, headers=headers).status_code == 422
