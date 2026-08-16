"""add starts column to players

Revision ID: c4d3e2f1a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-08-13 00:00:00.000000

Adds the real FPL ``starts`` field (matches started) to the players table so
the Feature Store can preserve the starts/minutes distinction instead of
fabricating starts from minutes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d3e2f1a5b6"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the starts column to players."""
    op.add_column(
        "players",
        sa.Column("starts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Drop the starts column."""
    op.drop_column("players", "starts")
