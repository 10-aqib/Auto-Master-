"""initial schema: identity, campaigns, prospects, audits, designs, proposals,
compliance, outreach and operations tables; append-only activity log.

Revision ID: 0001
Revises:
Create Date: 2026-11-26 13:18:41.499737
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("license_id", sa.String(length=64), nullable=True),
        sa.Column("license_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "attribution_required", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_assets_storage_key")),
    )
    op.create_index(op.f("ix_assets_sha256"), "assets", ["sha256"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("payload_schema_version", sa.String(length=16), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "RETRYING",
                "SUCCEEDED",
                "FAILED",
                "DEAD",
                "CANCELLED",
                name="job_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="QUEUED",
            nullable=False,
        ),
        sa.Column("queue", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts > 0", name=op.f("ck_jobs_attempts_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_jobs_idempotency_key")),
    )
    op.create_index(op.f("ix_jobs_correlation_id"), "jobs", ["correlation_id"], unique=False)
    op.create_index(
        "ix_jobs_queue_status_available", "jobs", ["queue", "status", "available_at"], unique=False
    )
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"], unique=False)
    op.create_table(
        "policy_configs",
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column(
            "recipient_type",
            sa.Enum(
                "UNKNOWN",
                "CORPORATE",
                "SOLE_TRADER",
                "INDIVIDUAL",
                "ROLE_ACCOUNT",
                name="policy_recipient_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("message_category", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "IN_REVIEW",
                "ACTIVE",
                "RETIRED",
                name="policy_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "rules", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("reviewer_name", sa.String(length=200), nullable=True),
        sa.Column("reviewer_qualification", sa.String(length=200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "source_references", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'ACTIVE' OR (reviewer_name IS NOT NULL AND reviewer_qualification IS NOT NULL AND reviewed_at IS NOT NULL AND effective_from IS NOT NULL AND cardinality(source_references) > 0)",
            name=op.f("ck_policy_configs_active_requires_review"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_configs")),
        sa.UniqueConstraint(
            "country_code",
            "recipient_type",
            "message_category",
            "version",
            name=op.f("uq_policy_configs_country_code_recipient_type_message_category_version"),
        ),
    )
    op.create_index(
        "uq_policy_configs_one_active",
        "policy_configs",
        ["country_code", "recipient_type", "message_category"],
        unique=True,
        postgresql_where="status = 'ACTIVE'",
    )
    op.create_table(
        "prospects",
        sa.Column("business_name", sa.String(length=300), nullable=False),
        sa.Column("verified_domain", sa.String(length=253), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("business_type", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "DISCOVERED",
                "SOURCE_VERIFYING",
                "VERIFIED",
                "DEDUPLICATED",
                "QUALIFYING",
                "QUALIFIED",
                "AUDITING",
                "AUDITED",
                "GENERATING_DESIGN",
                "VALIDATING",
                "PROPOSAL_READY",
                "COMPLIANCE_CHECK",
                "HUMAN_REVIEW",
                "SCHEDULED",
                "SENT",
                "DELIVERED",
                "REPLIED",
                "INTERESTED",
                "CLIENT",
                "REJECTED",
                "FAILED",
                "BOUNCED",
                "UNSUBSCRIBED",
                "DO_NOT_CONTACT",
                "POLICY_HOLD",
                "EXPIRED",
                name="prospect_state",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DISCOVERED",
            nullable=False,
        ),
        sa.Column(
            "state_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("qualification_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("qualification_band", sa.String(length=16), nullable=True),
        sa.Column("owner_notes", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "country_code IS NULL OR country_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_prospects_country_iso"),
        ),
        sa.CheckConstraint(
            "qualification_score IS NULL OR (qualification_score >= 0 AND qualification_score <= 100)",
            name=op.f("ck_prospects_score_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prospects")),
    )
    op.create_index(
        "ix_prospects_country_state", "prospects", ["country_code", "state"], unique=False
    )
    op.create_index(
        "ix_prospects_state_created_at", "prospects", ["state", "created_at"], unique=False
    )
    op.create_index("ix_prospects_verified_domain", "prospects", ["verified_domain"], unique=False)
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "OWNER",
                "ADMIN",
                "REVIEWER",
                "READ_ONLY",
                name="user_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "password_change_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mfa_secret_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("mfa_pending_secret_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("mfa_last_used_step", sa.Integer(), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_normalized")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(
        "uq_users_single_owner", "users", ["role"], unique=True, postgresql_where="role = 'OWNER'"
    )
    op.create_table(
        "activity_logs",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user','system','anonymous')", name=op.f("ck_activity_logs_actor_type")
        ),
        sa.CheckConstraint(
            "outcome IN ('success','failure','denied')", name=op.f("ck_activity_logs_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_activity_logs_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_logs")),
    )
    op.create_index(
        op.f("ix_activity_logs_actor_user_id"), "activity_logs", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_activity_logs_entity", "activity_logs", ["entity_type", "entity_id"], unique=False
    )
    op.create_index("ix_activity_logs_occurred_at", "activity_logs", ["occurred_at"], unique=False)
    op.create_table(
        "campaigns",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "PAUSED",
                "COMPLETED",
                "ARCHIVED",
                name="campaign_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "target_countries",
            postgresql.ARRAY(sa.String(length=2)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "target_regions",
            postgresql.ARRAY(sa.String(length=120)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "industries",
            postgresql.ARRAY(sa.String(length=120)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "filters", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("candidate_cap", sa.Integer(), server_default="0", nullable=False),
        sa.Column("daily_budget_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("monthly_budget_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("budget_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column(
            "sending_mode",
            sa.Enum(
                "DISABLED",
                "MANUAL_REVIEW",
                "AUTOMATIC_ELIGIBLE_ONLY",
                name="sending_mode",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DISABLED",
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "candidate_cap >= 0", name=op.f("ck_campaigns_candidate_cap_non_negative")
        ),
        sa.CheckConstraint(
            "daily_budget_minor >= 0 AND monthly_budget_minor >= 0",
            name=op.f("ck_campaigns_budgets_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_campaigns_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
    )
    op.create_index(
        "ix_campaigns_status_created_at", "campaigns", ["status", "created_at"], unique=False
    )
    op.create_table(
        "email_contacts",
        sa.Column("prospect_id", sa.Uuid(), nullable=True),
        sa.Column("email_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column(
            "recipient_type",
            sa.Enum(
                "UNKNOWN",
                "CORPORATE",
                "SOLE_TRADER",
                "INDIVIDUAL",
                "ROLE_ACCOUNT",
                name="recipient_type",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="UNKNOWN",
            nullable=False,
        ),
        sa.Column("role_function", sa.String(length=120), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column(
            "verification_state",
            sa.Enum(
                "UNVERIFIED",
                "VERIFIED",
                "INVALID",
                name="contact_verification_state",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="UNVERIFIED",
            nullable=False,
        ),
        sa.Column("verification_method", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_email_contacts_prospect_id_prospects"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_contacts")),
        sa.UniqueConstraint(
            "prospect_id", "email_hash", name=op.f("uq_email_contacts_prospect_id_email_hash")
        ),
    )
    op.create_index(
        op.f("ix_email_contacts_email_hash"), "email_contacts", ["email_hash"], unique=False
    )
    op.create_index(
        op.f("ix_email_contacts_prospect_id"), "email_contacts", ["prospect_id"], unique=False
    )
    op.create_table(
        "external_place_identifiers",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("place_id", sa.String(length=255), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_external_place_identifiers_prospect_id_prospects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_place_identifiers")),
        sa.UniqueConstraint(
            "provider", "place_id", name=op.f("uq_external_place_identifiers_provider_place_id")
        ),
    )
    op.create_index(
        op.f("ix_external_place_identifiers_prospect_id"),
        "external_place_identifiers",
        ["prospect_id"],
        unique=False,
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_mfa_recovery_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_recovery_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_mfa_recovery_codes_code_hash")),
    )
    op.create_index(
        op.f("ix_mfa_recovery_codes_user_id"), "mfa_recovery_codes", ["user_id"], unique=False
    )
    op.create_table(
        "prospect_sources",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("fact_field", sa.String(length=64), nullable=False),
        sa.Column("safe_value", sa.Text(), nullable=True),
        sa.Column("value_hash", sa.String(length=64), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_version", sa.String(length=64), nullable=True),
        sa.Column("is_independent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "safe_value IS NOT NULL OR value_hash IS NOT NULL",
            name=op.f("ck_prospect_sources_value_present"),
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_prospect_sources_prospect_id_prospects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prospect_sources")),
    )
    op.create_index(
        op.f("ix_prospect_sources_prospect_id"), "prospect_sources", ["prospect_id"], unique=False
    )
    op.create_table(
        "suppressions",
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "scope",
            sa.Enum(
                "GLOBAL",
                "CAMPAIGN",
                name="suppression_scope",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="GLOBAL",
            nullable=False,
        ),
        sa.Column("scope_ref", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "UNSUBSCRIBE",
                "HARD_BOUNCE",
                "COMPLAINT",
                "DO_NOT_CONTACT",
                "MANUAL",
                "LEGAL",
                name="suppression_reason",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_event", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(scope = 'GLOBAL') = (scope_ref = '')",
            name=op.f("ck_suppressions_scope_ref_matches_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_suppressions_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppressions")),
        sa.UniqueConstraint(
            "email_hash",
            "scope",
            "scope_ref",
            name=op.f("uq_suppressions_email_hash_scope_scope_ref"),
        ),
    )
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("refresh_token_hash", name=op.f("uq_user_sessions_refresh_token_hash")),
    )
    op.create_index(
        "ix_user_sessions_active", "user_sessions", ["user_id", "revoked_at"], unique=False
    )
    op.create_index(
        op.f("ix_user_sessions_previous_refresh_token_hash"),
        "user_sessions",
        ["previous_refresh_token_hash"],
        unique=False,
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_table(
        "website_audits",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                name="audit_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("audit_version", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desktop_screenshot_key", sa.String(length=512), nullable=True),
        sa.Column("mobile_screenshot_key", sa.String(length=512), nullable=True),
        sa.Column("performance_source", sa.String(length=64), nullable=True),
        sa.Column(
            "scores", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("browser_version", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_website_audits_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_website_audits")),
    )
    op.create_index(
        op.f("ix_website_audits_prospect_id"), "website_audits", ["prospect_id"], unique=False
    )
    op.create_index(
        "ix_website_audits_status_created_at",
        "website_audits",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "api_usage",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("units", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("estimated_cost_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_api_usage_campaign_id_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_api_usage_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_usage")),
    )
    op.create_index(op.f("ix_api_usage_campaign_id"), "api_usage", ["campaign_id"], unique=False)
    op.create_index(
        "ix_api_usage_provider_occurred_at", "api_usage", ["provider", "occurred_at"], unique=False
    )
    op.create_table(
        "audit_findings",
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "INFO",
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="severity",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.String(length=2048), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("screenshot_key", sa.String(length=512), nullable=True),
        sa.Column("viewport", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reproduction_steps", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["audit_id"],
            ["website_audits.id"],
            name=op.f("fk_audit_findings_audit_id_website_audits"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_findings")),
    )
    op.create_index(
        op.f("ix_audit_findings_audit_id"), "audit_findings", ["audit_id"], unique=False
    )
    op.create_table(
        "compliance_assessments",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("email_contact_id", sa.Uuid(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column(
            "recipient_type",
            sa.Enum(
                "UNKNOWN",
                "CORPORATE",
                "SOLE_TRADER",
                "INDIVIDUAL",
                "ROLE_ACCOUNT",
                name="assessment_recipient_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("message_category", sa.String(length=64), nullable=False),
        sa.Column("legal_basis", sa.String(length=64), nullable=True),
        sa.Column("legal_basis_evidence", sa.Text(), nullable=True),
        sa.Column("policy_config_id", sa.Uuid(), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column("provider_policy_version", sa.String(length=32), nullable=True),
        sa.Column(
            "decision",
            sa.Enum(
                "ELIGIBLE",
                "INELIGIBLE",
                "HOLD",
                "HUMAN_REVIEW",
                name="compliance_decision",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason_codes",
            postgresql.ARRAY(sa.String(length=64)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["email_contact_id"],
            ["email_contacts.id"],
            name=op.f("fk_compliance_assessments_email_contact_id_email_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["policy_config_id"],
            ["policy_configs.id"],
            name=op.f("fk_compliance_assessments_policy_config_id_policy_configs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_compliance_assessments_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name=op.f("fk_compliance_assessments_reviewer_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_assessments")),
    )
    op.create_index(
        op.f("ix_compliance_assessments_email_contact_id"),
        "compliance_assessments",
        ["email_contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_compliance_assessments_prospect_id"),
        "compliance_assessments",
        ["prospect_id"],
        unique=False,
    )
    op.create_table(
        "consent_records",
        sa.Column("email_contact_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["email_contact_id"],
            ["email_contacts.id"],
            name=op.f("fk_consent_records_email_contact_id_email_contacts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_records")),
    )
    op.create_index(
        op.f("ix_consent_records_email_contact_id"),
        "consent_records",
        ["email_contact_id"],
        unique=False,
    )
    op.create_table(
        "design_projects",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                name="design_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("brief_schema_version", sa.String(length=32), nullable=True),
        sa.Column("design_tokens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("page_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("renderer_version", sa.String(length=32), nullable=True),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audit_id"],
            ["website_audits.id"],
            name=op.f("fk_design_projects_audit_id_website_audits"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_design_projects_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_projects")),
    )
    op.create_index(
        op.f("ix_design_projects_prospect_id"), "design_projects", ["prospect_id"], unique=False
    )
    op.create_table(
        "prospect_campaigns",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_prospect_campaigns_campaign_id_campaigns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_prospect_campaigns_prospect_id_prospects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prospect_campaigns")),
        sa.UniqueConstraint(
            "prospect_id", "campaign_id", name=op.f("uq_prospect_campaigns_prospect_id_campaign_id")
        ),
    )
    op.create_index(
        op.f("ix_prospect_campaigns_campaign_id"),
        "prospect_campaigns",
        ["campaign_id"],
        unique=False,
    )
    op.create_table(
        "design_pages",
        sa.Column("design_project_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("page_type", sa.String(length=40), nullable=False),
        sa.Column(
            "content", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "render_status",
            sa.Enum(
                "PENDING",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                name="render_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("screenshot_key", sa.String(length=512), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["design_project_id"],
            ["design_projects.id"],
            name=op.f("fk_design_pages_design_project_id_design_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_pages")),
        sa.UniqueConstraint(
            "design_project_id",
            "slug",
            "version",
            name=op.f("uq_design_pages_design_project_id_slug_version"),
        ),
    )
    op.create_table(
        "proposals",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("design_project_id", sa.Uuid(), nullable=False),
        sa.Column("pdf_storage_key", sa.String(length=512), nullable=True),
        sa.Column("proposal_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("template_version", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "READY",
                "SENT",
                "EXPIRED",
                "REVOKED",
                name="proposal_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["design_project_id"],
            ["design_projects.id"],
            name=op.f("fk_proposals_design_project_id_design_projects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_proposals_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposals")),
    )
    op.create_index(op.f("ix_proposals_prospect_id"), "proposals", ["prospect_id"], unique=False)
    op.create_table(
        "outreach_messages",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("email_contact_id", sa.Uuid(), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("message_category", sa.String(length=64), nullable=False),
        sa.Column("subject_version", sa.String(length=32), nullable=True),
        sa.Column("body_version", sa.String(length=32), nullable=True),
        sa.Column("body_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("body_storage_key", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PENDING_REVIEW",
                "SCHEDULED",
                "SENDING",
                "ACCEPTED",
                "SENT",
                "DELIVERED",
                "BOUNCED",
                "COMPLAINED",
                "FAILED",
                "CANCELLED",
                "AMBIGUOUS",
                name="message_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compliance_assessment_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_outreach_messages_campaign_id_campaigns"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["compliance_assessment_id"],
            ["compliance_assessments.id"],
            name=op.f("fk_outreach_messages_compliance_assessment_id_compliance_assessments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["email_contact_id"],
            ["email_contacts.id"],
            name=op.f("fk_outreach_messages_email_contact_id_email_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name=op.f("fk_outreach_messages_proposal_id_proposals"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_outreach_messages_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outreach_messages")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_outreach_messages_idempotency_key")),
        sa.UniqueConstraint(
            "provider",
            "provider_message_id",
            name=op.f("uq_outreach_messages_provider_provider_message_id"),
        ),
    )
    op.create_index(
        op.f("ix_outreach_messages_prospect_id"), "outreach_messages", ["prospect_id"], unique=False
    )
    op.create_index(
        "ix_outreach_messages_status_created_at",
        "outreach_messages",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "preview_deployments",
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "EXPIRED",
                "REVOKED",
                name="preview_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name=op.f("fk_preview_deployments_proposal_id_proposals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preview_deployments")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_preview_deployments_token_hash")),
    )
    op.create_index(
        op.f("ix_preview_deployments_proposal_id"),
        "preview_deployments",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_preview_deployments_status_expires",
        "preview_deployments",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_table(
        "email_events",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("outreach_message_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "processing_state",
            sa.Enum(
                "RECEIVED",
                "PROCESSED",
                "IGNORED",
                "FAILED",
                name="event_processing_state",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="RECEIVED",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["outreach_message_id"],
            ["outreach_messages.id"],
            name=op.f("fk_email_events_outreach_message_id_outreach_messages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_events")),
        sa.UniqueConstraint(
            "provider", "provider_event_id", name=op.f("uq_email_events_provider_provider_event_id")
        ),
    )
    op.create_index(
        op.f("ix_email_events_outreach_message_id"),
        "email_events",
        ["outreach_message_id"],
        unique=False,
    )
    op.create_table(
        "replies",
        sa.Column("prospect_id", sa.Uuid(), nullable=True),
        sa.Column("email_contact_id", sa.Uuid(), nullable=True),
        sa.Column("outreach_message_id", sa.Uuid(), nullable=True),
        sa.Column("provider_thread_id", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body_storage_key", sa.String(length=512), nullable=True),
        sa.Column(
            "needs_human_review", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["email_contact_id"],
            ["email_contacts.id"],
            name=op.f("fk_replies_email_contact_id_email_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["outreach_message_id"],
            ["outreach_messages.id"],
            name=op.f("fk_replies_outreach_message_id_outreach_messages"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_replies_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_replies")),
    )
    op.create_index(op.f("ix_replies_prospect_id"), "replies", ["prospect_id"], unique=False)

    # Append-only activity log: block UPDATE, DELETE and TRUNCATE for every role.
    op.execute(
        """
        CREATE FUNCTION activity_logs_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'activity_logs is append-only (% blocked)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER activity_logs_no_update_delete BEFORE UPDATE OR DELETE ON activity_logs "
        "FOR EACH ROW EXECUTE FUNCTION activity_logs_append_only()"
    )
    op.execute(
        "CREATE TRIGGER activity_logs_no_truncate BEFORE TRUNCATE ON activity_logs "
        "FOR EACH STATEMENT EXECUTE FUNCTION activity_logs_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS activity_logs_no_truncate ON activity_logs")
    op.execute("DROP TRIGGER IF EXISTS activity_logs_no_update_delete ON activity_logs")
    op.execute("DROP FUNCTION IF EXISTS activity_logs_append_only()")
    op.drop_index(op.f("ix_replies_prospect_id"), table_name="replies")
    op.drop_table("replies")
    op.drop_index(op.f("ix_email_events_outreach_message_id"), table_name="email_events")
    op.drop_table("email_events")
    op.drop_index("ix_preview_deployments_status_expires", table_name="preview_deployments")
    op.drop_index(op.f("ix_preview_deployments_proposal_id"), table_name="preview_deployments")
    op.drop_table("preview_deployments")
    op.drop_index("ix_outreach_messages_status_created_at", table_name="outreach_messages")
    op.drop_index(op.f("ix_outreach_messages_prospect_id"), table_name="outreach_messages")
    op.drop_table("outreach_messages")
    op.drop_index(op.f("ix_proposals_prospect_id"), table_name="proposals")
    op.drop_table("proposals")
    op.drop_table("design_pages")
    op.drop_index(op.f("ix_prospect_campaigns_campaign_id"), table_name="prospect_campaigns")
    op.drop_table("prospect_campaigns")
    op.drop_index(op.f("ix_design_projects_prospect_id"), table_name="design_projects")
    op.drop_table("design_projects")
    op.drop_index(op.f("ix_consent_records_email_contact_id"), table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index(
        op.f("ix_compliance_assessments_prospect_id"), table_name="compliance_assessments"
    )
    op.drop_index(
        op.f("ix_compliance_assessments_email_contact_id"), table_name="compliance_assessments"
    )
    op.drop_table("compliance_assessments")
    op.drop_index(op.f("ix_audit_findings_audit_id"), table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_index("ix_api_usage_provider_occurred_at", table_name="api_usage")
    op.drop_index(op.f("ix_api_usage_campaign_id"), table_name="api_usage")
    op.drop_table("api_usage")
    op.drop_index("ix_website_audits_status_created_at", table_name="website_audits")
    op.drop_index(op.f("ix_website_audits_prospect_id"), table_name="website_audits")
    op.drop_table("website_audits")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_previous_refresh_token_hash"), table_name="user_sessions")
    op.drop_index("ix_user_sessions_active", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("suppressions")
    op.drop_index(op.f("ix_prospect_sources_prospect_id"), table_name="prospect_sources")
    op.drop_table("prospect_sources")
    op.drop_index(op.f("ix_mfa_recovery_codes_user_id"), table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_index(
        op.f("ix_external_place_identifiers_prospect_id"), table_name="external_place_identifiers"
    )
    op.drop_table("external_place_identifiers")
    op.drop_index(op.f("ix_email_contacts_prospect_id"), table_name="email_contacts")
    op.drop_index(op.f("ix_email_contacts_email_hash"), table_name="email_contacts")
    op.drop_table("email_contacts")
    op.drop_index("ix_campaigns_status_created_at", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index("ix_activity_logs_occurred_at", table_name="activity_logs")
    op.drop_index("ix_activity_logs_entity", table_name="activity_logs")
    op.drop_index(op.f("ix_activity_logs_actor_user_id"), table_name="activity_logs")
    op.drop_table("activity_logs")
    op.drop_index("uq_users_single_owner", table_name="users", postgresql_where="role = 'OWNER'")
    op.drop_table("users")
    op.drop_index("ix_prospects_verified_domain", table_name="prospects")
    op.drop_index("ix_prospects_state_created_at", table_name="prospects")
    op.drop_index("ix_prospects_country_state", table_name="prospects")
    op.drop_table("prospects")
    op.drop_index(
        "uq_policy_configs_one_active",
        table_name="policy_configs",
        postgresql_where="status = 'ACTIVE'",
    )
    op.drop_table("policy_configs")
    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_index("ix_jobs_queue_status_available", table_name="jobs")
    op.drop_index(op.f("ix_jobs_correlation_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_assets_sha256"), table_name="assets")
    op.drop_table("assets")
