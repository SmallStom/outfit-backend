"""add tryon_results table

Revision ID: f1g2h3i4j5k6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-29 21:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1g2h3i4j5k6"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tryon_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=50), nullable=False),
        sa.Column("person_image_url", sa.Text(), nullable=False),
        sa.Column("top_garment_url", sa.Text(), nullable=True),
        sa.Column("bottom_garment_url", sa.Text(), nullable=True),
        sa.Column("outer_garment_url", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_image_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tryon_results_user_id", "tryon_results", ["user_id"], unique=False)
    op.create_index("ix_tryon_results_task_id", "tryon_results", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tryon_results_task_id", table_name="tryon_results")
    op.drop_index("ix_tryon_results_user_id", table_name="tryon_results")
    op.drop_table("tryon_results")
