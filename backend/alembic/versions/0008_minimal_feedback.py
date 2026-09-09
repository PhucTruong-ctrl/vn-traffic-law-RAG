"""Align feedback with the anonymous LIKE/DISLIKE contract."""

from alembic import op

revision = "0008_minimal_feedback"
down_revision = "0007_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep upgrades safe when a partially-applied deployment already added either column.
    op.execute("ALTER TABLE query_feedback ADD COLUMN IF NOT EXISTS message_id varchar(128)")
    op.execute("ALTER TABLE query_feedback ADD COLUMN IF NOT EXISTS rating varchar(7)")
    op.execute(
        """
        UPDATE query_feedback
        SET rating = CASE WHEN useful THEN 'LIKE' ELSE 'DISLIKE' END
        WHERE rating IS NULL
        """
    )
    op.execute("ALTER TABLE query_feedback ALTER COLUMN rating SET NOT NULL")
    op.execute("ALTER TABLE query_feedback DROP CONSTRAINT IF EXISTS query_feedback_rating_check")
    op.execute(
        "ALTER TABLE query_feedback ADD CONSTRAINT query_feedback_rating_check "
        "CHECK (rating IN ('LIKE', 'DISLIKE'))"
    )
    op.execute("ALTER TABLE query_feedback DROP CONSTRAINT IF EXISTS query_feedback_category_check")
    op.execute("ALTER TABLE query_feedback DROP COLUMN IF EXISTS useful")
    op.execute("ALTER TABLE query_feedback DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE query_feedback DROP COLUMN IF EXISTS comment")


def downgrade() -> None:
    op.execute("ALTER TABLE query_feedback ADD COLUMN IF NOT EXISTS useful boolean")
    op.execute("UPDATE query_feedback SET useful = (rating = 'LIKE') WHERE useful IS NULL")
    op.execute("ALTER TABLE query_feedback ALTER COLUMN useful SET NOT NULL")
    op.execute("ALTER TABLE query_feedback DROP CONSTRAINT IF EXISTS query_feedback_rating_check")
    op.execute("ALTER TABLE query_feedback DROP COLUMN IF EXISTS rating")
    op.execute("ALTER TABLE query_feedback DROP COLUMN IF EXISTS message_id")
    op.execute("ALTER TABLE query_feedback ADD COLUMN IF NOT EXISTS category varchar")
    op.execute("ALTER TABLE query_feedback ADD COLUMN IF NOT EXISTS comment text")
