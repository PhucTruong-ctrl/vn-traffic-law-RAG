"""Restore the active review-item evidence payload when absent."""

from alembic import op

revision = "0010_review_item_evidence"
down_revision = "0009_schema_drift_remediation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE review_items ADD COLUMN IF NOT EXISTS evidence jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE review_items DROP COLUMN IF EXISTS evidence")
