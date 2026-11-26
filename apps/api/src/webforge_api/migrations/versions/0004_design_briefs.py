"""design briefs: versioned AI briefs with model, prompt and schema versions, usage and review.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26 17:59:05.874031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "design_briefs",
        sa.Column("design_project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_output_sha256", sa.String(length=64), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("facts_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "validation_issues",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_milliminor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'REJECTED', 'NEEDS_REVIEW')",
            name=op.f("ck_design_briefs_brief_status"),
        ),
        sa.ForeignKeyConstraint(
            ["design_project_id"],
            ["design_projects.id"],
            name=op.f("fk_design_briefs_design_project_id_design_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_design_briefs_reviewed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_briefs")),
        sa.UniqueConstraint(
            "design_project_id", "version", name=op.f("uq_design_briefs_design_project_id_version")
        ),
    )
    op.create_index(
        op.f("ix_design_briefs_design_project_id"),
        "design_briefs",
        ["design_project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_design_briefs_design_project_id"), table_name="design_briefs")
    op.drop_table("design_briefs")
