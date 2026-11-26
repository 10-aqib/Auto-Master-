"""Private artifact storage (screenshots, PDFs, previews). Never served directly to the public."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from webforge_api.config import Settings

_KEY = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,400}$")


class StorageError(Exception):
    pass


def validate_key(key: str) -> str:
    if not _KEY.fullmatch(key) or ".." in key or "//" in key or key.endswith("/"):
        raise StorageError("invalid storage key")
    return key


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str
    content_type: str


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Files under a private root directory (a Docker volume in Compose)."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if self.root.resolve() not in path.parents:
            raise StorageError("key escapes storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)  # atomic
        return StoredObject(key, len(data), hashlib.sha256(data).hexdigest(), content_type)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("not found") from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage:
    """S3-compatible bucket (private; server-side encryption requested on every write)."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            region_name=settings.s3_region or None,
            aws_access_key_id=settings.s3_access_key.get_secret_value() or None,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value() or None,
        )

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        self.client.put_object(
            Bucket=self.bucket,
            Key=validate_key(key),
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        return StoredObject(key, len(data), hashlib.sha256(data).hexdigest(), content_type)

    def get(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=validate_key(key))
        except Exception as exc:
            raise StorageError("not found") from exc
        data: bytes = obj["Body"].read()
        return data

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=validate_key(key))
        except Exception:
            return False
        return True


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.storage_local_root)
