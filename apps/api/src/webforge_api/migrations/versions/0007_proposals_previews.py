"""proposals and previews: render/validation links, PDF hash, checks, deletion and access tracking.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-26 18:49:15.486711
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "preview_deployments",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("proposals", sa.Column("render_id", sa.Uuid(), nullable=True))
    op.add_column("proposals", sa.Column("validation_id", sa.Uuid(), nullable=True))
    op.add_column("proposals", sa.Column("pdf_sha256", sa.String(length=64), nullable=True))
    op.add_column("proposals", sa.Column("pdf_bytes", sa.BigInteger(), nullable=True))
    op.add_column("proposals", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column("proposals", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "proposals",
        sa.Column(
            "checks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )
    op.add_column("proposals", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        op.f("uq_proposals_design_project_id_proposal_version"),
        "proposals",
        ["design_project_id", "proposal_version"],
    )
    op.create_foreign_key(
        op.f("fk_proposals_validation_id_design_validations"),
        "proposals",
        "design_validations",
        ["validation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_proposals_render_id_design_renders"),
        "proposals",
        "design_renders",
        ["render_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_proposals_render_id_design_renders"), "proposals", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_proposals_validation_id_design_validations"), "proposals", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("uq_proposals_design_project_id_proposal_version"), "proposals", type_="unique"
    )
    op.drop_column("proposals", "deleted_at")
    op.drop_column("proposals", "checks")
    op.drop_column("proposals", "summary")
    op.drop_column("proposals", "page_count")
    op.drop_column("proposals", "pdf_bytes")
    op.drop_column("proposals", "pdf_sha256")
    op.drop_column("proposals", "validation_id")
    op.drop_column("proposals", "render_id")
    op.drop_column("preview_deployments", "last_accessed_at")
