"""Migrations apply from empty, round-trip, and match the ORM models exactly."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import webforge_api.models  # noqa: F401
from webforge_api.db.base import Base
from webforge_api.db.migrate import downgrade, upgrade

EXPECTED_TABLES = {
    "users", "user_sessions", "mfa_recovery_codes", "activity_logs", "campaigns", "prospects",
    "prospect_campaigns", "prospect_sources", "external_place_identifiers", "email_contacts",
    "website_audits", "audit_findings", "design_projects", "design_pages", "assets", "proposals",
    "preview_deployments", "compliance_assessments", "consent_records", "suppressions",
    "outreach_messages", "email_events", "replies", "jobs", "api_usage", "policy_configs",
}  # fmt: skip


def test_upgrade_from_empty_database(empty_db_url: str) -> None:
    upgrade(empty_db_url)
    engine = create_engine(empty_db_url)
    try:
        tables = set(inspect(engine).get_table_names())
        assert tables >= EXPECTED_TABLES
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
    finally:
        engine.dispose()


def test_downgrade_to_base_and_upgrade_again(empty_db_url: str) -> None:
    upgrade(empty_db_url)
    downgrade(empty_db_url, "base")
    engine = create_engine(empty_db_url)
    try:
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    text("SELECT count(*) FROM pg_proc WHERE proname = 'activity_logs_append_only'")
                )
                == 0
            )
    finally:
        engine.dispose()
    upgrade(empty_db_url)


def test_models_match_migrations(db_url: str) -> None:
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"Models and migrations differ; add a migration: {diff}"
