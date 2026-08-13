from __future__ import annotations

from datetime import UTC, datetime, timedelta

from veritylake.config import Settings
from veritylake.text import INSTRUCTION_PATTERNS, normalize
from veritylake.util import digest


class QualityError(RuntimeError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__("Data quality gate failed: " + ", ".join(c["name"] for c in report["checks"] if not c["passed"]))


def prepare_documents(rows: list[dict], settings: Settings) -> tuple[list[dict], list[dict]]:
    prepared, rejected = [], []
    now = datetime.now(UTC)
    for original in rows:
        doc = dict(original)
        doc["text"] = normalize(doc.get("text", ""), settings.redact_emails)
        doc["title"] = normalize(doc.get("title", ""), settings.redact_emails)
        reason = None
        if not doc["title"] or len(doc["text"]) < settings.min_text_chars:
            reason = "missing_title_or_short_text"
        elif settings.quarantine_instruction_patterns and INSTRUCTION_PATTERNS.search(doc["text"]):
            reason = "instruction_pattern"
        else:
            try:
                fetched = datetime.fromisoformat(doc["fetched_at"])
                if fetched.tzinfo is None:
                    raise ValueError("Missing timezone")
                if fetched > now + timedelta(minutes=5) or now - fetched > timedelta(hours=settings.max_source_age_hours):
                    reason = "stale_or_future_timestamp"
            except (ValueError, KeyError, TypeError):
                reason = "invalid_timestamp"
        if reason:
            rejected.append({"doc_id": doc.get("doc_id"), "url": doc.get("url"), "reason": reason})
        else:
            doc["content_sha256"] = digest(doc["text"])
            prepared.append(doc)
    return prepared, rejected


def silver_report(raw_count: int, rows: list[dict], rejected: list[dict], settings: Settings) -> dict:
    checks = [
        {"name": "minimum_documents", "passed": len(rows) >= settings.min_documents,
         "observed": len(rows), "threshold": settings.min_documents},
        {"name": "unique_document_ids", "passed": len({r["doc_id"] for r in rows}) == len(rows)},
        {"name": "unique_content", "passed": len({r["content_sha256"] for r in rows}) == len(rows)},
        {"name": "rejection_budget", "passed": len(rejected) / max(raw_count, 1) <= settings.max_reject_fraction,
         "observed": len(rejected) / max(raw_count, 1), "threshold": settings.max_reject_fraction},
        {"name": "not_empty", "passed": bool(rows)},
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "input_rows": raw_count,
            "output_rows": len(rows), "quarantined_rows": len(rejected),
            "deduplicated_rows": raw_count - len(rejected) - len(rows)}


def gold_report(chunks: list[dict], documents: list[dict], settings: Settings) -> dict:
    docs = {d["doc_id"]: d for d in documents}
    checks = [
        {"name": "bounded_chunk_count", "passed": 0 < len(chunks) <= settings.max_chunks,
         "observed": len(chunks), "threshold": settings.max_chunks},
        {"name": "unique_chunk_ids", "passed": len({c["chunk_id"] for c in chunks}) == len(chunks)},
        {"name": "document_coverage", "passed": {c["doc_id"] for c in chunks} == set(docs)},
        {"name": "exact_text_offsets", "passed": all(c["doc_id"] in docs and
            docs[c["doc_id"]]["text"][c["char_start"]:c["char_end"]] == c["text"] for c in chunks)},
        {"name": "chunk_text_size", "passed": all(0 < len(c["text"]) <= 12000 for c in chunks)},
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "output_rows": len(chunks)}


def enforce(report: dict) -> None:
    if not report["passed"]:
        raise QualityError(report)
