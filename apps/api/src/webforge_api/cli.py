"""Operator CLI: `python -m webforge_api.cli <command>`.

Commands:
  migrate                Apply database migrations (alembic upgrade head).
  bootstrap-owner        Create the single OWNER account (one time only).
  purge-expired          Delete revoked/expired sessions older than the retention window.
  openapi                Print the OpenAPI contract as JSON (for packages/contracts).
  refresh-place-ids      Re-check stored Place IDs older than N days (IDs-only lookups).
  purge-transient        Delete expired or no-longer-permitted cached third-party values.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from sqlalchemy.orm import Session

from webforge_api.config import ConfigurationError, Settings, get_settings
from webforge_api.db.base import utcnow
from webforge_api.db.migrate import upgrade
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.security.crypto import Crypto
from webforge_api.services.bootstrap import bootstrap_owner
from webforge_api.services.errors import ServiceError
from webforge_api.services.retention import purge_expired_sessions
from webforge_api.sources.transient import TransientStore


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Owner password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise ServiceError("password_mismatch", "Passwords do not match.")
    return first


def openapi_contract() -> dict[str, object]:
    """OpenAPI schema built with throwaway settings (no real secrets or connections)."""
    import base64
    import secrets

    from webforge_api.config import Settings
    from webforge_api.main import create_app
    from webforge_api.security.rate_limit import MemoryRateLimiter

    settings = Settings(
        app_env="test",
        app_secret_key=secrets.token_urlsafe(48),
        jwt_signing_key=secrets.token_urlsafe(48),
        encryption_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        lookup_hash_key=secrets.token_urlsafe(48),
    )
    return create_app(settings, rate_limiter=MemoryRateLimiter()).openapi()


def _refresh_place_ids(db: Session, settings: Settings, days: int, limit: int) -> dict[str, int]:
    import redis as redis_lib

    from webforge_api.net.safe_fetch import FetchPolicy, SafeFetcher
    from webforge_api.security.rate_limit import RedisRateLimiter
    from webforge_api.services.places import PlacesService
    from webforge_api.sources.places import ConnectorFactory
    from webforge_api.sources.registry import SourceRegistry
    from webforge_api.sources.usage import UsageService
    from webforge_api.sources.website import WebsiteVerifier

    now = utcnow()
    crypto = Crypto.from_settings(settings)
    connectors = ConnectorFactory(settings.google_maps_api_key.get_secret_value())
    limiter = RedisRateLimiter(redis_lib.Redis.from_url(settings.redis_url.get_secret_value()))
    service = PlacesService(
        db,
        settings,
        crypto,
        SourceRegistry(db, settings, crypto, now),
        UsageService(db, settings, limiter, now),
        connectors,
        WebsiteVerifier(SafeFetcher(FetchPolicy()), settings.website_fetch_user_agent),
        now,
    )
    try:
        return service.refresh_place_ids(older_than_days=days, limit=limit)
    finally:
        connectors.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webforge_api.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    boot = sub.add_parser("bootstrap-owner", help="create the single OWNER account")
    boot.add_argument("--email", required=True)
    boot.add_argument("--name", required=True, help="display name")
    boot.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin (one line)"
    )
    purge = sub.add_parser("purge-expired", help="delete old revoked/expired sessions")
    purge.add_argument("--keep-days", type=int, default=30)
    sub.add_parser("openapi", help="print the OpenAPI contract")
    refresh = sub.add_parser("refresh-place-ids", help="refresh stale Place IDs")
    refresh.add_argument("--older-than-days", type=int, default=365)
    refresh.add_argument("--limit", type=int, default=100)
    sub.add_parser("purge-transient", help="purge expired/disallowed transient values")
    sub.add_parser(
        "purge-artifacts", help="expire preview links and delete proposal PDFs past retention"
    )
    args = parser.parse_args(argv)

    if args.command == "openapi":
        print(json.dumps(openapi_contract(), indent=2, sort_keys=True))
        return 0

    try:
        settings = get_settings()
        if args.command == "migrate":
            upgrade(settings.sqlalchemy_url)
            print("Migrations applied.")
            return 0

        engine = build_engine(settings)
        factory = build_sessionmaker(engine)
        with factory() as db:
            if args.command == "bootstrap-owner":
                owner = bootstrap_owner(
                    db,
                    Crypto.from_settings(settings),
                    email=args.email,
                    display_name=args.name,
                    password=_read_password(args.password_stdin),
                )
                print(f"Owner created: {owner.email}. Sign in and set up two-factor auth.")
            elif args.command == "refresh-place-ids":
                counts = _refresh_place_ids(db, settings, args.older_than_days, args.limit)
                print(f"Place IDs: {counts}")
            elif args.command == "purge-transient":
                store = TransientStore(db, Crypto.from_settings(settings), utcnow())
                expired, disallowed = store.purge_expired(), store.purge_disallowed()
                print(f"Purged {expired} expired and {disallowed} disallowed transient values.")
            elif args.command == "purge-artifacts":
                from webforge_api.services.proposals import purge_expired as purge_artifacts
                from webforge_api.storage import build_storage

                counts = purge_artifacts(
                    db, Crypto.from_settings(settings), build_storage(settings), now=utcnow()
                )
                print(f"Artifacts: {counts}")
            elif args.command == "purge-expired":
                count = purge_expired_sessions(db, now=utcnow(), keep_days=args.keep_days)
                print(f"Purged {count} sessions.")
        engine.dispose()
        return 0
    except (ConfigurationError, ServiceError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
