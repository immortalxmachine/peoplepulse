"""Star-schema definition (SQLAlchemy Core).

We define the schema once with SQLAlchemy Core so it emits *dialect-correct* DDL
on both SQLite (local dev) and PostgreSQL (CI) from the same source. Surrogate
keys are plain INTEGERs assigned in Python (not auto-increment) so inserts and
DDL are identical across both backends.

Model (Kimball-style star):

  dim_date ─┐
  dim_department ─┤
  dim_country ─┤──< fact_headcount_monthly
  dim_employee ─┤──< fact_exits
                └──< fact_hiring_funnel

  quarantine  -- rejected source rows + the reason they failed DQ.

`schema.sql` (committed, Postgres dialect) is generated from these tables for
documentation; it is not the source of truth.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
)

metadata = MetaData()

dim_country = Table(
    "dim_country",
    metadata,
    Column("country_key", Integer, primary_key=True, autoincrement=False),
    Column("country_code", String(2), nullable=False, unique=True),
    Column("country_name", String(64), nullable=False),
    Column("region", String(32), nullable=False),
)

dim_department = Table(
    "dim_department",
    metadata,
    Column("department_key", Integer, primary_key=True, autoincrement=False),
    Column("department_name", String(64), nullable=False, unique=True),
    Column("function_group", String(32), nullable=False),
)

# Monthly grain. date_key is YYYYMM (e.g. 202501) so facts join on an integer.
dim_date = Table(
    "dim_date",
    metadata,
    Column("date_key", Integer, primary_key=True, autoincrement=False),
    Column("full_date", Date, nullable=False),  # first day of the month
    Column("year", Integer, nullable=False),
    Column("month", Integer, nullable=False),
    Column("month_name", String(12), nullable=False),
    Column("quarter", String(2), nullable=False),  # Q1..Q4
    Column("year_month", String(7), nullable=False),  # 'YYYY-MM'
)

dim_employee = Table(
    "dim_employee",
    metadata,
    Column("employee_key", Integer, primary_key=True, autoincrement=False),
    Column("employee_id", String(16), nullable=False, unique=True),
    Column("full_name", String(80), nullable=False),
    Column("gender", String(1), nullable=False),
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    Column(
        "department_key",
        Integer,
        ForeignKey("dim_department.department_key"),
        nullable=False,
    ),
    Column("grade", String(4), nullable=False),
    Column("band", String(4), nullable=False),
    Column("annual_ctc_usd", Integer, nullable=False),
    Column("hire_date", Date, nullable=False),
    Column("exit_date", Date, nullable=True),
    Column("exit_type", String(12), nullable=True),
    Column("exit_reason", String(32), nullable=True),
    Column("is_active", Integer, nullable=False),  # 1/0
    Column("latest_rating", Integer, nullable=True),
)

fact_headcount_monthly = Table(
    "fact_headcount_monthly",
    metadata,
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column(
        "department_key",
        Integer,
        ForeignKey("dim_department.department_key"),
        nullable=False,
    ),
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    Column("grade", String(4), nullable=False),
    Column("gender", String(1), nullable=False),
    Column("headcount", Integer, nullable=False),
)

fact_exits = Table(
    "fact_exits",
    metadata,
    Column("exit_key", Integer, primary_key=True, autoincrement=False),
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column("employee_key", Integer, ForeignKey("dim_employee.employee_key"), nullable=False),
    Column(
        "department_key",
        Integer,
        ForeignKey("dim_department.department_key"),
        nullable=False,
    ),
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    Column("grade", String(4), nullable=False),
    Column("gender", String(1), nullable=False),
    Column("exit_type", String(12), nullable=False),
    Column("exit_reason", String(32), nullable=False),
    Column("tenure_days", Integer, nullable=False),
)

fact_hiring_funnel = Table(
    "fact_hiring_funnel",
    metadata,
    Column("funnel_key", Integer, primary_key=True, autoincrement=False),
    Column("date_key", Integer, ForeignKey("dim_date.date_key"), nullable=False),
    Column(
        "department_key",
        Integer,
        ForeignKey("dim_department.department_key"),
        nullable=False,
    ),
    Column("country_key", Integer, ForeignKey("dim_country.country_key"), nullable=False),
    Column("applications", Integer, nullable=False),
    Column("screened", Integer, nullable=False),
    Column("interviewed", Integer, nullable=False),
    Column("offers", Integer, nullable=False),
    Column("accepts", Integer, nullable=False),
    Column("hires", Integer, nullable=False),
    Column("avg_time_to_hire_days", Float, nullable=False),
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
    dim_country,
    dim_department,
    dim_date,
    dim_employee,
    fact_headcount_monthly,
    fact_exits,
    fact_hiring_funnel,
    quarantine,
]
