"""Add tasks.subtasks and tasks.definition_of_done JSONB lists.

Revision ID: 9dd4af6536bc
Revises: d7f1c4e82b19
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9dd4af6536bc"
down_revision: str | Sequence[str] | None = "d7f1c4e82b19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "subtasks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "definition_of_done",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "definition_of_done")
    op.drop_column("tasks", "subtasks")
