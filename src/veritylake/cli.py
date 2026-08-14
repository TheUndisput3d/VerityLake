from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path

from veritylake.config import Settings
from veritylake.logging import configure
from veritylake.pipeline import STAGES, Pipeline
from veritylake.storage import S3Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="veritylake")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-store")
    commands.add_parser("new-run")
    run = commands.add_parser("run")
    run.add_argument("--run-id")
    run.add_argument("--output", type=Path)
    stage = commands.add_parser("stage")
    stage.add_argument("stage", choices=STAGES)
    stage.add_argument("--run-id", required=True)
    commands.add_parser("catalog")
    commands.add_parser("history")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--run-id", required=True)
    download = commands.add_parser("download-catalog")
    download.add_argument("--output", type=Path, default=Path("catalog.duckdb"))
    verify = commands.add_parser("verify-release")
    verify.add_argument("--run-id")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--dataset", type=Path, default=Path("eval/retrieval.jsonl"))
    evaluate.add_argument("--output", type=Path, default=Path("reports/retrieval-evaluation.json"))
    evaluate.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    settings = Settings()
    configure(settings.log_format)
    pipeline = Pipeline(settings)
    if args.command == "init-store":
        if isinstance(pipeline.store, S3Store):
            pipeline.store.ensure_bucket()
        output = {"status": "initialized"}
    elif args.command == "new-run":
        output = {"run_id": pipeline.new_run()}
    elif args.command == "run":
        output = pipeline.run(args.run_id)
        output["host"] = {"cpu_count": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version()}
        output["warm_cli_pipeline_under_300_seconds"] = output["duration_seconds"] <= 300
        output["timing_scope"] = "CLI pipeline only; excludes downloads, image builds and Airflow scheduling"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, indent=2))
    elif args.command == "stage":
        output = getattr(pipeline, args.stage)(args.run_id)
    elif args.command == "catalog":
        output = pipeline.publications.active()
    elif args.command == "history":
        output = pipeline.publications.history()
    elif args.command == "rollback":
        output = pipeline.rollback(args.run_id)
    elif args.command == "download-catalog":
        release = pipeline.publications.active()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(pipeline.store.get(release["catalog"]["key"]))
        output = {"saved_to": str(args.output)}
    elif args.command == "verify-release":
        release = pipeline.publications.load(args.run_id) if args.run_id else pipeline.publications.active()
        checks = {"gold_rows": len(pipeline.tables.read(release["tables"]["gold"])) == release["vector_count"],
                  "vector_rows": pipeline.index.count(release["collection"]) == release["vector_count"],
                  "embedding_identity": pipeline.embedder.identity() == release["embedding_identity"]}
        output = {"run_id": release["run_id"], "checks": checks, "passed": all(checks.values())}
        if not output["passed"]:
            print(json.dumps(output, indent=2))
            raise SystemExit(1)
    else:
        from veritylake.evaluation import evaluate_retrieval
        from veritylake.rag import OllamaGenerator, RAGService

        service = RAGService(settings, pipeline.publications, pipeline.embedder, pipeline.index, OllamaGenerator(settings))
        output = evaluate_retrieval(service, args.dataset, args.top_k)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
