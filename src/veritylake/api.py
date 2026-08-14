from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from importlib.resources import files
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from veritylake.config import Settings
from veritylake.embeddings import OllamaEmbedder
from veritylake.logging import configure
from veritylake.publication import Publications
from veritylake.rag import AskResponse, OllamaGenerator, RAGService
from veritylake.storage import make_store
from veritylake.vectors import ChromaIndex

log = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=4, ge=1, le=10)


class RequestBudget:
    """Single-process limits. A shared gateway is required before horizontally scaling this policy."""
    def __init__(self, rate: int, concurrent: int, clock=time.monotonic):
        self.rate, self.clock = rate, clock
        self.timestamps: deque[float] = deque()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(concurrent)

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            while self.timestamps and self.timestamps[0] <= now - 60:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.rate:
                raise HTTPException(429, "Per-minute request budget exceeded", headers={"Retry-After": "60"})
            if not self.slots.acquire(blocking=False):
                raise HTTPException(429, "Generation capacity is busy", headers={"Retry-After": "5"})
            self.timestamps.append(now)

    def release(self) -> None:
        self.slots.release()


def create_app(settings: Settings | None = None, service: RAGService | None = None) -> FastAPI:
    settings = settings or Settings()
    configure(settings.log_format)
    key = settings.api_key.get_secret_value()
    if len(key) < 32:
        raise RuntimeError("Set a random API_KEY (32+ characters). Run python3 scripts/bootstrap.py.")
    owns_service = service is None
    if service is None:
        service = RAGService(settings, Publications(make_store(settings)), OllamaEmbedder(settings),
                             ChromaIndex(settings), OllamaGenerator(settings))
    rag = service

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if owns_service:
            rag.embedder.close()
            rag.generator.close()

    app = FastAPI(title="VerityLake", version="0.1.0", lifespan=lifespan,
                  description="Local, evidence-aware RAG over quality-gated lakehouse releases.")
    registry = CollectorRegistry()
    requests = Counter("veritylake_http_requests_total", "HTTP requests", ["route", "method", "status"], registry=registry)
    duration = Histogram("veritylake_http_duration_seconds", "HTTP latency", ["route"],
                         buckets=(0.1, 0.5, 1, 5, 15, 30, 60, 120, 240), registry=registry)
    answers = Counter("veritylake_answers_total", "RAG answer outcomes", ["status", "reason"], registry=registry)
    ready = Gauge("veritylake_ready", "Result of the last readiness probe (1=ready)", registry=registry)
    published = Gauge("veritylake_dataset_created_timestamp_seconds", "Active dataset creation time", registry=registry)
    chunk_count = Gauge("veritylake_active_chunks", "Published vector count", registry=registry)
    budget = RequestBudget(settings.requests_per_minute, settings.max_concurrent_requests)
    app.state.rag = rag
    app.state.budget = budget

    def auth(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not secrets.compare_digest(x_api_key, key):
            raise HTTPException(401, "A valid X-API-Key is required")

    @app.middleware("http")
    async def observe(request: Request, call_next):
        request_id, started = uuid4().hex, time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
            if request.url.path == "/" or request.url.path.startswith("/static"):
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                    "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
                )
            return response
        finally:
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", "unmatched")
            elapsed = time.monotonic() - started
            requests.labels(route, request.method, str(status)).inc()
            duration.labels(route).observe(elapsed)
            if route not in ("/metrics", "/healthz"):
                log.info("http_request", extra={"fields": {"request_id": request_id, "route": route,
                         "method": request.method, "status": status, "duration_seconds": elapsed}})

    @app.get("/healthz")
    def health():
        return {"status": "alive", "version": "0.1.0"}

    @app.get("/readyz")
    def readiness():
        try:
            result = rag.ready()
            ready.set(1)
            return result
        except Exception as exc:
            ready.set(0)
            log.warning("readiness_failed", extra={"fields": {"error_type": type(exc).__name__}})
            raise HTTPException(503, "Dataset or model dependency is not ready") from exc

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        try:
            release = rag.publications.active()
            published.set(datetime.fromisoformat(release["created_at"]).timestamp())
            chunk_count.set(release["vector_count"])
            # Readiness is updated by readiness probes, not by this cheap scrape.
        except Exception:
            published.set(0)
            chunk_count.set(0)
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/catalog", dependencies=[Depends(auth)])
    def catalog():
        try:
            release = rag.publications.active()
            return {k: release[k] for k in ("run_id", "created_at", "published_at", "source_url", "source_terms_note",
                                            "tables", "quality", "catalog", "embedding_identity", "vector_count", "git_sha")}
        except Exception as exc:
            raise HTTPException(503, "No usable catalog release") from exc

    def answer(question: str, top_k: int) -> AskResponse:
        if not question.strip():
            raise HTTPException(422, "Question must not be blank")
        budget.acquire()
        try:
            result = rag.ask(question.strip(), top_k)
            answers.labels(result.status, result.reason or "none").inc()
            return result
        except Exception as exc:
            log.warning("rag_dependency_failure", extra={"fields": {"error_type": type(exc).__name__}})
            raise HTTPException(503, "RAG dependency unavailable; consult the service logs") from exc
        finally:
            budget.release()

    @app.get("/ask", response_model=AskResponse, dependencies=[Depends(auth)])
    def ask_get(question: str = Query(min_length=1, max_length=1000), top_k: int = Query(default=4, ge=1, le=10)):
        return answer(question, top_k)

    @app.post("/ask", response_model=AskResponse, dependencies=[Depends(auth)])
    def ask_post(body: AskRequest):
        return answer(body.question, body.top_k)

    ui = str(files("veritylake").joinpath("ui"))
    app.mount("/static", StaticFiles(directory=ui), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(str(files("veritylake").joinpath("ui/index.html")))

    return app
