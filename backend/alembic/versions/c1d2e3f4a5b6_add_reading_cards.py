"""add reading cards

A second SRS track per item for the kanji-reading drill: see the kanji
without furigana, recall the reading. Kept apart from the item's own SRS
fields so reading and meaning recall don't mask each other.

A new table, so SQLite needs nothing in sqlite_migrate — create_all builds it.

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reading_cards',
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('srs_interval', sa.Float(), nullable=False),
        sa.Column('srs_ease', sa.Float(), nullable=False),
        sa.Column('srs_due', sa.DateTime(), nullable=False),
        sa.Column('srs_reviews', sa.Integer(), nullable=False),
        sa.Column('srs_correct', sa.Integer(), nullable=False),
        sa.Column('srs_hard', sa.Integer(), nullable=False),
        sa.Column('srs_lapses', sa.Integer(), nullable=False),
    )
    op.create_index('ix_reading_cards_user_id', 'reading_cards', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_reading_cards_user_id', table_name='reading_cards')
    op.drop_table('reading_cards')
