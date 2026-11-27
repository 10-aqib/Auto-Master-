"""backup runs: recorded backups and restore tests for the operations view.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27 07:04:11.077889
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=512), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('backup','restore_test')", name=op.f("ck_backup_runs_backup_kind")
        ),
        sa.CheckConstraint("status IN ('ok','failed')", name=op.f("ck_backup_runs_backup_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )
    op.create_index(
        op.f("ix_backup_runs_finished_at"), "backup_runs", ["finished_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_backup_runs_finished_at"), table_name="backup_runs")
    op.drop_table("backup_runs")
