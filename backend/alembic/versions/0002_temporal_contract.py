"""W4 temporal contract: allow uncertain effect dates pending review (VNLRAG-136)."""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("legal_effect_events", "event_date", nullable=True)

def downgrade() -> None:
    # Refuse downgrade while uncertain events exist; never silently discard facts.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM legal_effect_events WHERE event_date IS NULL) "
        "THEN RAISE EXCEPTION 'cannot downgrade: uncertain effect events exist'; END IF; "
        "END $$"
    )
    op.alter_column("legal_effect_events", "event_date", nullable=False)
