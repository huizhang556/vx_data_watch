"""Persist the model and protocol applied to each chat session."""
import sqlalchemy as sa
from alembic import op

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_chat_sessions", sa.Column("applied_model", sa.String(length=200), nullable=True))
    op.add_column("ai_chat_sessions", sa.Column("applied_protocol", sa.String(length=50), nullable=True))
    op.add_column("ai_chat_sessions", sa.Column("applied_mode", sa.String(length=20), nullable=True))
    op.add_column("ai_chat_sessions", sa.Column("model_applied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_chat_sessions", "model_applied_at")
    op.drop_column("ai_chat_sessions", "applied_mode")
    op.drop_column("ai_chat_sessions", "applied_protocol")
    op.drop_column("ai_chat_sessions", "applied_model")
