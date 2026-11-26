"""Data-quality checks for the raw IBM HR employee feed.

Each check returns rows it rejects together with a machine-readable reason, so
bad data is *quarantined* (not silently dropped and not loaded). The caller
inserts rejected rows into the `quarantine` table.

The published dataset is clean, so on the real feed every row passes and nothing
is quarantined — that is the honest result, and we report it as such. The checks
are real constraints (not decoration): they run on every row and would catch a
corrupted or tampered extract. `tests/test_quality.py` proves each rule by
feeding it deliberately broken rows.

Checks implemented (in order):
  1. null_employee_id       -- employee_id is blank
  2. duplicate_employee_id  -- employee_id seen more than once (keep first)
  3. invalid_attrition      -- attrition_flag not 'Yes'/'No'
  4. unknown_department     -- department not in the department dimension
  5. out_of_range_ordinal   -- a 1..4 / 1..5 survey/level field out of range
  6. negative_measure       -- income / rate / years is negative
"""

from __future__ import annotations

import pandas as pd

# 1..4 Likert survey fields, 1..5 level fields, and measures that must be >= 0.
_ORDINAL_1_4 = [
    "environment_satisfaction",
    "job_satisfaction",
    "job_involvement",
    "relationship_satisfaction",
    "work_life_balance",
]
_ORDINAL_1_5 = ["education_level", "job_level"]
_NON_NEGATIVE = [
    "monthly_income",
    "daily_rate",
    "hourly_rate",
    "monthly_rate",
    "distance_from_home",
    "total_working_years",
    "years_at_company",
]


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def check_employees(
    raw: pd.DataFrame, known_departments: set[str]
) -> tuple[pd.DataFrame, list[dict]]:
    """Split raw employees into (clean_rows, quarantine_records)."""
    quarantined: list[dict] = []
    kept_rows: list[dict] = []
    seen_ids: set[str] = set()

    def reject(eid: str, raw_repr: str, reason: str) -> None:
        quarantined.append(
            {
                "source_table": "raw_employees",
                "employee_id": eid or None,
                "reason": reason,
                "raw_row": raw_repr,
            }
        )

    for _, row in raw.iterrows():
        r = row.to_dict()
        eid = str(r.get("employee_id") or "").strip()
        if eid.lower() in {"", "nan", "none", "<na>"}:
            eid = ""
        raw_repr = "|".join(f"{k}={v}" for k, v in r.items())[:512]

        # 1) null id
        if not eid:
            reject(eid, raw_repr, "null_employee_id")
            continue
        # 2) duplicate id (first occurrence wins)
        if eid in seen_ids:
            reject(eid, raw_repr, "duplicate_employee_id")
            continue
        # 3) attrition label valid?
        if str(r.get("attrition_flag")).strip() not in {"Yes", "No"}:
            reject(eid, raw_repr, "invalid_attrition")
            continue
        # 4) known department?
        if str(r.get("department")).strip() not in known_departments:
            reject(eid, raw_repr, "unknown_department")
            continue
        # 5) ordinal survey / level fields in range?
        bad_ordinal = False
        for col in _ORDINAL_1_4:
            v = _as_int(r.get(col))
            if v is None or not (1 <= v <= 4):
                bad_ordinal = True
                break
        if not bad_ordinal:
            for col in _ORDINAL_1_5:
                v = _as_int(r.get(col))
                if v is None or not (1 <= v <= 5):
                    bad_ordinal = True
                    break
        if bad_ordinal:
            reject(eid, raw_repr, "out_of_range_ordinal")
            continue
        # 6) non-negative measures?
        if any((_as_int(r.get(col)) or 0) < 0 for col in _NON_NEGATIVE):
            reject(eid, raw_repr, "negative_measure")
            continue

        seen_ids.add(eid)
        kept_rows.append(r)

    clean = pd.DataFrame(kept_rows)
    return clean, quarantined
