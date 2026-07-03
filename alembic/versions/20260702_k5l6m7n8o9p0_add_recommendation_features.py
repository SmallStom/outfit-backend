"""add recommendation features (pgvector, item attributes, embeddings, feedback)

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-07-02 15:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. items 表增补结构化属性列
    op.add_column("items", sa.Column("attributes", postgresql.JSONB(), nullable=True))
    op.add_column("items", sa.Column("formality", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("femininity", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("athletic", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("vintage", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("thickness", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("suitable_temp_min", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("suitable_temp_max", sa.Integer(), nullable=True))
    op.add_column(
        "items",
        sa.Column("occasion_tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("color_hex_list", postgresql.ARRAY(sa.String(length=10)), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column("keywords", postgresql.ARRAY(sa.String(length=50)), nullable=True),
    )
    op.add_column(
        "items",
        sa.Column(
            "feature_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column("items", sa.Column("feature_error", sa.Text(), nullable=True))

    op.create_index(
        "idx_items_temp_range",
        "items",
        ["user_id", "suitable_temp_min", "suitable_temp_max"],
        unique=False,
    )
    op.create_index(
        "idx_items_feature_status",
        "items",
        ["feature_status"],
        unique=False,
    )

    # 3. item_embeddings 表
    op.execute(
        """
        CREATE TABLE item_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_item_embeddings_item_id UNIQUE (item_id)
        );
        """
    )
    op.create_index("ix_item_embeddings_user_id", "item_embeddings", ["user_id"], unique=False)
    # HNSW 索引（pgvector >= 0.5）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_item_embeddings_hnsw "
        "ON item_embeddings USING hnsw (embedding vector_cosine_ops);"
    )

    # 4. outfits 表增补
    op.add_column("outfits", sa.Column("reason", sa.String(length=200), nullable=True))
    op.add_column("outfits", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("outfits", sa.Column("temperature", sa.Float(), nullable=True))

    # 5. outfit_feedbacks 表
    op.create_table(
        "outfit_feedbacks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "outfit_id", "item_id", "action",
            name="uq_outfit_feedbacks_user_outfit_item_action",
        ),
    )
    op.create_index(
        "ix_outfit_feedbacks_user_id", "outfit_feedbacks", ["user_id"], unique=False
    )
    op.create_index(
        "ix_outfit_feedbacks_user_item", "outfit_feedbacks", ["user_id", "item_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_outfit_feedbacks_user_item", table_name="outfit_feedbacks")
    op.drop_index("ix_outfit_feedbacks_user_id", table_name="outfit_feedbacks")
    op.drop_table("outfit_feedbacks")

    op.drop_column("outfits", "temperature")
    op.drop_column("outfits", "score")
    op.drop_column("outfits", "reason")

    op.execute("DROP INDEX IF EXISTS ix_item_embeddings_hnsw;")
    op.drop_index("ix_item_embeddings_user_id", table_name="item_embeddings")
    op.drop_table("item_embeddings")

    op.drop_index("idx_items_feature_status", table_name="items")
    op.drop_index("idx_items_temp_range", table_name="items")
    op.drop_column("items", "feature_error")
    op.drop_column("items", "feature_status")
    op.drop_column("items", "keywords")
    op.drop_column("items", "color_hex_list")
    op.drop_column("items", "occasion_tags")
    op.drop_column("items", "suitable_temp_max")
    op.drop_column("items", "suitable_temp_min")
    op.drop_column("items", "thickness")
    op.drop_column("items", "vintage")
    op.drop_column("items", "athletic")
    op.drop_column("items", "femininity")
    op.drop_column("items", "formality")
    op.drop_column("items", "attributes")

    # 注意：不 drop extension，可能被其他项目共用
