"""Store per-purpose AI provider model categories."""
import sqlalchemy as sa
from alembic import op

revision = "j3d4e5f6g7h8"
down_revision = "i2c3d4e5f6g7"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("model_categories_json", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("ai_provider_configs", "model_categories_json")
