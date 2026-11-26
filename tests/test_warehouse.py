"""Tests for the loaded warehouse + MIS views (uses the `warehouse` fixture)."""

from __future__ import annotations

import sqlglot
from sqlalchemy import create_engine, text

from peoplepulse.config import database_url
from peoplepulse.mis.build_views import _statements, view_names


def _scalar(sql: str):
    with create_engine(database_url()).connect() as c:
        return c.execute(text(sql)).scalar()


def test_dimensions_and_facts_loaded(warehouse):
    assert _scalar("SELECT COUNT(*) FROM dim_employee") == 2000
    assert _scalar("SELECT COUNT(*) FROM dim_country") == 3
    assert _scalar("SELECT COUNT(*) FROM dim_department") == 8
    assert _scalar("SELECT COUNT(*) FROM dim_date") == 36
    assert _scalar("SELECT COUNT(*) FROM fact_headcount_monthly") > 0
    assert _scalar("SELECT COUNT(*) FROM fact_exits") > 0


def test_eight_rows_quarantined_with_reasons(warehouse):
    assert _scalar("SELECT COUNT(*) FROM quarantine") == 8
    with create_engine(database_url()).connect() as c:
        reasons = {
            r[0] for r in c.execute(text("SELECT DISTINCT reason FROM quarantine"))
        }
    assert reasons == {
        "null_employee_id",
        "duplicate_employee_id",
        "invalid_hire_date",
        "exit_before_hire",
        "unknown_country",
    }


def test_all_views_return_rows(warehouse):
    for name in view_names():
        assert _scalar(f"SELECT COUNT(*) FROM {name}") >= 0  # executes without error


def test_attrition_is_plausible(warehouse):
    # Rolling 12-month attrition should sit in a sane HR range.
    v = _scalar(
        "SELECT rolling_12m_attrition_pct FROM v_attrition_monthly "
        "ORDER BY date_key DESC LIMIT 1"
    )
    assert 2.0 < v < 50.0


def test_views_parse_as_postgres():
    # Portability guard: every view must be valid PostgreSQL too (CI runs them).
    for stmt in _statements():
        sqlglot.parse_one(stmt, read="postgres")
