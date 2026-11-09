"""add kanji marks

Kanji the learner starred on the reading drill's reveal, to revisit on the
Kanji page and drill through the "Marked kanji" practice. Per user, unlike
kanji_info.

A new table, so SQLite needs nothing in sqlite_migrate — create_all builds it.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kanji_marks',
        sa.Column('user_id', sa.String(length=100), primary_key=True),
        sa.Column('kanji', sa.String(length=4), primary_key=True),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('kanji_marks')
