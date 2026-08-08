from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from veritylake.util import digest, json_bytes


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    environment: Literal["local", "test", "production"] = "local"
    storage_backend: Literal["s3", "local"] = "s3"
    local_lake_dir: Path = Path(".local/lake")
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "veritylake"
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None
    delta_lock_table: str | None = None
    source_url: str = "https://books.toscrape.com/"
    source_adapter: Literal["books", "generic"] = "books"
    source_path_prefix: str = "/"
    source_record_pattern: str = r"/catalogue/(?!category/|page-)[^/]+/index\.html$"
    source_selector: str = "main"
    source_terms_note: str = "Public scraping sandbox; source content is not licensed by this repository."
    user_agent: str = "VerityLakeBot/0.1 (educational local demo)"
    allow_private_sources: bool = False
    max_pages: int = Field(default=60, ge=1, le=100)
    min_documents: int = Field(default=50, ge=1, le=100)
    max_fetches: int = Field(default=180, ge=1, le=400)
    request_interval_seconds: float = Field(default=0.5, ge=0.1, le=60)
    http_timeout_seconds: float = Field(default=20, ge=1, le=120)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    max_retry_wait_seconds: int = Field(default=30, ge=1, le=120)
    min_text_chars: int = Field(default=100, ge=1, le=5000)
    max_reject_fraction: float = Field(default=0.2, ge=0, le=1)
    max_source_age_hours: float = Field(default=72, ge=1, le=8760)
    redact_emails: bool = True
    quarantine_instruction_patterns: bool = True
    chunk_words: int = Field(default=220, ge=20, le=500)
    chunk_overlap_words: int = Field(default=35, ge=0, le=200)
    max_chunks: int = Field(default=1500, ge=1, le=10000)
    ollama_base_url: str = "http://ollama:11434"
    embedding_model: str = "nomic-embed-text:v1.5"
    llm_model: str = "qwen3:4b"
    llm_think: bool = False
    embedding_batch_size: int = Field(default=16, ge=1, le=64)
    model_timeout_seconds: float = Field(default=180, ge=5, le=600)
    chroma_mode: Literal["http", "local"] = "http"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    chroma_ssl: bool = False
    chroma_dir: Path = Path(".local/chroma")
    retrieval_max_distance: float = Field(default=0.65, ge=0, le=2)
    api_key: SecretStr = SecretStr("")
    requests_per_minute: int = Field(default=30, ge=1, le=1000)
    max_concurrent_requests: int = Field(default=2, ge=1, le=16)
    openlineage_url: str | None = None
    git_sha: str = "development"
    log_format: Literal["json", "pretty"] = "json"

    @field_validator("s3_endpoint_url", "openlineage_url", "delta_lock_table", "aws_access_key_id",
                     "aws_secret_access_key", "aws_session_token", mode="before")
    @classmethod
    def empty_is_none(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def coherent(self) -> "Settings":
        if self.min_documents > self.max_pages:
            raise ValueError("MIN_DOCUMENTS must be <= MAX_PAGES")
        if self.chunk_overlap_words >= self.chunk_words:
            raise ValueError("CHUNK_OVERLAP_WORDS must be less than CHUNK_WORDS")
        if self.max_fetches < self.max_pages:
            raise ValueError("MAX_FETCHES must be >= MAX_PAGES")
        if self.environment != "test" and self.allow_private_sources:
            raise ValueError("Private crawl targets are permitted only in ENVIRONMENT=test")
        if self.environment == "production":
            if self.s3_endpoint_url and urlsplit(self.s3_endpoint_url).scheme != "https":
                raise ValueError("Production object storage must use TLS")
        return self

    def public_pipeline_config(self) -> dict:
        names = (
            "source_url", "source_adapter", "source_path_prefix", "source_record_pattern", "source_selector",
            "source_terms_note", "max_pages", "min_documents", "max_fetches", "min_text_chars",
            "max_reject_fraction", "max_source_age_hours", "redact_emails", "quarantine_instruction_patterns",
            "chunk_words", "chunk_overlap_words", "max_chunks", "embedding_model", "git_sha",
        )
        return {name: getattr(self, name) for name in names}

    def pipeline_fingerprint(self) -> str:
        return digest(json_bytes(self.public_pipeline_config()))
