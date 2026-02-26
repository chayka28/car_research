"""relax legacy inactive constraint

Revision ID: 20260226_0007
Revises: 20260226_0006
Create Date: 2026-02-26 00:13:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260226_0007"
down_revision: Union[str, None] = "20260226_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "listings" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("listings")}
    inactive = columns.get("inactive")
    if inactive is not None and not inactive.get("nullable", True):
        op.alter_column(
            "listings",
            "inactive",
            existing_type=sa.Boolean(),
            nullable=True,
        )


def downgrade() -> None:
    return
