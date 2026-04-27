"""initial schema

Revision ID: 85aa03c41c9e
Revises:
Create Date: 2026-04-26 01:07:38.369710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85aa03c41c9e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(500)),
        sa.Column('type', sa.String(20)),
        sa.Column('url', sa.Text),
        sa.Column('content', sa.Text),
        sa.Column('created_at', sa.DateTime),
    )

    op.create_table(
        'tags',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
    )

    op.create_table(
        'items',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('type', sa.String(20), nullable=False, index=True),
        sa.Column('japanese', sa.Text, nullable=False),
        sa.Column('reading', sa.Text),
        sa.Column('meaning', sa.Text, nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('example_sentences', sa.Text),
        sa.Column('jlpt_level', sa.String(5)),
        sa.Column('source_id', sa.Integer, sa.ForeignKey('sources.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime),
        sa.Column('srs_interval', sa.Float, nullable=False, server_default='0'),
        sa.Column('srs_ease', sa.Float, nullable=False, server_default='2.5'),
        sa.Column('srs_due', sa.DateTime),
        sa.Column('srs_reviews', sa.Integer, nullable=False, server_default='0'),
        sa.Column('srs_correct', sa.Integer, nullable=False, server_default='0'),
    )

    op.create_table(
        'item_tags',
        sa.Column('item_id', sa.Integer, sa.ForeignKey('items.id', ondelete='CASCADE')),
        sa.Column('tag_id', sa.Integer, sa.ForeignKey('tags.id', ondelete='CASCADE')),
    )

    op.create_table(
        'settings',
        sa.Column('key', sa.String(50), primary_key=True),
        sa.Column('value', sa.Text),
    )

    op.create_table(
        'study_sessions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('started_at', sa.DateTime),
        sa.Column('ended_at', sa.DateTime),
        sa.Column('items_reviewed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('items_correct', sa.Integer, nullable=False, server_default='0'),
        sa.Column('mode', sa.String(30)),
    )


def downgrade() -> None:
    op.drop_table('item_tags')
    op.drop_table('items')
    op.drop_table('tags')
    op.drop_table('sources')
    op.drop_table('settings')
    op.drop_table('study_sessions')
