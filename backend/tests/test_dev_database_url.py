from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dev_script_rewrites_compose_database_url_without_extra_slash() -> None:
    script = r"""DATABASE_URL="postgresql+psycopg://vnlaw:secret@postgres:5432/vnlaw"
source <(sed -n '13,22p' dev.sh)
printf '%s\n' "$DATABASE_URL"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "postgresql+psycopg://vnlaw:secret@127.0.0.1:5432/vnlaw"
    assert ":5432//" not in result.stdout
