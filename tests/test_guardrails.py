"""Unit tests for the SQL guardrails (no database needed)."""

from __future__ import annotations

from peoplepulse.api.guardrails import validate


def test_allows_valid_view_select():
    r = validate("SELECT * FROM v_headcount_trend", dialect="sqlite")
    assert r.ok
    assert "LIMIT" in r.sql.upper()  # a row limit was enforced


def test_adds_limit_when_missing():
    r = validate("SELECT year_month FROM v_attrition_monthly", dialect="sqlite")
    assert r.ok and "1000" in r.sql


def test_caps_oversized_limit():
    r = validate("SELECT * FROM v_headcount_trend LIMIT 999999", dialect="sqlite")
    assert r.ok and "999999" not in r.sql


def test_blocks_non_select():
    assert not validate("DROP TABLE dim_employee").ok
    assert not validate("UPDATE fact_exits SET exits = 0").ok
    assert not validate("INSERT INTO dim_country VALUES (9,'XX','x','y')").ok


def test_blocks_stacked_statements():
    r = validate("SELECT * FROM v_headcount_trend; DROP TABLE dim_employee")
    assert not r.ok and r.reason == "multiple_statements"


def test_blocks_non_allowlisted_table():
    # dim_employee holds individual records -> never queryable via the assistant.
    r = validate("SELECT * FROM dim_employee")
    assert not r.ok and r.reason.startswith("table_not_allowed")


def test_blocks_unparseable():
    assert not validate("this is not sql ;;;").ok
