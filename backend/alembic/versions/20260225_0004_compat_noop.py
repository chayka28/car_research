"""compatibility no-op migration for legacy environments

Revision ID: 20260225_0004
Revises: 20260225_0003
Create Date: 2026-02-25 18:35:00
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20260225_0004"
down_revision: Union[str, None] = "20260225_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
