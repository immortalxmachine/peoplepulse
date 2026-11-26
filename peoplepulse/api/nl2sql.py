"""Orchestrate a natural-language HR question into a safe, answered query.

Pipeline:
  1. Scope check   -- refuse questions about individuals (PII) or off-topic
                      requests *before* any LLM call.
  2. Translate     -- the configured provider turns the question into SQL.
  3. Guardrail     -- validate + rewrite the SQL (see guardrails.py).
  4. Execute       -- run it on a READ-ONLY connection and return rows.

Anything that fails a step returns a structured refusal rather than data.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from sqlalchemy import create_engine, event, text

from peoplepulse.api import guardrails
from peoplepulse.api.providers import get_provider
from peoplepulse.config import MAX_ROWS, database_url_ro, is_sqlite

# Phrases that indicate a request for an individual / personal data. The
# assistant answers aggregate MIS questions only, never anything about a person.
_PII_PATTERNS = [
    r"\be\d{4,}\b",  # an employee id like E100123
    r"\bwho (is|are)\b",
    r"\bwhose\b",
    r"\bname[sd]?\b",
    r"\bindividual",
    r"\bpersonal\b",
    r"\bsalary of\b",
    r"\bhome address\b",
    r"\bphone\b",
    r"\bemail\b",
    r"\beach employee\b",
    r"\bevery employee\b",
    r"\bspecific (employee|person)\b",
    r"\bwhich (employees|people|individuals)\b",
    r"\blist (all )?(the )?employees\b",
    r"\bfire\b",
]

# Obvious injection / write attempts in the natural-language text itself.
_INJECTION_PATTERNS = [
    r";",
    r"--",
    r"\bdrop\b",
    r"\bdelete\b",
    r"\bupdate\b",
    r"\binsert\b",
    r"\balter\b",
    r"\btruncate\b",
    r"ignore (the )?(previous|above|all) instructions",
]


@dataclass
class QueryResult:
    refused: bool
    reason: str | None = None  # why it was refused
    sql: str | None = None  # the safe SQL that ran (when not refused)
    columns: list[str] | None = None
    rows: list[list] | None = None
    provider: str | None = None


def _scope_refusal(question: str) -> str | None:
    q = f" {question.lower()} "
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, q):
            return "blocked_injection_or_write"
    for pat in _PII_PATTERNS:
        if re.search(pat, q):
            return "individual_data_request"
    return None


def _read_only_engine():
    """An engine whose connections are forced read-only (defence in depth)."""
    engine = create_engine(database_url_ro())
    if is_sqlite(database_url_ro()):
        @event.listens_for(engine, "connect")
        def _set_query_only(dbapi_conn, _record):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA query_only = ON")
    else:
        @event.listens_for(engine, "connect")
        def _set_pg_read_only(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("SET default_transaction_read_only = on")
            cur.close()
    return engine


def answer(question: str, provider_name: str | None = None) -> QueryResult:
    """Run the full pipeline for one question."""
    provider = get_provider(provider_name)

    # 1) Scope / PII check before touching any model.
    reason = _scope_refusal(question)
    if reason:
        return QueryResult(refused=True, reason=reason, provider=provider.name)

    # 2) Translate.
    raw_sql = provider.to_sql(question)
    if not raw_sql:
        return QueryResult(refused=True, reason="out_of_scope", provider=provider.name)

    # 3) Guardrail validate + rewrite.
    dialect = "sqlite" if is_sqlite(database_url_ro()) else "postgres"
    gr = guardrails.validate(raw_sql, dialect=dialect)
    if not gr.ok:
        return QueryResult(refused=True, reason=gr.reason, provider=provider.name)

    # 4) Execute read-only.
    engine = _read_only_engine()
    with engine.connect() as conn:
        cursor = conn.execute(text(gr.sql))
        columns = list(cursor.keys())
        rows = [list(r) for r in cursor.fetchmany(MAX_ROWS)]
    return QueryResult(
        refused=False,
        sql=gr.sql,
        columns=columns,
        rows=rows,
        provider=provider.name,
    )


def answer_dict(question: str, provider_name: str | None = None) -> dict:
    return asdict(answer(question, provider_name))
