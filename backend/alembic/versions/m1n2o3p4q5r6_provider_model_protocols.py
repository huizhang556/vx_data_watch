"""add per-model AI protocol mapping"""

from alembic import op
import sqlalchemy as sa

revision = "m1n2o3p4q5r6"
down_revision = "l5f6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("model_protocols_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_provider_configs", "model_protocols_json")
