"""Add daily usage counters."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table("usage_counters", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("usage_date", sa.Date(), nullable=False), sa.Column("kind", sa.String(30), nullable=False), sa.Column("count", sa.Integer(), nullable=False, server_default="0"), sa.UniqueConstraint("user_id", "usage_date", "kind", name="uq_usage_counter"))
    op.create_index("ix_usage_counters_user_id", "usage_counters", ["user_id"])
    op.create_index("ix_usage_counters_usage_date", "usage_counters", ["usage_date"])
    op.create_index("ix_usage_counters_kind", "usage_counters", ["kind"])

def downgrade() -> None:
    op.drop_table("usage_counters")
