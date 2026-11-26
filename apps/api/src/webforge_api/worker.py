"""Job worker: `python -m webforge_api.worker --queues discovery,verification,qualification`.

Claims one job at a time per process (scale with replicas), binds job/correlation IDs to logs,
and stops gracefully on SIGTERM after the current job.
"""

from __future__ import annotations

import argparse
import signal
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import redis
import structlog

from webforge_api.config import Settings, get_settings
from webforge_api.db.base import utcnow
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.logging_config import configure_logging, get_logger
from webforge_api.models import Job
from webforge_api.models.enums import JobStatus
from webforge_api.net.safe_fetch import FetchPolicy, SafeFetcher
from webforge_api.security.crypto import Crypto
from webforge_api.security.rate_limit import RateLimiter, RedisRateLimiter
from webforge_api.services import jobs as jobqueue
from webforge_api.services.job_handlers import HANDLERS, JobContext, JobDeferred
from webforge_api.services.jobs import JobError
from webforge_api.services.places import PlacesService
from webforge_api.sources.places import ConnectorFactory
from webforge_api.sources.registry import SourceRegistry
from webforge_api.sources.usage import UsageService
from webforge_api.sources.website import WebsiteVerifier

log = get_logger("webforge_api.worker")
ALL_QUEUES = ["discovery", "verification", "qualification"]


class Runtime:
    """Long-lived dependencies shared by jobs in one worker process."""

    def __init__(
        self,
        settings: Settings,
        *,
        limiter: RateLimiter | None = None,
        connectors: ConnectorFactory | None = None,
        fetch_policy: FetchPolicy | None = None,
        clock: Callable[[], Any] = utcnow,
        handlers: dict[str, Callable[[JobContext, Job], dict[str, Any] | None]] | None = None,
    ) -> None:
        self.settings = settings
        self.engine = build_engine(settings)
        self.sessions = build_sessionmaker(self.engine)
        self.crypto = Crypto.from_settings(settings)
        self.limiter = limiter or RedisRateLimiter(
            redis.Redis.from_url(settings.redis_url.get_secret_value(), socket_timeout=2)
        )
        self.connectors = connectors or ConnectorFactory(
            settings.google_maps_api_key.get_secret_value()
        )
        self.fetch_policy = fetch_policy or FetchPolicy(
            max_bytes=settings.browser_max_response_bytes,
            read_timeout=float(settings.browser_page_timeout_seconds),
            total_timeout=float(settings.browser_page_timeout_seconds),
            user_agent=settings.website_fetch_user_agent,
        )
        self.clock = clock
        self.handlers = handlers or dict(HANDLERS)

    def context(self, db: Any) -> JobContext:
        now = self.clock()
        places = PlacesService(
            db,
            self.settings,
            self.crypto,
            SourceRegistry(db, self.settings, self.crypto, now),
            UsageService(db, self.settings, self.limiter, now),
            self.connectors,
            WebsiteVerifier(SafeFetcher(self.fetch_policy), self.settings.website_fetch_user_agent),
            now,
        )
        return JobContext(db=db, settings=self.settings, crypto=self.crypto, now=now, places=places)

    def close(self) -> None:
        self.connectors.close()
        self.engine.dispose()


def run_once(runtime: Runtime, queues: list[str]) -> Job | None:
    """Claim and run at most one job. Returns the job (refreshed) or None when idle."""
    with runtime.sessions() as db:
        job = jobqueue.claim(db, queues, runtime.clock())
        if job is None:
            return None
        job_id = job.id
        structlog.contextvars.bind_contextvars(
            job_id=str(job.id), job_type=job.job_type, request_id=job.correlation_id
        )
        handler = runtime.handlers.get(job.job_type)
        try:
            if handler is None:
                raise JobError("unknown_job_type", f"No handler for {job.job_type}")
            ctx = runtime.context(db)
            result = handler(ctx, job)
            jobqueue.complete(db, db.get(Job, job_id) or job, runtime.clock(), result)
            log.info("job_succeeded")
        except JobDeferred as exc:
            db.rollback()
            fresh = db.get(Job, job_id)
            if fresh is not None:
                from datetime import timedelta

                fresh.status = JobStatus.QUEUED
                fresh.attempts = max(0, fresh.attempts - 1)
                fresh.available_at = runtime.clock() + timedelta(seconds=exc.seconds)
                fresh.lease_expires_at = None
                fresh.error_code = "deferred"
                fresh.error_message = str(exc)[:1000]
                db.commit()
            log.info("job_deferred", reason=str(exc))
        except JobError as exc:
            db.rollback()
            fresh = db.get(Job, job_id)
            if fresh is not None:
                jobqueue.fail(db, fresh, runtime.clock(), exc)
            log.warning("job_failed", code=exc.code, retryable=exc.retryable)
        except Exception as exc:
            db.rollback()
            fresh = db.get(Job, job_id)
            if fresh is not None:
                # Unexpected errors are retried (bounded); details stay out of the job record.
                jobqueue.fail(
                    db,
                    fresh,
                    runtime.clock(),
                    JobError("internal_error", type(exc).__name__, retryable=True),
                )
            log.error("job_crashed", error_type=type(exc).__name__)
        finally:
            structlog.contextvars.clear_contextvars()
        with runtime.sessions() as fresh_db:
            return fresh_db.get(Job, job_id)


def drain(runtime: Runtime, queues: list[str], limit: int = 100) -> int:
    """Run jobs until the queues are idle (tests and one-off runs)."""
    done = 0
    while done < limit and run_once(runtime, queues) is not None:
        done += 1
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webforge_api.worker")
    parser.add_argument("--queues", default=",".join(ALL_QUEUES))
    parser.add_argument("--idle-sleep", type=float, default=2.0)
    parser.add_argument("--heartbeat-file", default="/tmp/worker-heartbeat")  # noqa: S108
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level.value)
    queues = [q.strip() for q in args.queues.split(",") if q.strip()]
    runtime = Runtime(settings)
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker_started", queues=queues, host=socket.gethostname())
    heartbeat = Path(args.heartbeat_file)
    try:
        while not stopping:
            heartbeat.touch()  # container healthcheck reads this file's age
            if run_once(runtime, queues) is None:
                time.sleep(args.idle_sleep)
    finally:
        runtime.close()
        log.info("worker_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
