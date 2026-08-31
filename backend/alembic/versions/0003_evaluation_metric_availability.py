"""Add immutable evaluation metric availability metadata (VNLRAG-147)."""

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evaluation_runs", op.Column("metric_availability", JSONB, nullable=True))
    op.execute("UPDATE evaluation_runs SET metric_availability = '{}'::jsonb")
    op.alter_column("evaluation_runs", "metric_availability", nullable=False)
    op.create_check_constraint(
        "evaluation_runs_status_check",
        "evaluation_runs",
        "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
    )


def downgrade() -> None:
    op.drop_constraint("evaluation_runs_status_check", "evaluation_runs", type_="check")
    op.drop_column("evaluation_runs", "metric_availability")
