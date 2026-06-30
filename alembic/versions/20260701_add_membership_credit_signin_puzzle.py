"""add membership, credit, sign_in, order, model_template and puzzle_result tables

Revision ID: g1h2i3j4k5l6
Revises: f1g2h3i4j5k6
Create Date: 2026-07-01 10:00:00.000000+08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f1g2h3i4j5k6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users 表新增字段
    op.add_column("users", sa.Column("is_new_user", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("users", sa.Column("referral_code", sa.String(length=16), nullable=True))
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)
    op.add_column("users", sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_users_invited_by", "users", ["invited_by"], unique=False)
    op.create_foreign_key("fk_users_invited_by", "users", "users", ["invited_by"], ["id"], ondelete="SET NULL")

    # membership_tiers
    op.create_table(
        "membership_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_price", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("yearly_price", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("new_user_price", sa.Integer(), nullable=True),
        sa.Column("ai_tryon_quota", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("puzzle_quota", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # user_memberships
    op.create_table(
        "user_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ai_tryon_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("puzzle_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tier_id"], ["membership_tiers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memberships_user_id", "user_memberships", ["user_id"], unique=False)
    op.create_index("ix_user_memberships_tier_id", "user_memberships", ["tier_id"], unique=False)

    # credit_accounts
    op.create_table(
        "credit_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("free_balance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("paid_balance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_balance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_credit_accounts_user_id", "credit_accounts", ["user_id"], unique=True)

    # credit_transactions
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("free_amount", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("paid_amount", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("related_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"], unique=False)
    op.create_index("ix_credit_transactions_related_order_id", "credit_transactions", ["related_order_id"], unique=False)

    # credit_packages
    op.create_table(
        "credit_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("discount_price", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # tasks
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reward_credits", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("trigger_event", sa.String(length=50), nullable=False),
        sa.Column("max_times", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_trigger_event", "tasks", ["trigger_event"], unique=False)

    # user_tasks
    op.create_table(
        "user_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("claimed_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "task_id", name="uix_user_task"),
    )
    op.create_index("ix_user_tasks_task_id", "user_tasks", ["task_id"], unique=False)
    op.create_index("ix_user_tasks_user_id", "user_tasks", ["user_id"], unique=False)

    # sign_in_records
    op.create_table(
        "sign_in_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sign_date", sa.Date(), nullable=False),
        sa.Column("consecutive_days", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("reward_credits", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sign_date", name="uix_user_sign_date"),
    )
    op.create_index("ix_sign_in_records_user_id", "sign_in_records", ["user_id"], unique=False)
    op.create_index("ix_sign_in_records_sign_date", "sign_in_records", ["sign_date"], unique=False)

    # orders
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("original_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("payment_method", sa.String(length=30), nullable=True),
        sa.Column("out_trade_no", sa.String(length=64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("out_trade_no"),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)
    op.create_index("ix_orders_target_id", "orders", ["target_id"], unique=False)
    op.create_index("ix_orders_out_trade_no", "orders", ["out_trade_no"], unique=True)

    # promo_codes
    op.create_table(
        "promo_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("discount_type", sa.String(length=20), server_default=sa.text("'amount'"), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("applicable_type", sa.String(length=30), server_default=sa.text("'all'"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_uses_per_user", sa.Integer(), nullable=True),
        sa.Column("min_order_amount", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    # promo_code_usages
    op.create_table(
        "promo_code_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("promo_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_promo_code_usages_promo_code_id", "promo_code_usages", ["promo_code_id"], unique=False)
    op.create_index("ix_promo_code_usages_user_id", "promo_code_usages", ["user_id"], unique=False)
    op.create_index("ix_promo_code_usages_order_id", "promo_code_usages", ["order_id"], unique=False)

    # model_templates
    op.create_table(
        "model_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("preview_image_url", sa.Text(), nullable=False),
        sa.Column("template_image_url", sa.Text(), nullable=False),
        sa.Column("slots", postgresql.JSONB(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # puzzle_results
    op.create_table(
        "puzzle_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("item_ids", postgresql.JSONB(), nullable=False),
        sa.Column("cutout_image_urls", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_image_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["model_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_puzzle_results_user_id", "puzzle_results", ["user_id"], unique=False)
    op.create_index("ix_puzzle_results_template_id", "puzzle_results", ["template_id"], unique=False)
    op.create_index("ix_puzzle_results_task_id", "puzzle_results", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_puzzle_results_task_id", table_name="puzzle_results")
    op.drop_index("ix_puzzle_results_template_id", table_name="puzzle_results")
    op.drop_index("ix_puzzle_results_user_id", table_name="puzzle_results")
    op.drop_table("puzzle_results")

    op.drop_table("model_templates")

    op.drop_index("ix_promo_code_usages_order_id", table_name="promo_code_usages")
    op.drop_index("ix_promo_code_usages_user_id", table_name="promo_code_usages")
    op.drop_index("ix_promo_code_usages_promo_code_id", table_name="promo_code_usages")
    op.drop_table("promo_code_usages")

    op.drop_table("promo_codes")

    op.drop_index("ix_orders_out_trade_no", table_name="orders")
    op.drop_index("ix_orders_target_id", table_name="orders")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_sign_in_records_sign_date", table_name="sign_in_records")
    op.drop_index("ix_sign_in_records_user_id", table_name="sign_in_records")
    op.drop_table("sign_in_records")

    op.drop_index("ix_user_tasks_user_id", table_name="user_tasks")
    op.drop_index("ix_user_tasks_task_id", table_name="user_tasks")
    op.drop_table("user_tasks")

    op.drop_index("ix_tasks_trigger_event", table_name="tasks")
    op.drop_table("tasks")

    op.drop_table("credit_packages")

    op.drop_index("ix_credit_transactions_related_order_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    op.drop_index("ix_credit_accounts_user_id", table_name="credit_accounts")
    op.drop_table("credit_accounts")

    op.drop_index("ix_user_memberships_tier_id", table_name="user_memberships")
    op.drop_index("ix_user_memberships_user_id", table_name="user_memberships")
    op.drop_table("user_memberships")

    op.drop_table("membership_tiers")

    op.drop_constraint("fk_users_invited_by", "users", type_="foreignkey")
    op.drop_index("ix_users_invited_by", table_name="users")
    op.drop_column("users", "invited_by")
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
    op.drop_column("users", "is_new_user")

