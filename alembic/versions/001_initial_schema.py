"""Initial schema: users, links, clicks

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 2. Links table
    op.create_table(
        'links',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('short_code', sa.String(length=32), nullable=False),
        sa.Column('original_url', sa.String(length=2048), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('max_clicks', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('click_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_links_short_code'), 'links', ['short_code'], unique=True)
    op.create_index(op.f('ix_links_user_id'), 'links', ['user_id'], unique=False)

    # 3. Clicks table
    op.create_table(
        'clicks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('link_id', sa.Integer(), nullable=False),
        sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('city', sa.String(length=128), nullable=True),
        sa.Column('device_type', sa.String(length=32), nullable=True),
        sa.Column('browser', sa.String(length=64), nullable=True),
        sa.Column('os', sa.String(length=64), nullable=True),
        sa.Column('referrer', sa.String(length=2048), nullable=True),
        sa.ForeignKeyConstraint(['link_id'], ['links.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_clicks_link_id_clicked_at', 'clicks', ['link_id', 'clicked_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_clicks_link_id_clicked_at', table_name='clicks')
    op.drop_table('clicks')
    op.drop_index(op.f('ix_links_user_id'), table_name='links')
    op.drop_index(op.f('ix_links_short_code'), table_name='links')
    op.drop_table('links')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
