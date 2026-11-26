"""design renders: versioned deterministic six-page renders with one active version per project.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26 18:16:47.736177
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "design_renders",
        sa.Column("design_project_id", sa.Uuid(), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("renderer_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("variant", sa.String(length=32), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "scan_issues",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('RENDERED','APPROVED','REJECTED','FAILED')",
            name=op.f("ck_design_renders_design_render_status"),
        ),
        sa.ForeignKeyConstraint(
            ["brief_id"],
            ["design_briefs.id"],
            name=op.f("fk_design_renders_brief_id_design_briefs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["design_project_id"],
            ["design_projects.id"],
            name=op.f("fk_design_renders_design_project_id_design_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_design_renders_reviewed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_renders")),
        sa.UniqueConstraint(
            "design_project_id", "version", name=op.f("uq_design_renders_design_project_id_version")
        ),
    )
    op.create_index(
        op.f("ix_design_renders_design_project_id"),
        "design_renders",
        ["design_project_id"],
        unique=False,
    )
    op.create_index(
        "uq_design_renders_one_active",
        "design_renders",
        ["design_project_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_design_renders_one_active",
        table_name="design_renders",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(op.f("ix_design_renders_design_project_id"), table_name="design_renders")
    op.drop_table("design_renders")
