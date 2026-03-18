"""Add auth_identities table and backfill legacy invite users.

Deletion notes:
- Removes the old contract where hosted invite relogin scanned `users.nickname`
  directly, which hardcoded invite-only assumptions into the user model.
- Introduces provider-scoped auth identities so future OAuth providers can reuse
  the same provisioning/session flow without adding provider-specific fields to
  `users`.

Rollback:
- `alembic downgrade 031`
- When removing GitHub OAuth routes, keep the invite-fallback identity contract so
  OAuth-created hosted users can still recover the same `users` row via invite.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INVITE_PROVIDER = "invite"


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("provider_login", sa.String(length=255), nullable=True),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_auth_identities_provider_user"),
    )
    op.create_index("ix_auth_identities_user_provider", "auth_identities", ["user_id", "provider"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, nickname, created_at "
            "FROM users "
            "WHERE nickname IS NOT NULL AND TRIM(nickname) <> '' "
            "ORDER BY created_at ASC, id ASC"
        )
    ).mappings()

    seen_nicknames: set[str] = set()
    insert_stmt = sa.text(
        "INSERT INTO auth_identities "
        "(user_id, provider, provider_user_id, provider_login, created_at, last_login_at) "
        "VALUES (:user_id, :provider, :provider_user_id, :provider_login, COALESCE(:created_at, CURRENT_TIMESTAMP), :last_login_at)"
    )

    for row in rows:
        nickname = str(row["nickname"] or "").strip()
        if not nickname or nickname in seen_nicknames:
            continue
        seen_nicknames.add(nickname)
        created_at = row.get("created_at")
        bind.execute(
            insert_stmt,
            {
                "user_id": row["id"],
                "provider": _INVITE_PROVIDER,
                "provider_user_id": nickname,
                "provider_login": nickname,
                "created_at": created_at,
                "last_login_at": created_at,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_auth_identities_user_provider", table_name="auth_identities")
    op.drop_table("auth_identities")
