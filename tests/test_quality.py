"""Unit tests for the data-quality checks (no database needed).

The real dataset is clean, so these tests prove each rule by feeding it rows that
are *deliberately* broken — the checks are real constraints, not decoration.
"""

from __future__ import annotations

import pandas as pd

from peoplepulse.warehouse.quality import check_employees

KNOWN = {"Sales", "Research & Development", "Human Resources"}


def _row(**kw):
    base = {
        "employee_id": "1",
        "gender": "Male",
        "age": "35",
        "attrition_flag": "No",
        "department": "Sales",
        "job_role": "Sales Executive",
        "education_level": "3",
        "education_field": "Life Sciences",
        "job_level": "2",
        "marital_status": "Single",
        "business_travel": "Travel_Rarely",
        "overtime": "No",
        "monthly_income": "5000",
        "daily_rate": "800",
        "hourly_rate": "60",
        "monthly_rate": "15000",
        "distance_from_home": "5",
        "total_working_years": "10",
        "years_at_company": "5",
        "environment_satisfaction": "3",
        "job_satisfaction": "4",
        "job_involvement": "3",
        "relationship_satisfaction": "3",
        "work_life_balance": "3",
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
            _row(employee_id="1"),  # valid, kept
            _row(employee_id="1"),  # duplicate id
            _row(employee_id=""),  # null id
            _row(employee_id="2", attrition_flag="Maybe"),  # invalid label
            _row(employee_id="3", department="Marketing"),  # unknown department
            _row(employee_id="4", job_satisfaction="9"),  # ordinal out of range
            _row(employee_id="5", monthly_income="-100"),  # negative measure
        ]
    )
    clean, bad = check_employees(raw, KNOWN)
    reasons = sorted(b["reason"] for b in bad)
    assert reasons == [
        "duplicate_employee_id",
        "invalid_attrition",
        "negative_measure",
        "null_employee_id",
        "out_of_range_ordinal",
        "unknown_department",
    ]
    assert len(clean) == 1  # only the first valid row survives
