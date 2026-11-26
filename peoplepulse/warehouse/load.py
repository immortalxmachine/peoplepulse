"""ETL: raw CSVs -> star schema in the warehouse.

Steps:
  1. (Re)create all tables from the SQLAlchemy schema.
  2. Load reference dimensions (country, department, date).
  3. Run data-quality checks on raw employees; quarantine bad rows.
  4. Build dim_employee (surrogate keys + latest performance rating).
  5. Derive fact_headcount_monthly and fact_exits from employees.
  6. Load fact_hiring_funnel from the raw funnel feed.

Run:  python -m peoplepulse.warehouse.load
"""

from __future__ import annotations

import calendar
import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from peoplepulse.config import DATA_OUT, database_url
from peoplepulse.data.generate import WINDOW_END, WINDOW_START
from peoplepulse.data.generate import main as generate_raw
from peoplepulse.warehouse import schema
from peoplepulse.warehouse.quality import check_employees

# --- Reference data (small, fixed) -------------------------------------------
COUNTRIES = [
    # key, code, name, region
    (1, "IN", "India", "APAC"),
    (2, "AE", "United Arab Emirates", "MENA"),
    (3, "DE", "Germany", "EMEA"),
]

DEPARTMENTS = [
    # key, name, function_group
    (1, "Engineering", "Technology"),
    (2, "Product", "Technology"),
    (3, "Sales", "Go-To-Market"),
    (4, "Marketing", "Go-To-Market"),
    (5, "Customer Support", "Go-To-Market"),
    (6, "Finance", "G&A"),
    (7, "Human Resources", "G&A"),
    (8, "Operations", "G&A"),
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _month_starts(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(dt.date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _date_key(d: dt.date) -> int:
    return d.year * 100 + d.month


def build_dim_date() -> pd.DataFrame:
    rows = []
    for d in _month_starts(WINDOW_START, WINDOW_END):
        rows.append(
            {
                "date_key": _date_key(d),
                "full_date": d,
                "year": d.year,
                "month": d.month,
                "month_name": MONTH_NAMES[d.month - 1],
                "quarter": f"Q{(d.month - 1) // 3 + 1}",
                "year_month": f"{d.year:04d}-{d.month:02d}",
            }
        )
    return pd.DataFrame(rows)


def _latest_ratings(perf: pd.DataFrame) -> dict[str, int]:
    """Map employee_id -> rating in their most recent review year."""
    if perf.empty:
        return {}
    idx = perf.groupby("employee_id")["review_year"].idxmax()
    latest = perf.loc[idx]
    return dict(zip(latest["employee_id"], latest["rating"], strict=True))


def load(raw_dir: Path | None = None) -> dict[str, int]:
    """Run the full ETL and return counts for metrics/logging."""
    raw_dir = Path(raw_dir) if raw_dir else (DATA_OUT / "raw")
    if not (raw_dir / "raw_employees.csv").exists():
        generate_raw(raw_dir)

    emp_raw = pd.read_csv(raw_dir / "raw_employees.csv", dtype=str, keep_default_na=False)
    perf_raw = pd.read_csv(raw_dir / "raw_performance.csv")
    funnel_raw = pd.read_csv(raw_dir / "raw_hiring_funnel.csv")

    engine = create_engine(database_url())

    # 1) Fresh schema every load (idempotent rebuild).
    with engine.begin() as conn:
        schema.metadata.drop_all(conn)
        schema.metadata.create_all(conn)

    country_key = {c[1]: c[0] for c in COUNTRIES}  # code -> key
    dept_key = {d[1]: d[0] for d in DEPARTMENTS}  # name -> key

    dim_country_df = pd.DataFrame(
        COUNTRIES, columns=["country_key", "country_code", "country_name", "region"]
    )
    dim_department_df = pd.DataFrame(
        DEPARTMENTS, columns=["department_key", "department_name", "function_group"]
    )
    dim_date_df = build_dim_date()

    # 3) Data-quality on employees.
    clean, quarantined = check_employees(emp_raw, set(country_key))

    # 4) dim_employee.
    ratings = _latest_ratings(perf_raw)
    clean = clean.reset_index(drop=True)
    clean["employee_key"] = range(1, len(clean) + 1)
    clean["country_key"] = clean["country_code"].map(country_key)
    clean["department_key"] = clean["department"].map(dept_key)
    clean["is_active"] = clean["_exit"].isna().astype(int)
    clean["latest_rating"] = clean["employee_id"].map(ratings)

    dim_employee_df = pd.DataFrame(
        {
            "employee_key": clean["employee_key"],
            "employee_id": clean["employee_id"],
            "full_name": clean["full_name"],
            "gender": clean["gender"],
            "country_key": clean["country_key"],
            "department_key": clean["department_key"],
            "grade": clean["grade"],
            "band": clean["band"],
            "annual_ctc_usd": clean["annual_ctc_usd"].astype(int),
            "hire_date": clean["_hire"],
            "exit_date": clean["_exit"],
            "exit_type": clean["exit_type"].replace("", None),
            "exit_reason": clean["exit_reason"].replace("", None),
            "is_active": clean["is_active"],
            "latest_rating": clean["latest_rating"],
        }
    )

    # 5a) fact_headcount_monthly: active employees as of each month-end.
    hc_rows = []
    for d in _month_starts(WINDOW_START, WINDOW_END):
        last_day = dt.date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        active = clean[
            (clean["_hire"] <= last_day)
            & (clean["_exit"].isna() | (clean["_exit"] > last_day))
        ]
        if active.empty:
            continue
        grp = (
            active.groupby(["department_key", "country_key", "grade", "gender"])
            .size()
            .reset_index(name="headcount")
        )
        grp["date_key"] = _date_key(d)
        hc_rows.append(grp)
    fact_headcount_df = pd.concat(hc_rows, ignore_index=True)[
        ["date_key", "department_key", "country_key", "grade", "gender", "headcount"]
    ]

    # 5b) fact_exits: one row per exit inside the window.
    leavers = clean[clean["_exit"].notna()].copy()
    leavers = leavers[
        (leavers["_exit"] >= WINDOW_START) & (leavers["_exit"] <= WINDOW_END)
    ]
    fact_exits_df = pd.DataFrame(
        {
            "exit_key": range(1, len(leavers) + 1),
            "date_key": [_date_key(d) for d in leavers["_exit"]],
            "employee_key": leavers["employee_key"],
            "department_key": leavers["department_key"],
            "country_key": leavers["country_key"],
            "grade": leavers["grade"],
            "gender": leavers["gender"],
            "exit_type": leavers["exit_type"],
            "exit_reason": leavers["exit_reason"],
            "tenure_days": [
                (e - h).days for e, h in zip(leavers["_exit"], leavers["_hire"], strict=True)
            ],
        }
    )

    # 6) fact_hiring_funnel: map natural keys to surrogate keys.
    funnel_raw["date_key"] = pd.to_datetime(funnel_raw["month"]).apply(
        lambda t: t.year * 100 + t.month
    )
    funnel_raw["country_key"] = funnel_raw["country_code"].map(country_key)
    funnel_raw["department_key"] = funnel_raw["department"].map(dept_key)
    fact_funnel_df = pd.DataFrame(
        {
            "funnel_key": range(1, len(funnel_raw) + 1),
            "date_key": funnel_raw["date_key"],
            "department_key": funnel_raw["department_key"],
            "country_key": funnel_raw["country_key"],
            "applications": funnel_raw["applications"],
            "screened": funnel_raw["screened"],
            "interviewed": funnel_raw["interviewed"],
            "offers": funnel_raw["offers"],
            "accepts": funnel_raw["accepts"],
            "hires": funnel_raw["hires"],
            "avg_time_to_hire_days": funnel_raw["avg_time_to_hire_days"],
        }
    )

    quarantine_df = pd.DataFrame(quarantined)
    if not quarantine_df.empty:
        quarantine_df.insert(0, "id", range(1, len(quarantine_df) + 1))

    # Write everything (append into the freshly-created empty tables).
    with engine.begin() as conn:
        dim_country_df.to_sql("dim_country", conn, if_exists="append", index=False)
        dim_department_df.to_sql("dim_department", conn, if_exists="append", index=False)
        dim_date_df.to_sql("dim_date", conn, if_exists="append", index=False)
        dim_employee_df.to_sql("dim_employee", conn, if_exists="append", index=False)
        fact_headcount_df.to_sql(
            "fact_headcount_monthly", conn, if_exists="append", index=False
        )
        fact_exits_df.to_sql("fact_exits", conn, if_exists="append", index=False)
        fact_funnel_df.to_sql("fact_hiring_funnel", conn, if_exists="append", index=False)
        if not quarantine_df.empty:
            quarantine_df.to_sql("quarantine", conn, if_exists="append", index=False)

    counts = {
        "employees_loaded": len(dim_employee_df),
        "rows_quarantined": len(quarantined),
        "fact_headcount_rows": len(fact_headcount_df),
        "fact_exits_rows": len(fact_exits_df),
        "fact_funnel_rows": len(fact_funnel_df),
    }
    print("Warehouse load complete:")
    for k, v in counts.items():
        print(f"  {k:22s} {v:>7d}")
    return counts


if __name__ == "__main__":
    load()
