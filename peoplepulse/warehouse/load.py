"""ETL: real IBM HR CSV -> star schema in the warehouse.

Steps:
  1. Ingest the real Kaggle CSV (peoplepulse/data/source.py) -- no fabrication.
  2. (Re)create all tables from the SQLAlchemy schema.
  3. Build reference dimensions (department, job role, education) from the data.
  4. Run data-quality checks; quarantine any bad rows (0 on the clean source).
  5. Build dim_employee (surrogate keys + attrition label).
  6. Build fact_employee (numeric measures per employee).

Run:  python -m peoplepulse.warehouse.load
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from peoplepulse.config import database_url
from peoplepulse.data.source import EDUCATION_LABELS, ingest
from peoplepulse.warehouse import schema
from peoplepulse.warehouse.quality import check_employees

# Department -> function group (stable mapping for the 3 IBM departments).
FUNCTION_GROUP = {
    "Sales": "Go-To-Market",
    "Research & Development": "Technology",
    "Human Resources": "G&A",
}

# Numeric measure columns copied straight into fact_employee.
_FACT_MEASURES = [
    "monthly_income", "daily_rate", "hourly_rate", "monthly_rate",
    "distance_from_home", "total_working_years", "years_at_company",
    "years_in_current_role", "years_since_last_promotion", "years_with_curr_manager",
    "num_companies_worked", "percent_salary_hike", "training_times_last_year",
    "job_satisfaction", "environment_satisfaction", "job_involvement",
    "relationship_satisfaction", "work_life_balance", "performance_rating",
    "stock_option_level",
]


def load(csv_path: Path | None = None) -> dict[str, int]:
    """Run the full ETL and return counts for metrics/logging."""
    raw = ingest(csv_path)
    engine = create_engine(database_url())

    # Reference dimensions, derived from the data (stable, sorted order).
    departments = sorted(raw["department"].unique())
    dept_key = {name: i + 1 for i, name in enumerate(departments)}
    dim_department_df = pd.DataFrame(
        {
            "department_key": [dept_key[d] for d in departments],
            "department_name": departments,
            "function_group": [FUNCTION_GROUP.get(d, "Other") for d in departments],
        }
    )

    roles = sorted(raw["job_role"].unique())
    role_key = {name: i + 1 for i, name in enumerate(roles)}
    role_dept = (
        raw[["job_role", "department"]]
        .drop_duplicates()
        .set_index("job_role")["department"]
        .to_dict()
    )
    dim_job_role_df = pd.DataFrame(
        {
            "job_role_key": [role_key[r] for r in roles],
            "job_role": roles,
            "department_name": [role_dept[r] for r in roles],
        }
    )

    edu_levels = sorted(int(x) for x in raw["education_level"].unique())
    edu_key = {lvl: i + 1 for i, lvl in enumerate(edu_levels)}
    dim_education_df = pd.DataFrame(
        {
            "education_key": [edu_key[lvl] for lvl in edu_levels],
            "education_level": edu_levels,
            "education_label": [EDUCATION_LABELS.get(lvl, str(lvl)) for lvl in edu_levels],
        }
    )

    # 1) Fresh schema every load (drop dependent views first).
    from peoplepulse.mis.build_views import view_names  # local import, no cycle

    with engine.begin() as conn:
        for view in view_names():
            conn.execute(text(f"DROP VIEW IF EXISTS {view}"))
        schema.metadata.drop_all(conn)
        schema.metadata.create_all(conn)

    # 2) Data quality.
    clean, quarantined = check_employees(raw, set(departments))
    clean = clean.reset_index(drop=True)
    clean["employee_key"] = range(1, len(clean) + 1)
    clean["department_key"] = clean["department"].map(dept_key)
    clean["job_role_key"] = clean["job_role"].map(role_key)
    clean["education_key"] = clean["education_level"].astype(int).map(edu_key)
    clean["attrition"] = (clean["attrition_flag"].astype(str) == "Yes").astype(int)

    # 3) dim_employee (descriptive attributes + label).
    dim_employee_df = pd.DataFrame(
        {
            "employee_key": clean["employee_key"],
            "employee_id": clean["employee_id"].astype(str),
            "gender": clean["gender"],
            "age": clean["age"].astype(int),
            "marital_status": clean["marital_status"],
            "business_travel": clean["business_travel"],
            "overtime": clean["overtime"],
            "department_key": clean["department_key"],
            "job_role_key": clean["job_role_key"],
            "education_key": clean["education_key"],
            "education_field": clean["education_field"],
            "job_level": clean["job_level"].astype(int),
            "attrition": clean["attrition"],
        }
    )

    # 4) fact_employee (numeric measures per employee).
    fact_cols = {
        "employee_key": clean["employee_key"],
        "department_key": clean["department_key"],
        "job_role_key": clean["job_role_key"],
    }
    for col in _FACT_MEASURES:
        fact_cols[col] = clean[col].astype(int)
    fact_cols["attrition"] = clean["attrition"]
    fact_employee_df = pd.DataFrame(fact_cols)

    quarantine_df = pd.DataFrame(quarantined)
    if not quarantine_df.empty:
        quarantine_df.insert(0, "id", range(1, len(quarantine_df) + 1))

    with engine.begin() as conn:
        dim_department_df.to_sql("dim_department", conn, if_exists="append", index=False)
        dim_job_role_df.to_sql("dim_job_role", conn, if_exists="append", index=False)
        dim_education_df.to_sql("dim_education", conn, if_exists="append", index=False)
        dim_employee_df.to_sql("dim_employee", conn, if_exists="append", index=False)
        fact_employee_df.to_sql("fact_employee", conn, if_exists="append", index=False)
        if not quarantine_df.empty:
            quarantine_df.to_sql("quarantine", conn, if_exists="append", index=False)

    counts = {
        "employees_loaded": len(dim_employee_df),
        "rows_quarantined": len(quarantined),
        "departments": len(dim_department_df),
        "job_roles": len(dim_job_role_df),
        "leavers": int(dim_employee_df["attrition"].sum()),
    }
    print("Warehouse load complete (REAL IBM HR data):")
    for k, v in counts.items():
        print(f"  {k:22s} {v:>7d}")
    return counts


if __name__ == "__main__":
    load()
