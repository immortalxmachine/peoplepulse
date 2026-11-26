"""Create (or recreate) the MIS views from views.sql.

SQLite has no CREATE OR REPLACE VIEW, so we DROP VIEW IF EXISTS before each
CREATE -- a pattern both SQLite and Postgres accept. Views only depend on base
tables, so creation order does not matter.

Run:  python -m peoplepulse.mis.build_views
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import create_engine, text

from peoplepulse.config import database_url

VIEWS_SQL = Path(__file__).with_name("views.sql")

# Matches "CREATE VIEW <name> AS"; captures the view name.
_VIEW_NAME = re.compile(r"CREATE\s+VIEW\s+(\w+)\s+AS", re.IGNORECASE)


def view_names() -> list[str]:
    """All view names defined in views.sql, in file order."""
    return _VIEW_NAME.findall(VIEWS_SQL.read_text(encoding="utf-8"))


def _statements() -> list[str]:
    """Split views.sql into individual CREATE VIEW statements."""
    raw = VIEWS_SQL.read_text(encoding="utf-8")
    # Statements are separated by ';'. Keep only those that create a view.
    return [s.strip() for s in raw.split(";") if "CREATE VIEW" in s.upper()]


def build() -> list[str]:
    """Drop and recreate every view. Returns the list of view names built."""
    engine = create_engine(database_url())
    names = view_names()
    with engine.begin() as conn:
        # Drop in reverse so that if a dependency is ever added it is safe.
        for name in reversed(names):
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
        for stmt in _statements():
            conn.execute(text(stmt))
    print(f"Built {len(names)} MIS views: {', '.join(names)}")
    return names


if __name__ == "__main__":
    build()
