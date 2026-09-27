"""MVP v0 tables: drop P6 ingestion tables, keep audit_events, create documents /
features / feature_questions / chat_messages / tasks (plans/mvp-v0.md).

Revision ID: c4e8b2a91d07
Revises: af833a3ba944
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e8b2a91d07"
down_revision: str | Sequence[str] | None = "af833a3ba944"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("fk_features_current_version_id", "features", type_="foreignkey")
    op.drop_index(op.f("ix_review_items_status"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_project_id"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_feature_id"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_document_id"), table_name="review_items")
    op.drop_table("review_items")
    op.drop_index(op.f("ix_feature_versions_feature_id"), table_name="feature_versions")
    op.drop_table("feature_versions")
    op.drop_index(op.f("ix_feature_relations_feature_id_b"), table_name="feature_relations")
    op.drop_table("feature_relations")
    op.drop_index(op.f("ix_chunks_project_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_doc_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_features_project_id"), table_name="features")
    op.drop_index(op.f("ix_features_lifecycle_state"), table_name="features")
    op.drop_table("features")
    op.drop_index(op.f("ix_documents_project_id"), table_name="documents")
    op.drop_table("documents")

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("blob_path", sa.String(), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'converting', 'extracting', 'analysing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_documents_project_content_hash"),
    )
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)

    op.create_table(
        "features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "source_quotes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('extracted', 'analysed', 'needs_clarification', 'clarified', "
            "'planning', 'tasks_ready')",
            name="ck_features_status",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_features_project_id"), "features", ["project_id"], unique=False)
    op.create_index(op.f("ix_features_document_id"), "features", ["document_id"], unique=False)
    op.create_index(op.f("ix_features_status"), "features", ["status"], unique=False)

    op.create_table(
        "feature_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("target_field", sa.String(), nullable=False),
        sa.Column("is_follow_up", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'answered', 'skipped')",
            name="ck_feature_questions_status",
        ),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_feature_questions_project_id"), "feature_questions", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_feature_questions_feature_id"), "feature_questions", ["feature_id"], unique=False
    )
    op.create_index(
        op.f("ix_feature_questions_status"), "feature_questions", ["status"], unique=False
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("feature_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('ai', 'pm')", name="ck_chat_messages_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_messages_project_id"), "chat_messages", ["project_id"], unique=False
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("area", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column(
            "acceptance_criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("estimate", sa.String(), nullable=False),
        sa.Column(
            "traces_to",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("board_item_id", sa.Integer(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'approved', 'on_board')", name="ck_tasks_status"),
        sa.CheckConstraint("priority IN ('P0', 'P1', 'P2', 'P3')", name="ck_tasks_priority"),
        sa.CheckConstraint("estimate IN ('S', 'M', 'L')", name="ck_tasks_estimate"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_tasks_feature_id"), "tasks", ["feature_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_feature_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_chat_messages_project_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_feature_questions_status"), table_name="feature_questions")
    op.drop_index(op.f("ix_feature_questions_feature_id"), table_name="feature_questions")
    op.drop_index(op.f("ix_feature_questions_project_id"), table_name="feature_questions")
    op.drop_table("feature_questions")
    op.drop_index(op.f("ix_features_status"), table_name="features")
    op.drop_index(op.f("ix_features_document_id"), table_name="features")
    op.drop_index(op.f("ix_features_project_id"), table_name="features")
    op.drop_table("features")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_project_id"), table_name="documents")
    op.drop_table("documents")

    # Recreate the P6 tables so upgrade → downgrade → upgrade is reversible.
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("blob_path", sa.String(), nullable=True),
        sa.Column("upload_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ingestion_status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "doc_type IN ('upload', 'transcript', 'email', 'ticket', 'sheet', 'chat')",
            name="ck_documents_doc_type",
        ),
        sa.CheckConstraint(
            "ingestion_status IN "
            "('pending', 'parsed', 'extracted', 'consolidated', 'done', 'failed')",
            name="ck_documents_ingestion_status",
        ),
        sa.PrimaryKeyConstraint("doc_id"),
        sa.UniqueConstraint("project_id", "content_hash", name="uq_documents_project_content_hash"),
    )
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"], unique=False)
    op.create_table(
        "features",
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("lifecycle_state", sa.String(), nullable=False),
        sa.Column("classification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("readiness", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("override", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('extracted', 'consolidated', 'conflicted', 'classified', "
            "'assessing', 'awaiting_answers', 'answered', 'dev_ready', 'overridden', 'stale', "
            "'in_breakdown', 'needs_review', 'broken_down')",
            name="ck_features_lifecycle_state",
        ),
        sa.PrimaryKeyConstraint("feature_id"),
    )
    op.create_index(
        op.f("ix_features_lifecycle_state"), "features", ["lifecycle_state"], unique=False
    )
    op.create_index(op.f("ix_features_project_id"), "features", ["project_id"], unique=False)
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.String(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["documents.doc_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint("doc_id", "ordinal", name="uq_chunks_doc_ordinal"),
    )
    op.create_index(op.f("ix_chunks_doc_id"), "chunks", ["doc_id"], unique=False)
    op.create_index(op.f("ix_chunks_project_id"), "chunks", ["project_id"], unique=False)
    op.create_table(
        "feature_relations",
        sa.Column("feature_id_a", sa.Uuid(), nullable=False),
        sa.Column("feature_id_b", sa.Uuid(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('depends_on', 'extends', 'conflicts_with')",
            name="ck_feature_relations_relation_type",
        ),
        sa.ForeignKeyConstraint(["feature_id_a"], ["features.feature_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id_b"], ["features.feature_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feature_id_a", "feature_id_b", "relation_type"),
    )
    op.create_index(
        op.f("ix_feature_relations_feature_id_b"),
        "feature_relations",
        ["feature_id_b"],
        unique=False,
    )
    op.create_table(
        "feature_versions",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("created_from", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["feature_id"], ["features.feature_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint(
            "feature_id", "version_no", name="uq_feature_versions_feature_version_no"
        ),
    )
    op.create_index(
        op.f("ix_feature_versions_feature_id"), "feature_versions", ["feature_id"], unique=False
    )
    op.create_foreign_key(
        "fk_features_current_version_id",
        "features",
        "feature_versions",
        ["current_version_id"],
        ["version_id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("feature_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.CheckConstraint("kind IN ('conflict', 'sweep_flag')", name="ck_review_items_kind"),
        sa.CheckConstraint(
            "status IN ('open', 'approved', 'dismissed')", name="ck_review_items_status"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.doc_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.feature_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_items_document_id"), "review_items", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_items_feature_id"), "review_items", ["feature_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_items_project_id"), "review_items", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_review_items_status"), "review_items", ["status"], unique=False)
