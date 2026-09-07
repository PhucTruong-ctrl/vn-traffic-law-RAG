"""Bind review items to immutable versions."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_items", sa.Column("document_version_id", sa.UUID(), nullable=True))
    op.add_column("review_items", sa.Column("target_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "review_items_document_version_fk",
        "review_items",
        "document_versions",
        ["document_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("review_items_document_version_fk", "review_items", type_="foreignkey")
    op.drop_column("review_items", "target_version")
    op.drop_column("review_items", "document_version_id")
