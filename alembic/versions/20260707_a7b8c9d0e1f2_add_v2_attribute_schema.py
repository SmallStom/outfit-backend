"""add v2 attribute schema (Layer2-4)

Revision ID: a7b8c9d0e1f2
Revises: 29e06b3bb203
Create Date: 2026-07-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "29e06b3bb203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- Layer2: 视觉属性 ----------
    op.add_column("items", sa.Column("silhouette", sa.String(length=2), nullable=True))
    op.add_column("items", sa.Column("visual_weight", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("volume", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("drape", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("structure", sa.Integer(), nullable=True))
    op.add_column(
        "items",
        sa.Column("visual_focus", postgresql.ARRAY(sa.String(length=20)), nullable=True),
    )
    op.add_column("items", sa.Column("item_length", sa.String(length=20), nullable=True))

    # ---------- Layer3: 风格向量 ----------
    op.add_column("items", sa.Column("style_vector", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # ---------- Layer4: 搭配属性 ----------
    op.add_column("items", sa.Column("occasion_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("items", sa.Column("season_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("items", sa.Column("pairing_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # GIN 索引加速 JSONB 查询
    op.create_index(
        "ix_items_style_vector_gin",
        "items",
        ["style_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_items_style_vector_gin", table_name="items")
    op.drop_column("items", "pairing_preferences")
    op.drop_column("items", "season_scores")
    op.drop_column("items", "occasion_scores")
    op.drop_column("items", "style_vector")
    op.drop_column("items", "item_length")
    op.drop_column("items", "visual_focus")
    op.drop_column("items", "structure")
    op.drop_column("items", "drape")
    op.drop_column("items", "volume")
    op.drop_column("items", "visual_weight")
    op.drop_column("items", "silhouette")
