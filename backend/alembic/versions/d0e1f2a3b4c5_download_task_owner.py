"""Associate download tasks with their creating user."""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("download_tasks")}
    if "user_id" not in columns:
        with op.batch_alter_table("download_tasks") as batch:
            batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_download_tasks_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE")
    indexes = {index["name"] for index in inspector.get_indexes("download_tasks")}
    if "ix_download_tasks_user_id" not in indexes:
        op.create_index("ix_download_tasks_user_id", "download_tasks", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_download_tasks_user_id", table_name="download_tasks")
    op.drop_column("download_tasks", "user_id")
