"""add kanji info

Cached per-kanji details (readings, JLPT level, parts, mnemonic, origin)
for the kanji-reading drill's reveal. Global, like tags: no user_id.

A new table, so SQLite needs nothing in sqlite_migrate — create_all builds it.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-24 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kanji_info',
        sa.Column('kanji', sa.String(length=4), primary_key=True),
        sa.Column('meaning', sa.Text(), nullable=False),
        sa.Column('onyomi', sa.Text(), nullable=False),
        sa.Column('kunyomi', sa.Text(), nullable=False),
        sa.Column('jlpt_level', sa.String(length=5), nullable=True),
        sa.Column('strokes', sa.Integer(), nullable=True),
        sa.Column('components', sa.Text(), nullable=False),
        sa.Column('mnemonic', sa.Text(), nullable=False),
        sa.Column('origin', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('kanji_info')
