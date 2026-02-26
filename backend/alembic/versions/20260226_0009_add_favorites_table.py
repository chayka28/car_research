"""add favorites table

Revision ID: 20260226_0009
Revises: 20260226_0008
Create Date: 2026-02-26 23:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0009"
down_revision: Union[str, None] = "20260226_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "favorites" in inspector.get_table_names():
        return

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="carsensor"),
        sa.Column("external_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "source", "external_id", name="uq_favorites_user_source_external_id"),
    )

    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_source", "favorites", ["source"])
    op.create_index("ix_favorites_external_id", "favorites", ["external_id"])
    op.create_index("ix_favorites_created_at", "favorites", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "favorites" not in inspector.get_table_names():
        return

    for index_name in (
        "ix_favorites_user_id",
        "ix_favorites_source",
        "ix_favorites_external_id",
        "ix_favorites_created_at",
    ):
        existing_indexes = {item["name"] for item in inspector.get_indexes("favorites")}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="favorites")

    op.drop_table("favorites")
