"""Trigger and measure a real Airflow DAG via its 3.2 public API. Requires a warm, idle stack."""
import argparse
import json
import os
import platform
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from envutil import local_env


def request(base, path, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--budget", type=float, default=300)
    parser.add_argument("--output", type=Path, default=Path("reports/airflow-benchmark.json"))
    args = parser.parse_args()
    env = local_env()
    auth = request(args.url, "/auth/token", "POST", {"username": "admin", "password": env["AIRFLOW_ADMIN_PASSWORD"]})
    token = auth["access_token"]
    dag = "/api/v2/dags/veritylake_scrape_to_rag/dagRuns"
    run_id = "benchmark_" + uuid4().hex
    started = time.monotonic()
    record = request(args.url, dag, "POST", {"dag_run_id": run_id, "logical_date": None,
                     "conf": {}, "note": "Measured warm full DAG; record machine and cache conditions separately."}, token)
    while record["state"] not in ("success", "failed"):
        if time.monotonic() - started > args.timeout:
            break
        time.sleep(2)
        record = request(args.url, dag + "/" + run_id, token=token)
    observed = time.monotonic() - started
    duration = record.get("duration")
    if duration is None and record.get("start_date") and record.get("end_date"):
        duration = (datetime.fromisoformat(record["end_date"]) - datetime.fromisoformat(record["start_date"])).total_seconds()
    report = {"measured_at": datetime.now(UTC).isoformat(), "dag_run_id": run_id,
              "state": record["state"], "airflow_duration_seconds": duration,
              "trigger_to_terminal_observed_seconds": observed, "budget_seconds": args.budget,
              "passed": record["state"] == "success" and observed <= args.budget,
              "cpu_count": os.cpu_count(), "platform": platform.platform(),
              "scope": "Real DAG including trigger/queue/poll overhead; excludes image/model downloads and bootstrap",
              "cache_condition": "Operator must record whether embedding cache was populated; not inferred",
              "limitations": "Host CPU count is not a CPU quota; a non-4-core runner is not a 4-core certification."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
