"""Track one generation task per chat session."""
import sqlalchemy as sa
from alembic import op

revision = "k4e5f6g7h8i9"
down_revision = "j3d4e5f6g7h8"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_chat_sessions", sa.Column("generation_status", sa.String(length=20), nullable=False, server_default="idle"))
    op.add_column("ai_chat_sessions", sa.Column("generation_type", sa.String(length=20), nullable=True))
    op.add_column("ai_chat_sessions", sa.Column("generation_error", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("ai_chat_sessions", "generation_error")
    op.drop_column("ai_chat_sessions", "generation_type")
    op.drop_column("ai_chat_sessions", "generation_status")
