"""Add YouTube download tasks.

Revision ID: b4c5d6e7f809
Revises: f9a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f809"
down_revision = "f9a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500)),
        sa.Column("duration", sa.String(length=30)),
        sa.Column("estimated_size", sa.String(length=30)),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("output_path", sa.String(length=2000)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_download_tasks_status", "download_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_download_tasks_status", table_name="download_tasks")
    op.drop_table("download_tasks")