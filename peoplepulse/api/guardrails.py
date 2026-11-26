"""SQL guardrails for the GenAI HR query assistant.

An LLM turns a question into SQL. We never trust that SQL blindly -- before it
touches the database it must pass every check here. This is the project's main
safety boundary, so the rules are deliberately strict and explained inline.

Layers (any failure => the query is refused, nothing runs):
  1. Parse        -- must parse as valid SQL (sqlglot). Garbage is rejected.
  2. Single stmt  -- exactly one statement (blocks stacked "...; DROP TABLE").
  3. Read-only    -- the root must be a SELECT; any write/DDL/command node
                     (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/PRAGMA/ATTACH...)
                     anywhere in the tree is rejected.
  4. Allow-list   -- every real table referenced must be one of the MIS v_*
                     views. Base tables (e.g. dim_employee, which holds
                     individual records) are therefore unreachable.
  5. Row limit    -- a LIMIT <= MAX_ROWS is enforced (added or capped).

The connection is *also* opened read-only at execution time (see nl2sql.py):
defence in depth, so even a bug here cannot mutate data.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from peoplepulse.config import MAX_ROWS
from peoplepulse.mis.build_views import view_names

# The only tables a generated query may read: the MIS views.
ALLOWED_TABLES = {name.lower() for name in view_names()}

# Node types that must never appear in a generated query.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # PRAGMA / ATTACH / VACUUM / SET etc. parse as Command
    exp.Into,  # SELECT ... INTO (writes a new table)
)


@dataclass
class GuardrailResult:
    ok: bool
    sql: str | None = None  # safe, rewritten SQL (dialect-targeted) when ok
    reason: str | None = None  # machine-readable refusal reason when not ok


def validate(raw_sql: str, dialect: str = "postgres") -> GuardrailResult:
    """Validate and safely rewrite LLM-generated SQL. See module docstring."""
    raw_sql = (raw_sql or "").strip().rstrip(";").strip()
    if not raw_sql:
        return GuardrailResult(False, reason="empty_sql")

    # 1 + 2) Parse, and require exactly one statement.
    try:
        statements = sqlglot.parse(raw_sql, read=dialect)
    except Exception:
        return GuardrailResult(False, reason="unparseable_sql")
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return GuardrailResult(False, reason="multiple_statements")

    tree = statements[0]

    # 3) Root must be a SELECT (CTEs allowed); no write/DDL/command nodes.
    if not isinstance(tree, exp.Select):
        return GuardrailResult(False, reason="not_a_select")
    if any(tree.find(node) for node in _FORBIDDEN):
        return GuardrailResult(False, reason="forbidden_statement")

    # 4) Allow-list: every real table must be an MIS view.
    cte_aliases = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_aliases:
            continue  # reference to a CTE defined in this query, not a base table
        if name not in ALLOWED_TABLES:
            return GuardrailResult(False, reason=f"table_not_allowed:{name}")

    # 5) Enforce a row limit (add if missing, cap if too large).
    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(MAX_ROWS)
    else:
        try:
            current = int(limit.expression.this)
            if current > MAX_ROWS:
                tree = tree.limit(MAX_ROWS)
        except (AttributeError, ValueError):
            tree = tree.limit(MAX_ROWS)

    return GuardrailResult(True, sql=tree.sql(dialect=dialect))
