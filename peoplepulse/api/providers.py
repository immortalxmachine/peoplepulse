"""LLM providers for natural-language -> SQL, switchable at runtime.

LLM_PROVIDER selects one:
  * mock    -- a deterministic, rule-based translator (DEFAULT). No API key, so
              tests and CI are hermetic and reproducible. It also serves as a
              transparent baseline and documents exactly which questions the
              system is designed to answer.
  * gemini  -- Google Gemini (needs GEMINI_API_KEY).
  * ollama  -- a local Ollama server (needs it running).

Every provider returns raw SQL text (or None if it cannot answer). That SQL is
ALWAYS run through api/guardrails.py before execution -- providers are never
trusted, LLM or not.

The warehouse is the REAL IBM HR Attrition dataset (cross-sectional), so the
assistant answers cross-sectional attrition / pay / diversity questions over the
MIS v_* views. There are no time-series questions (the data has no dates).
"""

from __future__ import annotations

import re

from peoplepulse import config

# Short schema description handed to a real LLM so it targets the MIS views.
SCHEMA_DOC = """You translate HR analytics questions into a single read-only
PostgreSQL SELECT over ONLY these views (never any other table). The data is a
cross-sectional snapshot of 1,470 employees with an attrition outcome.

  v_attrition_overall(total_employees, leavers, attrition_pct)
  v_attrition_by_department(department_name, function_group, employees, leavers, attrition_pct)
  v_attrition_by_job_role(job_role, department_name, employees, leavers, attrition_pct)
  v_attrition_by_overtime(overtime, employees, leavers, attrition_pct)
  v_attrition_by_job_level(job_level, employees, leavers, attrition_pct)
  v_attrition_by_tenure_bucket(tenure_bucket, bucket_order, employees, leavers, attrition_pct)
  v_attrition_by_income_band(income_band, band_order, employees, leavers, attrition_pct)
  v_attrition_by_age_band(age_band, band_order, employees, leavers, attrition_pct)
  v_satisfaction_by_attrition(attrition, employees, avg_job_satisfaction,
                              avg_environment_satisfaction, avg_work_life_balance,
                              avg_job_involvement)
  v_income_by_department(department_name, employees, avg_monthly_income)
  v_gender_diversity(department_name, female_headcount, male_headcount,
                     total_headcount, female_pct)

Departments are exactly: 'Sales', 'Research & Development', 'Human Resources'.
overtime is 'Yes'/'No'. attrition is 1 (left) / 0 (stayed).
Rules: one SELECT only; no writes/DDL; never reference employee-level tables;
return ONLY the SQL, no prose, no markdown fences."""

# --- shared filter extraction (used by the mock) -----------------------------
_DEPT = {
    "research & development": "Research & Development",
    "research and development": "Research & Development",
    "r&d": "Research & Development",
    "research": "Research & Development",
    "development": "Research & Development",
    "sales": "Sales",
    "human resources": "Human Resources",
    " hr ": "Human Resources",
}


def _find(mapping: dict[str, str], text: str) -> str | None:
    for key, value in mapping.items():
        if key in text:
            return value
    return None


def _job_level(text: str) -> int | None:
    m = re.search(r"\b(?:job\s*)?level\s*([1-5])\b", text)
    return int(m.group(1)) if m else None


class MockProvider:
    """Rule-based NL->SQL. Returns None when the question is not understood."""

    name = "mock"

    def to_sql(self, question: str) -> str | None:
        q = f" {question.lower()} "
        dept = _find(_DEPT, q)
        level = _job_level(q)
        overtime = None
        if "overtime" in q or "over time" in q:
            negated = any(n in q for n in ("no overtime", "not work", "without overtime",
                                           "do not", "don't", "never work"))
            overtime = "No" if negated else "Yes"

        # --- counts (leavers before total, so "how many left" is not caught) --
        if ("how many" in q and ("left" in q or "leavers" in q or "quit" in q
                                 or "churned" in q)) or "number of leavers" in q:
            return "SELECT leavers FROM v_attrition_overall"
        if ("how many employees" in q or "total employees" in q
                or "total headcount" in q or "number of employees" in q
                or "workforce" in q or "headcount" in q):
            return "SELECT total_employees FROM v_attrition_overall"

        # --- income / pay --------------------------------------------------
        if "income" in q or "salary" in q or "pay" in q or "compensation" in q:
            if dept:
                return (
                    "SELECT avg_monthly_income FROM v_income_by_department "
                    f"WHERE department_name = '{dept}'"
                )
            return (
                "SELECT SUM(avg_monthly_income * employees) / NULLIF(SUM(employees), 0) "
                "AS avg_monthly_income FROM v_income_by_department"
            )

        # --- gender diversity ----------------------------------------------
        if "diversity" in q or "gender" in q or "female" in q or "women" in q:
            if dept:
                return (
                    "SELECT female_pct FROM v_gender_diversity "
                    f"WHERE department_name = '{dept}'"
                )
            return (
                "SELECT 100.0 * SUM(female_headcount) / NULLIF(SUM(total_headcount), 0) "
                "AS female_pct FROM v_gender_diversity"
            )

        # --- satisfaction --------------------------------------------------
        if "satisfaction" in q or "work-life" in q or "work life" in q or "engagement" in q:
            return (
                "SELECT attrition, avg_job_satisfaction, avg_work_life_balance "
                "FROM v_satisfaction_by_attrition ORDER BY attrition"
            )

        # --- attrition / turnover (checked after the specific cuts) --------
        if "attrition" in q or "turnover" in q or "attrit" in q or "leave" in q or "quit" in q:
            if overtime:
                return (
                    "SELECT attrition_pct FROM v_attrition_by_overtime "
                    f"WHERE overtime = '{overtime}'"
                )
            if level is not None:
                return (
                    "SELECT attrition_pct FROM v_attrition_by_job_level "
                    f"WHERE job_level = {level}"
                )
            if dept:
                return (
                    "SELECT attrition_pct FROM v_attrition_by_department "
                    f"WHERE department_name = '{dept}'"
                )
            return "SELECT attrition_pct FROM v_attrition_overall"

        return None  # not understood -> caller refuses as out_of_scope


class GeminiProvider:
    """Google Gemini. Imported lazily so it is optional."""

    name = "gemini"

    def to_sql(self, question: str) -> str | None:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        prompt = f"{SCHEMA_DOC}\n\nQuestion: {question}\nSQL:"
        resp = model.generate_content(prompt)
        return _strip_sql(resp.text)


class OllamaProvider:
    """Local Ollama server via its HTTP API."""

    name = "ollama"

    def to_sql(self, question: str) -> str | None:
        import httpx

        prompt = f"{SCHEMA_DOC}\n\nQuestion: {question}\nSQL:"
        resp = httpx.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json={"model": config.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        return _strip_sql(resp.json().get("response", ""))


def _strip_sql(text: str) -> str:
    """Remove markdown fences / 'sql' labels an LLM may wrap the query in."""
    text = text.strip()
    text = re.sub(r"^```(?:sql)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def get_provider(name: str | None = None):
    """Return the configured provider instance (defaults to the mock)."""
    name = (name or config.LLM_PROVIDER or "mock").lower()
    if name == "gemini":
        return GeminiProvider()
    if name == "ollama":
        return OllamaProvider()
    return MockProvider()
