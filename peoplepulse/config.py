"""Central configuration.

Everything that varies between local dev and CI lives here so the rest of the
code never reads os.environ directly. We deliberately support two database
backends:

* SQLite  -- local dev default (because `pgserver` has no Windows wheel and we
             do not require a system Postgres install).
* Postgres -- used in CI via a `services: postgres` container, exercised through
             the same SQLAlchemy code path.

The SQL we write is kept portable (CTEs + window functions only, no
dialect-specific date functions) so the identical schema and views run on both.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (no-op in CI where real env vars are set).
load_dotenv()

# Project root = the folder that contains this package.
ROOT = Path(__file__).resolve().parent.parent

# Where generated CSV extracts / star-schema exports are written.
DATA_OUT = ROOT / "data_out"

# Default local warehouse file (git-ignored).
_DEFAULT_SQLITE = f"sqlite:///{(ROOT / 'warehouse.db').as_posix()}"


def database_url() -> str:
    """Read-write warehouse URL. Used by loaders and view builders."""
    return os.environ.get("DATABASE_URL") or _DEFAULT_SQLITE


def database_url_ro() -> str:
    """Read-only URL for the GenAI query API.

    On Postgres this should point at a role with SELECT-only grants. On SQLite
    there is no role system, so we fall back to the same file but the API opens
    it read-only and only ever runs validated SELECTs against allow-listed
    views (defence in depth -- see api/guardrails.py).
    """
    return os.environ.get("DATABASE_URL_RO") or database_url()


def is_sqlite(url: str | None = None) -> bool:
    return (url or database_url()).startswith("sqlite")


# --- GenAI provider selection -------------------------------------------------
# "mock" is the default so tests / CI need no API key.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mock").lower()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

# Hard cap on rows the query API will ever return (guardrail).
MAX_ROWS = 1000
