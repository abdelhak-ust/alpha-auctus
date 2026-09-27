"""Add features.review_status and chat_messages.kind (chat workflow UX).

Revision ID: d7f1c4e82b19
Revises: c4e8b2a91d07
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f1c4e82b19"
down_revision: str | Sequence[str] | None = "c4e8b2a91d07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "features",
        sa.Column(
            "review_status",
            sa.String(),
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_features_review_status",
        "features",
        "review_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_index(
        op.f("ix_features_review_status"), "features", ["review_status"], unique=False
    )

    op.add_column("chat_messages", sa.Column("kind", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_chat_messages_kind",
        "chat_messages",
        "kind IN ('progress', 'decision', 'question', 'text')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chat_messages_kind", "chat_messages", type_="check")
    op.drop_column("chat_messages", "kind")
    op.drop_index(op.f("ix_features_review_status"), table_name="features")
    op.drop_constraint("ck_features_review_status", "features", type_="check")
    op.drop_column("features", "review_status")
