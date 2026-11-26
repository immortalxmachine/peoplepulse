"""Tests for the real-data source loader (reads the committed IBM HR CSV)."""

from __future__ import annotations

from peoplepulse.data import source


def test_ingest_shape_and_columns():
    df = source.ingest()
    # The published dataset has exactly 1,470 employees.
    assert len(df) == 1470
    # Key tidy columns must be present after rename.
    for col in ("employee_id", "department", "job_role", "attrition_flag", "monthly_income"):
        assert col in df.columns
    # Constant/useless source columns are dropped.
    for col in ("EmployeeCount", "Over18", "StandardHours"):
        assert col not in df.columns


def test_ids_are_unique():
    df = source.ingest()
    assert df["employee_id"].is_unique


def test_attrition_is_real_label():
    df = source.ingest()
    # Only the two real label values exist; roughly 16% left.
    assert set(df["attrition_flag"].unique()) == {"Yes", "No"}
    rate = (df["attrition_flag"] == "Yes").mean()
    assert 0.10 < rate < 0.25
