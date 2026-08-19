#!/usr/bin/env python3
"""Live smoke check. Requires the real Docker stack, downloaded models and a published release."""
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from envutil import local_env


def main():
    env = local_env()
    base = "http://127.0.0.1:8000"
    checks = {}
    for path in ("/healthz", "/readyz", "/catalog"):
        req = urllib.request.Request(base + path, headers={"X-API-Key": env["API_KEY"]})
        with urllib.request.urlopen(req, timeout=30) as response:
            checks[path] = json.load(response)
    req = urllib.request.Request(base + "/ask", method="POST", headers={"X-API-Key": env["API_KEY"], "Content-Type": "application/json"},
        data=json.dumps({"question": "What is the listed price of A Light in the Attic?", "top_k": 4}).encode())
    with urllib.request.urlopen(req, timeout=240) as response:
        answer = json.load(response)
    checks["/ask"] = answer
    checks["timestamp"] = datetime.now(UTC).isoformat()
    checks["passed"] = answer["status"] == "answered" and len(answer["sources"]) > 0
    path = Path(__file__).resolve().parents[1] / "reports/runtime/live-smoke.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks, indent=2))
    if not checks["passed"]:
        raise SystemExit("Live answer smoke test did not pass; inspect retrieval/model behavior, not just service health")


if __name__ == "__main__":
    main()
