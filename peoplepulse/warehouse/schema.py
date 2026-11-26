"""Star-schema definition (SQLAlchemy Core) for the REAL IBM HR dataset.

We define the schema once with SQLAlchemy Core so it emits *dialect-correct* DDL
on both SQLite (local dev) and PostgreSQL (CI) from the same source. Surrogate
keys are plain INTEGERs assigned in Python (not auto-increment) so inserts and
DDL are identical across both backends.

The source data (IBM HR Analytics Employee Attrition) is a single cross-sectional
snapshot: one row per employee with an ``attrition`` outcome. The model is a
Kimball-style star at employee grain:

  dim_department ─┐
  dim_job_role  ─┤──< dim_employee >──┐
  dim_education ─┘                    └──< fact_employee

  * dim_employee  -- one row per employee: descriptive attributes + the
                     attrition outcome (the label).
  * fact_employee -- one row per employee: the numeric measures (income, tenure,
                     satisfaction scores, ...). Keyed by employee_key.
  * quarantine    -- rejected source rows + the reason they failed DQ.

`schema.sql` (committed, Postgres dialect) is generated from these tables for
documentation; it is not the source of truth.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
)

metadata = MetaData()

dim_department = Table(
    "dim_department",
    metadata,
    Column("department_key", Integer, primary_key=True, autoincrement=False),
    Column("department_name", String(48), nullable=False, unique=True),
    Column("function_group", String(32), nullable=False),
)

dim_job_role = Table(
    "dim_job_role",
    metadata,
    Column("job_role_key", Integer, primary_key=True, autoincrement=False),
    Column("job_role", String(48), nullable=False, unique=True),
    Column("department_name", String(48), nullable=False),
)

dim_education = Table(
    "dim_education",
    metadata,
    Column("education_key", Integer, primary_key=True, autoincrement=False),
    Column("education_level", Integer, nullable=False, unique=True),  # 1..5
    Column("education_label", String(24), nullable=False),
)

dim_employee = Table(
    "dim_employee",
    metadata,
    Column("employee_key", Integer, primary_key=True, autoincrement=False),
    Column("employee_id", String(16), nullable=False, unique=True),
    Column("gender", String(6), nullable=False),
    Column("age", Integer, nullable=False),
    Column("marital_status", String(12), nullable=False),
    Column("business_travel", String(20), nullable=False),
    Column("overtime", String(3), nullable=False),  # 'Yes' / 'No'
    Column("department_key", Integer, ForeignKey("dim_department.department_key"), nullable=False),
    Column("job_role_key", Integer, ForeignKey("dim_job_role.job_role_key"), nullable=False),
    Column("education_key", Integer, ForeignKey("dim_education.education_key"), nullable=False),
    Column("education_field", String(24), nullable=False),
    Column("job_level", Integer, nullable=False),  # 1..5
    # The outcome / label: 1 = the employee left, 0 = still employed.
    Column("attrition", Integer, nullable=False),
)

fact_employee = Table(
    "fact_employee",
    metadata,
    Column(
        "employee_key",
        Integer,
        ForeignKey("dim_employee.employee_key"),
        primary_key=True,
        autoincrement=False,
    ),
    Column("department_key", Integer, ForeignKey("dim_department.department_key"), nullable=False),
    Column("job_role_key", Integer, ForeignKey("dim_job_role.job_role_key"), nullable=False),
    Column("monthly_income", Integer, nullable=False),
    Column("daily_rate", Integer, nullable=False),
    Column("hourly_rate", Integer, nullable=False),
    Column("monthly_rate", Integer, nullable=False),
    Column("distance_from_home", Integer, nullable=False),
    Column("total_working_years", Integer, nullable=False),
    Column("years_at_company", Integer, nullable=False),
    Column("years_in_current_role", Integer, nullable=False),
    Column("years_since_last_promotion", Integer, nullable=False),
    Column("years_with_curr_manager", Integer, nullable=False),
    Column("num_companies_worked", Integer, nullable=False),
    Column("percent_salary_hike", Integer, nullable=False),
    Column("training_times_last_year", Integer, nullable=False),
    Column("job_satisfaction", Integer, nullable=False),  # 1..4
    Column("environment_satisfaction", Integer, nullable=False),  # 1..4
    Column("job_involvement", Integer, nullable=False),  # 1..4
    Column("relationship_satisfaction", Integer, nullable=False),  # 1..4
    Column("work_life_balance", Integer, nullable=False),  # 1..4
    Column("performance_rating", Integer, nullable=False),  # 3..4
    Column("stock_option_level", Integer, nullable=False),  # 0..3
    # Mirror of the label so measure-only views need not join dim_employee.
    Column("attrition", Integer, nullable=False),
)

quarantine = Table(
    "quarantine",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("source_table", String(32), nullable=False),
    Column("employee_id", String(16), nullable=True),
    Column("reason", String(48), nullable=False),
    Column("raw_row", String(512), nullable=False),
)

# Tables that are rebuilt on every load, in dependency-safe order.
ALL_TABLES = [
    dim_department,
    dim_job_role,
    dim_education,
    dim_employee,
    fact_employee,
    quarantine,
]
