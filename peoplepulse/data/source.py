"""Real-data source for PeoplePulse.

======================================================================
This project uses a REAL, PUBLIC dataset — nothing is synthetic.
Source: IBM HR Analytics Employee Attrition & Performance (Kaggle,
`pavansubhasht/ibm-hr-analytics-attrition-dataset`, License: DbCL-1.0).
1,470 employees of a fictional company, created by IBM data scientists
as a public teaching dataset. No real individual's data is used, and
PeoplePulse adds nothing of its own to it.
======================================================================

This module replaces the previous synthetic generator. It reads the raw
Kaggle CSV and normalises its 35 wide columns into the tidy, snake_case
`employees` frame the warehouse loads. It fabricates no rows and invents
no values — every field is a column of the published dataset (a few are
dropped because they are constant: ``EmployeeCount``, ``Over18``,
``StandardHours``).

The dataset is a single cross-sectional snapshot: one row per current/past
employee with an ``Attrition`` (Yes/No) outcome. It therefore has no hire or
exit dates, no monthly facts and no hiring funnel — PeoplePulse models exactly
what the data contains (cross-sectional attrition analytics + a prediction
model), nothing more.

Run (download + preview):  python -m peoplepulse.data.source
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from peoplepulse.config import ROOT

KAGGLE_DATASET = "pavansubhasht/ibm-hr-analytics-attrition-dataset"
RAW_DIR = ROOT / "data" / "raw"
RAW_CSV = RAW_DIR / "WA_Fn-UseC_-HR-Employee-Attrition.csv"

# Education is an ordinal 1..5 with IBM's documented labels.
EDUCATION_LABELS = {
    1: "Below College",
    2: "College",
    3: "Bachelor",
    4: "Master",
    5: "Doctor",
}

# Columns that are constant across all 1,470 rows and carry no information.
_CONSTANT_COLS = ["EmployeeCount", "Over18", "StandardHours"]

# Wide IBM column -> tidy snake_case name used everywhere downstream.
_RENAME = {
    "EmployeeNumber": "employee_id",
    "Age": "age",
    "Attrition": "attrition_flag",  # 'Yes'/'No' -> mapped to 1/0 in the loader
    "BusinessTravel": "business_travel",
    "DailyRate": "daily_rate",
    "Department": "department",
    "DistanceFromHome": "distance_from_home",
    "Education": "education_level",
    "EducationField": "education_field",
    "EnvironmentSatisfaction": "environment_satisfaction",
    "Gender": "gender",
    "HourlyRate": "hourly_rate",
    "JobInvolvement": "job_involvement",
    "JobLevel": "job_level",
    "JobRole": "job_role",
    "JobSatisfaction": "job_satisfaction",
    "MaritalStatus": "marital_status",
    "MonthlyIncome": "monthly_income",
    "MonthlyRate": "monthly_rate",
    "NumCompaniesWorked": "num_companies_worked",
    "OverTime": "overtime",
    "PercentSalaryHike": "percent_salary_hike",
    "PerformanceRating": "performance_rating",
    "RelationshipSatisfaction": "relationship_satisfaction",
    "StockOptionLevel": "stock_option_level",
    "TotalWorkingYears": "total_working_years",
    "TrainingTimesLastYear": "training_times_last_year",
    "WorkLifeBalance": "work_life_balance",
    "YearsAtCompany": "years_at_company",
    "YearsInCurrentRole": "years_in_current_role",
    "YearsSinceLastPromotion": "years_since_last_promotion",
    "YearsWithCurrManager": "years_with_curr_manager",
}


def download(force: bool = False) -> Path:
    """Download the Kaggle CSV if it is not already present.

    Needs Kaggle credentials (``~/.kaggle/kaggle.json`` or the
    ``KAGGLE_API_TOKEN`` env var). Does nothing if the file already exists.
    """
    if RAW_CSV.exists() and not force:
        return RAW_CSV
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    subprocess.run(
        [
            sys.executable, "-m", "kaggle", "datasets", "download",
            "-d", KAGGLE_DATASET, "-p", str(RAW_DIR), "--unzip",
        ],
        check=True,
        env=env,
    )
    if not RAW_CSV.exists():
        raise FileNotFoundError(
            f"Kaggle download did not produce {RAW_CSV}. Download it manually "
            f"from https://www.kaggle.com/datasets/{KAGGLE_DATASET} and place "
            f"the CSV at that path."
        )
    return RAW_CSV


def load_raw(csv_path: Path | None = None) -> pd.DataFrame:
    """Read the raw Kaggle CSV exactly as published (string-safe)."""
    path = Path(csv_path) if csv_path else RAW_CSV
    if not path.exists():
        download()
    # utf-8-sig strips the BOM the Kaggle file ships with on the first header.
    return pd.read_csv(path, encoding="utf-8-sig")


def ingest(csv_path: Path | None = None) -> pd.DataFrame:
    """Return the tidy employees frame used by the warehouse loader.

    Pure projection + rename of the published columns — no new rows, no
    imputed values. ``employee_id`` is the dataset's ``EmployeeNumber``.
    """
    raw = load_raw(csv_path)
    df = raw.drop(columns=[c for c in _CONSTANT_COLS if c in raw.columns])
    df = df.rename(columns=_RENAME)
    # Normalise the id to a string so the DQ layer and keys treat it uniformly.
    df["employee_id"] = df["employee_id"].astype("Int64").astype(str)
    return df


def main() -> dict[str, int]:
    download()
    df = ingest()
    counts = {"employees": len(df), "columns": df.shape[1]}
    print("Loaded REAL IBM HR Attrition data:")
    print(f"  employees {counts['employees']}  |  columns {counts['columns']}")
    print(f"  attrition (Yes) {int((df['attrition_flag'] == 'Yes').sum())}")
    print(f"  -> {RAW_CSV}")
    return counts


if __name__ == "__main__":
    main()
