"""design validations: offline browser validation reports and screenshot evidence per render.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26 18:34:55.847012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "design_validations",
        sa.Column("render_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("validator_version", sa.String(length=32), nullable=False),
        sa.Column("browser_version", sa.String(length=64), nullable=True),
        sa.Column("site_sha256", sa.String(length=64), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "screenshots",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('READY','NEEDS_REVISION')",
            name=op.f("ck_design_validations_design_validation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["render_id"],
            ["design_renders.id"],
            name=op.f("fk_design_validations_render_id_design_renders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_validations")),
    )
    op.create_index(
        op.f("ix_design_validations_render_id"), "design_validations", ["render_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_design_validations_render_id"), table_name="design_validations")
    op.drop_table("design_validations")
