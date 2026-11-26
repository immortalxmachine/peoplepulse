"""Unit tests for the data-quality checks (no database needed)."""

from __future__ import annotations

import pandas as pd

from peoplepulse.warehouse.quality import check_employees

KNOWN = {"IN", "AE", "DE"}


def _row(**kw):
    base = {
        "employee_id": "E1",
        "full_name": "Test",
        "gender": "M",
        "country_code": "IN",
        "department": "Sales",
        "grade": "G2",
        "band": "B2",
        "annual_ctc_usd": "25000",
        "hire_date": "2023-01-01",
        "exit_date": "",
        "exit_type": "",
        "exit_reason": "",
    }
    base.update(kw)
    return base


def test_clean_row_passes():
    raw = pd.DataFrame([_row()])
    clean, bad = check_employees(raw, KNOWN)
    assert len(clean) == 1
    assert bad == []


def test_each_failure_reason():
    raw = pd.DataFrame(
        [
            _row(employee_id="E1"),  # valid, kept
            _row(employee_id="E1", full_name="dup"),  # duplicate
            _row(employee_id=""),  # null id
            _row(employee_id="E2", hire_date="not-a-date"),  # bad date
            _row(employee_id="E3", hire_date="2024-06-01", exit_date="2023-01-01"),  # order
            _row(employee_id="E4", country_code="ZZ"),  # unknown country
        ]
    )
    clean, bad = check_employees(raw, KNOWN)
    reasons = sorted(b["reason"] for b in bad)
    assert reasons == [
        "duplicate_employee_id",
        "exit_before_hire",
        "invalid_hire_date",
        "null_employee_id",
        "unknown_country",
    ]
    assert len(clean) == 1  # only the first valid E1 survives
