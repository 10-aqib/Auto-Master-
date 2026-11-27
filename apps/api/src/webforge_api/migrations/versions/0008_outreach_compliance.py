"""outreach compliance: assessment checks, message subject/recipient hash/unsubscribe token hash, reply storage.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26 19:10:06.364075
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "compliance_assessments",
        sa.Column(
            "checks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
    )
    op.add_column("outreach_messages", sa.Column("subject", sa.Text(), nullable=True))
    op.add_column(
        "outreach_messages", sa.Column("recipient_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "outreach_messages",
        sa.Column("unsubscribe_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("outreach_messages", sa.Column("preview_id", sa.Uuid(), nullable=True))
    op.add_column("outreach_messages", sa.Column("approved_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "outreach_messages", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "outreach_messages", sa.Column("cancelled_reason", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_outreach_messages_recipient_hash"),
        "outreach_messages",
        ["recipient_hash"],
        unique=False,
    )
    op.create_unique_constraint(
        op.f("uq_outreach_messages_unsubscribe_token_hash"),
        "outreach_messages",
        ["unsubscribe_token_hash"],
    )
    op.create_foreign_key(
        op.f("fk_outreach_messages_approved_by_user_id_users"),
        "outreach_messages",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_outreach_messages_preview_id_preview_deployments"),
        "outreach_messages",
        "preview_deployments",
        ["preview_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("replies", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("replies", sa.Column("provider_event_id", sa.String(length=255), nullable=True))
    op.add_column("replies", sa.Column("from_hash", sa.String(length=64), nullable=True))
    op.add_column("replies", sa.Column("body_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column("replies", sa.Column("subject", sa.Text(), nullable=True))
    op.add_column("replies", sa.Column("handled_by_user_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_replies_provider_provider_event_id"), "replies", ["provider", "provider_event_id"]
    )
    op.create_foreign_key(
        op.f("fk_replies_handled_by_user_id_users"),
        "replies",
        "users",
        ["handled_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_replies_handled_by_user_id_users"), "replies", type_="foreignkey")
    op.drop_constraint(op.f("uq_replies_provider_provider_event_id"), "replies", type_="unique")
    op.drop_column("replies", "handled_by_user_id")
    op.drop_column("replies", "subject")
    op.drop_column("replies", "body_encrypted")
    op.drop_column("replies", "from_hash")
    op.drop_column("replies", "provider_event_id")
    op.drop_column("replies", "provider")
    op.drop_constraint(
        op.f("fk_outreach_messages_preview_id_preview_deployments"),
        "outreach_messages",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_outreach_messages_approved_by_user_id_users"),
        "outreach_messages",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_outreach_messages_unsubscribe_token_hash"), "outreach_messages", type_="unique"
    )
    op.drop_index(op.f("ix_outreach_messages_recipient_hash"), table_name="outreach_messages")
    op.drop_column("outreach_messages", "cancelled_reason")
    op.drop_column("outreach_messages", "approved_at")
    op.drop_column("outreach_messages", "approved_by_user_id")
    op.drop_column("outreach_messages", "preview_id")
    op.drop_column("outreach_messages", "unsubscribe_token_hash")
    op.drop_column("outreach_messages", "recipient_hash")
    op.drop_column("outreach_messages", "subject")
    op.drop_column("compliance_assessments", "checks")
