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
"""

from __future__ import annotations

import re

from peoplepulse import config

# Short schema description handed to a real LLM so it targets the MIS views.
SCHEMA_DOC = """You translate HR analytics questions into a single read-only
PostgreSQL SELECT over ONLY these views (never any other table):

  v_headcount_trend(year_month, total_headcount)
  v_headcount_monthly(year_month, year, department_name, country_name, grade, gender, headcount)
  v_attrition_monthly(year_month, exits, end_headcount,
                      monthly_attrition_pct, rolling_12m_attrition_pct)
  v_attrition_by_segment(year_month, year, department_name, country_name,
                         exits, end_headcount, attrition_pct)
  v_exits_by_type(year_month, year, exit_type, exits)
  v_exit_reasons(exit_type, exit_reason, exits, pct_of_all_exits)
  v_tenure_buckets(tenure_bucket, bucket_order, exits, avg_tenure_days)
  v_time_to_hire(year_month, year, department_name, country_name,
                 hires, avg_time_to_hire_days)
  v_offer_acceptance(year_month, year, department_name, country_name,
                     offers, accepts, offer_acceptance_pct)
  v_gender_diversity_by_grade(grade, female_headcount, male_headcount,
                              total_headcount, female_pct)

Rules: one SELECT only; no writes/DDL; never reference employee-level tables;
return ONLY the SQL, no prose, no markdown fences."""

# --- shared filter extraction (used by the mock) -----------------------------
_COUNTRY = {
    "india": "India",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "germany": "Germany",
    "german": "Germany",
}
_DEPT = {
    "engineering": "Engineering",
    "engineer": "Engineering",
    "product": "Product",
    "sales": "Sales",
    "marketing": "Marketing",
    "customer support": "Customer Support",
    "support": "Customer Support",
    "finance": "Finance",
    "human resources": "Human Resources",
    " hr ": "Human Resources",
    "operations": "Operations",
}


def _find(mapping: dict[str, str], text: str) -> str | None:
    for key, value in mapping.items():
        if key in text:
            return value
    return None


def _year(text: str) -> int | None:
    m = re.search(r"\b(2023|2024|2025)\b", text)
    return int(m.group(1)) if m else None


def _grade(text: str) -> str | None:
    m = re.search(r"\b(?:grade\s*)?g?([1-6])\b", text)
    if m and ("grade" in text or re.search(r"\bg[1-6]\b", text)):
        return f"G{m.group(1)}"
    return None


def _where(pairs: list[tuple[str, object]]) -> str:
    """Build a WHERE clause from (column, value) pairs (fixed vocab, no injection)."""
    clauses = []
    for col, val in pairs:
        if val is None:
            continue
        clauses.append(f"{col} = {val}" if isinstance(val, int) else f"{col} = '{val}'")
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


class MockProvider:
    """Rule-based NL->SQL. Returns None when the question is not understood."""

    name = "mock"

    def to_sql(self, question: str) -> str | None:
        q = f" {question.lower()} "
        country = _find(_COUNTRY, q)
        dept = _find(_DEPT, q)
        year = _year(q)
        grade = _grade(q)

        # --- attrition / turnover ------------------------------------------
        if "attrition" in q or "turnover" in q or "attrit" in q:
            where = _where(
                [("country_name", country), ("department_name", dept), ("year", year)]
            )
            return (
                "SELECT 100.0 * SUM(exits) / NULLIF(AVG(end_headcount), 0) "
                f"AS attrition_pct FROM v_attrition_by_segment{where}"
            )

        # --- offer acceptance ----------------------------------------------
        if "offer" in q and ("accept" in q or "acceptance" in q):
            where = _where(
                [("country_name", country), ("department_name", dept), ("year", year)]
            )
            return (
                "SELECT 100.0 * SUM(accepts) / NULLIF(SUM(offers), 0) "
                f"AS offer_acceptance_pct FROM v_offer_acceptance{where}"
            )

        # --- time to hire --------------------------------------------------
        if "time to hire" in q or "time-to-hire" in q or ("hire" in q and "time" in q):
            where = _where(
                [("country_name", country), ("department_name", dept), ("year", year)]
            )
            return (
                "SELECT SUM(avg_time_to_hire_days * hires) / NULLIF(SUM(hires), 0) "
                f"AS avg_time_to_hire_days FROM v_time_to_hire{where}"
            )

        # --- gender diversity ----------------------------------------------
        if "diversity" in q or "gender" in q or "female" in q or "women" in q:
            if grade:
                return f"SELECT female_pct FROM v_gender_diversity_by_grade WHERE grade = '{grade}'"
            return (
                "SELECT 100.0 * SUM(female_headcount) / NULLIF(SUM(total_headcount), 0) "
                "AS female_pct FROM v_gender_diversity_by_grade"
            )

        # --- voluntary / involuntary exits ---------------------------------
        if "voluntary" in q or "involuntary" in q:
            exit_type = "Involuntary" if "involuntary" in q else "Voluntary"
            where = _where([("exit_type", exit_type), ("year", year)])
            return f"SELECT SUM(exits) AS exits FROM v_exits_by_type{where}"

        # --- tenure at exit ------------------------------------------------
        if "tenure" in q:
            return (
                "SELECT tenure_bucket FROM v_tenure_buckets "
                "ORDER BY exits DESC LIMIT 1"
            )

        # --- exit reasons --------------------------------------------------
        if "reason" in q or "why" in q:
            return (
                "SELECT exit_reason FROM v_exit_reasons ORDER BY exits DESC LIMIT 1"
            )

        # --- headcount (checked last; keywords are generic) ----------------
        if (
            "headcount" in q
            or "how many employees" in q
            or "total employees" in q
            or "workforce" in q
            or "team size" in q
            or "number of employees" in q
        ):
            year_filter = f" WHERE year = {year}" if year else ""
            where = _where([("country_name", country), ("department_name", dept)])
            # Sum the latest monthly snapshot (within the year if one was given).
            sub = f"(SELECT MAX(year_month) FROM v_headcount_monthly{year_filter})"
            base = f"WHERE year_month = {sub}"
            extra = where.replace(" WHERE ", " AND ") if where else ""
            return f"SELECT SUM(headcount) AS headcount FROM v_headcount_monthly {base}{extra}"

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
