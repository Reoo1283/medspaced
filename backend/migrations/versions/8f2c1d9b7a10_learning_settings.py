"""user learning settings for FSRS personalization

Revision ID: 8f2c1d9b7a10
Revises: e6e3eefa062a
Create Date: 2026-11-06 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8f2c1d9b7a10'
down_revision: Union[str, None] = 'e6e3eefa062a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_learning_settings',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('desired_retention', sa.Float(), nullable=False),
    sa.Column('fsrs_parameters', sa.JSON(), nullable=True),
    sa.Column('reviews_analyzed', sa.Integer(), nullable=False),
    sa.Column('accuracy', sa.Float(), nullable=True),
    sa.Column('lapse_rate', sa.Float(), nullable=True),
    sa.Column('optimized_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_learning_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_learning_settings_user_id'), ['user_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('user_learning_settings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_learning_settings_user_id'))
    op.drop_table('user_learning_settings')
