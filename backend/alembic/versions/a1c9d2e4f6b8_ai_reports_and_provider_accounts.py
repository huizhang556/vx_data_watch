"""Store AI report context and scope providers to channels accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c9d2e4f6b8"
down_revision: str | None = "6b90e27ce148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_ai_provider_configs_account_id", "ai_provider_configs", ["account_id"], unique=False
    )
    op.add_column("ai_analysis_reports", sa.Column("prompt_text", sa.Text(), nullable=True))
    op.add_column(
        "ai_analysis_reports", sa.Column("provider_snapshot_json", sa.Text(), nullable=True)
    )
    op.add_column("ai_analysis_reports", sa.Column("history_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_ai_analysis_reports_history_id", "ai_analysis_reports", ["history_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ai_analysis_reports_history_id", table_name="ai_analysis_reports")
    op.drop_column("ai_analysis_reports", "history_id")
    op.drop_column("ai_analysis_reports", "provider_snapshot_json")
    op.drop_column("ai_analysis_reports", "prompt_text")
    op.drop_index("ix_ai_provider_configs_account_id", table_name="ai_provider_configs")
    op.drop_column("ai_provider_configs", "account_id")
