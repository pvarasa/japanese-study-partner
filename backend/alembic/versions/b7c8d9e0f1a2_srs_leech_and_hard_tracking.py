"""add leech suspension and hard/lapse tracking

Splits "hard" out of srs_correct (it used to be counted as a plain success) and
adds the suspension flag leech detection sets.

Existing rows keep their old srs_correct, which folds in every past "hard" —
there's no way to unmix them retroactively, so pre-migration accuracy reads as
the lenient (non-lapse) figure.

Revision ID: b7c8d9e0f1a2
Revises: a2b3c4d5e6f7
Create Date: 2026-08-09 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('srs_hard', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('items', sa.Column('srs_lapses', sa.Integer(), nullable=False, server_default='0'))
    # Not indexed: a low-cardinality boolean on a table this size, always
    # filtered alongside user_id and srs_due.
    op.add_column(
        'items',
        sa.Column('suspended', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        'study_sessions',
        sa.Column('items_hard', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('study_sessions', 'items_hard')
    op.drop_column('items', 'suspended')
    op.drop_column('items', 'srs_lapses')
    op.drop_column('items', 'srs_hard')
