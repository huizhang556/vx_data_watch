"""Track the most recent pin operation for chat tree ordering."""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_chat_categories", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_chat_sessions", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("ai_chat_sessions", "pinned_at")
    op.drop_column("ai_chat_categories", "pinned_at")
