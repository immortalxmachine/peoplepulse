"""Export the star schema and MIS views to CSV for Power BI / sharing.

Power BI Desktop imports these CSVs and rebuilds the same star schema (the
relationships are documented in docs/POWERBI.md). Dimension + fact tables are
exported so BI can model its own measures; the v_* views are exported too for
quick validation against the SQL definitions.

Run:  python -m peoplepulse.warehouse.export
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from peoplepulse.config import DATA_OUT, database_url
from peoplepulse.mis.build_views import view_names
from peoplepulse.warehouse.schema import ALL_TABLES

STAR_TABLES = [t.name for t in ALL_TABLES if t.name != "quarantine"]


def export(out_dir: Path | None = None) -> dict[str, int]:
    out = Path(out_dir) if out_dir else (DATA_OUT / "export")
    out.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url())
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for name in STAR_TABLES + view_names():
            df = pd.read_sql(text(f"SELECT * FROM {name}"), conn)
            df.to_csv(out / f"{name}.csv", index=False)
            counts[name] = len(df)
    print(f"Exported {len(counts)} tables/views to {out}")
    for name, n in counts.items():
        print(f"  {name:30s} {n:>7d}")
    return counts


if __name__ == "__main__":
    export()
