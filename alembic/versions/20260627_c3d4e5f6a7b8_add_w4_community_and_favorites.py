"""add w4 community and favorites

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-27 18:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_color", sa.String(length=10), nullable=True),
    )

    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_name", sa.String(length=50), nullable=True),
        sa.Column("author_avatar_color", sa.String(length=10), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("images", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("cover_color", sa.String(length=10), nullable=True),
        sa.Column("img_height", sa.Integer(), nullable=True),
        sa.Column("style", sa.String(length=20), nullable=True),
        sa.Column("city", sa.String(length=50), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_user_id", "posts", ["user_id"], unique=False)
    op.create_index("ix_posts_style", "posts", ["style"], unique=False)
    op.create_index("ix_posts_city", "posts", ["city"], unique=False)
    op.create_index("ix_posts_created_at", "posts", ["created_at"], unique=False)

    op.create_table(
        "post_likes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "post_id", name="uq_post_likes_user_post"),
    )
    op.create_index("ix_post_likes_user_id", "post_likes", ["user_id"], unique=False)
    op.create_index("ix_post_likes_post_id", "post_likes", ["post_id"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_name", sa.String(length=50), nullable=True),
        sa.Column("avatar_color", sa.String(length=10), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_post_id", "comments", ["post_id"], unique=False)
    op.create_index("ix_comments_user_id", "comments", ["user_id"], unique=False)

    op.create_table(
        "favorite_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "post_id", name="uq_favorite_posts_user_post"),
    )
    op.create_index("ix_favorite_posts_user_id", "favorite_posts", ["user_id"], unique=False)
    op.create_index("ix_favorite_posts_post_id", "favorite_posts", ["post_id"], unique=False)

    op.create_table(
        "favorite_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id", name="uq_favorite_items_user_item"),
    )
    op.create_index("ix_favorite_items_user_id", "favorite_items", ["user_id"], unique=False)
    op.create_index("ix_favorite_items_item_id", "favorite_items", ["item_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_favorite_items_item_id", table_name="favorite_items")
    op.drop_index("ix_favorite_items_user_id", table_name="favorite_items")
    op.drop_table("favorite_items")
    op.drop_index("ix_favorite_posts_post_id", table_name="favorite_posts")
    op.drop_index("ix_favorite_posts_user_id", table_name="favorite_posts")
    op.drop_table("favorite_posts")
    op.drop_index("ix_comments_user_id", table_name="comments")
    op.drop_index("ix_comments_post_id", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_post_likes_post_id", table_name="post_likes")
    op.drop_index("ix_post_likes_user_id", table_name="post_likes")
    op.drop_table("post_likes")
    op.drop_index("ix_posts_created_at", table_name="posts")
    op.drop_index("ix_posts_city", table_name="posts")
    op.drop_index("ix_posts_style", table_name="posts")
    op.drop_index("ix_posts_user_id", table_name="posts")
    op.drop_table("posts")
    op.drop_column("users", "avatar_color")
