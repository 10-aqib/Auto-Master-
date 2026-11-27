"""Operational alert checks (Phase 11).

    python -m webforge_api.ops_alerts            one run; prints JSON; exit 1 when any alert fires
    python -m webforge_api.ops_alerts --loop 300 run forever (the `ops` service in production)

Alerts go to stdout/structured logs and, when ALERT_WEBHOOK_URL is set, are POSTed there as JSON (for example an
ntfy or chat webhook the owner controls). Email alerts are not used: outbound email is disabled.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import ssl
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

import httpx
import redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from webforge_api.config import Settings, get_settings
from webforge_api.db.base import utcnow
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.models import ActivityLog, ApiUsage, BackupRun, Job, OutreachMessage
from webforge_api.models.enums import JobStatus, MessageStatus, UsageOutcome
from webforge_api.services import overview


@dataclass
class Alert:
    code: str
    severity: Literal["critical", "warning", "info"]
    message: str


def _db_checks(
    db: Session, settings: Settings, now: datetime, client: redis.Redis | None
) -> list[Alert]:
    out: list[Alert] = []
    workers = overview.workers(client)
    if workers is None:
        out.append(
            Alert(
                "redis_unreachable",
                "critical",
                "Redis is unreachable; queues, rate limits and heartbeats are affected.",
            )
        )
    else:
        served = {q for w in workers for q in w.get("queues", [])}
        missing = {
            "discovery",
            "verification",
            "qualification",
            "design",
            "outreach",
            "audit",
        } - served
        if missing:
            out.append(
                Alert(
                    "worker_missing",
                    "critical",
                    f"No live worker for queues: {', '.join(sorted(missing))}.",
                )
            )
    oldest = db.scalar(
        select(func.min(Job.available_at)).where(
            Job.status.in_((JobStatus.QUEUED, JobStatus.RETRYING)), Job.available_at <= now
        )
    )
    if oldest is not None and now - oldest > timedelta(minutes=30):
        out.append(
            Alert(
                "queue_stale",
                "warning",
                f"Oldest runnable job has waited {int((now - oldest).total_seconds() // 60)} minutes.",
            )
        )
    dead = (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.DEAD, Job.updated_at >= now - timedelta(days=1))
        )
        or 0
    )
    if dead:
        out.append(
            Alert(
                "dead_letters", "warning", f"{dead} job(s) moved to dead letters in the last 24 h."
            )
        )
    for b in overview.budgets(db, settings, now):
        if b["limit"] and b["status"] != "ok":
            out.append(Alert(f"budget_{b['key']}", "critical" if b["status"] == "stopped" else "warning",
                             f"{b['label']}: {b['used']}/{b['limit']} {b['unit']} ({b['status']})."))  # fmt: skip
    for provider, n in db.execute(select(ApiUsage.provider, func.count()).where(ApiUsage.outcome == UsageOutcome.ERROR, ApiUsage.occurred_at >= now - timedelta(hours=1))
                                  .group_by(ApiUsage.provider)).all():  # fmt: skip
        if n >= 5:
            out.append(
                Alert("provider_errors", "warning", f"{n} {provider} errors in the last hour.")
            )
    failed_logins = db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.action == "auth.login", ActivityLog.outcome == "failure",
                                                                                  ActivityLog.occurred_at >= now - timedelta(hours=1))) or 0  # fmt: skip
    if failed_logins >= 20:
        out.append(
            Alert("login_anomaly", "warning", f"{failed_logins} failed sign-ins in the last hour.")
        )
    sig = (
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.action == "webhook.signature_failed",
                ActivityLog.occurred_at >= now - timedelta(hours=1),
            )
        )
        or 0
    )
    if sig >= 5:
        out.append(
            Alert(
                "webhook_signature_failures",
                "warning",
                f"{sig} webhook signature failures in the last hour.",
            )
        )
    pause_changes = db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.action.in_(("control.paused", "control.resumed")),
                                                                                  ActivityLog.occurred_at >= now - timedelta(minutes=15))) or 0  # fmt: skip
    if pause_changes:
        out.append(
            Alert(
                "pause_changed",
                "info",
                f"{pause_changes} pause switch change(s) in the last 15 minutes.",
            )
        )
    week = now - timedelta(days=7)
    counts = dict(
        db.execute(
            select(OutreachMessage.status, func.count())
            .where(OutreachMessage.last_attempt_at >= week)
            .group_by(OutreachMessage.status)
        ).all()
    )
    sent = sum(
        counts.get(s, 0)
        for s in (
            MessageStatus.ACCEPTED,
            MessageStatus.SENT,
            MessageStatus.DELIVERED,
            MessageStatus.BOUNCED,
            MessageStatus.COMPLAINED,
        )
    )
    if sent >= 10:
        if counts.get(MessageStatus.BOUNCED, 0) / sent > 0.05:
            out.append(
                Alert(
                    "bounce_rate",
                    "critical",
                    "Hard-bounce rate above 5% this week. Pause email and review sources.",
                )
            )
        if counts.get(MessageStatus.COMPLAINED, 0) / sent > 0.001:
            out.append(
                Alert(
                    "complaint_rate",
                    "critical",
                    "Complaint rate above 0.1% this week. Pause email immediately.",
                )
            )
    last_ok = db.scalar(
        select(func.max(BackupRun.finished_at)).where(
            BackupRun.kind == "backup", BackupRun.status == "ok"
        )
    )
    if last_ok is None or now - last_ok > timedelta(hours=26):
        out.append(Alert("backup_stale", "critical", "No successful backup in the last 26 hours."))
    last_restore = db.scalar(
        select(func.max(BackupRun.finished_at)).where(
            BackupRun.kind == "restore_test", BackupRun.status == "ok"
        )
    )
    if last_restore is None or now - last_restore > timedelta(days=8):
        out.append(
            Alert(
                "restore_test_stale", "critical", "No successful restore test in the last 8 days."
            )
        )
    if db.scalar(
        select(func.count())
        .select_from(BackupRun)
        .where(BackupRun.status == "failed", BackupRun.finished_at >= now - timedelta(days=1))
    ):
        out.append(
            Alert(
                "backup_failed", "critical", "A backup or restore test failed in the last 24 hours."
            )
        )
    return out


def _host_checks(settings: Settings) -> list[Alert]:
    out: list[Alert] = []
    root = settings.storage_local_root if settings.storage_backend == "local" else "/"
    try:
        usage = shutil.disk_usage(root)
        if usage.used / usage.total > 0.85:
            out.append(
                Alert(
                    "disk",
                    "critical" if usage.used / usage.total > 0.95 else "warning",
                    f"Disk {int(usage.used / usage.total * 100)}% used at {root}.",
                )
            )
    except OSError:
        out.append(Alert("disk_unknown", "warning", f"Cannot read disk usage at {root}."))
    try:
        with open("/proc/meminfo") as fh:
            info = dict(line.split(":", 1) for line in fh.read().splitlines() if ":" in line)
        total, avail = int(info["MemTotal"].split()[0]), int(info["MemAvailable"].split()[0])
        if avail / total < 0.1:
            out.append(Alert("memory", "warning", f"Only {avail // 1024} MiB memory available."))
    except (OSError, KeyError, ValueError):
        pass
    for url in {settings.app_url, settings.api_url, settings.preview_base_url}:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            continue
        try:
            ctx = ssl.create_default_context()
            with (
                socket.create_connection((parts.hostname, parts.port or 443), timeout=5) as sock,
                ctx.wrap_socket(sock, server_hostname=parts.hostname) as tls,
            ):
                cert = tls.getpeercert() or {}
                expires = datetime.fromtimestamp(
                    ssl.cert_time_to_seconds(str(cert["notAfter"])), UTC
                )
            days = (expires - datetime.now(UTC)).days
            if days < 14:
                out.append(
                    Alert(
                        "tls_expiry",
                        "critical" if days < 3 else "warning",
                        f"TLS certificate for {parts.hostname} expires in {days} days.",
                    )
                )
        except (OSError, ssl.SSLError, KeyError) as exc:
            out.append(
                Alert(
                    "tls_check_failed",
                    "warning",
                    f"Cannot verify TLS for {parts.hostname}: {type(exc).__name__}.",
                )
            )
    return out


def run(settings: Settings, now: datetime | None = None) -> list[Alert]:
    now = now or utcnow()
    alerts: list[Alert] = []
    engine = build_engine(settings)
    try:
        with build_sessionmaker(engine)() as db:
            db.execute(text("SELECT 1"))
            client = redis.Redis.from_url(
                settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
            )
            try:
                client.ping()
            except redis.RedisError:
                client.close()
                client = None  # type: ignore[assignment]
            alerts += _db_checks(db, settings, now, client)
            if client is not None:
                client.close()
    except Exception as exc:  # database down is itself the alert
        alerts.append(
            Alert(
                "database_unreachable", "critical", f"Database check failed: {type(exc).__name__}."
            )
        )
    finally:
        engine.dispose()
    alerts += _host_checks(settings)
    return alerts


def deliver(settings: Settings, alerts: list[Alert]) -> None:
    if not settings.alert_webhook_url or not any(a.severity != "info" for a in alerts):
        return
    body = {
        "service": "webforge",
        "at": utcnow().isoformat(),
        "alerts": [asdict(a) for a in alerts],
    }
    try:
        httpx.post(settings.alert_webhook_url, json=body, timeout=10)
    except httpx.HTTPError as exc:
        print(
            json.dumps({"event": "alert_delivery_failed", "error": type(exc).__name__}),
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webforge_api.ops_alerts")
    parser.add_argument("--loop", type=int, default=0, help="seconds between runs; 0 = run once")
    args = parser.parse_args(argv)
    settings = get_settings()
    while True:
        alerts = run(settings)
        print(
            json.dumps(
                {"event": "ops_alerts", "count": len(alerts), "alerts": [asdict(a) for a in alerts]}
            ),
            flush=True,
        )
        deliver(settings, alerts)
        if not args.loop:
            return 1 if any(a.severity != "info" for a in alerts) else 0
        time.sleep(args.loop)


if __name__ == "__main__":
    raise SystemExit(main())
