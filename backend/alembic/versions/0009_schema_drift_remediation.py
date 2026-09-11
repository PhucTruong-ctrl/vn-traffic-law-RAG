"""Restore review audit columns and align schema with ORM."""

from alembic import op

revision = "0009_schema_drift_remediation"
down_revision = "0008_minimal_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS reviewer varchar")
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS reviewed_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS reviewer")
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS reviewed_at")
