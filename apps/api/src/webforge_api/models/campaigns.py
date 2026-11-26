from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import CampaignStatus, SendingMode


class Campaign(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        str_enum(CampaignStatus, "campaign_status"),
        default=CampaignStatus.DRAFT,
        server_default=CampaignStatus.DRAFT.value,
        nullable=False,
    )
    target_countries: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)), default=list, server_default="{}", nullable=False
    )
    target_regions: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}", nullable=False
    )
    industries: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}", nullable=False
    )
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    candidate_cap: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    daily_budget_minor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    monthly_budget_minor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    budget_currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD", nullable=False
    )
    sending_mode: Mapped[SendingMode] = mapped_column(
        str_enum(SendingMode, "sending_mode"),
        default=SendingMode.DISABLED,
        server_default=SendingMode.DISABLED.value,
        nullable=False,
    )
    policy_version: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("candidate_cap >= 0", name="candidate_cap_non_negative"),
        CheckConstraint(
            "daily_budget_minor >= 0 AND monthly_budget_minor >= 0", name="budgets_non_negative"
        ),
        Index("ix_campaigns_status_created_at", "status", "created_at"),
    )
