"""add shop_items

Revision ID: 29e06b3bb203
Revises: l6m7n8o9p0q1
Create Date: 2026-07-05 12:36:51.168270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "29e06b3bb203"
down_revision: Union[str, None] = "l6m7n8o9p0q1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_items",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("sub_category", sa.String(length=30), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("image_color", sa.String(length=10), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("material", sa.String(length=200), nullable=True),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("color_hex", sa.String(length=10), nullable=True),
        sa.Column("season", sa.String(length=50), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shop_items_category"), "shop_items", ["category"], unique=False)
    op.create_index(op.f("ix_shop_items_is_enabled"), "shop_items", ["is_enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_shop_items_is_enabled"), table_name="shop_items")
    op.drop_index(op.f("ix_shop_items_category"), table_name="shop_items")
    op.drop_table("shop_items")
