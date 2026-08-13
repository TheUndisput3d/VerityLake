from __future__ import annotations

import json
from uuid import uuid4

from veritylake.storage import ObjectStore
from veritylake.util import json_bytes, utcnow, validate_run_id

ACTIVE_KEY = "catalog/active.json"


class NoActiveRelease(RuntimeError):
    pass


class InvalidRelease(RuntimeError):
    pass


class Publications:
    def __init__(self, store: ObjectStore):
        self.store = store

    def active(self) -> dict:
        value = self.store.maybe_json(ACTIVE_KEY)
        if value is None:
            raise NoActiveRelease("No dataset has passed the publication gate")
        return self.load(value["run_id"])

    def active_etag(self) -> str | None:
        value = self.store.get_versioned(ACTIVE_KEY)
        return value[1] if value else None

    def load(self, run_id: str) -> dict:
        validate_run_id(run_id)
        release = self.store.get_json(f"catalog/releases/{run_id}.json")
        self.validate(release)
        if release["run_id"] != run_id:
            raise InvalidRelease("Release ID mismatch")
        return release

    @staticmethod
    def validate(release: dict) -> None:
        if release.get("schema_version") != 1:
            raise InvalidRelease("Unsupported release schema")
        validate_run_id(release["run_id"])
        for stage in ("silver", "gold", "embed"):
            report = release.get("quality", {}).get(stage, {})
            checks = report.get("checks", [])
            if report.get("passed") is not True or not checks or not all(c.get("passed") is True for c in checks):
                raise InvalidRelease(f"Missing or failed {stage} quality evidence")
        if not release.get("embedding_identity", {}).get("digest"):
            raise InvalidRelease("Embedding model identity is missing")
        if release.get("vector_count", 0) != release.get("tables", {}).get("gold", {}).get("rows"):
            raise InvalidRelease("Vector and Gold row counts differ")
        if not release.get("collection") or release.get("vector_count", 0) < 1:
            raise InvalidRelease("No retrievable chunks")

    def publish(self, release: dict, expected_etag: str | None, actor: str = "pipeline") -> dict:
        self.validate(release)
        run_id = release["run_id"]
        key = f"catalog/releases/{run_id}.json"
        encoded = json_bytes(release)
        prior = self.store.get_versioned(key)
        if prior and prior[0] != encoded:
            raise InvalidRelease("A release manifest is immutable")
        if prior is None:
            self.store.compare_and_swap(key, encoded, None)
        current = self.store.maybe_json(ACTIVE_KEY)
        if current and current["run_id"] == run_id:
            return current  # idempotent retry after CAS committed but task acknowledgement failed
        return self._switch(run_id, expected_etag, actor, "publish")

    def rollback(self, run_id: str, actor: str = "operator") -> dict:
        self.load(run_id)  # only previously validated releases are eligible
        return self._switch(run_id, self.active_etag(), actor, "rollback")

    def _switch(self, run_id: str, expected_etag: str | None, actor: str, operation: str) -> dict:
        event_id = uuid4().hex
        marker = {"schema_version": 1, "run_id": run_id, "operation": operation, "actor": actor,
                  "operation_id": event_id, "changed_at": utcnow()}
        # Intent is durable before the atomic visibility point. An intent alone is not a successful publish.
        self.store.put_json(f"catalog/publication_intents/{event_id}.json", marker)
        self.store.compare_and_swap(ACTIVE_KEY, json_bytes(marker), expected_etag)
        return marker

    def history(self) -> list[dict]:
        return [json.loads(self.store.get(k)) for k in self.store.list_keys("catalog/releases/") if k.endswith(".json")]
