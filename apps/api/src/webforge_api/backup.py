"""Backup helpers (Phase 11): streaming encryption, off-site upload and run records.

    python -m webforge_api.backup encrypt  < plain  > file.enc     (BACKUP_ENCRYPTION_KEY)
    python -m webforge_api.backup decrypt  < file.enc > plain
    python -m webforge_api.backup upload FILE                       (BACKUP_S3_* settings; optional)
    python -m webforge_api.backup record --kind backup|restore_test --status ok|failed [--detail ...]
    python -m webforge_api.backup check-head                        (prints the current migration head)

Format "WFB1": magic, then chunks of [4-byte big-endian length][12-byte nonce][ciphertext+16-byte tag], AES-256-GCM
with the chunk index and a final-chunk flag as associated data, so truncation, reordering and tampering fail.
The key is separate from ENCRYPTION_KEY so a backup can be restored on a fresh host from the key alone.
"""

from __future__ import annotations

import argparse
import base64
import os
import struct
import sys
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"WFB1"
CHUNK = 4 * 1024 * 1024


class BackupError(Exception):
    pass


def load_key(value: str | None = None) -> bytes:
    raw = value if value is not None else os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    try:
        key = base64.urlsafe_b64decode(raw.encode())
    except ValueError as exc:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be urlsafe base64 of 32 bytes") from exc
    if len(key) != 32:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be urlsafe base64 of 32 bytes")
    return key


def _aad(index: int, final: bool) -> bytes:
    return MAGIC + struct.pack(">Q?", index, final)


def encrypt_stream(src: BinaryIO, dst: BinaryIO, key: bytes) -> int:
    aes = AESGCM(key)
    dst.write(MAGIC)
    total, index = 0, 0
    current = src.read(CHUNK)
    while True:
        nxt = src.read(CHUNK)
        final = not nxt
        nonce = os.urandom(12)
        sealed = aes.encrypt(nonce, current, _aad(index, final))
        dst.write(struct.pack(">I", len(sealed)) + nonce + sealed)
        total += len(current)
        index += 1
        if final:
            return total
        current = nxt


def decrypt_stream(src: BinaryIO, dst: BinaryIO, key: bytes) -> int:
    if src.read(4) != MAGIC:
        raise BackupError("not a WFB1 backup file")
    aes = AESGCM(key)
    total, index = 0, 0
    header = src.read(4)
    while header:
        if len(header) != 4:
            raise BackupError("truncated backup")
        (length,) = struct.unpack(">I", header)
        nonce, sealed = src.read(12), src.read(length)
        if len(nonce) != 12 or len(sealed) != length:
            raise BackupError("truncated backup")
        nxt = src.read(4)
        try:
            plain = aes.decrypt(nonce, sealed, _aad(index, not nxt))
        except Exception as exc:  # InvalidTag: wrong key, tampering, truncation or reordering
            raise BackupError("backup failed authentication (wrong key or damaged file)") from exc
        dst.write(plain)
        total += len(plain)
        index += 1
        header = nxt
    if index == 0:
        raise BackupError("empty backup")
    return total


def _upload(path: str) -> str:
    import boto3

    bucket = os.environ.get("BACKUP_S3_BUCKET", "")
    if not bucket:
        raise BackupError(
            "BACKUP_S3_BUCKET is not set; keep the local copy and configure off-site storage"
        )
    client = boto3.client("s3", endpoint_url=os.environ.get("BACKUP_S3_ENDPOINT_URL") or None,
                          region_name=os.environ.get("BACKUP_S3_REGION") or None,
                          aws_access_key_id=os.environ.get("BACKUP_S3_ACCESS_KEY_ID") or None,
                          aws_secret_access_key=os.environ.get("BACKUP_S3_SECRET_ACCESS_KEY") or None)  # fmt: skip
    key = os.environ.get("BACKUP_S3_PREFIX", "webforge/") + os.path.basename(path)
    client.upload_file(path, bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    return f"s3://{bucket}/{key}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webforge_api.backup")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("encrypt")
    sub.add_parser("decrypt")
    up = sub.add_parser("upload")
    up.add_argument("path")
    rec = sub.add_parser("record")
    rec.add_argument("--kind", choices=["backup", "restore_test"], required=True)
    rec.add_argument("--status", choices=["ok", "failed"], required=True)
    rec.add_argument("--detail", default="")
    rec.add_argument("--bytes", type=int, default=0)
    rec.add_argument("--sha256", default="")
    rec.add_argument("--location", default="")
    sub.add_parser("check-head")
    args = parser.parse_args(argv)
    try:
        if args.command == "encrypt":
            n = encrypt_stream(sys.stdin.buffer, sys.stdout.buffer, load_key())
            print(f"encrypted {n} bytes", file=sys.stderr)
        elif args.command == "decrypt":
            n = decrypt_stream(sys.stdin.buffer, sys.stdout.buffer, load_key())
            print(f"decrypted {n} bytes", file=sys.stderr)
        elif args.command == "upload":
            print(_upload(args.path))
        elif args.command == "check-head":
            from alembic.script import ScriptDirectory

            from webforge_api.db.migrate import alembic_config

            print(ScriptDirectory.from_config(alembic_config()).get_current_head())
        elif args.command == "record":
            from webforge_api.config import get_settings
            from webforge_api.db.base import utcnow
            from webforge_api.db.session import build_engine, build_sessionmaker
            from webforge_api.models import BackupRun

            engine = build_engine(get_settings())
            with build_sessionmaker(engine)() as db:
                db.add(BackupRun(kind=args.kind, status=args.status, finished_at=utcnow(), bytes=args.bytes,
                                 sha256=args.sha256 or None, location=args.location or None, detail=args.detail[:1000] or None))  # fmt: skip
                db.commit()
            engine.dispose()
            print(f"recorded {args.kind} {args.status}")
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
