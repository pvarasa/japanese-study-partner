"""add user_id for multi-user support

Revision ID: a2b3c4d5e6f7
Revises: 85aa03c41c9e
Create Date: 2026-04-26 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = '85aa03c41c9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('user_id', sa.String(100), nullable=False, server_default='default'))
    op.create_index('ix_items_user_id', 'items', ['user_id'])

    op.add_column('sources', sa.Column('user_id', sa.String(100), nullable=False, server_default='default'))
    op.create_index('ix_sources_user_id', 'sources', ['user_id'])

    op.add_column('study_sessions', sa.Column('user_id', sa.String(100), nullable=False, server_default='default'))
    op.create_index('ix_study_sessions_user_id', 'study_sessions', ['user_id'])

    # settings: add user_id then promote PK to (user_id, key)
    op.add_column('settings', sa.Column('user_id', sa.String(100), nullable=False, server_default='default'))
    op.drop_constraint('settings_pkey', 'settings', type_='primary')
    op.create_primary_key('settings_pkey', 'settings', ['user_id', 'key'])


def downgrade() -> None:
    op.drop_constraint('settings_pkey', 'settings', type_='primary')
    op.create_primary_key('settings_pkey', 'settings', ['key'])
    op.drop_column('settings', 'user_id')

    op.drop_index('ix_study_sessions_user_id', 'study_sessions')
    op.drop_column('study_sessions', 'user_id')

    op.drop_index('ix_sources_user_id', 'sources')
    op.drop_column('sources', 'user_id')

    op.drop_index('ix_items_user_id', 'items')
    op.drop_column('items', 'user_id')
