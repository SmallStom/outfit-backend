"""add favorite_tryon_results table

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-07-02 14:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "favorite_tryon_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "tryon_result_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["tryon_result_id"], ["tryon_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "tryon_result_id",
            name="uq_favorite_tryon_results_user_result"
        ),
    )
    op.create_index(
        "ix_favorite_tryon_results_user_id",
        "favorite_tryon_results",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_favorite_tryon_results_tryon_result_id",
        "favorite_tryon_results",
        ["tryon_result_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_favorite_tryon_results_tryon_result_id",
        table_name="favorite_tryon_results",
    )
    op.drop_index(
        "ix_favorite_tryon_results_user_id",
        table_name="favorite_tryon_results",
    )
    op.drop_table("favorite_tryon_results")
