"""compatibility no-op migration

Revision ID: 20260225_0003
Revises: 20260225_0002
Create Date: 2026-02-25 18:25:00
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20260225_0003"
down_revision: Union[str, None] = "20260225_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DB on some machines was already pinned to this revision name.
    # Keep it as a no-op to preserve upgrade path.
    return


def downgrade() -> None:
    return
