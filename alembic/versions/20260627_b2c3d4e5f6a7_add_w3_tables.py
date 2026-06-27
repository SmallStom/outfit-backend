"""add w3 tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-27 17:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "care_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("care_type", sa.String(length=20), nullable=False),
        sa.Column("care_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_records_item_id", "care_records", ["item_id"], unique=False)
    op.create_index("ix_care_records_care_date", "care_records", ["care_date"], unique=False)

    op.create_table(
        "purchase_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_image", sa.Text(), nullable=True),
        sa.Column("item_name", sa.String(length=100), nullable=True),
        sa.Column("estimated_price", sa.Integer(), nullable=True),
        sa.Column("match_rate", sa.Integer(), nullable=True),
        sa.Column("suggested_count", sa.Integer(), nullable=True),
        sa.Column("cost_per_wear", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("thumbnail_color", sa.String(length=10), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("match_details", postgresql.JSONB(), nullable=True),
        sa.Column("similar_items", sa.Integer(), nullable=True),
        sa.Column("suggestions", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_previews_user_id", "purchase_previews", ["user_id"], unique=False)

    op.create_table(
        "tryon_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("occasion", sa.String(length=50), nullable=True),
        sa.Column("item_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tryon_presets_user_id", "tryon_presets", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tryon_presets_user_id", table_name="tryon_presets")
    op.drop_table("tryon_presets")
    op.drop_index("ix_purchase_previews_user_id", table_name="purchase_previews")
    op.drop_table("purchase_previews")
    op.drop_index("ix_care_records_care_date", table_name="care_records")
    op.drop_index("ix_care_records_item_id", table_name="care_records")
    op.drop_table("care_records")
