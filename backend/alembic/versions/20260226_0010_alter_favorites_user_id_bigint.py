"""alter favorites user_id to bigint

Revision ID: 20260226_0010
Revises: 20260226_0009
Create Date: 2026-02-26 23:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0010"
down_revision: Union[str, None] = "20260226_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "favorites" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("favorites")}
    user_id_column = columns.get("user_id")
    if user_id_column is None:
        return

    if isinstance(user_id_column["type"], sa.BigInteger):
        return

    op.alter_column(
        "favorites",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        postgresql_using="user_id::bigint",
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "favorites" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("favorites")}
    user_id_column = columns.get("user_id")
    if user_id_column is None:
        return

    if isinstance(user_id_column["type"], sa.Integer):
        return

    op.alter_column(
        "favorites",
        "user_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        postgresql_using="user_id::integer",
        nullable=False,
    )
