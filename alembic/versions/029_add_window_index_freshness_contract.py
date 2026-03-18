"""Add window-index freshness contract metadata.

Deletion notes:
- Replaces the legacy implicit lifecycle where `novels.window_index` being NULL
  was the only durable signal for missing/stale state.
- Adds explicit revision/status/error columns so source-text invalidation and
  rebuild outcomes can be tracked independently from bootstrap job rows.

Rollback:
- `alembic downgrade 028`
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "novels" not in tables:
        return

    novel_columns = {column["name"] for column in inspector.get_columns("novels")}
    dialect = bind.dialect.name if bind is not None else ""

    def _add_columns(batch_op) -> None:
        if "window_index_status" not in novel_columns:
            batch_op.add_column(
                sa.Column(
                    "window_index_status",
                    sa.String(length=20),
                    nullable=False,
                    server_default="missing",
                )
            )
        if "window_index_revision" not in novel_columns:
            batch_op.add_column(
                sa.Column(
                    "window_index_revision",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "window_index_built_revision" not in novel_columns:
            batch_op.add_column(
                sa.Column("window_index_built_revision", sa.Integer(), nullable=True)
            )
        if "window_index_error" not in novel_columns:
            batch_op.add_column(
                sa.Column("window_index_error", sa.Text(), nullable=True)
            )

    if dialect == "sqlite":
        with op.batch_alter_table("novels") as batch_op:
            _add_columns(batch_op)
    else:
        _add_columns(op)

    op.execute(
        """
        UPDATE novels
        SET
            window_index_status = CASE
                WHEN window_index IS NOT NULL THEN 'fresh'
                ELSE 'missing'
            END,
            window_index_revision = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM chapters
                    WHERE chapters.novel_id = novels.id
                ) THEN 1
                ELSE 0
            END,
            window_index_built_revision = CASE
                WHEN window_index IS NOT NULL THEN 1
                ELSE NULL
            END,
            window_index_error = NULL
        """
    )

    if dialect == "sqlite":
        with op.batch_alter_table("novels") as batch_op:
            batch_op.alter_column("window_index_status", server_default=None)
            batch_op.alter_column("window_index_revision", server_default=None)
    else:
        op.alter_column("novels", "window_index_status", server_default=None)
        op.alter_column("novels", "window_index_revision", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "novels" not in tables:
        return

    novel_columns = {column["name"] for column in inspector.get_columns("novels")}
    dialect = bind.dialect.name if bind is not None else ""

    def _drop_columns(batch_op) -> None:
        if "window_index_error" in novel_columns:
            batch_op.drop_column("window_index_error")
        if "window_index_built_revision" in novel_columns:
            batch_op.drop_column("window_index_built_revision")
        if "window_index_revision" in novel_columns:
            batch_op.drop_column("window_index_revision")
        if "window_index_status" in novel_columns:
            batch_op.drop_column("window_index_status")

    if dialect == "sqlite":
        with op.batch_alter_table("novels") as batch_op:
            _drop_columns(batch_op)
    else:
        _drop_columns(op)
