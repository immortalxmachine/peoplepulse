"""Data-quality checks for the raw employee feed.

Each check returns rows it rejects together with a machine-readable reason, so
bad data is *quarantined* (not silently dropped and not loaded). The caller
inserts rejected rows into the `quarantine` table.

Checks implemented (in order):
  1. null_employee_id      -- employee_id is blank/NaN
  2. duplicate_employee_id -- employee_id seen more than once (keep first)
  3. invalid_hire_date     -- hire_date not an ISO date
  4. exit_before_hire      -- exit_date earlier than hire_date
  5. unknown_country       -- country_code not in the country dimension
"""

from __future__ import annotations

import datetime as dt

import pandas as pd


def _parse_iso(value: object) -> dt.date | None:
    """Return a date for an ISO 'YYYY-MM-DD' string, else None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def check_employees(
    raw: pd.DataFrame, known_countries: set[str]
) -> tuple[pd.DataFrame, list[dict]]:
    """Split raw employees into (clean_rows, quarantine_records).

    `clean_rows` has two extra parsed columns (`_hire`, `_exit`) as date objects
    so the loader does not re-parse.
    """
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
        raw_repr = "|".join(f"{k}={v}" for k, v in r.items())[:512]

        # 1) null id
        if not eid:
            reject(eid, raw_repr, "null_employee_id")
            continue
        # 2) duplicate id (first occurrence wins)
        if eid in seen_ids:
            reject(eid, raw_repr, "duplicate_employee_id")
            continue
        # 3) hire date parseable?
        hire = _parse_iso(r.get("hire_date"))
        if hire is None:
            reject(eid, raw_repr, "invalid_hire_date")
            continue
        # 4) exit before hire?
        exit_d = _parse_iso(r.get("exit_date"))
        if exit_d is not None and exit_d < hire:
            reject(eid, raw_repr, "exit_before_hire")
            continue
        # 5) known country?
        if str(r.get("country_code")) not in known_countries:
            reject(eid, raw_repr, "unknown_country")
            continue

        seen_ids.add(eid)
        r["_hire"] = hire
        r["_exit"] = exit_d
        kept_rows.append(r)

    clean = pd.DataFrame(kept_rows)
    return clean, quarantined
