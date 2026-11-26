"""Unit tests for the SQL guardrails (no database needed)."""

from __future__ import annotations

from peoplepulse.api.guardrails import validate


def test_allows_valid_view_select():
    r = validate("SELECT * FROM v_attrition_overall", dialect="sqlite")
    assert r.ok
    assert "LIMIT" in r.sql.upper()  # a row limit was enforced


def test_adds_limit_when_missing():
    r = validate("SELECT attrition_pct FROM v_attrition_by_department", dialect="sqlite")
    assert r.ok and "1000" in r.sql


def test_caps_oversized_limit():
    r = validate("SELECT * FROM v_attrition_overall LIMIT 999999", dialect="sqlite")
    assert r.ok and "999999" not in r.sql


def test_blocks_non_select():
    assert not validate("DROP TABLE dim_employee").ok
    assert not validate("UPDATE fact_employee SET attrition = 0").ok
    assert not validate("INSERT INTO dim_department VALUES (9,'X','Y')").ok


def test_blocks_stacked_statements():
    r = validate("SELECT * FROM v_attrition_overall; DROP TABLE dim_employee")
    assert not r.ok and r.reason == "multiple_statements"


def test_blocks_non_allowlisted_table():
    # dim_employee holds individual records -> never queryable via the assistant.
    r = validate("SELECT * FROM dim_employee")
    assert not r.ok and r.reason.startswith("table_not_allowed")


def test_blocks_unparseable():
    assert not validate("this is not sql ;;;").ok
