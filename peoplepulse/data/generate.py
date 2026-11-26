"""Generate a SYNTHETIC HRIS export for PeoplePulse.

======================================================================
EVERYTHING THIS FILE PRODUCES IS RANDOMLY GENERATED.  No real employee,
salary, or applicant data is used.  Names come from small generic pools.
======================================================================

The generator emulates a *source system* dump: three raw CSVs that look like
what an HRIS (e.g. Workday / SAP SuccessFactors) might export.  We deliberately
inject a small, fixed number of dirty rows so the warehouse data-quality checks
have something to quarantine (see peoplepulse/warehouse/load.py).

Raw outputs (written to data_out/raw/):
  raw_employees.csv       one row per employee (+ injected bad rows)
  raw_performance.csv     one row per employee per review year
  raw_hiring_funnel.csv   recruiting funnel per month / country / department

Run:  python -m peoplepulse.data.generate
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from peoplepulse.config import DATA_OUT

# --- Reproducibility ---------------------------------------------------------
SEED = 42
# Analysis window for the monthly facts: 3 full years.
WINDOW_START = date(2023, 1, 1)
WINDOW_END = date(2025, 12, 31)

N_EMPLOYEES = 2000  # distinct employees generated (some hired before the window)

# Number of intentionally dirty rows appended to raw_employees (kept explicit so
# the quarantine count in metrics.json is reproducible).
N_BAD_DUP_ID = 2
N_BAD_NULL_ID = 2
N_BAD_DATE_ORDER = 2  # exit_date before hire_date
N_BAD_DATE_PARSE = 1  # unparseable hire_date string
N_BAD_COUNTRY = 1  # unknown country code
N_BAD_ROWS_TOTAL = (
    N_BAD_DUP_ID + N_BAD_NULL_ID + N_BAD_DATE_ORDER + N_BAD_DATE_PARSE + N_BAD_COUNTRY
)

# --- Reference pools (all synthetic) -----------------------------------------
COUNTRIES = ["IN", "AE", "DE"]
# Relative hiring weight by country (India largest, as for many India-HQ firms).
COUNTRY_WEIGHTS = [0.60, 0.22, 0.18]

DEPARTMENTS = [
    "Engineering",
    "Product",
    "Sales",
    "Marketing",
    "Customer Support",
    "Finance",
    "Human Resources",
    "Operations",
]
DEPT_WEIGHTS = [0.30, 0.09, 0.18, 0.08, 0.14, 0.07, 0.06, 0.08]

GRADES = ["G1", "G2", "G3", "G4", "G5", "G6"]  # G1 junior .. G6 senior/leadership
# Most people sit in the middle grades.
GRADE_WEIGHTS = [0.22, 0.30, 0.24, 0.14, 0.07, 0.03]

# Compensation *bands* (synthetic, USD-equivalent annual) keyed by grade.
# Stored only as band code + a value sampled inside the band — not real pay.
BAND_BY_GRADE = {
    "G1": ("B1", 12_000, 20_000),
    "G2": ("B2", 18_000, 30_000),
    "G3": ("B3", 28_000, 48_000),
    "G4": ("B4", 45_000, 75_000),
    "G5": ("B5", 70_000, 120_000),
    "G6": ("B6", 110_000, 200_000),
}

VOLUNTARY_REASONS = [
    "Better opportunity",
    "Compensation",
    "Relocation",
    "Career growth",
    "Work-life balance",
    "Higher studies",
]
INVOLUNTARY_REASONS = [
    "Performance",
    "Restructuring",
    "Role redundancy",
    "Policy violation",
    "End of contract",
]

FIRST_NAMES = [
    "Aarav", "Diya", "Rohan", "Ananya", "Vikram", "Meera", "Karthik", "Priya",
    "Omar", "Layla", "Zaid", "Fatima", "Yusuf", "Noor", "Hassan", "Aisha",
    "Lukas", "Hanna", "Jonas", "Lena", "Felix", "Mia", "Paul", "Emilia",
]
LAST_NAMES = [
    "Sharma", "Iyer", "Patel", "Nair", "Reddy", "Das",
    "Al-Farsi", "Khan", "Hassan", "Rahman", "Saleh", "Aziz",
    "Müller", "Schmidt", "Weber", "Fischer", "Becker", "Wagner",
]


def _random_date(rng: np.random.Generator, start: date, end: date) -> date:
    """Uniform random date in [start, end]."""
    span = (end - start).days
    return start + timedelta(days=int(rng.integers(0, span + 1)))


def _month_starts(start: date, end: date) -> list[date]:
    """First-of-month dates covering [start, end] inclusive."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def generate_employees(rng: np.random.Generator) -> pd.DataFrame:
    """Build the clean employee table, then append injected dirty rows."""
    n = N_EMPLOYEES
    emp_ids = [f"E{100000 + i}" for i in range(n)]

    countries = rng.choice(COUNTRIES, size=n, p=COUNTRY_WEIGHTS)
    departments = rng.choice(DEPARTMENTS, size=n, p=DEPT_WEIGHTS)
    grades = rng.choice(GRADES, size=n, p=GRADE_WEIGHTS)

    # Gender is synthetic and given a mild, department-dependent skew purely so
    # the diversity-by-grade view has signal. Clearly not real.
    female_prob = {
        "Engineering": 0.28, "Product": 0.40, "Sales": 0.38, "Marketing": 0.55,
        "Customer Support": 0.52, "Finance": 0.46, "Human Resources": 0.62,
        "Operations": 0.34,
    }
    genders = np.array(
        [("F" if rng.random() < female_prob[d] else "M") for d in departments]
    )

    # Hire dates: 40% tenured (hired before the window, back to 2018),
    # 60% hired within the window.
    hire_dates = []
    pre_start = date(2018, 1, 1)
    for _ in range(n):
        if rng.random() < 0.40:
            hire_dates.append(_random_date(rng, pre_start, WINDOW_START - timedelta(days=1)))
        else:
            hire_dates.append(_random_date(rng, WINDOW_START, WINDOW_END))

    # Compensation band + sampled amount by grade.
    bands, ctc = [], []
    for g in grades:
        code, lo, hi = BAND_BY_GRADE[g]
        bands.append(code)
        ctc.append(int(rng.integers(lo, hi + 1)))

    # Exits: ~22% of employees leave. Exit date is after hire date and, for
    # realism, weighted toward the analysis window.
    exit_date: list[date | None] = [None] * n
    exit_type: list[str | None] = [None] * n
    exit_reason: list[str | None] = [None] * n
    for i in range(n):
        if rng.random() < 0.22:
            earliest = max(hire_dates[i] + timedelta(days=90), WINDOW_START)
            if earliest >= WINDOW_END:
                continue  # no room to exit inside the window; stays active
            ed = _random_date(rng, earliest, WINDOW_END)
            exit_date[i] = ed
            if rng.random() < 0.70:
                exit_type[i] = "Voluntary"
                exit_reason[i] = rng.choice(VOLUNTARY_REASONS)
            else:
                exit_type[i] = "Involuntary"
                exit_reason[i] = rng.choice(INVOLUNTARY_REASONS)

    names = [
        f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}" for _ in range(n)
    ]

    df = pd.DataFrame(
        {
            "employee_id": emp_ids,
            "full_name": names,
            "gender": genders,
            "country_code": countries,
            "department": departments,
            "grade": grades,
            "band": bands,
            "annual_ctc_usd": ctc,
            "hire_date": [d.isoformat() for d in hire_dates],
            "exit_date": [d.isoformat() if d else "" for d in exit_date],
            "exit_type": [t or "" for t in exit_type],
            "exit_reason": [r or "" for r in exit_reason],
        }
    )

    df = _inject_bad_rows(df, rng)
    return df


def _inject_bad_rows(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Append a fixed set of dirty rows for the DQ layer to quarantine."""
    bad = []

    # 1) Duplicate employee_id (reuse existing ids).
    for i in range(N_BAD_DUP_ID):
        r = df.iloc[i].to_dict()
        r["full_name"] = "Duplicate Record"
        bad.append(r)

    # 2) Null / missing employee_id.
    for _ in range(N_BAD_NULL_ID):
        r = df.iloc[0].to_dict()
        r = {**r, "employee_id": "", "full_name": "Missing ID"}
        bad.append(r)

    # 3) Exit date before hire date (impossible).
    for _ in range(N_BAD_DATE_ORDER):
        bad.append(
            {
                "employee_id": f"E9{rng.integers(10000, 99999)}",
                "full_name": "Bad Date Order",
                "gender": "M",
                "country_code": "IN",
                "department": "Sales",
                "grade": "G2",
                "band": "B2",
                "annual_ctc_usd": 25000,
                "hire_date": "2024-06-01",
                "exit_date": "2023-01-01",  # before hire
                "exit_type": "Voluntary",
                "exit_reason": "Compensation",
            }
        )

    # 4) Unparseable hire date.
    bad.append(
        {
            "employee_id": f"E9{rng.integers(10000, 99999)}",
            "full_name": "Bad Date Parse",
            "gender": "F",
            "country_code": "DE",
            "department": "Finance",
            "grade": "G3",
            "band": "B3",
            "annual_ctc_usd": 40000,
            "hire_date": "not-a-date",
            "exit_date": "",
            "exit_type": "",
            "exit_reason": "",
        }
    )

    # 5) Unknown country code.
    bad.append(
        {
            "employee_id": f"E9{rng.integers(10000, 99999)}",
            "full_name": "Bad Country",
            "gender": "M",
            "country_code": "ZZ",  # not in dim_country
            "department": "Operations",
            "grade": "G1",
            "band": "B1",
            "annual_ctc_usd": 15000,
            "hire_date": "2024-02-01",
            "exit_date": "",
            "exit_type": "",
            "exit_reason": "",
        }
    )

    return pd.concat([df, pd.DataFrame(bad)], ignore_index=True)


def generate_performance(rng: np.random.Generator, employees: pd.DataFrame) -> pd.DataFrame:
    """One performance rating (1-5) per employee per calendar year they were active."""
    rows = []
    for _, e in employees.iterrows():
        eid = e["employee_id"]
        if not eid:  # skip the null-id dirty rows
            continue
        try:
            hire_y = int(str(e["hire_date"])[:4])
        except ValueError:
            continue
        exit_y = None
        if e["exit_date"]:
            try:
                exit_y = int(str(e["exit_date"])[:4])
            except ValueError:
                exit_y = None
        last_y = exit_y or WINDOW_END.year
        for yr in range(max(hire_y, WINDOW_START.year), min(last_y, WINDOW_END.year) + 1):
            # Ratings centred on 3, leavers skew slightly lower.
            base = rng.normal(3.1 if e["exit_date"] else 3.3, 0.9)
            rating = int(min(5, max(1, round(base))))
            rows.append({"employee_id": eid, "review_year": yr, "rating": rating})
    return pd.DataFrame(rows)


def generate_hiring_funnel(rng: np.random.Generator) -> pd.DataFrame:
    """Monthly recruiting funnel per country / department.

    Funnel stages shrink at each step; time-to-hire varies by grade mix and
    country. All synthetic.
    """
    rows = []
    for month in _month_starts(WINDOW_START, WINDOW_END):
        for country in COUNTRIES:
            for dept in DEPARTMENTS:
                # Base volume scaled by country + department weighting.
                cw = COUNTRY_WEIGHTS[COUNTRIES.index(country)]
                dw = DEPT_WEIGHTS[DEPARTMENTS.index(dept)]
                apps = int(max(0, rng.normal(120 * cw * dw * 8, 6)))
                if apps == 0:
                    continue
                screened = int(apps * rng.uniform(0.45, 0.65))
                interviewed = int(screened * rng.uniform(0.35, 0.55))
                offers = int(interviewed * rng.uniform(0.25, 0.45))
                accepts = int(offers * rng.uniform(0.60, 0.85))
                hires = accepts  # accepted offers become hires next cycle
                tth = round(rng.normal(38, 10) + GRADES.index("G3") * 1.5, 1)
                rows.append(
                    {
                        "month": month.isoformat(),
                        "country_code": country,
                        "department": dept,
                        "applications": apps,
                        "screened": screened,
                        "interviewed": interviewed,
                        "offers": offers,
                        "accepts": accepts,
                        "hires": hires,
                        "avg_time_to_hire_days": max(10.0, tth),
                    }
                )
    return pd.DataFrame(rows)


def main(out_dir: Path | None = None) -> dict[str, int]:
    """Generate all raw CSVs. Returns row counts for metrics/logging."""
    rng = np.random.default_rng(SEED)
    out = Path(out_dir) if out_dir else (DATA_OUT / "raw")
    out.mkdir(parents=True, exist_ok=True)

    employees = generate_employees(rng)
    performance = generate_performance(rng, employees)
    funnel = generate_hiring_funnel(rng)

    employees.to_csv(out / "raw_employees.csv", index=False)
    performance.to_csv(out / "raw_performance.csv", index=False)
    funnel.to_csv(out / "raw_hiring_funnel.csv", index=False)

    counts = {
        "raw_employees": len(employees),
        "injected_bad_rows": N_BAD_ROWS_TOTAL,
        "raw_performance": len(performance),
        "raw_hiring_funnel": len(funnel),
    }
    print("Generated SYNTHETIC HRIS data:")
    for k, v in counts.items():
        print(f"  {k:22s} {v:>7d}")
    print(f"  -> {out}")
    return counts


if __name__ == "__main__":
    main()
