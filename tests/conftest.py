"""Shared pytest fixtures.

The `warehouse` fixture builds a full SQLite warehouse once per test session from
the REAL IBM HR Attrition CSV (data/raw/): load star schema -> build MIS views.
It points DATABASE_URL at a temp DB so tests never touch a real database. The raw
CSV is read locally (committed with the repo), so the suite is offline and needs
no Kaggle credentials.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def warehouse(tmp_path_factory):
    # In CI, DATABASE_URL points at the Postgres service -> run the whole suite
    # against real Postgres. Locally (unset), use a throwaway SQLite file.
    existing = os.environ.get("DATABASE_URL", "")
    if not existing.startswith("postgresql"):
        db = tmp_path_factory.mktemp("wh") / "test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
        os.environ.pop("DATABASE_URL_RO", None)  # RO falls back to the same URL

    from peoplepulse.mis.build_views import build as build_views
    from peoplepulse.warehouse.load import load

    load()  # ingest real CSV -> load star schema into the target DB
    build_views()
    return {"url": os.environ["DATABASE_URL"]}
