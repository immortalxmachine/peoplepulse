"""Emit the star-schema DDL as PostgreSQL SQL for documentation.

The SQLAlchemy schema (schema.py) is the source of truth; this just compiles it
to Postgres-dialect `CREATE TABLE` statements and writes schema.sql.

Run:  python -m peoplepulse.warehouse.emit_sql
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from peoplepulse.warehouse import schema

HEADER = """-- PeoplePulse star-schema DDL (PostgreSQL dialect).
-- AUTO-GENERATED from peoplepulse/warehouse/schema.py (SQLAlchemy Core),
-- which is the source of truth. Regenerate: python -m peoplepulse.warehouse.emit_sql
-- Local dev uses SQLite; CI runs this same model on PostgreSQL 16.

"""


def main() -> None:
    parts = [
        str(CreateTable(t).compile(dialect=postgresql.dialect())).strip() + ";"
        for t in schema.ALL_TABLES
    ]
    out = Path(__file__).with_name("schema.sql")
    out.write_text(HEADER + "\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
