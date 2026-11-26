"""Tests for the synthetic data generator."""

from __future__ import annotations

import pandas as pd

from peoplepulse.data import generate


def test_counts_and_bad_rows(tmp_path):
    counts = generate.main(tmp_path)
    # 2000 clean employees + the fixed number of injected dirty rows.
    assert counts["raw_employees"] == generate.N_EMPLOYEES + generate.N_BAD_ROWS_TOTAL
    assert counts["injected_bad_rows"] == 8
    assert counts["raw_hiring_funnel"] > 0


def test_export_has_no_hidden_risk_column(tmp_path):
    generate.main(tmp_path)
    df = pd.read_csv(tmp_path / "raw_employees.csv")
    # The latent risk helper must never be exported (it is not observable data).
    assert "_risk" not in df.columns
    assert {"employee_id", "department", "grade", "hire_date"} <= set(df.columns)


def test_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate.main(a)
    generate.main(b)
    # Same seed -> identical output.
    da = pd.read_csv(a / "raw_employees.csv")
    db = pd.read_csv(b / "raw_employees.csv")
    pd.testing.assert_frame_equal(da, db)
