"""Add owner-scoped persisted conversations and messages."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("title_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_owner_key", "conversations", ["owner_key"])
    op.create_index(
        "idx_conversations_owner_activity",
        "conversations",
        ["owner_key", "last_activity_at", "id"],
    )
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("query_trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="messages_role_check"),
        sa.CheckConstraint("status IN ('PENDING', 'COMPLETED', 'FAILED')", name="messages_status_check"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_trace_id"], ["query_traces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_conversation_created", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_owner_activity", table_name="conversations")
    op.drop_index("ix_conversations_owner_key", table_name="conversations")
    op.drop_table("conversations")
