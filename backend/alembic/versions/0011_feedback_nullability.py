"""Enforce required trace and rating fields for anonymous feedback."""

from alembic import op

revision = "0011_feedback_nullability"
down_revision = "0010_review_item_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE query_feedback ALTER COLUMN query_trace_id SET NOT NULL")
    op.execute("ALTER TABLE query_feedback ALTER COLUMN rating SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE query_feedback ALTER COLUMN query_trace_id DROP NOT NULL")
    op.execute("ALTER TABLE query_feedback ALTER COLUMN rating DROP NOT NULL")
