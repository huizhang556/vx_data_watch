"""Store compressed context summaries for long AI conversations."""
import sqlalchemy as sa
from alembic import op

revision = "h1b2c3d4e5f6"
down_revision = "g0a1b2c3d4e5f"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_chat_sessions", sa.Column("context_summary", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("ai_chat_sessions", "context_summary")
