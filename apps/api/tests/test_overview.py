"""Phase 10: overview analytics, budget warnings, review queues and operations health."""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
import redis
from sqlalchemy import select

from tests.conftest import Harness
from tests.test_sources_api import _owner
from webforge_api.models import ApiUsage, DesignBrief, DesignProject, Job, Prospect, Reply
from webforge_api.models.enums import JobStatus, ProspectState, Role, RunStatus, UsageOutcome
from webforge_api.services.overview import HEARTBEAT_PREFIX, record_heartbeat, workers


def _prospect(h: Harness, state: ProspectState, country: str | None = "PK") -> uuid.UUID:
    with h.db() as db:
        p = Prospect(
            business_name=f"Fixture {uuid.uuid4().hex[:6]}", state=state, country_code=country
        )
        db.add(p)
        db.commit()
        return p.id


def test_funnel_is_cumulative_and_filterable(harness: Harness) -> None:
    csrf = _owner(harness)
    assert csrf
    for state in (
        ProspectState.DISCOVERED,
        ProspectState.AUDITED,
        ProspectState.PROPOSAL_READY,
        ProspectState.SENT,
    ):
        _prospect(harness, state)
    _prospect(harness, ProspectState.POLICY_HOLD, country="US")
    data = harness.client.get("/api/v1/overview").json()
    funnel = {f["stage"]: f for f in data["funnel"]}
    assert funnel["DISCOVERED"]["reached"] == 4 and funnel["AUDITED"]["reached"] == 3
    assert funnel["PROPOSAL_READY"]["reached"] == 2 and funnel["SENT"]["current"] == 1
    assert data["holds_and_exits"]["POLICY_HOLD"] == 1
    assert "not tracked" in data["tracking_note"]
    us = harness.client.get("/api/v1/overview?country=US").json()
    assert (
        sum(f["current"] for f in us["funnel"]) == 0 and us["holds_and_exits"]["POLICY_HOLD"] == 1
    )
    assert harness.client.get("/api/v1/overview?country=usa").status_code == 422


def test_budgets_warn_at_80_percent_and_stop_at_limit(harness_factory: Any) -> None:
    h: Harness = harness_factory(
        mfa_required_for_owner=True, ai_daily_budget_minor=100, email_daily_max=5
    )
    _owner(h)
    with h.db() as db:
        db.add(ApiUsage(provider="anthropic", operation="design_brief", units=1, outcome=UsageOutcome.SUCCESS,
                        cost_milliminor=85_000, estimated_cost_minor=85, currency="USD", occurred_at=h.clock()))  # fmt: skip
        db.commit()
    budgets = {b["key"]: b for b in h.client.get("/api/v1/overview").json()["budgets"]}
    assert budgets["ai_spend"]["status"] == "warning" and budgets["ai_spend"]["ratio"] == 0.85
    assert (
        budgets["places_spend"]["status"] == "stopped"
        and "blocked" in budgets["places_spend"]["note"]
    )
    assert budgets["email_daily"]["status"] == "ok"


def test_review_queues_collect_manual_work(harness: Harness) -> None:
    _owner(harness)
    pid = _prospect(harness, ProspectState.HUMAN_REVIEW)
    with harness.db() as db:
        project = DesignProject(prospect_id=pid, status=RunStatus.FAILED, current_version=1)
        db.add(project)
        db.flush()
        db.add(DesignBrief(design_project_id=project.id, version=1, status="NEEDS_REVIEW", schema_version="brief-1", prompt_version="p",
                           model="m", facts_snapshot={}, validation_issues=[{"code": "prohibited_award"}], attempts=3, created_at=harness.clock()))  # fmt: skip
        db.add(
            Reply(
                prospect_id=pid,
                received_at=harness.clock(),
                classification="UNCERTAIN",
                needs_human_review=True,
            )
        )
        db.commit()
    data = harness.client.get("/api/v1/review-queues").json()
    assert (
        data["counts"]["source_and_evidence_review"] == 1 and data["counts"]["content_claims"] == 1
    )
    assert data["counts"]["uncertain_replies"] == 1
    assert data["queues"]["content_claims"][0]["href"].startswith("/designs/")


def test_operations_view_is_admin_only_and_reports_queues(harness: Harness) -> None:
    _owner(harness)
    with harness.db() as db:
        now = harness.clock()
        db.add(
            Job(
                job_type="prospect.audit",
                queue="audit",
                status=JobStatus.QUEUED,
                idempotency_key="ops-1",
                payload={},
                payload_schema_version="1",
                available_at=now,
            )
        )
        db.add(Job(job_type="prospect.audit", queue="audit", status=JobStatus.DEAD, idempotency_key="ops-2", payload={}, payload_schema_version="1", available_at=now,
                   error_code="browser_unavailable"))  # fmt: skip
        db.commit()
    ops = harness.client.get("/api/v1/operations").json()
    assert {"queue": "audit", "status": "QUEUED"}.items() <= next(
        q for q in ops["queues"] if q["queue"] == "audit"
    ).items()
    assert ops["dead_letter"] == 1 and ops["failures_24h"][0]["error_code"] == "browser_unavailable"
    assert ops["backups"]["status"] == "unknown"
    assert {p["key"] for p in ops["pauses"]} >= {"global_pause", "email_pause"}
    harness.client.cookies.clear()
    reviewer, secret = harness.create_user(Role.REVIEWER, mfa=True)
    harness.login_active(reviewer, secret)
    assert harness.client.get("/api/v1/operations").status_code == 403
    assert harness.client.get("/api/v1/overview").status_code == 200


@pytest.mark.skipif(not os.environ.get("TEST_REDIS_URL"), reason="needs TEST_REDIS_URL")
def test_worker_heartbeats_expire() -> None:
    from datetime import UTC, datetime

    client = redis.Redis.from_url(os.environ["TEST_REDIS_URL"])
    for key in client.scan_iter(HEARTBEAT_PREFIX + "*"):
        client.delete(key)
    record_heartbeat(client, "host-a:1", ["audit", "design"], datetime.now(UTC))
    seen = workers(client)
    assert (
        seen is not None
        and seen[0]["worker"] == "host-a:1"
        and seen[0]["queues"] == ["audit", "design"]
    )
    assert 0 < int(client.ttl(HEARTBEAT_PREFIX + "host-a:1")) <= 60
    assert (
        workers(redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)) is None
    )


def test_outreach_draft_links_the_campaign(harness: Harness) -> None:
    from webforge_api.models import OutreachMessage

    with harness.db() as db:
        assert "campaign_id" in OutreachMessage.__table__.c
        assert db.scalar(select(Prospect).limit(1)) is None
