"""init users and items

Revision ID: 9f8e7d6c5b4a
Revises:
Create Date: 2026-06-27 15:55:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f8e7d6c5b4a"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("openid", sa.String(length=64), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("gender", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_users_openid", "users", ["openid"], unique=False)

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("care_method", sa.String(length=20), nullable=True),
        sa.Column("care_detail", sa.Text(), nullable=True),
        sa.Column("occasion", sa.String(length=200), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("wear_count", sa.Integer(), nullable=False),
        sa.Column("last_worn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_items_category", "items", ["category"], unique=False)
    op.create_index("ix_items_user_id", "items", ["user_id"], unique=False)
    op.create_index("ix_items_user_category", "items", ["user_id", "category"], unique=False, postgresql_where=sa.text("is_deleted = false"))
    op.create_index("ix_items_user_last_worn", "items", ["user_id", "last_worn_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_items_user_last_worn", table_name="items")
    op.drop_index("ix_items_user_category", table_name="items")
    op.drop_index("ix_items_user_id", table_name="items")
    op.drop_index("ix_items_category", table_name="items")
    op.drop_table("items")
    op.drop_index("ix_users_openid", table_name="users")
    op.drop_table("users")
