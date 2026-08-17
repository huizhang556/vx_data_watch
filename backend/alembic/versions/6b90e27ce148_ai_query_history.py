"""Store AI query history without report content.

Revision ID: 6b90e27ce148
Revises: 322555a6d5f7
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b90e27ce148"
down_revision: str | None = "322555a6d5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_query_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["channels_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_provider_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_query_history_account_id"), "ai_query_history", ["account_id"], unique=False
    )
    op.execute(
        "INSERT INTO ai_query_history (account_id, provider_id, start_date, end_date, created_at) "
        "SELECT account_id, provider_id, start_date, end_date, created_at FROM ai_analysis_reports"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_query_history_account_id"), table_name="ai_query_history")
    op.drop_table("ai_query_history")
