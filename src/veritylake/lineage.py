from __future__ import annotations

import logging
from contextlib import contextmanager
from uuid import UUID, uuid4, uuid5

import httpx

from veritylake.storage import ObjectStore
from veritylake.util import utcnow

log = logging.getLogger(__name__)
SCHEMA = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/definitions/RunEvent"
PRODUCER = "urn:veritylake:python:0.1.0"


class Lineage:
    def __init__(self, store: ObjectStore, endpoint: str | None = None):
        self.store, self.endpoint = store, endpoint

    def emit(self, pipeline_id: str, attempt: str, stage: str, event_type: str,
             inputs: list[str], outputs: list[str], error_type: str | None = None) -> dict:
        event = {
            "eventType": event_type, "eventTime": utcnow(), "producer": PRODUCER, "schemaURL": SCHEMA,
            "run": {"runId": attempt, "facets": {"parent": {
                "_producer": PRODUCER,
                "_schemaURL": "https://openlineage.io/spec/facets/1-0-1/ParentRunFacet.json#/$defs/ParentRunFacet",
                "run": {"runId": str(UUID(hex=pipeline_id))},
                "job": {"namespace": "veritylake", "name": "scrape_to_rag"},
            }}},
            "job": {"namespace": "veritylake", "name": stage},
            "inputs": [{"namespace": "veritylake", "name": item} for item in inputs],
            "outputs": [{"namespace": "veritylake", "name": item} for item in outputs],
        }
        if error_type:
            event["run"]["facets"]["errorMessage"] = {
                "_producer": PRODUCER,
                "_schemaURL": "https://openlineage.io/spec/facets/1-0-1/ErrorMessageRunFacet.json#/$defs/ErrorMessageRunFacet",
                "message": error_type, "programmingLanguage": "python",
            }
        key = f"lineage/{pipeline_id}/{stage}/{attempt}/{event_type.lower()}.json"
        # Durable local/S3 lineage is mandatory. Remote delivery is best effort and replayable.
        self.store.put_json(key, event)
        if self.endpoint:
            try:
                with httpx.Client(timeout=5, trust_env=False) as client:
                    client.post(self.endpoint.rstrip("/") + "/api/v1/lineage", json=event).raise_for_status()
            except httpx.HTTPError:
                log.warning("remote_lineage_delivery_failed", extra={"fields": {"object_key": key}})
        return event

    @contextmanager
    def stage(self, pipeline_id: str, stage: str, inputs: list[str], outputs: list[str]):
        attempt = str(uuid5(UUID(hex=pipeline_id), f"{stage}:{uuid4()}"))
        self.emit(pipeline_id, attempt, stage, "START", inputs, outputs)
        try:
            yield
        except Exception as exc:
            self.emit(pipeline_id, attempt, stage, "FAIL", inputs, outputs, type(exc).__name__)
            raise
        else:
            self.emit(pipeline_id, attempt, stage, "COMPLETE", inputs, outputs)
