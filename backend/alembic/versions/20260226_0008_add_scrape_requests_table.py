"""add scrape requests table

Revision ID: 20260226_0008
Revises: 20260226_0007
Create Date: 2026-02-26 21:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0008"
down_revision: Union[str, None] = "20260226_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "scrape_requests" in inspector.get_table_names():
        return

    op.create_table(
        "scrape_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="carsensor"),
        sa.Column("requested_by", sa.String(length=64), nullable=False, server_default="telegram_bot"),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_scrape_requests_source", "scrape_requests", ["source"])
    op.create_index("ix_scrape_requests_status", "scrape_requests", ["status"])
    op.create_index("ix_scrape_requests_requested_at", "scrape_requests", ["requested_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "scrape_requests" not in inspector.get_table_names():
        return

    for index_name in (
        "ix_scrape_requests_source",
        "ix_scrape_requests_status",
        "ix_scrape_requests_requested_at",
    ):
        existing_indexes = {item["name"] for item in inspector.get_indexes("scrape_requests")}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="scrape_requests")

    op.drop_table("scrape_requests")
