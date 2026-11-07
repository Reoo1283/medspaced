"""phase 4B learning intelligence

Revision ID: 4c7a1e9d2b83
Revises: 8f2c1d9b7a10
Create Date: 2026-11-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4c7a1e9d2b83"
down_revision: Union[str, None] = "8f2c1d9b7a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("difficulty_at_approval", sa.Float(), nullable=True)
        )

    with op.batch_alter_table("user_learning_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mastery_threshold",
                sa.Float(),
                nullable=False,
                server_default="70.0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "daily_new_card_limit",
                sa.Integer(),
                nullable=False,
                server_default="20",
            )
        )

    op.create_table(
        "user_ability_dimensions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("dimension", sa.String(length=120), nullable=False),
        sa.Column("theta", sa.Float(), nullable=False),
        sa.Column("se", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "dimension", name="uq_user_ability_dimension"
        ),
    )
    with op.batch_alter_table("user_ability_dimensions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_user_ability_dimensions_user_id"),
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_user_ability_dimensions_dimension"),
            ["dimension"],
            unique=False,
        )

    op.create_table(
        "srs_migration_audits",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("card_id", sa.String(length=36), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["user_card_state.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("srs_migration_audits", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_srs_migration_audits_batch_id"),
            ["batch_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_srs_migration_audits_card_id"),
            ["card_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_srs_migration_audits_status"),
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("srs_migration_audits", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_srs_migration_audits_status"))
        batch_op.drop_index(batch_op.f("ix_srs_migration_audits_card_id"))
        batch_op.drop_index(batch_op.f("ix_srs_migration_audits_batch_id"))
    op.drop_table("srs_migration_audits")

    with op.batch_alter_table("user_ability_dimensions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_ability_dimensions_dimension"))
        batch_op.drop_index(batch_op.f("ix_user_ability_dimensions_user_id"))
    op.drop_table("user_ability_dimensions")

    with op.batch_alter_table("user_learning_settings", schema=None) as batch_op:
        batch_op.drop_column("daily_new_card_limit")
        batch_op.drop_column("mastery_threshold")

    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.drop_column("difficulty_at_approval")
