import json
from uuid import UUID, uuid4

import pytest

from veritylake.publication import InvalidRelease, NoActiveRelease, Publications
from veritylake.quality import QualityError
from veritylake.storage import ConflictError
from tests.helpers import valid_release


def test_no_release_before_gate(store):
    with pytest.raises(NoActiveRelease):
        Publications(store).active()


def test_publish_is_idempotent_and_release_immutable(store):
    manager = Publications(store)
    release = valid_release(uuid4().hex)
    marker = manager.publish(release, None)
    assert manager.publish(release, None) == marker
    changed = dict(release, vector_count=2)
    with pytest.raises(InvalidRelease):
        manager.publish(changed, manager.active_etag())


def test_concurrent_publish_rejects_stale_writer(store):
    manager = Publications(store)
    first, second = valid_release(uuid4().hex), valid_release(uuid4().hex)
    manager.publish(first, None)
    with pytest.raises(ConflictError):
        manager.publish(second, None)
    assert manager.active()["run_id"] == first["run_id"]


def test_rollback_to_validated_release(store):
    manager = Publications(store)
    first, second = valid_release(uuid4().hex), valid_release(uuid4().hex)
    manager.publish(first, None)
    manager.publish(second, manager.active_etag())
    manager.rollback(first["run_id"])
    assert manager.active()["run_id"] == first["run_id"]


@pytest.mark.parametrize("stage", ["silver", "gold", "embed"])
def test_bad_quality_cannot_be_published(store, stage):
    release = valid_release(uuid4().hex)
    release["quality"][stage]["checks"][0]["passed"] = False
    with pytest.raises(InvalidRelease):
        Publications(store).publish(release, None)


def test_pipeline_fixture_runs_all_stages_with_lineage(pipeline, store):
    report = pipeline.run()
    release = pipeline.publications.active()
    assert release["run_id"] == report["run_id"]
    assert release["tables"]["silver"]["rows"] == 3
    assert release["vector_count"] == release["tables"]["gold"]["rows"]
    events = [store.get_json(k) for k in store.list_keys("lineage/")]
    assert len(events) == 12
    assert {e["eventType"] for e in events} == {"START", "COMPLETE"}
    for event in events:
        assert UUID(event["run"]["runId"])
        assert event["job"]["namespace"] == "veritylake"
    # This test does not use Delta, DuckDB, Chroma, network or a real LLM.


def test_retry_does_not_repeat_embeddings(pipeline):
    first = pipeline.run()
    before = pipeline.embedder.calls
    pipeline.run(first["run_id"])
    assert pipeline.embedder.calls == before


def test_cross_run_embedding_cache(pipeline):
    pipeline.run()
    before = pipeline.embedder.calls
    second = pipeline.run()
    assert pipeline.embedder.calls == before
    assert pipeline.result(second["run_id"], "embed")["cache_hits"] > 0


def test_failed_silver_preserves_previous_publication(pipeline, settings, store):
    first = pipeline.run()
    settings.min_text_chars = 5000
    second = pipeline.new_run()
    pipeline.scrape(second)
    pipeline.bronze(second)
    with pytest.raises(QualityError):
        pipeline.silver(second)
    assert pipeline.publications.active()["run_id"] == first["run_id"]
    assert store.get_json(f"runs/{second}/stages/silver.json")["status"] == "failed"
    events = [json.loads(store.get(k)) for k in store.list_keys(f"lineage/{second}/silver/")]
    assert {e["eventType"] for e in events} == {"START", "FAIL"}


def test_configuration_drift_refuses_resume(pipeline, settings):
    run_id = pipeline.new_run()
    settings.chunk_words += 1
    with pytest.raises(ValueError):
        pipeline.scrape(run_id)


def test_embedding_model_drift_blocks_rollback(pipeline):
    result = pipeline.run()
    pipeline.embedder.model_digest = "new-model"
    with pytest.raises(RuntimeError):
        pipeline.rollback(result["run_id"])
