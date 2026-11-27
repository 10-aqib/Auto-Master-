#!/usr/bin/env python3
"""Create .env from .env.example with fresh random secrets. Never overwrites an existing file.

Usage: python3 infrastructure/scripts/generate-env.py [--output .env]
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / ".env"))
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        print(f"{out} already exists; not overwriting.", file=sys.stderr)
        return 1

    db_pw = secrets.token_urlsafe(24)
    redis_pw = secrets.token_urlsafe(24)
    generated = {
        "APP_SECRET_KEY": secrets.token_urlsafe(48),
        "JWT_SIGNING_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "LOOKUP_HASH_KEY": secrets.token_urlsafe(48),
        "POSTGRES_PASSWORD": db_pw,
        "REDIS_PASSWORD": redis_pw,
        "EMAIL_WEBHOOK_SECRET": secrets.token_urlsafe(32),
        "EMAIL_INBOUND_SIGNING_SECRET": secrets.token_urlsafe(32),
    }
    lines = []
    for line in (ROOT / ".env.example").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            if key in generated:
                value = generated[key]
            elif key == "DATABASE_URL":
                value = value.replace("CHANGE_ME", db_pw)
            elif key in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
                value = value.replace("CHANGE_ME", redis_pw)
            line = f"{key}={value}"
        lines.append(line)

    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Created {out} (mode 600) with fresh random secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
