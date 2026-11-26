"""source registry, domain verification, transient cache, Places candidates,
independent-only provenance and precise usage costs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26 13:42:33.810798
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

PLACES_POLICY_URLS = [
    "https://developers.google.com/maps/documentation/places/web-service/policies",
    "https://developers.google.com/maps/documentation/places/web-service/choose-fields",
    "https://developers.google.com/maps/documentation/places/web-service/data-fields",
    "https://developers.google.com/maps/documentation/places/web-service/usage-and-billing",
    "https://developers.google.com/maps/documentation/places/web-service/place-id",
    "https://cloud.google.com/maps-platform/terms/maps-service-terms",
]

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # prospect_sources gains NOT NULL provenance columns; no code wrote to it before 0002.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM prospect_sources")).scalar():
        raise RuntimeError("prospect_sources must be empty before migration 0002; see docs")
    op.create_table(
        "source_registrations",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "MAPS_API",
                "OFFICIAL_WEBSITE",
                "REGISTRY",
                "LICENSED_PROVIDER",
                "OWNER_UPLOAD",
                "MOCK",
                name="source_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DISABLED",
                "ENABLED",
                name="source_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="DISABLED",
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "persistable_fields",
            postgresql.ARRAY(sa.String(length=64)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "cache_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "attribution_required", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("attribution_text", sa.String(length=120), nullable=True),
        sa.Column("policy_urls", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("terms_url", sa.String(length=2048), nullable=True),
        sa.Column("terms_version", sa.String(length=64), nullable=True),
        sa.Column("terms_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_changed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status_reason", sa.String(length=500), nullable=True),
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
            "status <> 'ENABLED' OR source_type = 'MOCK' OR (terms_url IS NOT NULL AND terms_version IS NOT NULL AND terms_reviewed_at IS NOT NULL AND reviewed_by_user_id IS NOT NULL)",
            name=op.f("ck_source_registrations_enabled_requires_terms_review"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_source_registrations_reviewed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["status_changed_by_user_id"],
            ["users.id"],
            name=op.f("fk_source_registrations_status_changed_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_registrations")),
        sa.UniqueConstraint("key", name=op.f("uq_source_registrations_key")),
    )
    op.create_table(
        "transient_source_values",
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "expires_at > fetched_at", name=op.f("ck_transient_source_values_expiry_after_fetch")
        ),
        sa.ForeignKeyConstraint(
            ["source_key"],
            ["source_registrations.key"],
            name=op.f("fk_transient_source_values_source_key_source_registrations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transient_source_values")),
        sa.UniqueConstraint(
            "source_key",
            "external_ref",
            "field",
            name=op.f("uq_transient_source_values_source_key_external_ref_field"),
        ),
    )
    op.create_index(
        "ix_transient_source_values_expires_at",
        "transient_source_values",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "domain_verifications",
        sa.Column("prospect_id", sa.Uuid(), nullable=True),
        sa.Column("place_identifier_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("domain", sa.String(length=253), nullable=True),
        sa.Column("candidate_origin", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "VERIFIED",
                "HOLD",
                "REJECTED",
                name="domain_verification_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.ARRAY(sa.String(length=64)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "evidence", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_domain_verifications_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["checked_by_user_id"],
            ["users.id"],
            name=op.f("fk_domain_verifications_checked_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["place_identifier_id"],
            ["external_place_identifiers.id"],
            name=op.f("fk_domain_verifications_place_identifier_id_external_place_identifiers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prospect_id"],
            ["prospects.id"],
            name=op.f("fk_domain_verifications_prospect_id_prospects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domain_verifications")),
    )
    op.create_index(
        op.f("ix_domain_verifications_domain"), "domain_verifications", ["domain"], unique=False
    )
    op.create_index(
        op.f("ix_domain_verifications_place_identifier_id"),
        "domain_verifications",
        ["place_identifier_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_domain_verifications_prospect_id"),
        "domain_verifications",
        ["prospect_id"],
        unique=False,
    )
    op.add_column("api_usage", sa.Column("sku", sa.String(length=64), nullable=True))
    op.add_column(
        "api_usage",
        sa.Column(
            "outcome",
            sa.Enum(
                "RESERVED",
                "SUCCESS",
                "ERROR",
                name="usage_outcome",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="SUCCESS",
            nullable=False,
        ),
    )
    op.add_column(
        "api_usage",
        sa.Column("cost_milliminor", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.add_column("external_place_identifiers", sa.Column("campaign_id", sa.Uuid(), nullable=True))
    op.add_column(
        "external_place_identifiers",
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "OBSOLETE",
                name="place_id_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
    )
    op.add_column(
        "external_place_identifiers",
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.alter_column(
        "external_place_identifiers", "prospect_id", existing_type=sa.UUID(), nullable=True
    )
    op.create_index(
        op.f("ix_external_place_identifiers_campaign_id"),
        "external_place_identifiers",
        ["campaign_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_external_place_identifiers_campaign_id_campaigns"),
        "external_place_identifiers",
        "campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("prospect_sources", sa.Column("source_key", sa.String(length=64), nullable=True))
    op.add_column(
        "prospect_sources",
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
    )
    op.add_column(
        "prospect_sources", sa.Column("verification_method", sa.String(length=64), nullable=False)
    )
    op.alter_column(
        "prospect_sources",
        "source_type",
        existing_type=sa.VARCHAR(length=32),
        type_=sa.Enum(
            "OFFICIAL_WEBSITE",
            "REGISTRY",
            "LICENSED_PROVIDER",
            "OWNER_PROVIDED",
            name="provenance_source",
            native_enum=False,
            create_constraint=True,
        ),
        existing_nullable=False,
    )
    op.create_foreign_key(
        op.f("fk_prospect_sources_source_key_source_registrations"),
        "prospect_sources",
        "source_registrations",
        ["source_key"],
        ["key"],
        ondelete="RESTRICT",
    )
    # The type change above also creates CHECK ck_prospect_sources_provenance_source.

    registrations = sa.table(
        "source_registrations",
        sa.column("key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("source_type", sa.String),
        sa.column("description", sa.Text),
        sa.column("persistable_fields", postgresql.ARRAY(sa.String)),
        sa.column("cache_rules", postgresql.JSONB),
        sa.column("attribution_required", sa.Boolean),
        sa.column("attribution_text", sa.String),
        sa.column("policy_urls", postgresql.ARRAY(sa.Text)),
    )
    op.bulk_insert(
        registrations,
        [
            {
                "key": "google_places",
                "display_name": "Google Places API (New)",
                "source_type": "MAPS_API",
                "description": (
                    "Discovery of candidate places. Only Place IDs are stored; every other field "
                    "is Google Maps Content, used transiently and shown with attribution."
                ),
                "persistable_fields": ["place_id"],
                "cache_rules": {"location": 2592000},
                "attribution_required": True,
                "attribution_text": "Google Maps",
                "policy_urls": PLACES_POLICY_URLS,
            },
            {
                "key": "official_website",
                "display_name": "Business-owned official websites",
                "source_type": "OFFICIAL_WEBSITE",
                "description": (
                    "Independent verification of business identity from the business's own public "
                    "website. Public pages only, robots.txt respected, no forms or logins."
                ),
                "persistable_fields": ["business_name", "website_url", "verified_domain"],
                "cache_rules": {},
                "attribution_required": False,
                "attribution_text": None,
                "policy_urls": [],
            },
            {
                "key": "mock_places",
                "display_name": "Mock places (development and tests only)",
                "source_type": "MOCK",
                "description": "Deterministic fake places for development and CI. Never enabled in production.",
                "persistable_fields": ["place_id"],
                "cache_rules": {},
                "attribution_required": True,
                "attribution_text": "Mock data - not Google Maps",
                "policy_urls": [],
            },
        ],
    )


def downgrade() -> None:
    # Candidate Place IDs (no prospect yet) cannot satisfy the 0001 NOT NULL constraint.
    op.execute("DELETE FROM external_place_identifiers WHERE prospect_id IS NULL")
    op.drop_constraint(
        op.f("fk_prospect_sources_source_key_source_registrations"),
        "prospect_sources",
        type_="foreignkey",
    )
    op.alter_column(
        "prospect_sources",
        "source_type",
        existing_type=sa.Enum(
            "OFFICIAL_WEBSITE",
            "REGISTRY",
            "LICENSED_PROVIDER",
            "OWNER_PROVIDED",
            name="provenance_source",
            native_enum=False,
            create_constraint=True,
        ),
        type_=sa.VARCHAR(length=32),
        existing_nullable=False,
    )
    op.drop_column("prospect_sources", "verification_method")
    op.drop_column("prospect_sources", "confidence")
    op.drop_column("prospect_sources", "source_key")
    op.drop_constraint(
        op.f("fk_external_place_identifiers_campaign_id_campaigns"),
        "external_place_identifiers",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_external_place_identifiers_campaign_id"), table_name="external_place_identifiers"
    )
    op.alter_column(
        "external_place_identifiers", "prospect_id", existing_type=sa.UUID(), nullable=False
    )
    op.drop_column("external_place_identifiers", "first_seen_at")
    op.drop_column("external_place_identifiers", "status")
    op.drop_column("external_place_identifiers", "campaign_id")
    op.drop_column("api_usage", "cost_milliminor")
    op.drop_column("api_usage", "outcome")
    op.drop_column("api_usage", "sku")
    op.drop_index(op.f("ix_domain_verifications_prospect_id"), table_name="domain_verifications")
    op.drop_index(
        op.f("ix_domain_verifications_place_identifier_id"), table_name="domain_verifications"
    )
    op.drop_index(op.f("ix_domain_verifications_domain"), table_name="domain_verifications")
    op.drop_table("domain_verifications")
    op.drop_index("ix_transient_source_values_expires_at", table_name="transient_source_values")
    op.drop_table("transient_source_values")
    op.drop_table("source_registrations")
