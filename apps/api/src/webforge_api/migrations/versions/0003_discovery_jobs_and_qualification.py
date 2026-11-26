"""discovery jobs and qualification: system controls (pause), qualification results,
merge history, branch keys, do-not-contact flag, job results, MERGED state.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26 14:23:13.008751
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospect_merges",
        sa.Column("from_prospect_id", sa.Uuid(), nullable=False),
        sa.Column("into_prospect_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("merged_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "merged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "from_prospect_id <> into_prospect_id",
            name=op.f("ck_prospect_merges_distinct_prospects"),
        ),
        sa.ForeignKeyConstraint(
            ["from_prospect_id"],
            ["prospects.id"],
            name=op.f("fk_prospect_merges_from_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["into_prospect_id"],
            ["prospects.id"],
            name=op.f("fk_prospect_merges_into_prospect_id_prospects"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["merged_by_user_id"],
            ["users.id"],
            name=op.f("fk_prospect_merges_merged_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prospect_merges")),
    )
    op.create_index(
        op.f("ix_prospect_merges_from_prospect_id"),
        "prospect_merges",
        ["from_prospect_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_prospect_merges_into_prospect_id"),
        "prospect_merges",
        ["into_prospect_id"],
        unique=False,
    )
    op.create_table(
        "system_controls",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_system_controls_updated_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_controls")),
    )
    op.create_table(
        "qualification_results",
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("rubric_version", sa.String(length=16), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "STRONG",
                "POTENTIAL",
                "INVESTIGATE",
                "REJECTED",
                "MANUAL_REVIEW",
                name="qualification_outcome",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("evidence_coverage", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.ARRAY(sa.String(length=64)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_qualification_results_campaign_id_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_qualification_results_prospect_id_prospects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_results")),
    )
    op.create_index(
        op.f("ix_qualification_results_prospect_id"),
        "qualification_results",
        ["prospect_id"],
        unique=False,
    )
    op.add_column(
        "jobs", sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("jobs", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_jobs_created_by_user_id_users"),
        "jobs",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "prospects",
        sa.Column("branch_key", sa.String(length=255), server_default="", nullable=False),
    )
    op.add_column(
        "prospects",
        sa.Column("do_not_contact", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index(
        "ix_prospects_domain_branch", "prospects", ["verified_domain", "branch_key"], unique=False
    )

    # Add MERGED to the prospect_state CHECK (enum stored as VARCHAR + CHECK).
    op.drop_constraint(op.f("ck_prospects_prospect_state"), "prospects", type_="check")
    op.create_check_constraint(
        op.f("ck_prospects_prospect_state"),
        "prospects",
        "state IN ('DISCOVERED', 'SOURCE_VERIFYING', 'VERIFIED', 'DEDUPLICATED', 'QUALIFYING', 'QUALIFIED', 'AUDITING', 'AUDITED', 'GENERATING_DESIGN', 'VALIDATING', 'PROPOSAL_READY', 'COMPLIANCE_CHECK', 'HUMAN_REVIEW', 'SCHEDULED', 'SENT', 'DELIVERED', 'REPLIED', 'INTERESTED', 'CLIENT', 'REJECTED', 'FAILED', 'BOUNCED', 'UNSUBSCRIBED', 'DO_NOT_CONTACT', 'POLICY_HOLD', 'EXPIRED', 'MERGED')",
    )
    op.execute(
        "INSERT INTO system_controls (key, enabled, reason) VALUES "
        "('global_pause', true, 'Initial state: paused until the owner resumes'),"
        "('email_pause', true, 'Initial state: email paused')"
    )
    op.execute(
        "UPDATE source_registrations SET persistable_fields = "
        "array_append(persistable_fields, 'industry') WHERE key = 'official_website'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE source_registrations SET persistable_fields = "
        "array_remove(persistable_fields, 'industry') WHERE key = 'official_website'"
    )
    op.execute("UPDATE prospects SET state = 'REJECTED' WHERE state = 'MERGED'")
    op.drop_constraint(op.f("ck_prospects_prospect_state"), "prospects", type_="check")
    op.create_check_constraint(
        op.f("ck_prospects_prospect_state"),
        "prospects",
        "state IN ('DISCOVERED', 'SOURCE_VERIFYING', 'VERIFIED', 'DEDUPLICATED', 'QUALIFYING', 'QUALIFIED', 'AUDITING', 'AUDITED', 'GENERATING_DESIGN', 'VALIDATING', 'PROPOSAL_READY', 'COMPLIANCE_CHECK', 'HUMAN_REVIEW', 'SCHEDULED', 'SENT', 'DELIVERED', 'REPLIED', 'INTERESTED', 'CLIENT', 'REJECTED', 'FAILED', 'BOUNCED', 'UNSUBSCRIBED', 'DO_NOT_CONTACT', 'POLICY_HOLD', 'EXPIRED')",
    )
    op.drop_index("ix_prospects_domain_branch", table_name="prospects")
    op.drop_column("prospects", "do_not_contact")
    op.drop_column("prospects", "branch_key")
    op.drop_constraint(op.f("fk_jobs_created_by_user_id_users"), "jobs", type_="foreignkey")
    op.drop_column("jobs", "created_by_user_id")
    op.drop_column("jobs", "result")
    op.drop_index(op.f("ix_qualification_results_prospect_id"), table_name="qualification_results")
    op.drop_table("qualification_results")
    op.drop_table("system_controls")
    op.drop_index(op.f("ix_prospect_merges_into_prospect_id"), table_name="prospect_merges")
    op.drop_index(op.f("ix_prospect_merges_from_prospect_id"), table_name="prospect_merges")
    op.drop_table("prospect_merges")
