"""Persist AI image and video generation tasks."""
import sqlalchemy as sa
from alembic import op

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_generation_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("generation_type", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("protocol", sa.String(length=50), nullable=False),
        sa.Column("upstream_task_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_chat_generation_tasks_session_id", "ai_chat_generation_tasks", ["session_id"])
    op.create_index("ix_ai_chat_generation_tasks_user_id", "ai_chat_generation_tasks", ["user_id"])
    op.create_index("ix_ai_chat_generation_tasks_upstream_task_id", "ai_chat_generation_tasks", ["upstream_task_id"])
    op.create_index("ix_ai_chat_generation_tasks_status", "ai_chat_generation_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("ai_chat_generation_tasks")
