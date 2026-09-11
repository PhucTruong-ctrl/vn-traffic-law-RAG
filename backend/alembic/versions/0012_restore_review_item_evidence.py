"""Restore review item evidence for databases where 0010 was skipped."""

from alembic import op

revision = "0012_restore_review_evidence"
down_revision = "0011_feedback_nullability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS evidence jsonb")
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS reviewer varchar")
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS reviewed_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS reviewer")
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS evidence")
