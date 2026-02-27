"""add listings and failed_scrapes tables

Revision ID: 20260225_0002
Revises: 20260225_0001
Create Date: 2026-02-25 18:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260225_0002"
down_revision: Union[str, None] = "20260225_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "listings" not in existing:
        op.create_table(
            "listings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("external_id", sa.String(length=32), nullable=False),
            sa.Column("url", sa.String(length=512), nullable=False),
            sa.Column("maker", sa.String(length=128), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("grade", sa.String(length=256), nullable=True),
            sa.Column("color", sa.String(length=128), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("mileage_km", sa.Integer(), nullable=True),
            sa.Column("price_jpy", sa.Integer(), nullable=True),
            sa.Column("price_rub", sa.Integer(), nullable=True),
            sa.Column("total_price_jpy", sa.Integer(), nullable=True),
            sa.Column("total_price_rub", sa.Integer(), nullable=True),
            sa.Column("prefecture", sa.String(length=128), nullable=True),
            sa.Column("shop_name", sa.String(length=256), nullable=True),
            sa.Column("shop_address", sa.String(length=512), nullable=True),
            sa.Column("shop_phone", sa.String(length=64), nullable=True),
            sa.Column("transmission", sa.String(length=128), nullable=True),
            sa.Column("drive_type", sa.String(length=128), nullable=True),
            sa.Column("engine_cc", sa.Integer(), nullable=True),
            sa.Column("fuel", sa.String(length=128), nullable=True),
            sa.Column("steering", sa.String(length=64), nullable=True),
            sa.Column("body_type", sa.String(length=128), nullable=True),
            sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
        )
    else:
        listing_columns = {column["name"] for column in inspector.get_columns("listings")}
        if "external_id" not in listing_columns:
            op.add_column("listings", sa.Column("external_id", sa.String(length=32), nullable=True))
            if "source_listing_id" in listing_columns:
                op.execute("UPDATE listings SET external_id = source_listing_id WHERE external_id IS NULL")
            op.execute("UPDATE listings SET external_id = CONCAT('legacy-', id::text) WHERE external_id IS NULL")
            op.alter_column("listings", "external_id", nullable=False)

        if "is_active" not in listing_columns:
            op.add_column("listings", sa.Column("is_active", sa.Boolean(), nullable=True))
            if "inactive" in listing_columns:
                op.execute("UPDATE listings SET is_active = NOT inactive WHERE is_active IS NULL")
            op.execute("UPDATE listings SET is_active = TRUE WHERE is_active IS NULL")
            op.alter_column("listings", "is_active", nullable=False)

        if "last_seen_at" not in listing_columns:
            op.add_column(
                "listings",
                sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
            )
            op.execute("UPDATE listings SET last_seen_at = NOW() WHERE last_seen_at IS NULL")
            op.alter_column("listings", "last_seen_at", nullable=False)

        if "deleted_at" not in listing_columns:
            op.add_column("listings", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

        if "price_jpy" not in listing_columns:
            op.add_column("listings", sa.Column("price_jpy", sa.Integer(), nullable=True))
        if "price_rub" not in listing_columns:
            op.add_column("listings", sa.Column("price_rub", sa.Integer(), nullable=True))
        if "total_price_jpy" not in listing_columns:
            op.add_column("listings", sa.Column("total_price_jpy", sa.Integer(), nullable=True))
        if "total_price_rub" not in listing_columns:
            op.add_column("listings", sa.Column("total_price_rub", sa.Integer(), nullable=True))

    listing_indexes = {index["name"] for index in inspector.get_indexes("listings")}
    listing_uniques = {item["name"] for item in inspector.get_unique_constraints("listings")}

    if "uq_listings_source_external_id" not in listing_uniques:
        op.create_unique_constraint("uq_listings_source_external_id", "listings", ["source", "external_id"])
    if "ix_listings_id" not in listing_indexes:
        op.create_index("ix_listings_id", "listings", ["id"], unique=False)
    if "ix_listings_source" not in listing_indexes:
        op.create_index("ix_listings_source", "listings", ["source"], unique=False)
    if "ix_listings_external_id" not in listing_indexes:
        op.create_index("ix_listings_external_id", "listings", ["external_id"], unique=False)
    if "ix_listings_last_seen_at" not in listing_indexes:
        op.create_index("ix_listings_last_seen_at", "listings", ["last_seen_at"], unique=False)
    if "ix_listings_is_active" not in listing_indexes:
        op.create_index("ix_listings_is_active", "listings", ["is_active"], unique=False)

    if "failed_scrapes" not in existing:
        op.create_table(
            "failed_scrapes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=512), nullable=False),
            sa.Column("source_listing_id", sa.String(length=32), nullable=True),
            sa.Column("error_type", sa.String(length=64), nullable=False),
            sa.Column("message", sa.String(length=512), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("debug_snippet", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        failed_columns = {column["name"] for column in inspector.get_columns("failed_scrapes")}
        if "source_listing_id" not in failed_columns:
            op.add_column("failed_scrapes", sa.Column("source_listing_id", sa.String(length=32), nullable=True))
        if "debug_snippet" not in failed_columns:
            op.add_column("failed_scrapes", sa.Column("debug_snippet", sa.Text(), nullable=True))
        if "status_code" not in failed_columns:
            op.add_column("failed_scrapes", sa.Column("status_code", sa.Integer(), nullable=True))

    failed_indexes = {index["name"] for index in inspector.get_indexes("failed_scrapes")}
    if "ix_failed_scrapes_id" not in failed_indexes:
        op.create_index("ix_failed_scrapes_id", "failed_scrapes", ["id"], unique=False)
    if "ix_failed_scrapes_url" not in failed_indexes:
        op.create_index("ix_failed_scrapes_url", "failed_scrapes", ["url"], unique=False)
    if "ix_failed_scrapes_source_listing_id" not in failed_indexes:
        op.create_index("ix_failed_scrapes_source_listing_id", "failed_scrapes", ["source_listing_id"], unique=False)
    if "ix_failed_scrapes_created_at" not in failed_indexes:
        op.create_index("ix_failed_scrapes_created_at", "failed_scrapes", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_failed_scrapes_created_at", table_name="failed_scrapes")
    op.drop_index("ix_failed_scrapes_source_listing_id", table_name="failed_scrapes")
    op.drop_index("ix_failed_scrapes_url", table_name="failed_scrapes")
    op.drop_index("ix_failed_scrapes_id", table_name="failed_scrapes")
    op.drop_table("failed_scrapes")

    op.drop_index("ix_listings_is_active", table_name="listings")
    op.drop_index("ix_listings_last_seen_at", table_name="listings")
    op.drop_index("ix_listings_external_id", table_name="listings")
    op.drop_index("ix_listings_source", table_name="listings")
    op.drop_index("ix_listings_id", table_name="listings")
    op.drop_table("listings")
