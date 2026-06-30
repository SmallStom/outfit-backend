"""update tryon_results provider default to highway

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-07-02 12:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tryon_results",
        "provider",
        existing_type=sa.String(length=20),
        server_default=sa.text("'highway'"),
    )


def downgrade() -> None:
    op.alter_column(
        "tryon_results",
        "provider",
        existing_type=sa.String(length=20),
        server_default=sa.text("'liblib'"),
    )
