"""redact unverified Maps website URLs: domain checks that started from Google's websiteUri and did not verify.

Google's websiteUri is Maps Content. A URL it supplied is kept only when the business's own site confirmed it.
Data-only migration; the redaction cannot be reversed, so downgrade does nothing.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE domain_verifications SET candidate_url = :redacted, final_url = NULL, domain = NULL, "
            "evidence = '{}'::jsonb WHERE candidate_origin LIKE :origin AND status <> 'VERIFIED'"
        ).bindparams(redacted="(not retained: Maps content)", origin="%:websiteUri (transient)")
    )


def downgrade() -> None:
    pass  # redacted values are gone by design
