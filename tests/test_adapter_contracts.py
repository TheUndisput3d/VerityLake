"""SDK/request contracts without external services. These are not live integration tests."""
import io
import json
import sys
from unittest.mock import Mock

import boto3
import httpx
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from veritylake import cli
from veritylake.evaluation import evaluate_retrieval
from veritylake.rag import OllamaGenerator
from veritylake.storage import ConflictError, S3Store
from veritylake.vectors import ChromaIndex
from tests.helpers import FakeEmbedder, document
from veritylake.text import chunk_document


def s3(settings):
    client = boto3.client("s3", endpoint_url="http://localhost:9000", region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test-only")
    return S3Store(settings, client), Stubber(client)


def test_s3_conditional_first_publish_request(settings):
    store, stub = s3(settings)
    stub.add_response("put_object", {"ETag": '"one"'},
        {"Bucket": settings.s3_bucket, "Key": "catalog/active.json", "Body": b"{}",
         "ContentType": "application/json", "IfNoneMatch": "*"})
    with stub:
        assert store.compare_and_swap("catalog/active.json", b"{}", None) == '"one"'
        stub.assert_no_pending_responses()


def test_s3_conditional_update_request(settings):
    store, stub = s3(settings)
    stub.add_response("put_object", {"ETag": '"two"'},
        {"Bucket": settings.s3_bucket, "Key": "catalog/active.json", "Body": b"{}",
         "ContentType": "application/json", "IfMatch": '"one"'})
    with stub:
        assert store.compare_and_swap("catalog/active.json", b"{}", '"one"') == '"two"'


@pytest.mark.parametrize("code,status", [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)])
def test_s3_lost_update_fails_closed(settings, code, status):
    store, stub = s3(settings)
    stub.add_client_error("put_object", service_error_code=code, http_status_code=status)
    with stub, pytest.raises(ConflictError):
        store.compare_and_swap("catalog/active.json", b"{}", '"stale"')


def test_s3_reads_body_and_preserves_quoted_etag(settings):
    store, stub = s3(settings)
    body = StreamingBody(io.BytesIO(b"hello"), 5)
    stub.add_response("get_object", {"ETag": '"etag"', "Body": body},
                      {"Bucket": settings.s3_bucket, "Key": "catalog/data"})
    with stub:
        assert store.get_versioned("catalog/data") == (b"hello", '"etag"')
        assert body._raw_stream.closed


def test_s3_missing_key_is_not_an_error(settings):
    store, stub = s3(settings)
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    with stub:
        assert store.get_versioned("catalog/missing") is None


def test_s3_delta_options_require_aws_locking(settings):
    settings.s3_endpoint_url = None
    store, _ = s3(settings)
    with pytest.raises(ValueError, match="DELTA_LOCK_TABLE"):
        store.delta_options()
    settings.delta_lock_table = "veritylake-test-locks"
    assert store.delta_options()["AWS_S3_LOCKING_PROVIDER"] == "dynamodb"
    assert "AWS_S3_ALLOW_UNSAFE_RENAME" not in store.delta_options()


def test_minio_delta_options_conditional_put(settings):
    store, _ = s3(settings)
    assert store.delta_options()["conditional_put"] == "etag"
    assert store.delta_options()["AWS_ALLOW_HTTP"] == "true"


def test_chroma_explicit_embedding_contract(settings):
    chunks = chunk_document(document())
    identity = FakeEmbedder().identity()
    collection = Mock()
    collection.metadata = {"embedding_digest": identity["digest"], "dimension": 2}
    collection.count.return_value = 1
    collection.query.return_value = {"ids": [["c1"]], "documents": [["evidence"]],
                                     "metadatas": [[{"url": "https://example.org"}]], "distances": [[0.2]]}
    client = Mock()
    client.get_or_create_collection.return_value = collection
    client.get_collection.return_value = collection
    index = ChromaIndex(settings, client)
    index.write("vl_test", chunks, [[0.2, 0.8]] * len(chunks), identity)
    kwargs = client.get_or_create_collection.call_args.kwargs
    assert kwargs["embedding_function"] is None
    assert kwargs["configuration"]["hnsw"]["space"] == "cosine"
    assert collection.upsert.call_args.kwargs["ids"] == [c["chunk_id"] for c in chunks]
    assert index.query("vl_test", [0.2, 0.8], 99)[0]["id"] == "c1"
    assert collection.query.call_args.kwargs["n_results"] == 1
    index.health()
    client.heartbeat.assert_called_once()


def test_chroma_rejects_embedding_space_mismatch(settings):
    client = Mock()
    client.get_or_create_collection.return_value.metadata = {"embedding_digest": "wrong", "dimension": 2}
    with pytest.raises(ValueError, match="another embedding space"):
        ChromaIndex(settings, client).write("vl_test", chunk_document(document()), [[0.5, 0.2]], FakeEmbedder().identity())


def test_generation_uses_local_chat_and_structured_output(settings):
    seen = []
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": settings.llm_model}]})
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"message": {"content": json.dumps(
            {"answer": "Not enough evidence", "abstain": True, "citations": []})}})
    generator = OllamaGenerator(settings, httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(handler)))
    generator.health()
    assert generator.generate("Question?", []).abstain
    assert seen[0]["model"] == settings.llm_model
    assert seen[0]["format"]["type"] == "object"
    assert seen[0]["stream"] is False and seen[0]["think"] is False


def test_generation_adds_declared_marker_when_local_model_omits_it(settings):
    payload = {"answer": "The listed price is GBP 10.00.", "abstain": False,
               "citations": [{"source_id": "S1", "quote": "The listed price is GBP 10.00"}]}
    client = httpx.Client(base_url="http://ollama", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"message": {"content": json.dumps(payload)}})))
    generated = OllamaGenerator(settings, client).generate("Price?", [])
    assert generated.answer == "The listed price is GBP 10.00. [S1]"


def test_retrieval_evaluation_counts_document_rank(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps({"id": "one", "question": "q", "expected_urls": ["b", "c"]}) + "\n")
    service = Mock()
    service.checked_release.return_value = {"run_id": "run", "collection": "col"}
    service.embedder.embed.return_value = [[1.0, 0.0]]
    service.index.query.return_value = [{"url": "a"}, {"url": "a"}, {"url": "b"}]
    result = evaluate_retrieval(service, dataset)
    assert result["mean_recall_at_k"] == 0.5 and result["mrr"] == 0.5
    assert result["scope"] == "retrieval_only"


def test_empty_evaluation_refuses_fake_score(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    with pytest.raises(ValueError, match="empty"):
        evaluate_retrieval(Mock(), path)


@pytest.mark.parametrize("command", ["new-run", "run", "catalog", "history"])
def test_cli_commands_use_real_pipeline_interface(command, pipeline, settings, monkeypatch, capsys):
    if command in ("catalog", "history"):
        pipeline.run()
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    monkeypatch.setattr(cli, "Pipeline", lambda _: pipeline)
    monkeypatch.setattr(sys, "argv", ["veritylake", command])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result is not None
    if command == "run":
        assert result["timing_scope"].startswith("CLI pipeline only")
        assert "warm_cli_pipeline_under_300_seconds" in result


def test_pipeline_preserves_original_html_bytes(pipeline, store):
    original = pipeline.crawler_factory
    class RawBytesCrawler(original):
        def crawl(self):
            result = super().crawl()
            result["pages"][0]["raw_html"] = b"<p>\xc2\xa3 original bytes</p>"
            return result
    pipeline.crawler_factory = RawBytesCrawler
    run = pipeline.new_run()
    pipeline.scrape(run)
    doc_id = document(1)["doc_id"]
    assert store.get(f"raw/{run}/pages/{doc_id}.html") == b"<p>\xc2\xa3 original bytes</p>"


def test_lineage_durable_before_completed_stage(pipeline, store, monkeypatch):
    original = store.put_json
    def checked_put(key, value):
        if key.endswith("/stages/scrape.json") and value["status"] == "complete":
            events = [store.get_json(k) for k in store.list_keys("lineage/")]
            assert any(e["eventType"] == "COMPLETE" for e in events)
        return original(key, value)
    monkeypatch.setattr(store, "put_json", checked_put)
    pipeline.scrape(pipeline.new_run())
