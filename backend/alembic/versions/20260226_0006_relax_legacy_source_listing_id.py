"""relax legacy source_listing_id constraint

Revision ID: 20260226_0006
Revises: 20260226_0005
Create Date: 2026-02-26 00:12:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0006"
down_revision: Union[str, None] = "20260226_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "listings" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("listings")}
    source_listing_id = columns.get("source_listing_id")
    if source_listing_id is not None and not source_listing_id.get("nullable", True):
        op.alter_column(
            "listings",
            "source_listing_id",
            existing_type=sa.String(length=32),
            nullable=True,
        )


def downgrade() -> None:
    return
