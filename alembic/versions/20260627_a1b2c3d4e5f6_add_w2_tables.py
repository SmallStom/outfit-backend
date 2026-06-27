"""add w2 tables

Revision ID: a1b2c3d4e5f6
Revises: 9f8e7d6c5b4a
Create Date: 2026-06-27 16:20:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9f8e7d6c5b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outfits",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("cover_color", sa.String(length=10), nullable=True),
        sa.Column("occasion", sa.String(length=50), nullable=True),
        sa.Column("weather", sa.String(length=20), nullable=True),
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False),
        sa.Column("color_scheme", postgresql.ARRAY(sa.String(length=10)), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outfits_user_id", "outfits", ["user_id"], unique=False)

    op.create_table(
        "outfit_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outfit_id", "item_id"),
    )
    op.create_index("ix_outfit_items_outfit_id", "outfit_items", ["outfit_id"], unique=False)
    op.create_index("ix_outfit_items_item_id", "outfit_items", ["item_id"], unique=False)

    op.create_table(
        "outfit_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("desc", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("cover_color", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outfit_collections_user_id", "outfit_collections", ["user_id"], unique=False)

    op.create_table(
        "outfit_collection_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["outfit_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "item_id"),
    )
    op.create_index("ix_outfit_collection_items_collection_id", "outfit_collection_items", ["collection_id"], unique=False)
    op.create_index("ix_outfit_collection_items_item_id", "outfit_collection_items", ["item_id"], unique=False)

    op.create_table(
        "body_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("height", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("weight", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("shoulder_width", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("chest", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("waist", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("hip", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("body_type", sa.String(length=20), nullable=True),
        sa.Column("body_type_label", sa.String(length=20), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("photo_color", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("size_advice", postgresql.JSONB(), nullable=True),
        sa.Column("advice", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_body_profiles_user_id", "body_profiles", ["user_id"], unique=False)

    op.create_table(
        "wear_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("weather", sa.String(length=50), nullable=True),
        sa.Column("occasion", sa.String(length=50), nullable=True),
        sa.Column("item_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wear_history_user_id", "wear_history", ["user_id"], unique=False)
    op.create_index("ix_wear_history_user_date", "wear_history", ["user_id", "date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wear_history_user_date", table_name="wear_history")
    op.drop_index("ix_wear_history_user_id", table_name="wear_history")
    op.drop_table("wear_history")
    op.drop_index("ix_body_profiles_user_id", table_name="body_profiles")
    op.drop_table("body_profiles")
    op.drop_index("ix_outfit_collection_items_item_id", table_name="outfit_collection_items")
    op.drop_index("ix_outfit_collection_items_collection_id", table_name="outfit_collection_items")
    op.drop_table("outfit_collection_items")
    op.drop_index("ix_outfit_collections_user_id", table_name="outfit_collections")
    op.drop_table("outfit_collections")
    op.drop_index("ix_outfit_items_item_id", table_name="outfit_items")
    op.drop_index("ix_outfit_items_outfit_id", table_name="outfit_items")
    op.drop_table("outfit_items")
    op.drop_index("ix_outfits_user_id", table_name="outfits")
    op.drop_table("outfits")
