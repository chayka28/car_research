"""create users and cars tables

Revision ID: 20260225_0001
Revises:
Create Date: 2026-02-25 03:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260225_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )

    users_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("users")}
    if "ix_users_id" not in users_indexes:
        op.create_index("ix_users_id", "users", ["id"], unique=False)

    if "cars" not in existing_tables:
        op.create_table(
            "cars",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("brand", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=64), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("price", sa.Integer(), nullable=False),
            sa.Column("color", sa.String(length=32), nullable=False),
            sa.Column("link", sa.String(length=512), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("link"),
        )

    cars_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("cars")}
    if "ix_cars_id" not in cars_indexes:
        op.create_index("ix_cars_id", "cars", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cars_id", table_name="cars")
    op.drop_table("cars")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
