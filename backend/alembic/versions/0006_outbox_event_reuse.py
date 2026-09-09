"""Allow repeated event types for a job across outbox event rows."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "outbox_events_event_type_job_id_key"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "outbox_events", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        _CONSTRAINT_NAME,
        "outbox_events",
        ["event_type", "job_id"],
    )
