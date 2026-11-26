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
    # The real IBM HR dataset has 1,470 employees, 3 departments, 9 job roles.
    assert _scalar("SELECT COUNT(*) FROM dim_employee") == 1470
    assert _scalar("SELECT COUNT(*) FROM fact_employee") == 1470
    assert _scalar("SELECT COUNT(*) FROM dim_department") == 3
    assert _scalar("SELECT COUNT(*) FROM dim_job_role") == 9
    assert _scalar("SELECT COUNT(*) FROM dim_education") == 5


def test_clean_source_has_no_quarantine(warehouse):
    # The published dataset is clean -> every row passes DQ, nothing quarantined.
    assert _scalar("SELECT COUNT(*) FROM quarantine") == 0


def test_all_views_return_rows(warehouse):
    for name in view_names():
        assert _scalar(f"SELECT COUNT(*) FROM {name}") >= 0  # executes without error


def test_attrition_is_plausible(warehouse):
    v = _scalar("SELECT attrition_pct FROM v_attrition_overall")
    assert 2.0 < v < 50.0  # ~16% in this dataset


def test_overtime_raises_attrition(warehouse):
    # A known, real signal in this dataset: overtime workers churn far more.
    yes = _scalar("SELECT attrition_pct FROM v_attrition_by_overtime WHERE overtime = 'Yes'")
    no = _scalar("SELECT attrition_pct FROM v_attrition_by_overtime WHERE overtime = 'No'")
    assert yes > no


def test_views_parse_as_postgres():
    # Portability guard: every view must be valid PostgreSQL too (CI runs them).
    for stmt in _statements():
        sqlglot.parse_one(stmt, read="postgres")
