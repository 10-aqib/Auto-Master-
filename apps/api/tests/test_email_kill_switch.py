"""Internal pilot: prove that no real email provider request can be made from any path.

Covers the code paths (API endpoints, dashboard actions which only call the API, worker jobs, retries,
reconciliation, scheduled loops), configuration, the production isolation of the test provider, the email kill
switch and its environment override, and a network sentinel around the whole mock email flow.
"""

from __future__ import annotations

import ast
import re
import socket
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import Harness, make_settings
from tests.test_outreach import EMAIL_SETTINGS, draft, message, post_signed, setup
from webforge_api.config import AppEnv, EmailProvider
from webforge_api.models import Job, OutreachMessage
from webforge_api.models.enums import JobStatus, MessageStatus
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.services.email.provider import (
    MockEmailProvider,
    OutgoingEmail,
    SendResult,
    build_provider,
)
from webforge_api.services.job_handlers import HANDLERS
from webforge_api.worker import Runtime, drain

SRC = Path(__file__).resolve().parents[1] / "src" / "webforge_api"
NETWORK_MODULES = {
    "smtplib",
    "aiosmtplib",
    "httpx",
    "requests",
    "urllib",
    "urllib3",
    "socket",
    "ssl",
    "boto3",
    "http",
}


class RecordingLiveProvider:
    """Stands in for a future real adapter. Records every call; must never be called."""

    name = "live-test"
    is_mock = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    def send(self, message: OutgoingEmail, idempotency_key: str) -> SendResult:
        self.calls.append(idempotency_key)
        return SendResult("accepted", "should-never-happen")

    def get_message_status(self, idempotency_key: str) -> str | None:
        self.calls.append("status:" + idempotency_key)
        return None

    def verify_webhook(
        self, headers: dict[str, str], raw_body: bytes, secret: str, now: float
    ) -> bool:
        return False

    def parse_events(self, payload: dict[str, Any]) -> list[Any]:
        return []

    def parse_inbound(self, payload: dict[str, Any]) -> Any:
        raise AssertionError("not used")


def _py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "migrations" not in p.parts]


# ----------------------------------------------------------------------------- static proof


def test_exactly_one_provider_send_call_site() -> None:
    hits = []
    for path in _py_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "send"
                and ast.unparse(node.func.value) != "outreach"  # the module function, covered below
            ):
                hits.append(f"{path.relative_to(SRC)}:{node.lineno}:{ast.unparse(node.func.value)}")
    assert hits == [f"services/outreach.py:{_send_line()}:provider"], hits


def _send_line() -> int:
    text = (SRC / "services" / "outreach.py").read_text().splitlines()
    return next(i for i, line in enumerate(text, 1) if "provider.send(" in line)


def test_send_is_reached_only_from_the_worker_job() -> None:
    callers = []
    for path in _py_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "send"
                and ast.unparse(node.func.value) == "outreach"
            ):
                callers.append(str(path.relative_to(SRC)))
    assert callers == ["services/job_handlers.py"], callers
    # No API module, CLI, ops loop or preview app calls the send function.
    for rel in ("api", "cli.py", "ops_alerts.py", "preview.py", "backup.py"):
        for path in (SRC / rel).rglob("*.py") if (SRC / rel).is_dir() else [SRC / rel]:
            assert not re.search(r"outreach\.send\(", path.read_text()), path


def test_email_package_has_no_network_code() -> None:
    for path in (SRC / "services" / "email").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert not set(names) & NETWORK_MODULES, f"{path.name} imports {names}"
    for path in _py_files():
        assert "smtplib" not in path.read_text(), path


def test_only_job_types_touching_email_are_send_and_reconcile() -> None:
    email_jobs = {
        name
        for name, fn in HANDLERS.items()
        if "email" in (fn.__code__.co_names + fn.__code__.co_varnames)
        or "outreach" in fn.__code__.co_names
    }
    assert email_jobs == {"email.send", "email.reconcile"}


def test_configuration_cannot_select_or_enable_a_live_provider() -> None:
    assert {p.value for p in EmailProvider} == {"mock"}
    for name in ("resend", "postmark", "smtp", "ses", "sendgrid", "mailgun", ""):
        with pytest.raises(ValueError, match="live providers are not enabled"):
            build_provider(name, 300)
    with pytest.raises(ValueError, match="EMAIL_SENDING_ENABLED"):
        make_settings(email_sending_enabled=True)
    with pytest.raises(ValueError, match="email_provider"):
        make_settings(email_provider="resend")
    assert make_settings().email_sending_enabled is False


# ----------------------------------------------------------------------------- runtime proof


def _approved(h: Harness) -> tuple[dict[str, str], dict[str, Any]]:
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    assert h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf).status_code == 200
    return csrf, m


def _run(h: Harness, provider: Any, settings: Any = None) -> None:
    storage = h.client.app.state.storage  # type: ignore[attr-defined]
    rt = Runtime(
        settings or h.settings,
        limiter=MemoryRateLimiter(),
        clock=h.clock,
        storage=storage,
        email=provider,
    )
    try:
        drain(rt, ["outreach"])
    finally:
        rt.close()


def _job(h: Harness) -> Job:
    with h.db() as db:
        job = db.scalars(select(Job).where(Job.job_type == "email.send")).one()
        db.expunge(job)
        return job


def test_a_live_provider_is_never_called_even_with_every_approval_flag(
    harness_factory: Any,
) -> None:
    h: Harness = harness_factory(**EMAIL_SETTINGS, email_provider_policy_approved=True,
                                 email_provider_approval_ref="TEST-ONLY", email_domain_authenticated=True)  # fmt: skip
    _, m = _approved(h)
    live = RecordingLiveProvider()
    _run(h, live)
    h.clock.advance(hours=1)
    _run(h, live)  # retries go through the same guard
    assert live.calls == []
    job = _job(h)
    assert (
        job.status in (JobStatus.FAILED, JobStatus.DEAD) and job.error_code == "live_email_disabled"
    )
    assert message(h, m["id"])["status"] == "SCHEDULED"  # never marked as sending


def test_test_provider_cannot_send_in_production(harness_factory: Any) -> None:
    h: Harness = harness_factory(**EMAIL_SETTINGS)
    _, m = _approved(h)
    mock = MockEmailProvider()
    _run(h, mock, h.settings.model_copy(update={"app_env": AppEnv.PRODUCTION}))
    assert mock.sent == [] and _job(h).error_code == "mock_provider_in_production"
    assert message(h, m["id"])["status"] == "SCHEDULED"


def test_environment_kill_switch_overrides_the_dashboard(harness_factory: Any) -> None:
    h: Harness = harness_factory(**EMAIL_SETTINGS, email_pause=True)
    csrf, p, contact, proposal = setup(h)  # setup tries to resume the email pause through the API
    controls = {c["key"]: c for c in h.client.get("/api/v1/controls").json()}
    assert (
        controls["email_pause"]["enabled"] is False and controls["email_pause"]["effective"] is True
    )
    assert controls["email_pause"]["env_override"] is True
    m = draft(h, csrf, p, contact, proposal)
    assert m["status"] == "DRAFT" and "paused_email_or_global" in m["assessment"]["reason_codes"]
    assert h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf).status_code == 409


def test_pause_applied_after_approval_holds_queued_mail(harness_factory: Any) -> None:
    h: Harness = harness_factory(**EMAIL_SETTINGS)
    csrf, m = _approved(h)
    assert (
        h.client.put(
            "/api/v1/controls/email_pause",
            json={"enabled": True, "reason": "kill switch drill"},
            headers=csrf,
        ).status_code
        == 200
    )
    mock = MockEmailProvider()
    _run(h, mock)
    assert mock.sent == [] and message(h, m["id"])["status"] == "SCHEDULED"
    job = _job(h)
    assert job.status is JobStatus.QUEUED and job.error_code == "deferred"


def test_no_network_connection_during_the_whole_mock_email_flow(
    harness_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draft, approve, send, transient retry, ambiguous reconcile, webhooks, reply and unsubscribe."""
    attempts: list[str] = []
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if self.family in (socket.AF_INET, socket.AF_INET6) and host not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            attempts.append(str(address))
            raise OSError("blocked by the pilot network sentinel")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    h: Harness = harness_factory(**EMAIL_SETTINGS)
    _csrf, m = _approved(h)
    mock = MockEmailProvider(script=["failed", "ambiguous"])
    _run(h, mock)
    h.clock.advance(minutes=10)
    _run(h, mock)
    h.clock.advance(minutes=5)
    _run(h, mock)
    with h.db() as db:
        sent = db.get(OutreachMessage, m["id"])
        assert sent is not None and sent.status is MessageStatus.ACCEPTED
        provider_id = sent.provider_message_id
    from tests.test_outreach import INBOUND, WEBHOOK

    event = {"events": [{"id": "sentinel-1", "type": "delivered", "message_id": provider_id}]}
    assert post_signed(h, "/webhooks/email/mock/events", event, WEBHOOK).status_code == 200
    reply: dict[str, Any] = {
        "id": "sentinel-r",
        "from": "info@bakery.example.test",
        "subject": "Re",
        "text": "please unsubscribe me",
        "in_reply_to": provider_id,
        "headers": {},
    }
    assert post_signed(h, "/webhooks/email/mock/inbound", reply, INBOUND).status_code == 200
    assert len(mock.sent) == 1  # one message, despite a failure and an ambiguous result
    assert attempts == [], attempts
