from __future__ import annotations

import fcntl
import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from typing import Any

from veritylake.config import Settings
from veritylake.util import digest, json_bytes


class ConflictError(RuntimeError):
    """A compare-and-swap failed. Never silently replace another writer's publication."""


class ObjectStore(ABC):
    @staticmethod
    def safe_key(key: str) -> str:
        path = PurePosixPath(key)
        if not key or key.startswith("/") or ".." in path.parts or "\\" in key or "\x00" in key:
            raise ValueError("Unsafe object key")
        return str(path)

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def get_versioned(self, key: str) -> tuple[bytes, str] | None: ...

    @abstractmethod
    def compare_and_swap(self, key: str, data: bytes, expected_etag: str | None) -> str: ...

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]: ...

    @abstractmethod
    def uri(self, key: str) -> str: ...

    def get(self, key: str) -> bytes:
        result = self.get_versioned(key)
        if result is None:
            raise FileNotFoundError(key)
        return result[0]

    def put_json(self, key: str, value: Any) -> None:
        self.put(key, json_bytes(value), "application/json")

    def get_json(self, key: str) -> Any:
        return json.loads(self.get(key))

    def maybe_json(self, key: str) -> Any | None:
        value = self.get_versioned(key)
        return None if value is None else json.loads(value[0])


class LocalStore(ObjectStore):
    """POSIX local development store. Atomic replace + advisory lock implement CAS."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / self.safe_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Object path escapes lake root")
        return path

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get_versioned(self, key: str) -> tuple[bytes, str] | None:
        try:
            data = self._path(key).read_bytes()
            return data, digest(data)
        except FileNotFoundError:
            return None

    def compare_and_swap(self, key: str, data: bytes, expected_etag: str | None) -> str:
        lock = self.root / ".locks" / digest(key)
        lock.parent.mkdir(exist_ok=True)
        with lock.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            current = self.get_versioned(key)
            actual = current[1] if current else None
            if actual != expected_etag:
                raise ConflictError("Publication changed; start a new run or explicitly rebase")
            self.put(key, data, "application/json")
            return digest(data)

    def list_keys(self, prefix: str) -> list[str]:
        prefix = self.safe_key(prefix)
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                      if p.is_file() and str(p.relative_to(self.root)).startswith(prefix))

    def uri(self, key: str) -> str:
        return str(self._path(key))


class S3Store(ObjectStore):
    def __init__(self, settings: Settings, client=None):
        import boto3
        from botocore.config import Config

        self.settings = settings
        self.bucket = settings.s3_bucket
        self.client = client or boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=(settings.aws_secret_access_key.get_secret_value()
                                   if settings.aws_secret_access_key else None),
            aws_session_token=(settings.aws_session_token.get_secret_value()
                               if settings.aws_session_token else None),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          connect_timeout=5, read_timeout=20, retries={"max_attempts": 3, "mode": "standard"}),
        )

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
                raise
            args = {"Bucket": self.bucket}
            if self.settings.s3_region != "us-east-1":
                args["CreateBucketConfiguration"] = {"LocationConstraint": self.settings.s3_region}
            self.client.create_bucket(**args)
        self.client.put_bucket_versioning(Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"})

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=self.safe_key(key), Body=data, ContentType=content_type)

    def get_versioned(self, key: str) -> tuple[bytes, str] | None:
        from botocore.exceptions import ClientError

        try:
            result = self.client.get_object(Bucket=self.bucket, Key=self.safe_key(key))
            body = result["Body"]
            try:
                return body.read(), result["ETag"]
            finally:
                body.close()
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    def compare_and_swap(self, key: str, data: bytes, expected_etag: str | None) -> str:
        from botocore.exceptions import ClientError

        condition = {"IfMatch": expected_etag} if expected_etag else {"IfNoneMatch": "*"}
        try:
            result = self.client.put_object(Bucket=self.bucket, Key=self.safe_key(key), Body=data,
                                           ContentType="application/json", **condition)
            return result["ETag"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict", "412", "409"):
                raise ConflictError("Publication changed; refusing lost update") from exc
            raise

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        return [o["Key"] for page in paginator.paginate(Bucket=self.bucket, Prefix=self.safe_key(prefix))
                for o in page.get("Contents", [])]

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{self.safe_key(key)}"

    def delta_options(self) -> dict[str, str]:
        s = self.settings
        opts = {"AWS_REGION": s.s3_region, "AWS_VIRTUAL_HOSTED_STYLE_REQUEST": "false"}
        if s.aws_access_key_id:
            opts["AWS_ACCESS_KEY_ID"] = s.aws_access_key_id
        if s.aws_secret_access_key:
            opts["AWS_SECRET_ACCESS_KEY"] = s.aws_secret_access_key.get_secret_value()
        if s.aws_session_token:
            opts["AWS_SESSION_TOKEN"] = s.aws_session_token.get_secret_value()
        if s.s3_endpoint_url:
            opts.update({"AWS_ENDPOINT_URL": s.s3_endpoint_url, "conditional_put": "etag"})
            if s.s3_endpoint_url.startswith("http://"):
                opts["AWS_ALLOW_HTTP"] = "true"
        else:
            if not s.delta_lock_table:
                raise ValueError("AWS S3 mode requires DELTA_LOCK_TABLE; unsafe rename is never enabled")
            opts.update({"AWS_S3_LOCKING_PROVIDER": "dynamodb", "DELTA_DYNAMO_TABLE_NAME": s.delta_lock_table})
        return opts


def make_store(settings: Settings) -> ObjectStore:
    return LocalStore(settings.local_lake_dir) if settings.storage_backend == "local" else S3Store(settings)
