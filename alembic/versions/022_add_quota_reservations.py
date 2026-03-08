"""Add quota_reservations table for durable hosted quota tracking

Revision ID: 022
Revises: 021
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quota_reservations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('reserved_count', sa.Integer(), nullable=False),
        sa.Column('charged_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('lease_token', sa.String(length=64), nullable=False),
        sa.Column('released_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint('reserved_count >= 0', name='ck_quota_reservations_reserved_nonnegative'),
        sa.CheckConstraint('charged_count >= 0', name='ck_quota_reservations_charged_nonnegative'),
        sa.CheckConstraint('charged_count <= reserved_count', name='ck_quota_reservations_charged_lte_reserved'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_quota_reservations_user_released_at', 'quota_reservations', ['user_id', 'released_at'])
    op.create_index('ix_quota_reservations_lease_token', 'quota_reservations', ['lease_token'])

    with op.batch_alter_table('quota_reservations') as batch_op:
        batch_op.alter_column(
            'charged_count',
            existing_type=sa.Integer(),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    op.drop_index('ix_quota_reservations_lease_token', table_name='quota_reservations')
    op.drop_index('ix_quota_reservations_user_released_at', table_name='quota_reservations')
    op.drop_table('quota_reservations')
