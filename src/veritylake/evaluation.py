from __future__ import annotations

import json
import time
from pathlib import Path


def evaluate_retrieval(service, dataset: Path, top_k: int = 4) -> dict:
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    release = service.checked_release()
    rows = []
    for case in cases:
        expected = set(case["expected_urls"])
        if not expected:
            raise ValueError("Retrieval cases must provide expected_urls; use answer evaluation for unanswerable cases")
        started = time.monotonic()
        vector = service.embedder.embed([case["question"]], query=True)[0]
        hits = service.index.query(release["collection"], vector, top_k)
        urls = list(dict.fromkeys(h["url"] for h in hits))
        found = expected.intersection(urls)
        rank = next((i + 1 for i, url in enumerate(urls) if url in expected), None)
        rows.append({"id": case["id"], "recall_at_k": len(found) / len(expected),
                     "reciprocal_rank": 1 / rank if rank else 0, "retrieved_urls": urls,
                     "duration_seconds": time.monotonic() - started})
    return {"run_id": release["run_id"], "top_k": top_k, "cases": len(rows), "scope": "retrieval_only",
            "mean_recall_at_k": sum(r["recall_at_k"] for r in rows) / len(rows),
            "mrr": sum(r["reciprocal_rank"] for r in rows) / len(rows), "results": rows,
            "limitation": "A small hand-authored smoke set, not a representative production benchmark."}
